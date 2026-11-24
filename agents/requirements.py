"""Requirements agent.

identify  lists the requirements the description states or implies, each with a quote from the text
regulate  maps the obligations retrieved from the knowledge base onto that list: each applicable
          obligation is linked to a requirement that already covers it, or added as a new one

IDs, types and each requirement's basis (stated, regulation or inferred) are assigned in code.
`reconcile` (off by default) lets stated requirements fill SDLC factors the extractor left unstated.
"""
from __future__ import annotations

import json
import re
import time
from difflib import SequenceMatcher

from agents import nodes
from agents.state import RunState
from core.backends import Backend

CATEGORIES = {
    "functional": ("FR", "what the system does for its users"),
    "security": ("NFR-SEC", "authentication, authorisation, fraud, protection against attack"),
    "privacy": ("NFR-PRI", "personal data collection, consent, retention, masking"),
    "regulatory": ("NFR-REG", "obligations from laws, regulators or standards"),
    "performance": ("NFR-PERF", "response times, throughput, capacity"),
    "availability": ("NFR-AVL", "uptime, recovery, resilience"),
    "usability": ("NFR-USE", "ease of use, accessibility"),
    "data": ("NFR-DATA", "data quality, storage, reporting data"),
    "integration": ("NFR-INT", "interfaces with other or legacy systems"),
    "audit": ("NFR-AUD", "audit trails, evidence, record keeping"),
    "operational": ("NFR-OPS", "monitoring, support, maintenance"),
}
FACTORS_BY_CATEGORY = {
    "functional": ("complexity",),
    "security": ("security_risk",),
    "privacy": ("security_risk", "regulatory_criticality"),
    "regulatory": ("regulatory_criticality",),
    "performance": ("complexity", "failure_consequence"),
    "availability": ("failure_consequence",),
    "usability": (),
    "data": ("security_risk",),
    "integration": ("legacy_dependence", "complexity"),
    "audit": ("regulatory_criticality", "verification_rigor", "test_doc_rigor"),
    "operational": ("continuous_delivery_need",),
}
MAX_REQUIREMENTS = 25
MAX_FROM_OBLIGATIONS = 8
MIN_QUOTE_CHARS = 12
MIN_QUOTE_SIMILARITY = 0.8
RESTATEMENT_SIMILARITY = 0.85
MAX_CLAUSES = 6
CLAUSE_CHARS = 700

_SYSTEM = """You are a requirements analyst. Read the project description and list its software requirements.

Rules:
- One requirement per item, written as "The system shall ...". Keep each one short and testable.
- category is one of:
{categories}
- source: copy, character for character, the shortest part of the description the requirement comes from.
  Use null if it does not come from the description.
- List what the description states or clearly implies, functional requirements first. Do not invent
  features the description does not support.
- At most {limit} requirements.

Answer with one JSON object and nothing else:
{{"requirements": [{{"statement": "The system shall ...", "category": "...", "source": "..." or null}}]}}"""

_REGULATE = """You are a compliance analyst. You are given a project description, the requirements already
identified for it, obligations from a compliance knowledge base, and clauses retrieved from official
regulatory documents. An obligation id or a clause id (P1, P2, ...) can be cited as "obligation".

For each obligation or clause that applies to this project:
- if one of the existing requirements already satisfies it, answer
  {{"obligation": "<obligation id>", "existing": "<requirement id>"}}
- otherwise add one requirement that satisfies it, written for this project:
  {{"obligation": "<obligation id>", "statement": "The system shall ...", "category": "..."}}
Leave out obligations that do not apply to this project. Add at most {limit} new requirements.
category is one of: {categories}

Answer with one JSON object and nothing else: {{"requirements": [...]}}"""


def _categories() -> str:
    return "\n".join(f"  {name}: {desc}" for name, (_, desc) in CATEGORIES.items())


def system_prompt(limit: int = MAX_REQUIREMENTS) -> str:
    return _SYSTEM.format(categories=_categories(), limit=limit)


def user_prompt(description: str) -> str:
    return f"Project description:\n<<<\n{description}\n>>>"


