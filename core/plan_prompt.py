"""Prompts for writing a project-specific SDLC plan."""
from __future__ import annotations

PLAN_SYSTEM = (
    "You are a senior software process engineer. You write project-specific SDLC plans that follow a given "
    "lifecycle skeleton and a list of mandatory elements exactly. The project's characteristics and the "
    "recommended lifecycle have already been decided by a documented rubric; you never change them. You "
    "never invent facts about the project that are not in the description. You return valid JSON only.\n\n"
    "OUTPUT\n"
    '{"justification": "<at most 150 words>", "plan": {"lifecycle": "<recommended model>", "phases": [\n'
    '  {"name": "<skeleton phase name>", "objective": "<one sentence>", "activities": [3-6 items], '
    '"roles": [roles from the allowed list], "deliverables": [...], "security_activities": [...], '
    '"testing": [...], "compliance_checkpoints": [...], "approval_gate": {"approver": "<allowed role(s), '
    'joined with +>", "criteria": "<what must be true to pass>"}, "entry_criteria": [...], '
    '"exit_criteria": [...]}, ... one object per skeleton phase, in skeleton order ]}}\n\n'
    "RULES\n"
    "1. Justification: explain why the recommended model ranks first by citing only its listed top "
    "contributing factors and their evidence; add one clause each on why the runner-up and the lowest-ranked "
    "model fit less well. No facts beyond the description.\n"
    "2. Use every skeleton phase name exactly, in order, and no other phases. For V-Model, name the paired test "
    "level in each specification phase's testing list.\n"
    "3. Every mandatory element must appear explicitly in the phase where it belongs, using its usual name "
    "(e.g. 'threat modelling', 'traceability matrix', 'penetration test').\n"
    "4. Do not add the discouraged elements unless the description itself calls for them.\n"
    "5. Be project-specific: name the actual components, integrations, regulators, user groups, deadlines "
    "and constraints from the description.\n"
    "6. The entry criteria of each phase must refer to the exit criteria or deliverables of the previous phase.\n"
    "7. Use only the allowed roles. Lists may be empty only where nothing applies. At most 5 items per list; "
    "terse phrases, not paragraphs."
)


def plan_system_prompt() -> str:
    return PLAN_SYSTEM


def plan_user_prompt(record: dict, req: dict) -> str:
    rec = record["recommendation"]
    scores = rec.get("scores") or {}
    ranking = rec["ranking"]
    contributors = rec.get("top_contributors") or {}
    factor_lines = "\n".join(
        f"- {f}: {v['level']}" + (f' (evidence: "{v["evidence"]}")' if v.get("evidence") else "")
        for f, v in record["factors"].items())
    phase_lines = []
    for p in req["phases"]:
        extra = []
        if p in req["pairings"]:
            extra.append(f"pairs with {req['pairings'][p]}")
        if p in req["anchors"]:
            extra.append(f"anchor point: {req['anchors'][p]}")
        phase_lines.append(f"- {p}" + (f" ({'; '.join(extra)})" if extra else ""))
    mandatory = "\n".join(f"- {m['description']} [because {', '.join(m['reasons'])}]" for m in req["mandatory"])
    discouraged = "\n".join(f"- {d['description']} [{', '.join(d['reasons'])}]" for d in req["discouraged"])
    runner_up, lowest = ranking[1], ranking[-1]

    def with_levels(model: str) -> str:
        # A factor can favour a model through its absence (e.g. low regulatory criticality for Agile).
        names = contributors.get(model, [])
        return ", ".join(f"{f}={record['factors'][f]['level']}" for f in names) or "none"

    return (
        f"Project description:\n<<<\n{record['description']}\n>>>\n\n"
        f"Assessed characteristics (authoritative, do not change):\n{factor_lines}\n\n"
        "Recommendation (computed by the rubric, do not change):\n"
        f"- ranking with scores: {', '.join(f'{m} {scores.get(m, 0):+d}' for m in ranking)}\n"
        f"- recommended: {rec['primary']}; acceptable set: {', '.join(rec['acceptable_set'])}; "
        f"margin to runner-up: {rec.get('margin', '?')}\n"
        f"- hybrid overlays: {', '.join(rec.get('hybrid') or []) or 'none'}\n"
        f"- triggered rules: {', '.join(rec.get('triggered_rules') or []) or 'none'}\n"
        f"- top contributing factors (with levels): {rec['primary']}: {with_levels(rec['primary'])}; "
        f"runner-up {runner_up}: {with_levels(runner_up)}; lowest-ranked {lowest}: {with_levels(lowest)}\n\n"
        f"Lifecycle skeleton for {req['lifecycle']} (use these phase names, in this order):\n"
        + "\n".join(phase_lines) + "\n\n"
        f"Mandatory elements (each must appear):\n{mandatory or '- none'}\n\n"
        f"Discouraged elements (over-engineering for this project):\n{discouraged or '- none'}\n\n"
        f"Allowed roles: {', '.join(req['roles'])}\n\n"
        "Return the JSON object now."
    )

