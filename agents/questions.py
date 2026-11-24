"""Pick the unstated factors worth asking about: those whose level would change the recommendation."""
from __future__ import annotations

from rubric.scorer import load_rubric, score
from train.tasks import recommendation_from_rubric

TRIALS = ("low", "medium", "high")


def _recommendation(levels: dict, rubric: dict) -> dict:
    return recommendation_from_rubric(score(levels, rubric))


def decision_relevant(levels: dict, rubric: dict | None = None) -> list[dict]:
    """[{factor, current, outcomes: {level: primary}, changes_primary}] for unstated factors,
    most influential first."""
    rubric = rubric or load_rubric()
    base = _recommendation(levels, rubric)
    out = []
    for factor, level in levels.items():
        if level != "not_stated":
            continue
        outcomes = {}
        for trial in TRIALS:
            outcomes[trial] = _recommendation({**levels, factor: trial}, rubric)["primary"]
        distinct = set(outcomes.values()) | {base["primary"]}
        if len(distinct) > 1:
            out.append({"factor": factor, "current": level, "outcomes": outcomes,
                        "primaries": sorted(distinct), "n_outcomes": len(distinct)})
    out.sort(key=lambda r: (-r["n_outcomes"], r["factor"]))
    return out