def regulate_prompts(description: str, requirements: list[dict], obligations: list[dict]) -> tuple[str, str]:
    system = _REGULATE.format(limit=MAX_FROM_OBLIGATIONS, categories=", ".join(CATEGORIES))
    existing = "\n".join(f"- {r['id']}: {r['statement']}" for r in requirements) or "(none)"
    rows = "\n".join(f"- {o['id']}: {o['description']} [{o['standard_name']} {o['ref']}]"
                     for o in obligations if not o.get("passage"))
    clauses = "\n".join(f"- {o['id']} [{o['standard_name']}, {o['ref']}]: {o['description'][:CLAUSE_CHARS]}"
                        for o in obligations if o.get("passage"))
    user = f"{user_prompt(description)}\n\nRequirements already identified:\n{existing}"
    if rows:
        user += f"\n\nObligations from the compliance knowledge base:\n{rows}"
    if clauses:
        user += f"\n\nClauses retrieved from official documents:\n{clauses}"
    return system, user


def clause_sources(clauses: list[dict]) -> list[dict]:
    """Retrieved passages in the same shape as obligations, with ids P1, P2, ..."""
    return [{"id": f"P{i}", "passage": c["id"], "standard": c["source"], "standard_name": c["title"],
             "ref": f"p. {c['page']}", "description": c["text"],
             "clause": {"passage": c["id"], "document": c["title"], "page": c["page"], "text": c["text"]}}
            for i, c in enumerate(clauses, 1)]


def retrieve_clauses(state: RunState, k: int = MAX_CLAUSES) -> list[dict]:
    """Passages of the applicable official documents closest to the description and its requirements."""
    from compliance.retrieve import sentences
    from knowledge.search import documents_for, search
    standards = [s["standard"] for s in (state.compliance or {}).get("standards", [])]
    documents = documents_for(standards)
    if not documents:
        return []
    queries = sentences(state.description) + [r["statement"] for r in state.requirements]
    return search(queries, documents, k=k)


def _squash(text: str) -> str:
    return " ".join(str(text).lower().split())


_WORD = re.compile(r"\w+(?:['’-]\w+)*")


def locate(quote, description: str, min_ratio: float = MIN_QUOTE_SIMILARITY) -> str | None:
    """The passage of `description` that `quote` comes from, copied from the description itself.
    Exact (case- and whitespace-insensitive) matches are returned as quoted; otherwise the closest
    run of words is used when its word-level similarity is at least `min_ratio`, because the model
    often paraphrases the edges of a quote ("the system extracts ..." for "a system that extracts ...")."""
    if not isinstance(quote, str) or quote.strip().lower() in ("", "null", "none", "n/a"):
        return None
    quote = " ".join(quote.split())
    if len(quote) < MIN_QUOTE_CHARS:
        return None
    if _squash(quote) in _squash(description):
        return quote
    q = [w.lower() for w in _WORD.findall(quote)]
    spans = list(_WORD.finditer(description))
    words = [m.group(0).lower() for m in spans]
    if len(q) < 3 or not words:
        return None
    best = (0.0, 0, 0)
    for width in range(max(1, len(q) - 2), len(q) + 6):
        for start in range(0, max(1, len(words) - width + 1)):
            matcher = SequenceMatcher(None, q, words[start:start + width], autojunk=False)
            ratio = matcher.ratio()
            if ratio > best[0]:
                blocks = [b for b in matcher.get_matching_blocks() if b.size]
                best = (ratio, start + blocks[0].b, start + blocks[-1].b + blocks[-1].size - 1)
    ratio, first, last = best
    if ratio < min_ratio:
        return None
    return description[spans[first].start():spans[last].end()]


def _items(raw: str) -> tuple[list[dict], bool]:
    """Item objects from the model output; falls back to item-by-item parsing when the JSON is
    truncated or malformed. The flag says whether the whole answer parsed."""
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(text[start:end + 1])
            items = obj.get("requirements") if isinstance(obj, dict) else None
            if isinstance(items, list):
                return [i for i in items if isinstance(i, dict)], True
        except json.JSONDecodeError:
            pass
    items = []
    for m in re.finditer(r"\{[^{}]*\"(?:statement|obligation)\"[^{}]*\}", text):
        try:
            items.append(json.loads(m.group(0)))
        except json.JSONDecodeError:
            continue
    return items, False


def _citation(ob: dict) -> dict:
    return {"obligation": ob.get("passage") or ob["id"], "standard": ob["standard_name"], "ref": ob["ref"],
            "clause": ob.get("clause")}


