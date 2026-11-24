"""Rule-based SDLC plan checks, scored against plan_requirements().

  schema_valid            every phase has the required fields with the right types
  lifecycle_conformance   1 - normalised edit distance between phase sequence and skeleton
  pairings_present        V-Model: share of spec phases whose paired test phase is present
  mandatory_recall        share of mandatory elements found (keyword match)
  overgeneration_rate     share of discouraged elements included anyway
  gate_completeness       share of phases with a known approver and criteria
  role_validity           share of role mentions in the vocabulary
  flow_coherence          share of transitions whose entry criteria share a word with the previous exit
  entity_recall           share of the description's named terms mentioned in the plan
"""
from __future__ import annotations

import re
import statistics

LIST_FIELDS = ("activities", "roles", "deliverables", "security_activities", "testing", "compliance_checkpoints",
               "entry_criteria", "exit_criteria")
# Optional lists: absent means empty, so a model is not pushed to fill them.
OPTIONAL_LIST_FIELDS = ("security_activities", "testing", "compliance_checkpoints")
TEXT_FIELDS = ("name", "objective")
STOPWORDS = set("""a an and are as at be been by for from has have in into is it its of on or that the their this
to was were will with all each every any per than then them they which who within without must should can may
phase phases plan project team approved complete completed completion ready review reviewed signed""".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9&/+.-]*")


def _norm(text: str) -> str:
    return " ".join(_TOKEN.findall(text.lower()))


def _content_words(text: str) -> set[str]:
    return {t.strip(".-") for t in _TOKEN.findall(text.lower()) if len(t) >= 4 and t not in STOPWORDS}


def phase_text(phase: dict, include_roles: bool = True) -> str:
    """All of a phase's text for keyword matching, with every value coerced to text.

    `include_roles=False` leaves out roles and the gate approver: a role name is not a practice.
    """
    parts = [str(phase.get(f, "")) for f in TEXT_FIELDS]
    for f in LIST_FIELDS:
        if f == "roles" and not include_roles:
            continue
        value = phase.get(f)
        parts.append(" ".join(map(str, value)) if isinstance(value, list) else str(value or ""))
    gate = phase.get("approval_gate")
    gate = gate if isinstance(gate, dict) else {}
    parts += ([str(gate.get("approver", ""))] if include_roles else []) + [str(gate.get("criteria", ""))]
    return " \n".join(parts).lower()


def schema_errors(plan) -> list[str]:
    if not isinstance(plan, dict) or not isinstance(plan.get("phases"), list) or not plan["phases"]:
        return ["plan must be an object with a non-empty 'phases' list"]
    errors = []
    for i, phase in enumerate(plan["phases"]):
        if not isinstance(phase, dict):
            errors.append(f"phase {i}: not an object")
            continue
        for f in TEXT_FIELDS:
            if not isinstance(phase.get(f), str) or not phase[f].strip():
                errors.append(f"phase {i}: missing {f}")
        for f in LIST_FIELDS:
            value = phase.get(f)
            if value is None and f in OPTIONAL_LIST_FIELDS:
                continue
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                errors.append(f"phase {i}: {f} must be a list of strings")
        gate = phase.get("approval_gate")
        if not isinstance(gate, dict) or not all(isinstance(gate.get(k), str) for k in ("approver", "criteria")):
            errors.append(f"phase {i}: approval_gate needs approver and criteria strings")
    return errors


def canonical_phase(name: str, req: dict) -> str | None:
    """Skeleton phase a plan phase name refers to (exact name, alias, or containment)."""
    n = _norm(name)
    for canon in req["phases"]:
        names = [_norm(canon)] + [_norm(a) for a in req["phase_aliases"].get(canon, [])]
        if n in names:
            return canon
    for canon in req["phases"]:
        names = [_norm(canon)] + [_norm(a) for a in req["phase_aliases"].get(canon, [])]
        if any(x and (x in n or n in x) for x in names):
            return canon
    return None


def _edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _loose(text: str) -> str:
    # "failure-mode" and "failure mode", "sign-off" and "sign off" match alike.
    return re.sub(r"[-\s]+", " ", text.lower())


def _element_present(element: dict, text: str) -> bool:
    loose = _loose(text)
    hits = [_loose(k) in loose for k in element["keywords"]]
    return all(hits) if element.get("require_all_keywords") else any(hits)


def elements_present(phases: list[dict], elements: list[dict]) -> dict[str, bool]:
    """Which elements a plan contains. Role names and approvers count only for elements that
    set `match_roles` (compliance approval, where the approver is the evidence)."""
    with_roles = "\n".join(phase_text(p) for p in phases)
    without_roles = "\n".join(phase_text(p, include_roles=False) for p in phases)
    return {e["id"]: _element_present(e, with_roles if e.get("match_roles") else without_roles)
            for e in elements}


def _role_lookup(req: dict) -> dict[str, str]:
    lookup = {}
    for role, aliases in req["role_aliases"].items():
        for name in [role] + list(aliases or []):
            lookup[_norm(name)] = role
    return lookup


