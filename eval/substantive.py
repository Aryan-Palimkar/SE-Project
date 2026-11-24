"""Locate where, and in what form, a plan mentions an obligation."""
from __future__ import annotations

from eval.plan_checker import _loose

FIELDS = ("objective", "activities", "deliverables", "testing", "security_activities",
          "compliance_checkpoints", "entry_criteria", "exit_criteria", "approval_gate")


def _items_of(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [str(value.get("criteria") or "")]
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [s for s in str(value).split("\n") if s.strip()]


def locations(obligation: dict, plan: dict | None) -> list[dict]:
    """Every (phase, field, item) where one of the obligation's keywords appears."""
    out = []
    for i, phase in enumerate((plan or {}).get("phases") or []):
        if not isinstance(phase, dict):
            continue
        name = str(phase.get("name") or f"Phase {i + 1}")
        for field in FIELDS:
            for item in _items_of(phase.get(field)):
                loose = _loose(item)
                hit = next((k for k in obligation["keywords"] if _loose(k) in loose), None)
                if hit:
                    out.append({"phase": name, "phase_index": i, "field": field, "item": item, "keyword": hit})
    return out