def _add(out: list[dict], statement: str, category: str, basis: str, source=None, citation=None) -> None:
    prefix = CATEGORIES[category][0]
    n = sum(r["id"].rsplit("-", 1)[0] == prefix for r in out) + 1
    out.append({"id": f"{prefix}-{n:02d}", "statement": statement,
                "type": "functional" if category == "functional" else "non-functional",
                "category": category, "basis": basis, "source": source, "citation": citation})


def _clean(item: dict) -> tuple[str, str]:
    statement = " ".join(str(item.get("statement") or "").split())
    category = str(item.get("category") or "").strip().lower()
    return statement, category if category in CATEGORIES else "functional"


def normalise(items: list[dict], description: str) -> list[dict]:
    """Validate the first pass: IDs, type, and stated vs inferred."""
    out, seen = [], set()
    for item in items:
        statement, category = _clean(item)
        if not statement or _squash(statement) in seen:
            continue
        seen.add(_squash(statement))
        source = locate(item.get("source"), description)
        _add(out, statement, category, "stated" if source else "inferred", source)
        if len(out) >= MAX_REQUIREMENTS:
            break
    return out


def merge_regulatory(requirements: list[dict], items: list[dict], obligations: list[dict],
                     restates=None) -> tuple[list, dict]:
    """Apply the RAG pass: link obligations to existing requirements or add cited ones.
    Items citing an unknown obligation are dropped. `restates(statement)` returns the id of an
    existing requirement a new one merely restates; that one is linked instead of added.
    Returns (requirements, counts)."""
    by_id = {o["id"]: o for o in obligations}
    out = [dict(r) for r in requirements]
    index = {r["id"]: r for r in out}
    seen = {_squash(r["statement"]) for r in out}
    linked = added = 0
    for item in items:
        ob = by_id.get(str(item.get("obligation") or "").strip())
        if not ob:
            continue
        target = index.get(str(item.get("existing") or "").strip())
        if target is None and restates is not None and item.get("statement"):
            target = index.get(restates(" ".join(str(item["statement"]).split())))
        if target is not None:
            if target["citation"] is None:
                target["citation"] = _citation(ob)
                linked += 1
            continue
        statement, category = _clean(item)
        if not statement or _squash(statement) in seen or added >= MAX_FROM_OBLIGATIONS:
            continue
        seen.add(_squash(statement))
        _add(out, statement, category, "regulation", citation=_citation(ob))
        index[out[-1]["id"]] = out[-1]
        added += 1
    return out, {"linked": linked, "added": added}


def _basis_counts(requirements: list[dict]) -> dict:
    return {b: sum(r["basis"] == b for r in requirements) for b in ("stated", "regulation", "inferred")}


def identify(state: RunState, backend: Backend) -> RunState:
    """First pass: the requirements the description states or implies."""
    started = time.time()
    items, parsed = _items(backend.complete(system_prompt(), user_prompt(state.description)))
    state.requirements = normalise(items, state.description)
    state.record("requirements", bool(state.requirements), started, parsed=parsed,
                 count=len(state.requirements), **_basis_counts(state.requirements))
    return state


def restatement_finder(requirements: list[dict], threshold: float = RESTATEMENT_SIMILARITY):
    """`restates(statement)` for merge_regulatory: the id of the stated requirement whose embedding
    (the retriever's bge-small model) is at least `threshold` similar, else None."""
    stated = [r for r in requirements if r["basis"] == "stated"]
    if not stated:
        return None
    from compliance.retrieve import _embedder
    embed = _embedder()
    vectors = embed.encode([r["statement"] for r in stated], normalize_embeddings=True)

    def restates(statement: str):
        sims = vectors @ embed.encode([statement], normalize_embeddings=True)[0]
        best = int(sims.argmax())
        return stated[best]["id"] if sims[best] >= threshold else None
    return restates


def regulate(state: RunState, backend: Backend, restates=None) -> RunState:
    """Second pass (RAG): map the retrieved obligations onto the requirements."""
    started = time.time()
    state.clauses = retrieve_clauses(state)
    obligations = ((state.compliance or {}).get("obligations") or []) + clause_sources(state.clauses)
    if not obligations:
        state.record("regulate", True, started, obligations_offered=0)
        return state
    system, user = regulate_prompts(state.description, state.requirements, obligations)
    items, parsed = _items(backend.complete(system, user))
    if restates is None and any(i.get("statement") for i in items):
        restates = restatement_finder(state.requirements)
    state.requirements, counts = merge_regulatory(state.requirements, items, obligations, restates)
    state.record("regulate", parsed, started, parsed=parsed, obligations_offered=len(obligations), **counts,
                 clauses=[c["id"] for c in state.clauses],
                 standards=sorted({o["standard"] for o in obligations}))
    return state


