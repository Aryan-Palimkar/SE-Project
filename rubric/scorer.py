"""Deterministic SDLC suitability rubric.

Maps a 14-factor profile to scores over five SDLC models, applies the interaction and
constraint rules, and derives the ranking, acceptable set, hybrid overlays and top factors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

RUBRIC_PATH = Path(__file__).resolve().parent.parent / "ontology" / "rubric.yaml"


def load_rubric(path: Path | str = RUBRIC_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _levels(factors: dict, rubric: dict) -> dict[str, str]:
    """Accept {name: level} or {name: {"level": level, ...}} and validate it."""
    expected = set(rubric["weights"])
    missing, unknown = expected - set(factors), set(factors) - expected
    if missing or unknown:
        raise ValueError(f"factor mismatch: missing={sorted(missing)} unknown={sorted(unknown)}")
    levels = {}
    for name, value in factors.items():
        level = value["level"] if isinstance(value, dict) else value
        if level not in rubric["encoding"]:
            raise ValueError(f"{name}: invalid level {level!r}")
        levels[name] = level
    return levels


def score(factors: dict, rubric: dict | None = None) -> dict:
    rubric = rubric or load_rubric()
    models, weights, rules = rubric["models"], rubric["weights"], rubric["rules"]
    lv = _levels(factors, rubric)
    x = {f: rubric["encoding"][lv[f]] for f in weights}

    contrib = {m: {f: weights[f][m] * x[f] for f in weights} for m in models}
    scores = {m: sum(contrib[m].values()) for m in models}
    triggered = []

    if (lv["technical_novelty"] == "high" and lv["failure_consequence"] == "high"
            and lv["size"] in ("medium", "high")):
        scores["Spiral"] += rules["R4_spiral_bonus"]
        triggered.append("R4")

    model_order = {m: i for i, m in enumerate(models)}
    ranking = sorted(models, key=lambda m: (-scores[m], model_order[m]))

    # C3: plan-driven models may not lead when continuous delivery is essential.
    blocked = set(rules["C3_blocked_models"]) if lv["continuous_delivery_need"] == "high" else set()
    if ranking[0] in blocked:
        triggered.append("C3")
    eligible = [m for m in ranking if m not in blocked]
    top, runner_up = eligible[0], eligible[1]
    ranking = [top] + [m for m in ranking if m != top]
    margin = scores[top] - scores[runner_up]

    acceptable, overlays = [top], []
    if margin <= rubric["delta"]:
        acceptable.append(runner_up)
        if {top, runner_up} in [set(pair) for pair in rubric["compatible_hybrids"]]:
            overlays.append(rubric["overlay_names"][runner_up])
            triggered.append("AMBIGUOUS_HYBRID")
    if (lv["failure_consequence"] == "high" and lv["verification_rigor"] == "high"
            and top in rules["C1_iterative_models"]):
        overlays.append(rules["C1_overlay"])
        triggered.append("C1")
    if lv["regulatory_criticality"] == "high" and "high" in (
            lv["change_frequency"], lv["continuous_delivery_need"]):
        overlays.append(rules["C2_overlay"])
        triggered.append("C2")
    overlays = list(dict.fromkeys(overlays))

    # Low-evidence gate: when too few factors are stated, widen the acceptable set.
    gate = rubric.get("low_evidence")
    coverage = sum(1 for level in lv.values() if level != "not_stated") / len(lv)
    low_evidence = bool(gate) and coverage < gate["min_coverage"]
    if low_evidence:
        widened = [m for m in ranking if m not in blocked][:gate["top_k"]]
        acceptable = widened or acceptable
        triggered.append("LOW_EVIDENCE")

    # Top contributors; ties prefer factors that are present over credit for absence.
    factor_order = {f: i for i, f in enumerate(weights)}

    def top_contributors(m: str) -> list[str]:
        positive = [f for f in weights if contrib[m][f] > 0]
        positive.sort(key=lambda f: (-contrib[m][f], x[f] != 1, factor_order[f]))
        return positive[:3]

    # Tie gate: flag a primary that is only the tie-break order.
    tie = rubric.get("tie_gate") or {}
    withheld = bool(tie) and (margin <= tie.get("withhold_at_margin", -1)
                              or (low_evidence and margin <= tie.get("withhold_at_margin_low_evidence", -1)))
    if withheld:
        widened = [m for m in ranking if m not in blocked][:max(len(acceptable), tie.get("top_k", 2))]
        acceptable = widened or acceptable
        triggered.append("TIE_WITHHELD")

    # Precondition gate: withhold the primary unless one of its defining conditions is stated.
    conditions = rubric.get("preconditions") or {}
    supported = [m for m in models if any(lv[f] in levels for f, levels in
                                          conditions.get("models", {}).get(m, {}).items())]
    if conditions and top not in supported:
        widened = [m for m in ranking if m not in blocked][:max(len(acceptable), conditions.get("top_k", 3))]
        acceptable = widened or acceptable
        withheld = True
        triggered.append("PRECONDITION_UNMET")

    return {
        "scores": scores,
        "ranking": ranking,
        "primary": top,
        "primary_withheld": withheld,
        "supported_models": supported if conditions else None,
        "acceptable_set": acceptable,
        "margin": margin,
        "low_evidence": low_evidence,
        "stated_coverage": round(coverage, 4),
        "hybrid": {"backbone": top, "overlays": overlays} if overlays else None,
        "triggered_rules": triggered,
        "top_contributors": {m: top_contributors(m) for m in models},
        "rubric_version": rubric["version"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a factor profile with the SDLC rubric.")
    parser.add_argument("path", help="JSON file: a record with a 'factors' key, or a plain factor map")
    parser.add_argument("--rubric", default=RUBRIC_PATH)
    args = parser.parse_args()
    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)
    result = score(data.get("factors", data), load_rubric(args.rubric))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
