"""Run the agent pipeline over one project description.

  python -m agents.cli --text "We are rebuilding..."
  python -m agents.cli --file brief.txt --answers change_frequency="monthly releases"
  python -m agents.cli --file brief.txt --no-ask --max-repairs 0
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path

from agents.orchestrator import local_pipeline, use_api
from agents.state import RunState

# Fine-tuned 4B extractor, base 4B planner ("none" = no plan adapter). The base model is the
# pre-quantised 4-bit copy of Qwen/Qwen3-4B-Instruct-2507 (same NF4 settings the runtime uses);
# --model-id Qwen/Qwen3-4B-Instruct-2507 quantises the original at load time instead.
PRESETS = {
    "4b": {"model_id": "unsloth/Qwen3-4B-Instruct-2507-bnb-4bit", "extract_adapter": "runs/extract-qwen3-4b/adapter",
           "plan_adapter": "none", "constrained_extract": False, "repair_scope": "all"},
}


def _print_plan(state: RunState, width: int = 96) -> None:
    plan = state.plan or {}
    if not plan:
        print("no plan produced")
        return
    print(f"\nLIFECYCLE: {plan.get('lifecycle')}")
    print("PHASES   : " + " -> ".join(str(p.get("name")) for p in plan.get("phases") or []))
    for phase in plan.get("phases") or []:
        print(f"\n  {phase.get('name')}")
        if phase.get("objective"):
            print(textwrap.fill(str(phase["objective"]), width, initial_indent="    ", subsequent_indent="    "))
        for key in ("activities", "roles", "deliverables", "security_activities", "testing",
                    "compliance_checkpoints"):
            value = phase.get(key)
            if value:
                body = value if isinstance(value, str) else "; ".join(map(str, value))
                print(textwrap.fill(body, width, initial_indent=f"    {key:<22} ", subsequent_indent=" " * 27))
        gate = phase.get("approval_gate") or {}
        if gate:
            print(f"    {'approval_gate':<22} {gate.get('approver')} - {gate.get('criteria')}")


def _print_requirements(state: RunState, width: int = 96) -> None:
    print(f"REQUIREMENTS ({len(state.requirements)})")
    for r in state.requirements:
        print(textwrap.fill(r["statement"], width, initial_indent=f"  {r['id']:<11} ", subsequent_indent=" " * 14))
        cite = f"{r['citation']['standard']} {r['citation']['ref']}" if r["citation"] else None
        if r["source"]:
            note = f'from the text: "{r["source"]}"' + (f"; satisfies {cite}" if cite else "")
        elif cite:
            note = f"required by {cite}"
        else:
            note = "inferred, not in the text: confirm with a stakeholder"
        print(textwrap.fill(f"[{r['category']}] {note}", width, initial_indent=" " * 14, subsequent_indent=" " * 14))


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent pipeline: description -> requirements, factors -> rubric -> plan.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="the project description")
    source.add_argument("--file", help="file containing the project description")
    source.add_argument("--replay", help="print a saved run (an --out file) without loading a model")
    parser.add_argument("--id", default="run")
    parser.add_argument("--answers", nargs="*", default=[], metavar="factor=answer",
                        help="answers to clarifying questions, e.g. change_frequency='monthly'")
    parser.add_argument("--no-ask", action="store_true", help="skip the clarifier")
    parser.add_argument("--max-questions", type=int, default=4)
    parser.add_argument("--max-repairs", type=int, default=2, help="0 disables the plan repair loop")
    parser.add_argument("--no-plan", action="store_true",
                        help="stop after the requirements and the SDLC recommendation (about 3 minutes)")
    parser.add_argument("--min-stated", type=int, default=3,
                        help="fewer stated factors than this: no recommendation or plan (0 always plans)")
    parser.add_argument("--repair-scope", choices=["invalid", "all"],
                        help="repair only unusable plans, or content faults too (default: from the preset)")
    parser.add_argument("--thorough-compliance", action="store_true",
                        help="repair also feeds back uncovered compliance obligations (about 4 min slower)")
    parser.add_argument("--no-requirements", action="store_true", help="skip the requirements agent")
    parser.add_argument("--no-rag", action="store_true",
                        help="skip the RAG pass that maps retrieved obligations onto the requirements")
    parser.add_argument("--reconcile", action="store_true",
                        help="let stated requirements fill unstated SDLC factors (off by default)")
    parser.add_argument("--strict-reconcile", action="store_true",
                        help="reconcile only on explicit statements, with longer evidence quotes")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="4b",
                        help="base model + adapters; the three flags below override single parts")
    parser.add_argument("--model-id")
    parser.add_argument("--extract-adapter")
    parser.add_argument("--plan-adapter", help="adapter directory, or 'none' to plan with the base model")
    parser.add_argument("--constrained-extract", action=argparse.BooleanOptionalAction, default=None,
                        help="JSON-schema decoding for extraction (preset default)")
    parser.add_argument("--api", metavar="MODEL", help="run stages on a Gemini model (needs GEMINI_API_KEY)")
    parser.add_argument("--api-stages", default="requirements,extract,plan",
                        help="comma-separated stages to run on --api: requirements, extract, plan")
    parser.add_argument("--no-4bit", action="store_true")
    parser.add_argument("--unload-after", action="store_true", help="free the GPU before printing")
    parser.add_argument("--out", help="write the full run (state + log) as JSON")
    parser.add_argument("--srs", metavar="FILE", help="also write a Software Requirements Specification (Markdown)")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.replay:
        _report(RunState.load(args.replay))
        return
    description = args.text if args.text else Path(args.file).read_text(encoding="utf-8")
    answers = dict(a.split("=", 1) for a in args.answers if "=" in a)

    cfg = {**PRESETS[args.preset], **{k: v for k, v in {
        "model_id": args.model_id, "extract_adapter": args.extract_adapter, "plan_adapter": args.plan_adapter,
        "constrained_extract": args.constrained_extract, "repair_scope": args.repair_scope}.items()
        if v is not None}}
    plan_adapter = None if cfg["plan_adapter"].lower() == "none" else cfg["plan_adapter"]
    pipeline, hub = local_pipeline(cfg["model_id"], cfg["extract_adapter"], plan_adapter,
                                   load_in_4bit=not args.no_4bit, max_questions=args.max_questions,
                                   max_repairs=args.max_repairs, repair_scope=cfg["repair_scope"],
                                   constrained_extract=cfg["constrained_extract"], min_stated=args.min_stated,
                                   identify_requirements=not args.no_requirements)
    if args.api:
        use_api(pipeline, args.api, [x.strip() for x in args.api_stages.split(",") if x.strip()])
    pipeline.thorough_compliance = args.thorough_compliance
    pipeline.write_plan = not args.no_plan
    pipeline.rag_requirements = not args.no_rag
    pipeline.reconcile = args.reconcile or args.strict_reconcile
    pipeline.reconcile_strict = args.strict_reconcile
    state = RunState(description=" ".join(description.split()), id=args.id)
    pipeline.run(state, answers=answers or None, ask=not args.no_ask)
    if args.unload_after:
        hub.unload()
    if args.srs:
        from agents import srs
        srs.write(state, pipeline.requirements_agent or pipeline.planner)
        Path(args.srs).write_text(srs.markdown(state.srs), encoding="utf-8")
    _report(state)
    if args.srs:
        print(f"\nwrote SRS to {args.srs}")
    if args.out:
        print(f"\nwrote {state.save(args.out)}")


def _print_factors(state: RunState, width: int = 96) -> None:
    stated = {f: v for f, v in state.factors.items() if v["level"] != "not_stated"}
    print(f"\nFACTORS ({len(stated)} of {len(state.factors)} stated)")
    for f, v in stated.items():
        quote = f' "{v["evidence"]}"' if v.get("evidence") else ""
        print(textwrap.shorten(f"  {f:<26} {v['level']:<7}{quote}", width, placeholder=' ..."'))


def _report(state: RunState) -> None:
    print("=" * 96)
    if state.requirements:
        _print_requirements(state)
        print()
    if state.requirement_questions:
        print("REQUIREMENTS TO CLARIFY")
        for q in state.requirement_questions:
            refs = f" ({', '.join(q['requirements'])})" if q["requirements"] else ""
            print(f"  {q['id']}. {q['question']}{refs}")
            for letter, option in zip("abcde", q["options"]):
                print(f"      {letter}) {option}")
        print()
    print(state.summary)
    if state.factors:
        _print_factors(state)
    if state.questions:
        print("\nANSWER THESE FIRST:" if state.insufficient_evidence else
              "\nQUESTIONS WORTH ASKING (each one would change the recommendation):")
        for q in state.questions:
            print(f"\n  [{q['factor']}]  could lead to: {', '.join(q['could_lead_to'])}")
            for line in q["question"].splitlines():
                print("    " + line.strip())
    if not state.insufficient_evidence:
        _print_plan(state)
    print("\nRUN LOG")
    for step in state.log:
        detail = {k: v for k, v in step.detail.items() if v not in (None, [], {})}
        print(f"  {step.node:<14} {'ok' if step.ok else 'FAILED':<7} {step.seconds:>6.2f}s  {json.dumps(detail)}"[:150])


if __name__ == "__main__":
    main()