MAX_QUESTIONS = 4

_ASK = """You review the software requirements of a project before they are agreed with stakeholders.
Find up to {n} requirements that are vague, have no measurable target, or depend on a decision the
description does not make. For each, write one question a stakeholder can answer by picking an option,
with 3 or 4 short, concrete, mutually exclusive options that cover the realistic choices for this project.
Do not ask about anything the description already answers.

Answer with one JSON object and nothing else:
{{"questions": [{{"requirements": ["<requirement id>"], "question": "...", "options": ["...", "...", "..."]}}]}}"""


def parse_questions(raw: str, requirement_ids, limit: int = MAX_QUESTIONS) -> list[dict]:
    """Validated multiple-choice questions: 2-5 distinct options, known requirement ids only."""
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        items = json.loads(text[start:end + 1]).get("questions") if 0 <= start < end else None
    except (json.JSONDecodeError, AttributeError):
        items = None
    known, out, seen = set(requirement_ids), [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        question = " ".join(str(item.get("question") or "").split())
        options = []
        for o in item.get("options") or []:
            o = " ".join(str(o).split())
            if o and o.lower() not in {x.lower() for x in options}:
                options.append(o)
        if not question or _squash(question) in seen or not 2 <= len(options) <= 5:
            continue
        seen.add(_squash(question))
        refs = [r for r in (item.get("requirements") or []) if isinstance(r, str) and r in known]
        out.append({"id": f"Q{len(out) + 1}", "question": question, "options": options, "requirements": refs})
        if len(out) >= limit:
            break
    return out


def ask(state: RunState, backend: Backend, limit: int = MAX_QUESTIONS) -> RunState:
    """Multiple-choice questions for requirements that are not clear enough to agree on."""
    started = time.time()
    if not state.requirements:
        state.record("ask_requirements", True, started, asked=0)
        return state
    listing = "\n".join(f"- {r['id']}: {r['statement']}" for r in state.requirements)
    user = f"{user_prompt(state.description)}\n\nRequirements:\n{listing}"
    raw = backend.complete(_ASK.format(n=limit), user)
    state.requirement_questions = parse_questions(raw, [r["id"] for r in state.requirements], limit)
    state.record("ask_requirements", True, started, asked=len(state.requirement_questions))
    return state


def answers_text(questions: list[dict], chosen: dict[str, str]) -> str:
    """Stakeholder answers as text to add to the description, e.g. for a re-run."""
    lines = [f"{q['question']} {chosen[q['id']]}." for q in questions if chosen.get(q["id"])]
    return "Clarifications: " + " ".join(lines) if lines else ""


_HINTS = ("\n\nRequirements already identified in this description, each with the part of the text it "
          "comes from. Use them to find where the description says something about the characteristics "
          "above; the evidence you give must still be copied from the description itself.\n{rows}")


def candidates(state: RunState) -> dict[str, list[str]]:
    """{unstated factor: [ids of stated requirements whose category bears on it]}."""
    unstated = {f for f, v in state.factors.items() if v["level"] == "not_stated"}
    out: dict[str, list[str]] = {}
    for r in state.requirements:
        if r["basis"] != "stated":
            continue
        for f in FACTORS_BY_CATEGORY.get(r["category"], ()):
            if f in unstated:
                out.setdefault(f, []).append(r["id"])
    return out


def reconcile(state: RunState, backend: Backend, onto: dict | None = None, strict: bool = False) -> RunState:
    """Re-check unstated factors that stated requirements bear on. The extractor's own ratings
    are never changed."""
    started = time.time()
    targets = candidates(state)
    if not targets:
        state.record("reconcile", True, started, candidates={})
        return state
    used = {i for ids in targets.values() for i in ids}
    rows = "\n".join(f'- {r["id"]} {r["statement"]} (text: "{r["source"]}")'
                     for r in state.requirements if r["id"] in used)
    ok, accepted, ungrounded = nodes.recheck(state, backend, list(targets), onto, strict,
                                             _HINTS.format(rows=rows), source="requirements")
    for f in accepted:
        state.factors[f]["requirements"] = targets[f]
    state.record("reconcile", ok, started, strict=strict, candidates=targets, accepted=accepted,
                 rejected_ungrounded=ungrounded)
    return state
