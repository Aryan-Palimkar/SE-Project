"""Agent nodes. Each takes the run state and a Backend and returns the updated state.

The model is only used for language; the ranking always comes from the rubric.
"""
from __future__ import annotations

import json
import re
import time

from agents.questions import decision_relevant
from agents.state import RunState
from core.backends import Backend
from core.config import load_factor_ontology
from core.plan_spec import load_plan_ontology, load_roles, plan_requirements
from eval.plan_checker import _element_present, canonical_phase, check_plan, phase_text
from rubric.scorer import load_rubric, score
from train.tasks import build_prompt, parse_output, plan_user_prompt_for, rubric_recommendation, system_prompt

LEVELS = ("low", "medium", "high", "not_stated")


def _record(state: RunState) -> dict:
    return {"id": state.id, "description": state.description, "factors": state.factors,
            "recommendation": state.recommendation}


def extract(state: RunState, backend: Backend, onto: dict | None = None, definitions: bool = False) -> RunState:
    """`definitions` adds the level descriptors to the prompt, for models not fine-tuned on them."""
    started, onto = time.time(), onto or load_factor_ontology()
    names = list(onto["factors"])
    system, user = build_prompt({"description": state.description}, "extract", onto, definitions)
    parsed = parse_output("extract", backend.complete(system, user), names)
    levels, evidence = parsed["levels"] or {}, parsed["evidence"] or {}
    state.factors = {f: {"level": levels.get(f) if levels.get(f) in LEVELS else "not_stated",
                         "evidence": evidence.get(f)} for f in names}
    state.record("extract", parsed["parse_ok"], started, parse_ok=parsed["parse_ok"],
                 stated=sum(v["level"] != "not_stated" for v in state.factors.values()))
    return state


_CHALLENGE_SYSTEM = (
    "You double-check a first reading of a software project description. The first reader marked the "
    "characteristics listed below as not stated. For each one, decide whether the description gives a "
    "basis for it after all. Rate a characteristic only when a specific part of the description supports "
    "the level; if you would have to guess, keep not_stated. For every rating, copy the shortest span of "
    "the description that shows the level, character for character.\n\nCharacteristics to re-check:\n"
    "{factors}\n\nAnswer with one JSON object and nothing else, covering exactly the listed "
    'characteristics: {{"<characteristic>": {{"level": "low|medium|high|not_stated", '
    '"evidence": "<exact span>" or null}}, ...}}')
_STRICT_EXTRA = (
    "\n\nBe strict. The description must say the thing outright: a fact, a number, a named standard, a "
    "date, a contract term. Do not rate a characteristic because this kind of project usually implies it, "
    "and do not use medium as a hedge for 'not sure' - that is what not_stated is for. Expect most of the "
    "listed characteristics to stay not_stated.")
MIN_EVIDENCE_CHARS = 12
STRICT_MIN_EVIDENCE_CHARS = 30
MAX_EVIDENCE_CHARS = 300


def _grounded(span, description: str, min_chars: int = MIN_EVIDENCE_CHARS) -> bool:
    """The span is a real quote from the description (whitespace and case normalised)."""
    if not isinstance(span, str) or not min_chars <= len(span.strip()) <= MAX_EVIDENCE_CHARS:
        return False
    squash = lambda s: " ".join(s.lower().split())  # noqa: E731
    return squash(span) in squash(description)


