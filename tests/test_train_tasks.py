"""SFT task formats: targets round-trip through the parser, prompts stay stable."""
import json
import random

import pytest

from core.config import load_factor_ontology
from rubric.scorer import score
from train.tasks import (LEVELS, MODELS, TASKS, build_messages, parse_output, recommendation_from_rubric,
                         rubric_recommendation, system_prompt, target)

ONTO = load_factor_ontology()
NAMES = list(ONTO["factors"])


def make_record(i: int, rng: random.Random) -> dict:
    levels = {f: rng.choice(LEVELS) for f in NAMES}
    desc = " ".join(f'Fact "{f}" number {i}.' for f, lvl in levels.items() if lvl != "not_stated") or f"Empty {i}."
    return {
        "id": f"r{i}", "description": desc,
        "metadata": {"length_bucket": "short", "explicitness": "implicit", "difficulty": "medium"},
        "factors": {f: {"level": lvl, "evidence": f'Fact "{f}" number {i}' if lvl != "not_stated" else None}
                    for f, lvl in levels.items()},
        "recommendation": recommendation_from_rubric(score(levels)),
        # plan targets come from gold plans joined by build_sft; a stub is enough here
        "plan_target": {"justification": f"Justification {i}.",
                        "plan": {"lifecycle": recommendation_from_rubric(score(levels))["primary"],
                                 "phases": [{"name": f"Phase {i}", "objective": "o", "activities": ["a"],
                                             "roles": ["Developer"], "deliverables": ["d"],
                                             "security_activities": [], "testing": [], "compliance_checkpoints": [],
                                             "approval_gate": {"approver": "Project Manager", "criteria": "c"},
                                             "entry_criteria": ["e"], "exit_criteria": ["x"]}]}},
    }


@pytest.mark.parametrize("task", TASKS)
def test_target_round_trips_through_parser(task):
    rng = random.Random(0)
    for i in range(20):
        record = make_record(i, rng)
        parsed = parse_output(task, target(record, task, ONTO), NAMES)
        assert parsed["parse_ok"]
        if task == "plan":
            assert parsed["plan"] == record["plan_target"]["plan"]
            assert parsed["justification"] == record["plan_target"]["justification"]
            continue
        if task != "direct":
            assert parsed["levels"] == {f: record["factors"][f]["level"] for f in NAMES}
            assert parsed["evidence"] == {f: record["factors"][f]["evidence"] for f in NAMES}
        if task != "extract":
            assert parsed["recommendation"] == record["recommendation"]


def test_target_keeps_factor_order_and_is_compact():
    record = make_record(1, random.Random(1))
    obj = json.loads(target(record, "e2e", ONTO))
    assert list(obj) == ["factors", "recommendation"]
    assert list(obj["factors"]) == NAMES
    assert ": " not in target(record, "extract", ONTO).split('"evidence"')[0]


def test_messages_and_prompts():
    record = make_record(2, random.Random(2))
    msgs = build_messages(record, "extract", ONTO)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert record["description"] in msgs[1]["content"]
    assert "not_stated" in msgs[0]["content"] and "Waterfall" not in msgs[0]["content"]
    assert all(m in system_prompt("direct", ONTO) for m in MODELS)
    assert "high =" not in system_prompt("extract", ONTO)
    assert "high =" in system_prompt("extract", ONTO, definitions=True)
    with pytest.raises(ValueError):
        system_prompt("summarise", ONTO)


def test_plan_prompt_carries_the_requirements_and_needs_a_gold_plan():
    record = make_record(4, random.Random(4))
    msgs = build_messages(record, "plan", ONTO)
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert record["description"] in user
    assert "Lifecycle skeleton" in user and "Mandatory elements" in user and "Allowed roles" in user
    assert "do not change" in user and "JSON" in system
    assert json.loads(msgs[2]["content"])["plan"]["lifecycle"] == record["recommendation"]["primary"]
    with pytest.raises(KeyError):
        target({k: v for k, v in record.items() if k != "plan_target"}, "plan", ONTO)


def test_parser_recovers_levels_from_truncated_json():
    record = make_record(3, random.Random(3))
    full = target(record, "extract", ONTO)
    cut = full[: len(full) // 2]
    parsed = parse_output("extract", cut, NAMES)
    assert not parsed["parse_ok"]
    got = {f: lvl for f, lvl in parsed["levels"].items() if lvl != "missing"}
    assert got and all(got[f] == record["factors"][f]["level"] for f in got)
    assert "missing" in parsed["levels"].values()


def test_parser_handles_garbage_and_bad_models():
    parsed = parse_output("e2e", "I cannot answer that.", NAMES)
    assert parsed["parse_ok"] is False and parsed["recommendation"] is None
    assert set(parsed["levels"].values()) == {"missing"}
    rec = parse_output("direct", '{"ranking": ["Scrum", "Agile", "Agile"], "hybrid": "x"}', NAMES)["recommendation"]
    assert rec == {"ranking": ["Agile"], "primary": "Agile", "acceptable_set": ["Agile"], "hybrid": []}


def test_rubric_recommendation_treats_missing_as_not_stated():
    levels = {f: "missing" for f in NAMES}
    assert rubric_recommendation(levels) == recommendation_from_rubric(score({f: "not_stated" for f in NAMES}))
