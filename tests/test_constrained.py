"""Constrained-decoding JSON schemas match what the parser expects."""
import json

import pytest

from core.config import load_factor_ontology
from train.constrained import json_schema
from train.tasks import LEVELS, MODELS, TASKS, parse_output, target
from test_train_tasks import ONTO, make_record

import random

NAMES = list(load_factor_ontology()["factors"])


@pytest.mark.parametrize("task", TASKS)
def test_schema_is_valid_json_and_names_the_task_output(task):
    schema = json_schema(task)
    json.dumps(schema)
    assert schema["type"] == "object" and schema["required"]


def test_extract_schema_requires_every_factor_and_only_valid_levels():
    factors = json_schema("extract")["properties"]["factors"]
    assert factors["required"] == NAMES
    level = factors["properties"][NAMES[0]]["properties"]["level"]
    assert level["enum"] == list(LEVELS)
    assert factors["properties"][NAMES[0]]["required"] == ["level", "evidence"]


def test_direct_schema_restricts_models_to_the_rubric_vocabulary():
    schema = json_schema("direct")
    assert schema["properties"]["primary"]["enum"] == list(MODELS)
    assert schema["properties"]["ranking"]["items"]["enum"] == list(MODELS)


def test_plan_schema_requires_the_fields_a_phase_must_have():
    phase = json_schema("plan")["properties"]["plan"]["properties"]["phases"]["items"]
    for field in ("name", "objective", "activities", "roles", "deliverables",
                  "entry_criteria", "exit_criteria", "approval_gate"):
        assert field in phase["required"], field
    assert phase["properties"]["approval_gate"]["required"] == ["approver", "criteria"]


def test_optional_phase_fields_are_offered_but_not_demanded():
    phase = json_schema("plan")["properties"]["plan"]["properties"]["phases"]["items"]
    for field in ("security_activities", "testing", "compliance_checkpoints"):
        assert field in phase["properties"] and field not in phase["required"], field


@pytest.mark.parametrize("task", TASKS)
def test_a_real_target_would_satisfy_its_own_schema(task):
    jsonschema = pytest.importorskip("jsonschema")
    record = make_record(1, random.Random(1))
    jsonschema.validate(json.loads(target(record, task, ONTO)), json_schema(task))
    assert parse_output(task, target(record, task, ONTO), NAMES)["parse_ok"]


def test_every_character_in_the_descriptions_can_be_quoted_as_evidence():
    """Evidence is verbatim, so the alphabet must allow every character in the descriptions."""
    pytest.importorskip("lmformatenforcer")
    from core.config import ROOT
    from train.constrained import parser_config

    allowed = set(parser_config().alphabet) | {" ", "\n", "\t"}
    texts = [p.read_text(encoding="utf-8") for p in (ROOT / "examples").glob("*.txt")]
    texts.append("Wrocław, ₹12 lakh, €100,000, “quoted” and – dashes")
    assert len(texts) > 1
    missing = sorted({ch for text in texts for ch in text} - allowed)
    assert missing == [], f"characters an evidence span could not reproduce: {missing}"


def test_parser_forces_compact_json_in_field_order():
    pytest.importorskip("lmformatenforcer")
    from train.constrained import parser_config

    config = parser_config()
    assert config.max_consecutive_whitespaces == 1 and config.force_json_field_order is True