def recheck(state: RunState, backend: Backend, factors: list[str], onto: dict | None = None,
            strict: bool = False, context: str = "", source: str = "challenger") -> tuple[bool, dict, list]:
    """Ask `backend` to rate `factors` (all currently unstated) and keep only proposals whose
    evidence quotes the description verbatim. Returns (parsed, accepted levels, ungrounded)."""
    onto = onto or load_factor_ontology()
    lines = []
    for f in factors:
        d = onto["factors"][f]
        line = f"- {f}: {d['question']} high = {d['high']} medium = {d['medium']} low = {d['low']}"
        if d.get("evidence_note"):
            line += f" NOTE: {d['evidence_note']}"
        if d.get("not_evidence"):
            line += f" NOT evidence: {d['not_evidence']}"
        lines.append(" ".join(line.split()))
    block = "\n".join(lines)
    system = _CHALLENGE_SYSTEM.format(factors=block) + (_STRICT_EXTRA if strict else "")
    raw = backend.complete(system, f"Project description:\n<<<\n{state.description}\n>>>{context}")
    min_chars = STRICT_MIN_EVIDENCE_CHARS if strict else MIN_EVIDENCE_CHARS
    obj = _json_object(raw)
    accepted, ungrounded = {}, []
    for f in factors:
        proposal = (obj or {}).get(f)
        if state.factors.get(f, {}).get("level") != "not_stated":
            continue
        if not isinstance(proposal, dict) or proposal.get("level") not in ("low", "medium", "high"):
            continue
        if _grounded(proposal.get("evidence"), state.description, min_chars):
            accepted[f] = proposal["level"]
            state.factors[f] = {"level": proposal["level"], "evidence": proposal["evidence"].strip(),
                                "source": source}
        else:
            ungrounded.append(f)
    return obj is not None, accepted, ungrounded


def challenge(state: RunState, backend: Backend, onto: dict | None = None, strict: bool = False) -> RunState:
    """Re-read the description for factors the extractor left unstated.

    A proposal is kept only if it quotes the description verbatim; the extractor's own
    ratings are never changed.
    """
    started = time.time()
    unstated = [f for f, v in state.factors.items() if v["level"] == "not_stated"]
    if not unstated:
        state.record("challenge", True, started, unstated=0)
        return state
    ok, accepted, ungrounded = recheck(state, backend, unstated, onto, strict)
    state.record("challenge", ok, started, strict=strict, unstated=len(unstated), accepted=accepted,
                 rejected_ungrounded=ungrounded)
    return state


_QUESTION = "{question}\n   low = {low}\n   medium = {medium}\n   high = {high}"


def clarify(state: RunState, backend: Backend | None = None, onto: dict | None = None,
            max_questions: int = 4) -> RunState:
    """Ask only about unstated factors whose level would change the recommendation."""
    started, onto = time.time(), onto or load_factor_ontology()
    relevant = decision_relevant(state.levels())[:max_questions]
    state.questions = []
    for r in relevant:
        d = onto["factors"][r["factor"]]
        state.questions.append({
            "factor": r["factor"], "could_lead_to": r["primaries"],
            "question": _QUESTION.format(question=d["question"], low=d["low"], medium=d["medium"], high=d["high"])})
    state.record("clarify", True, started, asked=len(state.questions),
                 unstated=sum(v["level"] == "not_stated" for v in state.factors.values()))
    return state


_ANSWER_SYSTEM = ("You convert a project stakeholder's answer into one level for a single project "
                  "characteristic. Answer with one word: low, medium, high, or not_stated when the "
                  "answer does not settle it.")


def apply_answers(state: RunState, backend: Backend, onto: dict | None = None) -> RunState:
    """Turn free-text answers into levels. The stakeholder's own words become the evidence."""
    started, onto = time.time(), onto or load_factor_ontology()
    applied = {}
    for factor, answer in (state.answers or {}).items():
        if factor not in state.factors or not str(answer).strip():
            continue
        d = onto["factors"][factor]
        user = (f"Characteristic: {factor}\nQuestion: {d['question']}\n"
                f"low = {d['low']}\nmedium = {d['medium']}\nhigh = {d['high']}\n\n"
                f"The stakeholder answered: {answer!r}\n\nOne word:")
        reply = backend.complete(_ANSWER_SYSTEM, user).strip().lower()
        word = re.sub(r"[^a-z_]", "", reply.split()[0]) if reply.split() else ""
        if word in LEVELS and word != "not_stated":
            state.factors[factor] = {"level": word, "evidence": f"stakeholder: {answer}"}
            applied[factor] = word
    state.record("apply_answers", True, started, applied=applied)
    return state


