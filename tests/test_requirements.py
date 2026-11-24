"""Requirements agent with scripted backends (no model loaded)."""
import json
import random

from agents import requirements
from agents.orchestrator import Pipeline
from agents.state import RunState
from core.backends import MockBackend
from test_agents import _extract_answer, _plan_for
from test_train_tasks import make_record

DESCRIPTION = ("A retail bank is building a mobile onboarding flow. New customers upload a photo of their "
               "passport and take a selfie, and the bank must verify identity before opening the account. "
               "Account data is synchronised with the core banking system every night.")
OBLIGATIONS = [{"id": "gdpr-5", "standard": "gdpr", "standard_name": "GDPR", "ref": "Art. 5",
                "phase": "design", "description": "Collect only the personal data that is needed.",
                "keywords": ["data minimisation"]},
               {"id": "fatf-10", "standard": "fatf", "standard_name": "FATF", "ref": "R.10",
                "phase": "design", "description": "Verify identity from reliable, independent sources.",
                "keywords": ["verify identity"]}]
ROWS = [
    {"statement": "The system shall verify identity before opening an account.", "category": "security",
     "source": "must verify identity before opening the account"},
    {"statement": "The system shall sync with core banking nightly.", "category": "integration",
     "source": "synchronised with the core banking system every night"},
    {"statement": "The system shall answer within one second.", "category": "performance", "source": None},
]


def _answer(items):
    return json.dumps({"requirements": items})


def test_first_pass_prompt_lists_every_category_and_no_obligations():
    system = requirements.system_prompt()
    assert all(f"  {c}:" in system for c in requirements.CATEGORIES)
    assert '"obligation"' not in system and "compliance knowledge base" not in system


def test_basis_ids_and_types_are_decided_in_code():
    items = [
        {"statement": "The system shall let customers upload a passport photo.", "category": "functional",
         "source": "upload a photo of their passport"},
        *ROWS,
        {"statement": "The system shall take a selfie.", "category": "made-up", "source": "take a selfie"},
    ]
    out = requirements.normalise(items, DESCRIPTION)
    assert [r["id"] for r in out] == ["FR-01", "NFR-SEC-01", "NFR-INT-01", "NFR-PERF-01", "FR-02"]
    assert [r["basis"] for r in out] == ["stated", "stated", "stated", "inferred", "stated"]
    assert out[3]["source"] is None and out[4]["category"] == "functional"
    assert [r["type"] for r in out][:2] == ["functional", "non-functional"]
    assert all(r["citation"] is None for r in out)


def test_duplicates_and_short_quotes_are_not_trusted():
    items = [{"statement": "The system shall open accounts.", "category": "functional", "source": "bank"},
             {"statement": "the system  shall open accounts.", "category": "functional", "source": None}]
    out = requirements.normalise(items, DESCRIPTION)
    assert len(out) == 1 and out[0]["basis"] == "inferred"


def test_a_lightly_paraphrased_quote_is_replaced_by_the_real_passage():
    text = "The society awarded a contract for a reporting system that extracts balances from the ledger every quarter."
    assert requirements.locate("the system extracts balances from the ledger every quarter", text) == \
        "system that extracts balances from the ledger every quarter"
    assert requirements.locate("EXTRACTS balances from the ledger", text) == "EXTRACTS balances from the ledger"
    assert requirements.locate("the system shows real-time dashboards to executives", text) is None
    assert requirements.locate("null", text) is None and requirements.locate(None, text) is None


def test_truncated_output_keeps_the_complete_items():
    raw = ('```json\n{"requirements": [{"statement": "The system shall A.", "category": "functional", '
           '"source": null}, {"obligation": "gdpr-5", "existing": "FR-01"}, {"statement": "The system shall B.", "categ')
    items, parsed = requirements._items(raw)
    assert not parsed and len(items) == 2 and items[1]["existing"] == "FR-01"


def test_rag_pass_links_existing_requirements_and_adds_cited_ones():
    base = requirements.normalise(ROWS, DESCRIPTION)
    items = [{"obligation": "fatf-10", "existing": "NFR-SEC-01"},
             {"obligation": "gdpr-5", "statement": "The system shall collect only necessary personal data.",
              "category": "privacy"},
             {"obligation": "no-such-id", "statement": "The system shall do something else.", "category": "audit"},
             {"obligation": "gdpr-5", "existing": "NFR-XXX-09"}]
    out, counts = requirements.merge_regulatory(base, items, OBLIGATIONS)
    assert counts == {"linked": 1, "added": 1}
    security = next(r for r in out if r["id"] == "NFR-SEC-01")
    assert security["basis"] == "stated" and security["citation"] == {"obligation": "fatf-10", "standard": "FATF",
                                                                      "ref": "R.10", "clause": None}
    added = out[-1]
    assert added["id"] == "NFR-PRI-01" and added["basis"] == "regulation" and added["source"] is None
    assert base[0]["citation"] is None                      # the first pass's list is not mutated


