"""Software Requirements Specification for a run, structured after ISO/IEC/IEEE 29148.

The narrative sections (purpose, scope, stakeholders, environment, constraints, assumptions, glossary)
are written by the model from the description, the requirements and the clauses retrieved from official
documents; constraints cite those clauses. Requirement tables, regulatory references, the SDLC
recommendation and the traceability matrix are assembled from the run itself.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date

from agents.requirements import CATEGORIES, user_prompt
from agents.state import RunState
from core.backends import Backend

VERIFICATION = {
    "functional": "Test", "security": "Test, inspection", "privacy": "Inspection", "regulatory": "Inspection",
    "performance": "Test (load)", "availability": "Test (failover)", "usability": "Demonstration",
    "data": "Analysis", "integration": "Test", "audit": "Inspection", "operational": "Demonstration",
}

_SYSTEM = """You write the narrative sections of a Software Requirements Specification (ISO/IEC/IEEE 29148).
Use only facts from the project description, its requirements and the retrieved regulatory clauses.
Constraints that come from a clause must end with its id in brackets, e.g. "[P2]". Be concise and formal.

Answer with one JSON object and nothing else:
{"title": "<system name>", "purpose": "<2-3 sentences>", "scope": "<2-4 sentences: what the system does and does not do>",
 "stakeholders": [{"role": "...", "interest": "..."}], "operating_environment": "<1-3 sentences>",
 "constraints": ["..."], "assumptions": ["..."], "glossary": [{"term": "...", "definition": "..."}]}"""


def _prompt(state: RunState) -> str:
    reqs = "\n".join(f"- {r['id']}: {r['statement']}" for r in state.requirements)
    clauses = "\n".join(f"- P{i} [{c['title']}, p. {c['page']}]: {c['text'][:600]}"
                        for i, c in enumerate(state.clauses, 1))
    return (f"{user_prompt(state.description)}\n\nRequirements:\n{reqs or '(none)'}"
            + (f"\n\nRetrieved regulatory clauses:\n{clauses}" if clauses else ""))


def _narrative(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        obj = json.loads(text[start:end + 1]) if 0 <= start < end else {}
    except json.JSONDecodeError:
        obj = {}
    obj = obj if isinstance(obj, dict) else {}
    strings = lambda v: [" ".join(str(x).split()) for x in v if str(x).strip()] if isinstance(v, list) else []  # noqa: E731
    pairs = lambda v, a, b: [{a: str(x.get(a, "")).strip(), b: str(x.get(b, "")).strip()}  # noqa: E731
                             for x in (v if isinstance(v, list) else []) if isinstance(x, dict) and x.get(a)]
    return {
        "title": str(obj.get("title") or "").strip(),
        "purpose": str(obj.get("purpose") or "").strip(),
        "scope": str(obj.get("scope") or "").strip(),
        "stakeholders": pairs(obj.get("stakeholders"), "role", "interest"),
        "operating_environment": str(obj.get("operating_environment") or "").strip(),
        "constraints": strings(obj.get("constraints")),
        "assumptions": strings(obj.get("assumptions")),
        "glossary": pairs(obj.get("glossary"), "term", "definition"),
    }


def _fallback(state: RunState) -> dict:
    first = re.split(r"(?<=[.!?])\s+", state.description.strip())
    return {"title": "", "purpose": " ".join(first[:2]), "scope": " ".join(first[2:4]), "stakeholders": [],
            "operating_environment": "", "constraints": [], "assumptions": [], "glossary": []}


def _regulations(state: RunState) -> list[dict]:
    compliance = state.compliance or {}
    by_standard: dict[str, dict] = {}
    for s in compliance.get("standards", []):
        by_standard[s["standard"]] = {"standard": s["standard"], "name": s["name"], "basis": s["how"],
                                      "evidence": s["evidence"], "obligations": []}
    for o in compliance.get("obligations", []):
        entry = by_standard.get(o["standard"])
        if entry is not None:
            clause = o.get("clause") or {}
            entry["obligations"].append({"id": o["id"], "ref": o["ref"], "text": o["description"],
                                         "page": clause.get("page"), "excerpt": clause.get("text")})
    return list(by_standard.values())


def _trace(state: RunState) -> list[dict]:
    rows = []
    for r in state.requirements:
        cite = r.get("citation") or {}
        rows.append({"id": r["id"], "requirement": r["statement"], "basis": r["basis"],
                     "source": r.get("source") or "",
                     "regulation": f"{cite['standard'].split(' - ')[0]} {cite['ref']}" if cite else "",
                     "verification": VERIFICATION.get(r["category"], "Test")})
    return rows


def build(state: RunState, narrative: dict) -> dict:
    rec = state.recommendation or {}
    groups = {}
    for r in state.requirements:
        groups.setdefault(r["category"], []).append(r)
    return {
        **{k: v for k, v in narrative.items()},
        "title": narrative.get("title") or "Untitled system",
        "date": date.today().isoformat(),
        "version": "0.1 (draft)",
        "functional": groups.get("functional", []),
        "non_functional": [{"category": c, "requirements": groups[c]} for c in CATEGORIES
                           if c != "functional" and c in groups],
        "regulations": _regulations(state),
        "clauses": [{"id": f"P{i}", "document": c["title"], "page": c["page"], "text": c["text"]}
                    for i, c in enumerate(state.clauses, 1)],
        "sdlc": None if not rec or state.insufficient_evidence else {
            "primary": rec.get("primary"), "hybrid": rec.get("hybrid") or [], "ranking": rec.get("ranking") or [],
            "acceptable": rec.get("acceptable_set") or [], "provisional": bool(rec.get("low_evidence")),
            "withheld": bool(rec.get("primary_withheld"))},
        "traceability": _trace(state),
        "open_questions": [{"question": q["question"], "options": q["options"]} for q in state.requirement_questions]
                          + [{"question": q["question"].splitlines()[0], "options": []} for q in state.questions],
    }


def write(state: RunState, backend: Backend | None) -> RunState:
    """Draft the SRS. Without a backend the narrative falls back to the description itself."""
    started = time.time()
    narrative = _narrative(backend.complete(_SYSTEM, _prompt(state))) if backend else _fallback(state)
    if backend and not (narrative["purpose"] or narrative["scope"]):
        narrative = {**_fallback(state), **{k: v for k, v in narrative.items() if v}}
    state.srs = build(state, narrative)
    state.record("srs", True, started, sections=sum(bool(v) for v in narrative.values()),
                 constraints=len(narrative["constraints"]))
    return state


def markdown(srs: dict, description: str = "") -> str:
    """The SRS as a Markdown document."""
    out = [f"# {srs['title']}", "", f"Software Requirements Specification, version {srs['version']}, {srs['date']}", ""]
    section = lambda n, t: out.extend([f"## {n}. {t}", ""])  # noqa: E731
    section(1, "Introduction")
    out += ["### 1.1 Purpose", "", srs.get("purpose") or "-", "", "### 1.2 Scope", "", srs.get("scope") or "-", ""]
    if srs.get("glossary"):
        out += ["### 1.3 Definitions", "", "| Term | Definition |", "|---|---|"]
        out += [f"| {g['term']} | {g['definition']} |" for g in srs["glossary"]] + [""]
    section(2, "Overall description")
    if srs.get("stakeholders"):
        out += ["### 2.1 Stakeholders", "", "| Role | Interest |", "|---|---|"]
        out += [f"| {s['role']} | {s['interest']} |" for s in srs["stakeholders"]] + [""]
    out += ["### 2.2 Operating environment", "", srs.get("operating_environment") or "-", ""]
    out += ["### 2.3 Constraints", ""] + [f"- {c}" for c in srs.get("constraints") or ["-"]] + [""]
    out += ["### 2.4 Assumptions and dependencies", ""] + [f"- {a}" for a in srs.get("assumptions") or ["-"]] + [""]
    section(3, "Requirements")

    def table(reqs):
        rows = ["| ID | Requirement | Basis |", "|---|---|---|"]
        for r in reqs:
            cite = r.get("citation")
            basis = (f"Description: \"{r['source']}\"" if r.get("source") else
                     f"{cite['standard'].split(' - ')[0]} {cite['ref']}" if cite else "Inferred - to confirm")
            rows.append(f"| {r['id']} | {r['statement']} | {basis} |")
        return rows + [""]
    out += ["### 3.1 Functional requirements", ""] + table(srs["functional"])
    for i, group in enumerate(srs["non_functional"], 2):
        out += [f"### 3.{i} {group['category'].capitalize()} requirements", ""] + table(group["requirements"])
    section(4, "Applicable regulations and standards")
    for reg in srs["regulations"]:
        out += [f"### {reg['name']}", "", f"Applies because the description mentions: \"{reg['evidence']}\"" if
                reg["basis"] == "named" else f"Inferred from: \"{reg['evidence']}\"", ""]
        for o in reg["obligations"]:
            out.append(f"- **{o['ref']}**: {o['text']}" + (f" (p. {o['page']})" if o.get("page") else ""))
        out.append("")
    if srs["clauses"]:
        out += ["### Retrieved clauses", ""]
        out += [f"- **{c['id']}** {c['document']}, p. {c['page']}: {c['text'][:400]}..." for c in srs["clauses"]] + [""]
    section(5, "Recommended development lifecycle")
    sdlc = srs.get("sdlc")
    if sdlc:
        name = sdlc["primary"] + (f" with {', '.join(sdlc['hybrid'])}" if sdlc["hybrid"] else "")
        out += [f"Recommended: **{name}**" + (" (provisional)" if sdlc["provisional"] or sdlc["withheld"] else ""),
                "", f"Ranking: {' > '.join(sdlc['ranking'])}", ""]
    else:
        out += ["Not enough information to recommend a lifecycle; see the open questions.", ""]
    section(6, "Traceability matrix")
    out += ["| ID | Source | Regulation | Verification |", "|---|---|---|---|"]
    for t in srs["traceability"]:
        src = (t["source"][:80] + "...") if len(t["source"]) > 80 else t["source"]
        out.append(f"| {t['id']} | {src or t['basis']} | {t['regulation'] or '-'} | {t['verification']} |")
    out.append("")
    if srs["open_questions"]:
        section(7, "Open questions")
        for q in srs["open_questions"]:
            out.append(f"- {q['question']}" + (f" Options: {'; '.join(q['options'])}." if q["options"] else ""))
        out.append("")
    return "\n".join(out)