def recommend(state: RunState, min_stated: int = 3) -> RunState:
    """Run the rubric and flag how much evidence the answer rests on.

    low_evidence: under half the factors stated; the answer is provisional.
    insufficient_evidence: fewer than `min_stated` factors; no recommendation or plan.
    """
    started = time.time()
    levels = state.levels()
    rec = rubric_recommendation(levels)
    result = score({f: (lvl if lvl in LEVELS else "not_stated") for f, lvl in levels.items()})
    n_stated = sum(1 for lvl in levels.values() if lvl in LEVELS and lvl != "not_stated")
    # The rubric may withhold the primary (tie or unmet precondition); carry that through.
    state.recommendation = {**rec, "low_evidence": result["low_evidence"], "stated": n_stated,
                            "stated_coverage": result["stated_coverage"],
                            "primary_withheld": result.get("primary_withheld", False),
                            "withheld_reasons": [r for r in result["triggered_rules"]
                                                 if r in ("TIE_WITHHELD", "PRECONDITION_UNMET")],
                            "supported_models": result.get("supported_models")}
    state.insufficient_evidence = n_stated < min_stated
    state.record("rubric", True, started, primary=rec["primary"], acceptable=rec["acceptable_set"],
                 hybrid=rec["hybrid"], stated=n_stated, low_evidence=result["low_evidence"],
                 insufficient_evidence=state.insufficient_evidence)
    return state


def _requirements(state: RunState) -> dict:
    return plan_requirements(state.factors, state.recommendation, load_plan_ontology(), load_roles())


_RAG_BLOCK = ("\n\n## Compliance obligations that apply\n"
              "These come from standards the description names or implies (retrieved, with clause "
              "references). Put each one into the phase where it belongs, as an activity, deliverable, "
              "compliance checkpoint or gate criterion, and name the standard. Do not add standards that "
              "are not listed.\n{rows}")


# Alternative wording: obligations grouped by the phase where the work happens.
_RAG_BLOCK_V2 = """

## Compliance obligations that apply
These come from standards the description names or implies. For each obligation, add a concrete
activity or deliverable to the phase where that work is actually done: say what is done or produced,
by which role, and what it is checked against, then put the standard and clause in brackets at the
end, e.g. "QA lead runs a data protection impact assessment on the claims data flow (GDPR Art. 35)".
Do not paste an obligation as a line, do not collect obligations into a checklist, and do not use them
as gate criteria unless the gate checks a named deliverable. Do not add standards that are not listed.
{groups}"""

_PHASE_ORDER = ("planning", "requirements", "design", "implementation", "verification", "release", "operations")


def _rag_prompt(obligations: list[dict], style) -> str:
    if style == "v2":
        groups = []
        for ph in _PHASE_ORDER:
            rows = [o for o in obligations if o["phase"] == ph]
            if rows:
                groups.append(f"\n{ph.capitalize()} work:\n" + "\n".join(
                    f"- {o['description']} [{o['standard_name']} {o['ref']}]" for o in rows))
        return _RAG_BLOCK_V2.format(groups="".join(groups))
    return _RAG_BLOCK.format(rows="\n".join(
        f"- [{o['standard_name']} {o['ref']}] ({o['phase']}) {o['description']}" for o in obligations))


def plan(state: RunState, backend: Backend, onto: dict | None = None, rag=False) -> RunState:
    """`rag` adds the retrieved obligations to the prompt: False, True/"v1" or "v2"."""
    started, onto = time.time(), onto or load_factor_ontology()
    user = plan_user_prompt_for(_record(state))
    obligations = (state.compliance or {}).get("obligations") or []
    if rag and obligations:
        user += _rag_prompt(obligations, "v2" if rag == "v2" else "v1")
    raw = backend.complete(system_prompt("plan", onto), user)
    parsed = parse_output("plan", raw, list(onto["factors"]))
    state.plan, state.justification = parsed["plan"], parsed["justification"]
    state.record("plan", parsed["parse_ok"], started, parse_ok=parsed["parse_ok"],
                 phases=len((state.plan or {}).get("phases") or []),
                 rag=(("v2" if rag == "v2" else "v1") if rag and obligations else None))
    return state


def comply(state: RunState) -> RunState:
    """Applicable standards and their obligations. Runs before planning so the plan can use them."""
    from compliance.analysis import compliance_map
    started = time.time()
    state.compliance = compliance_map(state.description)
    state.record("comply", True, started, standards=[s["standard"] for s in state.compliance["standards"]],
                 obligations=len(state.compliance["obligations"]))
    return state


