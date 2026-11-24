"""JSON-schema constrained decoding with lm-format-enforcer.

  fn = prefix_allowed_tokens_fn("extract", tokenizer)
  model.generate(**inputs, prefix_allowed_tokens_fn=fn)
"""
from __future__ import annotations

from core.config import load_factor_ontology
from train.tasks import LEVELS, MODELS, TASKS, _check_task

_STRING = {"type": "string"}
_STRING_LIST = {"type": "array", "items": _STRING}
_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

PHASE_FIELDS = ("objective", "activities", "roles", "deliverables", "security_activities", "testing",
                "compliance_checkpoints", "entry_criteria", "exit_criteria")

# Optional: an absent list means the same as an empty one.
OPTIONAL_PHASE_FIELDS = ("security_activities", "testing", "compliance_checkpoints")


def _factors_schema(names: list[str]) -> dict:
    factor = {"type": "object",
              "properties": {"level": {"type": "string", "enum": list(LEVELS)}, "evidence": _NULLABLE_STRING},
              "required": ["level", "evidence"]}
    return {"type": "object", "properties": {name: factor for name in names}, "required": list(names)}


def _recommendation_schema() -> dict:
    model = {"type": "string", "enum": list(MODELS)}
    return {"type": "object",
            "properties": {"ranking": {"type": "array", "items": model},
                           "primary": model,
                           "acceptable_set": {"type": "array", "items": model},
                           "hybrid": _STRING_LIST},
            "required": ["ranking", "primary", "acceptable_set", "hybrid"]}


def _plan_schema() -> dict:
    phase = {"type": "object",
             "properties": {"name": _STRING, "objective": _STRING,
                            **{f: _STRING_LIST for f in PHASE_FIELDS if f != "objective"},
                            "approval_gate": {"type": "object",
                                              "properties": {"approver": _STRING, "criteria": _STRING},
                                              "required": ["approver", "criteria"]}},
             "required": ["name", *(f for f in PHASE_FIELDS if f not in OPTIONAL_PHASE_FIELDS), "approval_gate"]}
    return {"type": "object",
            "properties": {"justification": _STRING,
                           "plan": {"type": "object",
                                    "properties": {"lifecycle": _STRING,
                                                   "phases": {"type": "array", "items": phase}},
                                    "required": ["lifecycle", "phases"]}},
            "required": ["justification", "plan"]}


def json_schema(task: str, onto: dict | None = None) -> dict:
    """The JSON schema a task's answer must satisfy."""
    _check_task(task)
    names = list((onto or load_factor_ontology())["factors"])
    if task == "extract":
        return {"type": "object", "properties": {"factors": _factors_schema(names)}, "required": ["factors"]}
    if task == "direct":
        return _recommendation_schema()
    if task == "e2e":
        return {"type": "object",
                "properties": {"factors": _factors_schema(names), "recommendation": _recommendation_schema()},
                "required": ["factors", "recommendation"]}
    return _plan_schema()


# Extra string characters beyond the enforcer's ASCII default, so evidence can be quoted verbatim.
_EXTRA_ALPHABET = ("".join(chr(c) for c in range(0xA0, 0x180))       # Latin-1 Supplement + Extended-A
                   + "".join(chr(c) for c in range(0x20A0, 0x20C1))   # currency signs
                   + "–—‘’‚“”„…•·°±×÷≤≥→←✓")


def parser_config():
    """Enforcer settings: compact whitespace, fixed field order, extended alphabet."""
    from lmformatenforcer import CharacterLevelParserConfig

    default = CharacterLevelParserConfig()
    return CharacterLevelParserConfig(alphabet=default.alphabet + _EXTRA_ALPHABET, max_consecutive_whitespaces=1,
                                      force_json_field_order=True, max_json_array_length=default.max_json_array_length)


def prefix_allowed_tokens_fn(task: str, tokenizer, onto: dict | None = None):
    """A `prefix_allowed_tokens_fn` for `model.generate` that permits only valid JSON for `task`.

    Raises ImportError if lm-format-enforcer is not installed.
    """
    try:
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
    except ImportError as exc:                                  # pragma: no cover - depends on environment
        raise ImportError("constrained decoding needs lm-format-enforcer: pip install lm-format-enforcer") from exc
    parser = JsonSchemaParser(json_schema(task, onto), config=parser_config())
    return build_transformers_prefix_allowed_tokens_fn(tokenizer, parser)


__all__ = ["TASKS", "json_schema", "prefix_allowed_tokens_fn"]