def test_a_restated_requirement_becomes_a_citation_not_a_duplicate():
    base = requirements.normalise(ROWS, DESCRIPTION)
    items = [{"obligation": "fatf-10", "statement": "The system shall verify each customer's identity.",
              "category": "security"},
             {"obligation": "gdpr-5", "statement": "The system shall collect only necessary data.",
              "category": "privacy"}]
    restates = lambda s: "NFR-SEC-01" if "identity" in s else None  # noqa: E731
    out, counts = requirements.merge_regulatory(base, items, OBLIGATIONS, restates)
    assert counts == {"linked": 1, "added": 1}
    assert next(r for r in out if r["id"] == "NFR-SEC-01")["citation"]["obligation"] == "fatf-10"
    assert [r["id"] for r in out if r["basis"] == "regulation"] == ["NFR-PRI-01"]


def test_rag_pass_is_capped():
    obligations = [dict(OBLIGATIONS[0], id=f"ob-{i}") for i in range(12)]
    items = [{"obligation": f"ob-{i}", "statement": f"The system shall meet obligation {i}.",
              "category": "regulatory"} for i in range(12)]
    out, counts = requirements.merge_regulatory([], items, obligations)
    assert counts["added"] == len(out) == requirements.MAX_FROM_OBLIGATIONS


def test_rag_pass_sees_the_first_pass_and_the_obligations():
    seen = []
    backend = MockBackend(lambda s, u: seen.append((s, u)) or _answer([]))
    state = RunState(description=DESCRIPTION, compliance={"obligations": OBLIGATIONS})
    state.requirements = requirements.normalise(ROWS, DESCRIPTION)
    requirements.regulate(state, backend)
    system, user = seen[0]
    assert "compliance analyst" in system and "NFR-SEC-01" in user and "fatf-10" in user
    requirements.regulate(RunState(description=DESCRIPTION), MockBackend(lambda s, u: 1 / 0))


def _pipeline(record, state, agent, **kw):
    return Pipeline(extractor=MockBackend(lambda s, u: _extract_answer(record)),
                    planner=MockBackend(lambda s, u: _plan_for(state, drop_element=False)),
                    assistant=MockBackend(lambda s, u: "high"), requirements_agent=agent, max_repairs=0, **kw)


def _agent(record):
    def answer(system, user):
        if "requirements analyst" in system:
            return _answer([{"statement": "The system shall do the thing.", "category": "functional",
                             "source": record["description"][:40]}])
        return _answer([]) if "compliance analyst" in system else "{}"
    return MockBackend(answer)


def test_pipeline_runs_retrieval_then_both_requirement_passes_before_extraction():
    record = make_record(5, random.Random(5))
    state = RunState(description=record["description"], id=record["id"])
    _pipeline(record, state, _agent(record)).run(state)
    nodes = [s.node for s in state.log]
    assert nodes[:2] == ["comply", "requirements"] and nodes.index("extract") > nodes.index("requirements")
    assert state.requirements[0]["basis"] == "stated"
    assert json.loads(json.dumps(state.to_dict()))["requirements"][0]["id"] == "FR-01"


def _state_with(requirement_rows, stated=None):
    state = RunState(description=DESCRIPTION)
    state.factors = {f: {"level": "not_stated", "evidence": None} for f in
                     ("security_risk", "legacy_dependence", "complexity", "regulatory_criticality",
                      "failure_consequence")}
    for f, level in (stated or {}).items():
        state.factors[f] = {"level": level, "evidence": "extractor quote"}
    state.requirements = requirements.normalise(requirement_rows, DESCRIPTION)
    return state


def test_only_stated_requirements_nominate_unstated_factors():
    state = _state_with(ROWS, stated={"complexity": "medium"})
    assert requirements.candidates(state) == {"security_risk": ["NFR-SEC-01"],
                                              "legacy_dependence": ["NFR-INT-01"]}


def test_reconcile_keeps_grounded_levels_and_never_overrides_the_extractor():
    state = _state_with(ROWS, stated={"complexity": "medium"})
    seen = []
    answer = {"security_risk": {"level": "high", "evidence": "must verify identity before opening the account"},
              "legacy_dependence": {"level": "high", "evidence": "a legacy mainframe"},
              "complexity": {"level": "high", "evidence": "synchronised with the core banking system every night"}}
    backend = MockBackend(lambda s, u: seen.append(u) or json.dumps(answer))
    requirements.reconcile(state, backend)
    assert state.factors["security_risk"] == {"level": "high", "source": "requirements",
                                              "evidence": "must verify identity before opening the account",
                                              "requirements": ["NFR-SEC-01"]}
    assert state.factors["legacy_dependence"]["level"] == "not_stated"      # quote not in the text
    assert state.factors["complexity"]["level"] == "medium"                 # extractor's rating kept
    assert "NFR-INT-01" in seen[0] and "NFR-PERF-01" not in seen[0]
    detail = state.log[-1].detail
    assert detail["accepted"] == {"security_risk": "high"} and detail["rejected_ungrounded"] == ["legacy_dependence"]


