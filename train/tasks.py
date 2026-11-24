"""Supervised fine-tuning tasks: prompts, targets and output parsing.

  extract  description -> 14 factor levels with verbatim evidence
  direct   description -> SDLC ranking without factors
  e2e      description -> factors, then the ranking, in one output
  plan     description + factors + recommendation + skeleton -> justification and plan
"""
from __future__ import annotations

import json
import re

from rubric.scorer import load_rubric, score

TASKS = ("extract", "direct", "e2e", "plan")
TASK_VERSION = "sft-v1"
LEVELS = ("low", "medium", "high", "not_stated")
MODELS = tuple(load_rubric()["models"])

_FACTORS_FORM = ('{"<characteristic>": {"level": "low|medium|high|not_stated", "evidence": "<exact span>" or null}, '
                 '... all 14, in the order listed}')
_REC_FORM = ('{"ranking": [all 5 models, best first], "primary": "<model>", '
             '"acceptable_set": ["<model>", ...], "hybrid": ["<overlay>", ...]}')
_FORMS = {
    "extract": '{"factors": ' + _FACTORS_FORM + "}",
    "direct": _REC_FORM,
    "e2e": '{"factors": ' + _FACTORS_FORM + ', "recommendation": ' + _REC_FORM + "}",
}


def _check_task(task: str) -> None:
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; choose from {TASKS}")


def system_prompt(task: str, onto: dict, definitions: bool = False) -> str:
    """Instructions for `task`. `definitions` adds the level descriptors (for zero-shot baselines)."""
    _check_task(task)
    if task == "plan":
        from core.plan_prompt import plan_system_prompt

        return plan_system_prompt()
    names = list(onto["factors"])
    parts = ["You analyse software project descriptions to support SDLC planning."]
    if task != "direct":
        parts.append(
            "Rate each of these 14 project characteristics as low, medium or high, or not_stated when the "
            "description gives no basis for it: " + ", ".join(names) + ". For every rated characteristic, "
            "copy the shortest span of the description that shows its level, character for character; use "
            "null for not_stated.")
    if task != "extract":
        parts.append(
            "Rank the SDLC models " + ", ".join(MODELS) + " from most to least suitable. Give the primary "
            "model, the acceptable set (the primary, plus the runner-up when the choice is too close to call) "
            "and any hybrid overlays (an empty list when none apply).")
    if definitions:
        # include the ontology's `not_evidence` and `evidence_note` hints
        lines = []
        for n, d in onto["factors"].items():
            line = f"- {n}: {d['question']} high = {d['high']} medium = {d['medium']} low = {d['low']}"
            if d.get("evidence_note"):
                line += f" NOTE: {d['evidence_note']}"
            if d.get("not_evidence"):
                line += f" NOT evidence: {d['not_evidence']}"
            lines.append(" ".join(line.split()))
        parts.append("Characteristics:\n" + "\n".join(lines))
        parts.append("Answer not_stated whenever the description only asserts something about a "
                     "characteristic without giving a fact that fixes its level.")
    parts.append("Answer with one JSON object and nothing else, in this form: " + _FORMS[task])
    return "\n\n".join(parts)


def user_prompt(description: str) -> str:
    return f"Project description:\n<<<\n{description}\n>>>"


def plan_user_prompt_for(record: dict) -> str:
    """The plan prompt for a record, built from the same code that produced the gold plans."""
    from core.plan_prompt import plan_user_prompt
    from core.plan_spec import plan_requirements

    return plan_user_prompt(record, plan_requirements(record["factors"], record["recommendation"]))


def build_prompt(record: dict, task: str, onto: dict, definitions: bool = False) -> tuple[str, str]:
    user = plan_user_prompt_for(record) if task == "plan" else user_prompt(record["description"])
    return system_prompt(task, onto, definitions), user


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def target(record: dict, task: str, onto: dict) -> str:
    """The assistant answer for a dataset record, as compact JSON."""
    _check_task(task)
    if task == "plan":
        gold = record.get("plan_target")
        if not gold:
            raise KeyError(f"record {record.get('id')} has no plan_target")
        return _dumps({"justification": gold["justification"], "plan": gold["plan"]})
    names = list(onto["factors"])
    factors = {f: {"level": record["factors"][f]["level"], "evidence": record["factors"][f]["evidence"]}
               for f in names}
    r = record["recommendation"]
    rec = {"ranking": list(r["ranking"]), "primary": r["primary"], "acceptable_set": list(r["acceptable_set"]),
           "hybrid": list(r["hybrid"] or [])}
    obj = {"extract": {"factors": factors}, "direct": rec, "e2e": {"factors": factors, "recommendation": rec}}[task]
    return _dumps(obj)


