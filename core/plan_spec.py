"""Deterministic plan requirements for a record.

Gives the phase skeleton for the recommended model, overlay elements, mandatory and
discouraged elements, and allowed roles. The generator and the checker use the same object.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent / "ontology"


def load_plan_ontology(path: Path | str = ONTOLOGY / "plan_skeletons.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_roles(path: Path | str = ONTOLOGY / "roles.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _levels(factors: dict) -> dict[str, str]:
    return {f: (v["level"] if isinstance(v, dict) else v) for f, v in factors.items()}


def _matches(conditions: list[dict], levels: dict[str, str]) -> list[str]:
    """Human-readable descriptions of the alternative conditions that hold (empty if none)."""
    hits = []
    for cond in conditions or []:
        if all(levels.get(f) in allowed for f, allowed in cond.items()):
            hits.append(" and ".join(f"{f}={levels[f]}" for f in cond))
    return hits


def plan_requirements(factors: dict, recommendation: dict, plan_ont: dict | None = None,
                      roles: dict | None = None) -> dict:
    """factors: {name: level} or {name: {"level": ...}}; recommendation: {"primary", "hybrid": [overlay names]}."""
    plan_ont, roles = plan_ont or load_plan_ontology(), roles or load_roles()
    levels, primary = _levels(factors), recommendation["primary"]
    if primary not in plan_ont["lifecycles"]:
        raise ValueError(f"no skeleton for lifecycle {primary!r}")
    overlays = list(recommendation.get("hybrid") or [])
    unknown = [o for o in overlays if o not in plan_ont["overlays"]]
    if unknown:
        raise ValueError(f"no plan elements for overlays {unknown}")

    mandatory: dict[str, dict] = {}

    def add(element_id: str, reason: str) -> None:
        el = plan_ont["elements"][element_id]
        entry = mandatory.setdefault(element_id, {
            "id": element_id, "description": el["description"], "keywords": el["keywords"],
            "require_all_keywords": el.get("require_all_keywords", False),
            "match_roles": el.get("match_roles", False), "reasons": []})
        entry["reasons"].append(reason)

    for overlay in overlays:
        for element_id in plan_ont["overlays"][overlay]:
            add(element_id, f"overlay: {overlay}")
    for element_id, el in plan_ont["elements"].items():
        for hit in _matches(el.get("when"), levels):
            add(element_id, hit)
    discouraged = [{"id": eid, "description": el["description"], "keywords": el["keywords"],
                    "match_roles": el.get("match_roles", False), "reasons": hits}
                   for eid, el in plan_ont["elements"].items()
                   if eid not in mandatory and (hits := _matches(el.get("discouraged_when"), levels))]
    phases = plan_ont["lifecycles"][primary]["phases"]
    return {
        "lifecycle": primary,
        "overlays": overlays,
        "phases": [p["name"] for p in phases],
        "phase_aliases": {p["name"]: p.get("aliases", []) for p in phases},
        "pairings": {p["name"]: p["pairs_with"] for p in phases if "pairs_with" in p},
        "anchors": {p["name"]: p["anchor"] for p in phases if "anchor" in p},
        "mandatory": list(mandatory.values()),
        "discouraged": discouraged,
        "roles": list(roles["roles"]),
        "role_aliases": roles["roles"],
        "plan_ontology_version": plan_ont["version"],
    }