def test_reconcile_makes_no_call_when_nothing_is_nominated():
    state = _state_with(ROWS[2:])
    requirements.reconcile(state, MockBackend(lambda s, u: 1 / 0))
    assert state.log[-1].detail == {"candidates": {}}


def test_pipeline_reconciles_only_when_asked():
    record = make_record(5, random.Random(5))
    record["factors"]["complexity"] = {"level": "not_stated", "evidence": None}
    for reconcile in (False, True):
        state = RunState(description=record["description"], id=record["id"])
        _pipeline(record, state, _agent(record), reconcile=reconcile).run(state)
        assert ("reconcile" in [s.node for s in state.log]) is reconcile


def test_without_a_plan_the_run_stops_after_the_recommendation():
    record = make_record(5, random.Random(5))
    state = RunState(description=record["description"], id=record["id"])
    _pipeline(record, state, _agent(record), write_plan=False).run(state)
    nodes = [s.node for s in state.log]
    assert "rubric" in nodes and "plan" not in nodes and nodes[-1] == "explain"
    assert state.recommendation and state.plan is None and "Recommended lifecycle" in state.summary


def test_api_stages_replace_only_the_chosen_backends(monkeypatch):
    from agents.orchestrator import use_api
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    local = MockBackend(lambda s, u: "", name="local")
    pipe = Pipeline(extractor=local, planner=local, assistant=local, requirements_agent=local)
    use_api(pipe, "gemini-test", ["requirements", "plan"])
    assert pipe.requirements_agent.name == pipe.planner.name == "gemini-test"
    assert pipe.extractor is local and pipe.extract_definitions is False
    use_api(pipe, "gemini-test", ["extract"])
    assert pipe.extractor.name == "gemini-test" and pipe.extract_definitions is True


def test_multiple_choice_questions_are_validated():
    raw = _answer([]).replace('"requirements"', '"questions"')
    assert requirements.parse_questions(raw, ["FR-01"]) == []
    raw = json.dumps({"questions": [
        {"requirements": ["NFR-PERF-01", "XX-9"], "question": "How fast must a decision be returned?",
         "options": ["Under 2 seconds", "Under 10 seconds", "Under a minute", "under 2 seconds"]},
        {"requirements": [], "question": "Only one option?", "options": ["Yes"]},
        {"requirements": [], "question": "how fast must a decision be returned?", "options": ["A", "B"]}]})
    out = requirements.parse_questions(raw, ["NFR-PERF-01"])
    assert out == [{"id": "Q1", "question": "How fast must a decision be returned?",
                    "options": ["Under 2 seconds", "Under 10 seconds", "Under a minute"],
                    "requirements": ["NFR-PERF-01"]}]
    assert requirements.answers_text(out, {"Q1": "Under 10 seconds"}) == \
        "Clarifications: How fast must a decision be returned? Under 10 seconds."
    assert requirements.answers_text(out, {}) == ""


def test_retrieved_clauses_can_be_cited_with_their_text_and_page():
    clauses = [{"id": "dpdp_rules_2025#11", "source": "dpdp_rules_2025", "title": "DPDP Rules", "page": 26,
                "text": "On becoming aware of any personal data breach, the Data Fiduciary shall intimate the Board."}]
    sources = requirements.clause_sources(clauses)
    system, user = requirements.regulate_prompts(DESCRIPTION, [], sources)
    assert "P1 [DPDP Rules, p. 26]" in user and "Obligations from" not in user
    items = [{"obligation": "P1", "statement": "The system shall report personal data breaches to the Board.",
              "category": "regulatory"}]
    out, counts = requirements.merge_regulatory([], items, sources)
    assert counts["added"] == 1 and out[0]["citation"]["clause"]["page"] == 26
    assert out[0]["citation"]["obligation"] == "dpdp_rules_2025#11"


def test_srs_builds_tables_traceability_and_markdown():
    from agents import srs
    state = RunState(description=DESCRIPTION)
    state.requirements = requirements.normalise(ROWS, DESCRIPTION)
    state.requirement_questions = [{"id": "Q1", "question": "How fast?", "options": ["1s", "5s"], "requirements": []}]
    srs.write(state, MockBackend(lambda s, u: json.dumps({
        "title": "Onboarding App", "purpose": "Open accounts remotely.", "scope": "Mobile onboarding only.",
        "stakeholders": [{"role": "Customer", "interest": "Fast onboarding"}], "constraints": ["Data in India [P1]"]})))
    doc = state.srs
    assert doc["title"] == "Onboarding App" and [r["id"] for r in doc["non_functional"][0]["requirements"]]
    assert {t["id"]: t["verification"] for t in doc["traceability"]}["NFR-PERF-01"] == "Test (load)"
    md = srs.markdown(doc)
    assert md.startswith("# Onboarding App") and "| NFR-SEC-01 |" in md and "How fast?" in md
    srs.write(state, None)
    assert state.srs["purpose"].startswith("A retail bank")