def build_messages(record: dict, task: str, onto: dict, definitions: bool = False) -> list[dict]:
    system, user = build_prompt(record, task, onto, definitions)
    return [{"role": "system", "content": system}, {"role": "user", "content": user},
            {"role": "assistant", "content": target(record, task, onto)}]


def _norm_level(text: str) -> str:
    return re.sub(r"[\s-]+", "_", text.strip().lower())


def _json_object(raw: str) -> dict | None:
    start, end = raw.find("{"), raw.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None
    return None


def _factors_from(obj_factors, raw: str, names: list[str]) -> tuple[dict, dict]:
    """Levels and evidence per factor, with a regex fallback for malformed JSON."""
    levels, evidence = {}, {}
    for f in names:
        value = obj_factors.get(f) if isinstance(obj_factors, dict) else None
        level = value.get("level") if isinstance(value, dict) else value
        span = value.get("evidence") if isinstance(value, dict) else None
        if isinstance(level, str) and _norm_level(level) in LEVELS:
            levels[f] = _norm_level(level)
        else:
            m = re.search(rf'"{re.escape(f)}"\s*:\s*\{{\s*"level"\s*:\s*"([A-Za-z_ -]+)"', raw)
            levels[f] = _norm_level(m.group(1)) if m and _norm_level(m.group(1)) in LEVELS else "missing"
        evidence[f] = span if isinstance(span, str) and span.strip() else None
    return levels, evidence


def _recommendation_from(obj) -> dict | None:
    if not isinstance(obj, dict):
        return None
    ranking = obj.get("ranking") if isinstance(obj.get("ranking"), list) else []
    ranking = list(dict.fromkeys(m for m in ranking if m in MODELS))
    primary = obj.get("primary") if obj.get("primary") in MODELS else (ranking[0] if ranking else None)
    if primary is None:
        return None
    acceptable = obj.get("acceptable_set") if isinstance(obj.get("acceptable_set"), list) else []
    hybrid = obj.get("hybrid") if isinstance(obj.get("hybrid"), list) else []
    return {"ranking": ranking, "primary": primary,
            "acceptable_set": [m for m in acceptable if m in MODELS] or [primary],
            "hybrid": [h for h in hybrid if isinstance(h, str)]}


def parse_output(task: str, raw: str, names: list[str]) -> dict:
    """{'parse_ok', 'levels', 'evidence', 'recommendation'} (None where the task has no such part)."""
    _check_task(task)
    obj = _json_object(raw)
    out = {"parse_ok": obj is not None, "levels": None, "evidence": None, "recommendation": None,
           "plan": None, "justification": None}
    if task == "plan":
        out["plan"] = (obj or {}).get("plan")
        out["justification"] = (obj or {}).get("justification")
        out["parse_ok"] = isinstance(out["plan"], dict)
        return out
    if task in ("extract", "e2e"):
        out["levels"], out["evidence"] = _factors_from((obj or {}).get("factors"), raw, names)
    if task in ("direct", "e2e"):
        out["recommendation"] = _recommendation_from((obj or {}).get("recommendation") if task == "e2e" else obj)
    return out


def recommendation_from_rubric(result: dict) -> dict:
    return {"ranking": result["ranking"], "primary": result["primary"], "acceptable_set": result["acceptable_set"],
            "hybrid": result["hybrid"]["overlays"] if result["hybrid"] else []}


def rubric_recommendation(levels: dict, rubric: dict | None = None) -> dict:
    """Run the rubric on predicted levels; unreadable ('missing') factors count as not_stated."""
    clean = {f: (lvl if lvl in LEVELS else "not_stated") for f, lvl in levels.items()}
    return recommendation_from_rubric(score(clean, rubric))