def assess(state: RunState) -> RunState:
    """Compliance coverage of the final plan, and the risk register."""
    from compliance.analysis import compliance_map, risk_register
    from compliance.retrieve import Hit
    started = time.time()
    hits = [Hit(**s) for s in (state.compliance or {}).get("standards", [])] if state.compliance else None
    state.compliance = compliance_map(state.description, state.plan, hits)
    state.risks = risk_register(state.factors, state.plan, state.compliance)
    state.record("assess", True, started, coverage=state.compliance.get("coverage"),
                 missing=len(state.compliance.get("missing") or []), risks=len(state.risks),
                 unmitigated=sum(r["mitigated"] is False for r in state.risks))
    return state


def check(state: RunState) -> RunState:
    started = time.time()
    state.report = check_plan(state.plan or {}, _requirements(state), state.description)
    state.record("check", bool(state.report.get("schema_valid")), started,
                 mandatory_recall=state.report.get("mandatory_recall"),
                 missing=state.report.get("missing_elements"),
                 missing_phases=state.report.get("missing_phases"))
    return state


def faults(report: dict, req: dict) -> list[str]:
    """What the checker objected to, phrased as instructions the planner can act on."""
    by_id = {m["id"]: m for m in req["mandatory"]}
    discouraged = {d["id"]: d["description"] for d in req["discouraged"]}
    out = []
    if not report.get("schema_valid"):
        out += [f"Schema problem: {e}" for e in (report.get("schema_errors") or [])[:4]]
    for phase in report.get("missing_phases") or []:
        out.append(f"The plan is missing the phase {phase!r}; every skeleton phase must appear, in order.")
    for element in report.get("missing_elements") or []:
        spec = by_id.get(element)
        if spec:
            words = ", ".join(spec["keywords"][:4])
            out.append(f"Missing mandatory element: {spec['description']}. Add it to the phase where it "
                       f"belongs, using wording such as: {words}.")
        else:
            out.append(f"Missing mandatory element: {element}.")
    for element in report.get("overgenerated_elements") or []:
        out.append(f"Remove this, it is over-engineering for this project: {discouraged.get(element, element)}.")
    for role in report.get("invalid_roles") or []:
        out.append(f"{role!r} is not in the allowed role list; use only the listed roles.")
    return out


def quality(report: dict) -> tuple:
    """How good a plan is, for comparing a repair against what it replaced."""
    return (bool(report.get("schema_valid")),
            report.get("mandatory_recall") or 0.0,
            -(report.get("overgeneration_rate") or 0.0),
            report.get("lifecycle_conformance") or 0.0)