def named_terms(description: str) -> set[str]:
    """Acronyms and capitalised words. A sentence's first word counts only when the next word is
    also capitalised (a multi-word name such as 'Kestrel Health') and it is not a stopword."""
    terms = set()
    for sentence in re.split(r"(?<=[.!?:])\s+|\n+", description):
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9&'-]*", sentence)
        for i, tok in enumerate(tokens):
            if tok.isupper() and len(tok) >= 2:
                terms.add(tok.lower())
            elif tok[0].isupper() and len(tok) >= 3 and tok.lower() not in STOPWORDS and (
                    i > 0 or (len(tokens) > 1 and tokens[1][0].isupper())):
                terms.add(tok.lower())
    return terms


def check_plan(plan: dict, req: dict, description: str | None = None) -> dict:
    errors = schema_errors(plan)
    if errors and not (isinstance(plan, dict) and isinstance(plan.get("phases"), list)):
        return {"schema_valid": False, "schema_errors": errors}
    phases = [p for p in plan["phases"] if isinstance(p, dict)]
    mapped = [canonical_phase(str(p.get("name", "")), req) for p in phases]
    seq = [m or f"?{i}" for i, m in enumerate(mapped)]
    distance = _edit_distance(seq, req["phases"])
    text = "\n".join(phase_text(p) for p in phases)
    found = {m for m in mapped if m}

    lookup = _role_lookup(req)

    def split_roles(text: str) -> list[str]:
        # Whole names first ("Independent V&V Engineer" contains '&'), then split combined approvers.
        if _norm(text) in lookup:
            return [text]
        return [x for x in re.split(r"\s*(?:\+|,|/|\s&\s|\band\b)\s*", text) if x.strip()]

    role_mentions = [r for p in phases for r in (p.get("roles") or []) if isinstance(r, str)]
    # A model can emit anything here (a list, a number, null), so coerce before matching.
    role_mentions += [str((p.get("approval_gate") or {}).get("approver", "") if isinstance(p.get("approval_gate"), dict)
                          else "") for p in phases]
    role_parts = [part for r in role_mentions for part in split_roles(r)]
    valid_roles = [part for part in role_parts if _norm(part) in lookup]

    gates = []
    for p in phases:
        gate = p.get("approval_gate") if isinstance(p.get("approval_gate"), dict) else {}
        approver_parts = split_roles(str(gate.get("approver", "")))
        gates.append(bool(approver_parts) and all(_norm(x) in lookup for x in approver_parts)
                     and bool(str(gate.get("criteria", "")).strip()))

    def text_of(value) -> str:
        return " ".join(map(str, value)) if isinstance(value, list) else str(value or "")

    transitions = []
    for prev, nxt in zip(phases, phases[1:]):
        before = _content_words(text_of(prev.get("exit_criteria")) + " " + text_of(prev.get("deliverables")))
        after = _content_words(text_of(nxt.get("entry_criteria")))
        transitions.append(bool(before & after))

    mandatory = elements_present(phases, req["mandatory"])
    discouraged = elements_present(phases, req["discouraged"])
    report = {
        "schema_valid": not errors,
        "schema_errors": errors,
        "n_phases": len(phases),
        "lifecycle_conformance": round(1 - distance / max(len(seq), len(req["phases"])), 4),
        "unmatched_phases": [str(p.get("name")) for p, m in zip(phases, mapped) if m is None],
        "missing_phases": [p for p in req["phases"] if p not in found],
        "pairings_present": (round(sum(a in found and b in found for a, b in req["pairings"].items())
                                   / len(req["pairings"]), 4) if req["pairings"] else None),
        "mandatory_recall": round(sum(mandatory.values()) / len(mandatory), 4) if mandatory else None,
        "missing_elements": [k for k, v in mandatory.items() if not v],
        "overgeneration_rate": round(sum(discouraged.values()) / len(discouraged), 4) if discouraged else None,
        "overgenerated_elements": [k for k, v in discouraged.items() if v],
        "gate_completeness": round(sum(gates) / len(gates), 4) if gates else None,
        "role_validity": round(len(valid_roles) / len(role_parts), 4) if role_parts else None,
        "invalid_roles": sorted({p for p in role_parts if _norm(p) not in lookup}),
        "flow_coherence": round(sum(transitions) / len(transitions), 4) if transitions else None,
    }
    if description is not None:
        terms = named_terms(description)
        report["entity_recall"] = round(sum(t in text for t in terms) / len(terms), 4) if terms else None
    return report


METRICS = ("lifecycle_conformance", "pairings_present", "mandatory_recall", "overgeneration_rate",
           "gate_completeness", "role_validity", "flow_coherence", "entity_recall")


def aggregate(reports: list[dict]) -> dict:
    out = {"n": len(reports), "schema_valid_rate": round(sum(r["schema_valid"] for r in reports) / max(len(reports), 1), 4)}
    for m in METRICS:
        values = [r[m] for r in reports if r.get(m) is not None]
        out[m] = round(statistics.mean(values), 4) if values else None
    return out
