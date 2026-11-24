"""Compliance map and risk register for one project (deterministic)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from compliance.retrieve import Hit, obligations, retrieve
from eval.plan_checker import _element_present, phase_text

ROOT = Path(__file__).resolve().parent.parent
LEVEL = {"low": 1, "medium": 2, "high": 3}
NAME = {1: "low", 2: "medium", 3: "high"}


@lru_cache(maxsize=1)
def _risk_templates() -> list[dict]:
    with open(ROOT / "ontology" / "risks.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["risks"]


@lru_cache(maxsize=1)
def _elements() -> dict:
    with open(ROOT / "ontology" / "plan_skeletons.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["elements"]


def _phases_covering(element: dict, plan: dict | None) -> list[str]:
    """Names of the plan phases whose text contains the element (roles excluded)."""
    out = []
    for i, phase in enumerate((plan or {}).get("phases") or []):
        if isinstance(phase, dict) and _element_present(element, phase_text(phase, include_roles=bool(element.get("match_roles")))):
            out.append(str(phase.get("name") or f"Phase {i + 1}"))
    return out


@lru_cache(maxsize=512)
def source_clause(text: str, document: str | None) -> dict | None:
    """The passage of the official document that an obligation paraphrases, with its page."""
    if not document:
        return None
    from knowledge.search import best_passage
    hit = best_passage(text, document)
    if not hit:
        return None
    return {"passage": hit["id"], "document": hit["title"], "page": hit["page"], "text": hit["text"]}


def compliance_map(description: str, plan: dict | None = None, hits: list[Hit] | None = None) -> dict:
    hits = hits if hits is not None else retrieve(description)
    rows = []
    for ob in obligations([h.standard for h in hits]):
        covered = _phases_covering(ob, plan) if plan else None
        rows.append({**{k: ob[k] for k in ("id", "standard", "standard_name", "ref", "phase", "description")},
                     "covered_by": covered, "clause": source_clause(ob["description"], ob.get("document"))})
    have_plan = plan is not None and bool((plan or {}).get("phases"))
    n_cov = sum(bool(r["covered_by"]) for r in rows) if have_plan else None
    return {
        "standards": [h.to_dict() for h in hits],
        "obligations": rows,
        "coverage": round(n_cov / len(rows), 4) if have_plan and rows else None,
        "missing": [r["id"] for r in rows if have_plan and not r["covered_by"]],
    }


def _holds(alt: dict, levels: dict, has_standards: bool) -> bool:
    for factor, allowed in alt.items():
        if factor == "standards":
            if not has_standards:
                return False
        elif levels.get(factor, "not_stated") not in allowed:
            return False
    return True


def _level(spec, levels: dict) -> tuple[int, bool]:
    """(1-3, assumed?) for a fixed level or {from: [factors]}; unstated factors read as medium."""
    if isinstance(spec, str):
        return LEVEL[spec], False
    vals, assumed = [], False
    for f in spec["from"]:
        lv = levels.get(f, "not_stated")
        if lv in LEVEL:
            vals.append(LEVEL[lv])
        else:
            vals.append(2)
            assumed = True
    return max(vals), assumed


def risk_register(factors: dict, plan: dict | None = None, comp: dict | None = None) -> list[dict]:
    """factors: {name: {"level", "evidence"}}. `comp` lets the regulatory risk see missing obligations."""
    levels = {f: v.get("level", "not_stated") for f, v in factors.items()}
    has_standards = bool(comp and comp.get("standards"))
    elements = _elements()
    out = []
    for t in _risk_templates():
        alts = [a for a in t["when"] if _holds(a, levels, has_standards)]
        if not alts:
            continue
        triggering = sorted({f for a in alts for f in a if f != "standards"})
        evidence = [{"factor": f, "level": levels[f], "evidence": factors[f].get("evidence")}
                    for f in triggering if levels.get(f) not in (None, "not_stated")]
        if has_standards and any("standards" in a for a in alts):
            evidence += [{"factor": "standard", "level": "applies", "evidence": f"{s['name']} ({s['how']}: {s['evidence']})"}
                         for s in comp["standards"]]
        like, a1 = _level(t["likelihood"], levels)
        imp, a2 = _level(t["impact"], levels)
        note = None
        if t["id"] == "regulatory_findings" and comp and comp.get("missing"):
            like, note = 3, f"{len(comp['missing'])} obligation(s) not in the plan"
        mitigations = []
        for eid in t["mitigations"]:
            el = {"id": eid, **elements[eid]}
            mitigations.append({"id": eid, "description": el["description"],
                                "covered_by": _phases_covering(el, plan) if plan else None})
        out.append({"id": t["id"], "title": t["title"], "owner": t["owner"], "evidence": evidence,
                    "likelihood": NAME[like], "impact": NAME[imp], "score": like * imp,
                    "assumed": a1 or a2, "note": note, "mitigations": mitigations,
                    "mitigated": (any(m["covered_by"] for m in mitigations) if plan else None)})
    return sorted(out, key=lambda r: (-r["score"], r["id"]))


def analyse(description: str, factors: dict, plan: dict | None = None) -> dict:
    """The compliance map and risk register together, as the API returns them."""
    comp = compliance_map(description, plan)
    return {"compliance": comp, "risks": risk_register(factors, plan, comp)}