def _json_object(raw: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def splice_phases(plan: dict, new_phases: list, req: dict) -> dict:
    """Replace or insert only the phases the model returned, keeping the rest untouched."""
    order = {name: i for i, name in enumerate(req["phases"])}
    phases = [dict(p) for p in (plan.get("phases") or []) if isinstance(p, dict)]
    canon_at = [canonical_phase(str(p.get("name", "")), req) for p in phases]
    for candidate in new_phases:
        if not isinstance(candidate, dict) or not str(candidate.get("name", "")).strip():
            continue
        name = str(candidate["name"])
        canon = canonical_phase(name, req)
        existing = next((i for i, c in enumerate(canon_at) if c is not None and c == canon), None)
        if existing is None:
            existing = next((i for i, p in enumerate(phases) if str(p.get("name", "")) == name), None)
        if existing is not None:
            phases[existing] = candidate
            canon_at[existing] = canon
            continue
        at = len(phases)
        if canon in order:
            at = next((i for i, c in enumerate(canon_at) if c in order and order[c] > order[canon]), len(phases))
        phases.insert(at, candidate)
        canon_at.insert(at, canon)
    return {"lifecycle": plan.get("lifecycle"), "phases": phases}


def _repair_prompt(state: RunState, problems: list[str]) -> str:
    """The plan prompt the adapter was trained on, plus the checker's objections."""
    return (plan_user_prompt_for(_record(state))
            + "\n\nYour previous answer was:\n"
            + json.dumps({"plan": state.plan or {}}, ensure_ascii=False)
            + "\n\nAn automatic checker found these problems:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nReturn the corrected JSON object now, keeping everything that was already correct.")


def missing_obligations(state: RunState, plan: dict | None = None) -> list[dict]:
    """Retrieved obligations the plan does not substantively cover."""
    from compliance.retrieve import obligations as full_obligations
    from eval.substantive import locations
    from eval.substantive_metric import substantively_covered
    plan = state.plan if plan is None else plan
    standards = [s["standard"] for s in (state.compliance or {}).get("standards") or []]
    return [o for o in full_obligations(standards) if not substantively_covered(o, locations(o, plan))]


def _obligation_fault(o: dict) -> str:
    return (f"Missing compliance obligation [{o['standard_name']} {o['ref']}]: {o['description']} Add a "
            f"concrete activity or deliverable to the {o['phase']} work that does this - who does what, "
            f"producing what. Do not paste the obligation as a line, a checklist item or a gate criterion.")


def obligation_faults(missing: list[dict]) -> list[str]:
    """Missing obligations as instructions (without keywords, to avoid pasted citations)."""
    return [_obligation_fault(o) for o in missing]


# Slim repair: only send the phases that need changing, keeping prompts short.

_ELEMENT_STAGE = {
    "threat_modelling": "design", "sast": "implementation", "dependency_scanning": "implementation",
    "penetration_test": "verification", "security_signoff": "release", "audit_trail": "release",
    "compliance_approval": "release", "compliance_review_release": "release", "traceability_matrix": "requirements",
    "independent_vv": "verification", "hazard_analysis": "requirements", "verification_gate": "verification",
    "interface_analysis": "design", "migration_plan": "design", "legacy_regression": "verification",
    "stakeholder_proxy": "planning", "scheduled_reviews": "planning", "change_control": "planning",
    "requirement_refinement": "requirements", "documentation_deliverables": "verification",
    "prototype_spike": "design", "risk_register": "planning", "automated_deployment": "release",
    "monitoring": "operations", "v_pairing": "verification", "incremental_delivery": "implementation",
    "automated_pipeline": "implementation",
}
_SLIM_SYSTEM = ("You revise individual phases of a software development plan so that they fix the problems "
                "an automatic checker found. You never invent facts about the project. Answer with one JSON "
                "object and nothing else.")


def _phase_for_stage(names: list[str], stage: str | None) -> str:
    from eval.substantive_metric import STAGES, stages_of
    if stage is None or stage not in STAGES:
        return names[-1]
    want = STAGES.index(stage)
    return min(names, key=lambda n: min((abs(STAGES.index(s) - want) for s in stages_of(n)), default=3))


def repair_targets(state: RunState, req: dict, missing: list[dict], max_phases: int = 4) -> dict[str, list[str]]:
    """{phase name: [problems to fix there]}, for the phases most in need, at most `max_phases`."""
    phases = [p for p in (state.plan or {}).get("phases") or [] if isinstance(p, dict)]
    names = [str(p.get("name") or f"Phase {i + 1}") for i, p in enumerate(phases)]
    if not names:
        return {}
    report, targets = state.report or {}, {}
    by_id = {m["id"]: m for m in req["mandatory"]}
    for element in report.get("missing_elements") or []:
        spec = by_id.get(element)
        if not spec:
            continue
        text = (f"Missing mandatory element: {spec['description']}. Add it here, using wording such as: "
                f"{', '.join(spec['keywords'][:4])}.")
        targets.setdefault(_phase_for_stage(names, _ELEMENT_STAGE.get(element)), []).append(text)
    discouraged = {d["id"]: d for d in req["discouraged"]}
    for element in report.get("overgenerated_elements") or []:
        d = discouraged.get(element)
        if not d:
            continue
        for name, phase in zip(names, phases):
            if _element_present(d, phase_text(phase)):
                targets.setdefault(name, []).append(f"Remove this, it is over-engineering for this project: "
                                                    f"{d['description']}.")
    for role in report.get("invalid_roles") or []:
        for name, phase in zip(names, phases):
            if role.lower() in phase_text(phase):
                targets.setdefault(name, []).append(f"{role!r} is not in the allowed role list; use only the "
                                                    f"listed roles.")
    for o in missing:
        targets.setdefault(_phase_for_stage(names, o["phase"]), []).append(_obligation_fault(o))
    return dict(sorted(targets.items(), key=lambda kv: -len(kv[1]))[:max_phases])


def _slim_repair_prompt(state: RunState, targets: dict[str, list[str]]) -> str:
    plan = state.plan or {}
    phases = {str(p.get("name")): p for p in plan.get("phases") or [] if isinstance(p, dict)}
    stated = ", ".join(f"{f}={v['level']}" for f, v in state.factors.items() if v.get("level") not in (None, "not_stated"))
    parts = [f"Project description:\n<<<\n{state.description}\n>>>",
             f"Lifecycle: {plan.get('lifecycle') or (state.recommendation or {}).get('primary')}. "
             f"Stated characteristics: {stated or 'none'}.",
             "The plan's phases, in order: " + " > ".join(phases),
             "The phases to revise, as JSON:\n"
             + json.dumps({"phases": [phases[n] for n in targets if n in phases]}, ensure_ascii=False),
             "An automatic checker found these problems. Fix each one in the phase it is listed under:\n"
             + "\n".join(f"[{name}]\n" + "\n".join(f"- {p}" for p in probs) for name, probs in targets.items()),
             'Return ONLY a JSON object {"phases": [...]} with the revised versions of the phases above: the '
             "same names and fields, keeping everything that was already correct and adding what is missing."]
    return "\n\n".join(parts)


def repair(state: RunState, backend: Backend, onto: dict | None = None, max_passes: int = 2,
           scope: str = "invalid", obligations: bool = False, slim: bool = True) -> RunState:
    """Fix the checker's objections by replacing individual phases, at most `max_passes` times.

    Each pass is spliced into the current plan and kept only if it scores better.
    `scope`: "invalid" repairs only unusable plans, "all" also attempts content faults.
    """
    onto = onto or load_factor_ontology()
    req = _requirements(state)
    if scope not in ("invalid", "all"):
        raise ValueError(f"scope must be 'invalid' or 'all', not {scope!r}")
    for _ in range(max_passes):
        problems = faults(state.report or {}, req)
        missing = missing_obligations(state) if obligations else []
        problems += obligation_faults(missing)
        if not problems:
            break
        if scope == "invalid" and (state.report or {}).get("schema_valid"):
            state.record("repair", True, time.time(), skipped="plan is valid; scope='invalid'",
                         faults=len(problems))
            break
        started = time.time()
        now = state.report or {}
        targets = repair_targets(state, req, missing) if (slim and now.get("schema_valid")
                                                          and not now.get("missing_phases")) else {}
        if targets:
            obj = _json_object(backend.complete(_SLIM_SYSTEM, _slim_repair_prompt(state, targets))) or {}
            phases = obj.get("phases") if isinstance(obj.get("phases"), list) else (obj.get("plan") or {}).get("phases")
        else:
            # unparseable plan or missing skeleton phase: fall back to a full repair
            parsed = parse_output("plan", backend.complete(system_prompt("plan", onto),
                                                           _repair_prompt(state, problems)),
                                  list(onto["factors"]))
            phases = ((parsed["plan"] or {}).get("phases") if parsed["parse_ok"] else None)
        state.repairs += 1
        if not isinstance(phases, list) or not phases:
            state.record("repair", False, started, faults=len(problems), reason="unparseable")
            break
        # merge so phases the model drops survive from the previous plan
        candidate = splice_phases(state.plan or {}, phases, req)
        report = check_plan(candidate, req, state.description)
        before, after = quality(state.report or {}), quality(report)
        if obligations:
            # keep a pass only if coverage rises and nothing gets worse
            n_before, n_after = len(missing), len(missing_obligations(state, candidate))
            gain = n_after < n_before or after[1] > before[1]
            no_loss = (n_after <= n_before and after[0] >= before[0] and after[1] >= before[1]
                       and after[2] >= before[2])
            if not (gain and no_loss):
                state.record("repair", False, started, faults=len(problems), obligations_missing=n_before,
                             obligations_missing_candidate=n_after, mandatory_recall_before=before[1],
                             mandatory_recall_candidate=after[1], reason="rejected, no net gain")
                break
            state.plan, state.report = candidate, report
            state.record("repair", True, started, faults=len(problems), phases_changed=len(phases),
                         obligations_missing_before=n_before, obligations_missing_after=n_after,
                         mandatory_recall_before=before[1], mandatory_recall_after=after[1])
            continue
        if after <= before:
            state.record("repair", False, started, faults=len(problems), phases_returned=len(phases),
                         reason="rejected, scored no better", mandatory_recall_before=before[1],
                         mandatory_recall_candidate=after[1],
                         still_missing=report.get("missing_elements"),
                         candidate_overgenerated=report.get("overgenerated_elements"))
            break
        state.plan, state.report = candidate, report
        state.record("repair", True, started, faults=len(problems), phases_changed=len(phases),
                     mandatory_recall_before=before[1], mandatory_recall_after=after[1])
    return state


def _conditions(model: str) -> list[str]:
    models = (load_rubric().get("preconditions") or {}).get("models", {})
    return [f"{f.replace('_', ' ')} {'/'.join(levels)}" for f, levels in models.get(model, {}).items()]


def _withheld_reason(rec: dict) -> str:
    reasons, top = rec.get("withheld_reasons") or [], rec.get("primary")
    if "PRECONDITION_UNMET" in reasons:
        needs = " or ".join(_conditions(top)) or "its defining conditions"
        return (f"{top} ranks first, but the description states nothing {top} needs "
                f"({needs}), so the ranking is not evidence for it.")
    return "the top models are level on the stated evidence."


def _deciding_conditions(candidates: list[str]) -> str:
    parts = [f"{m} if {' or '.join(c)}" for m in candidates if (c := _conditions(m))]
    return "; ".join(parts) or "more detail about scope, release cadence, verification and security."


def explain(state: RunState) -> RunState:
    started = time.time()
    rec, report = state.recommendation or {}, state.report or {}
    stated = {f: v["level"] for f, v in state.factors.items() if v["level"] != "not_stated"}
    read = f"Factors read from the description: {len(stated)} of {len(state.factors)}"
    if state.insufficient_evidence:
        lines = [f"NO RECOMMENDATION: too little evidence ({len(stated)} of {len(state.factors)} factors "
                 "could be read from the description).",
                 "The rubric scores unstated factors as neutral, so any ranking now would reflect its "
                 "tie-break order, not the project. Answer the questions below (or add detail to the "
                 "description) and run again.", read]
    else:
        caveat = (f"  [PROVISIONAL - low evidence: {len(stated)} of {len(state.factors)} factors stated]"
                  if rec.get("low_evidence") else "")
        if rec.get("primary_withheld"):
            lines = [f"NO SINGLE LIFECYCLE: {_withheld_reason(rec)}" + caveat,
                     f"Candidates: {', '.join(rec.get('acceptable_set') or [])}",
                     f"Ranking (provisional): {' > '.join(rec.get('ranking') or [])}",
                     *([f"The plan below follows the top-ranked candidate ({rec.get('primary')}) and is "
                        "provisional."] if state.plan else []),
                     "What would decide it: " + _deciding_conditions(rec.get("acceptable_set") or []), read]
        else:
            lines = [f"Recommended lifecycle: {rec.get('primary')}"
                     + (f" with {', '.join(rec['hybrid'])}" if rec.get("hybrid") else "") + caveat,
                     f"Acceptable alternatives: {', '.join(rec.get('acceptable_set') or [])}",
                     f"Ranking: {' > '.join(rec.get('ranking') or [])}", read]
    if stated:
        lines.append("  " + ", ".join(f"{k}={v}" for k, v in list(stated.items())[:8]))
    if state.questions:
        lines.append("Unanswered questions that could change this: "
                     + ", ".join(q["factor"] for q in state.questions))
    if report:
        accepted = sum(1 for s in state.log if s.node == "repair" and s.ok)
        repairs = ""
        if state.repairs:
            repairs = (f", repaired {accepted}x" if accepted else
                       f", {state.repairs} repair attempt{'s' if state.repairs > 1 else ''} rejected")
        lines.append(f"Plan check: mandatory recall {report.get('mandatory_recall')}, "
                     f"over-generation {report.get('overgeneration_rate')}, "
                     f"schema {'valid' if report.get('schema_valid') else 'INVALID'}" + repairs)
    state.summary = "\n".join(lines)
    state.record("explain", True, started)
    return state
