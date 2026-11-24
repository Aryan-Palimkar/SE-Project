"""Agent layer tests with scripted backends (no model loaded)."""
import json
import random

from agents import nodes
from agents.orchestrator import Pipeline
from agents.questions import decision_relevant
from agents.runtime import AdapterSpec, ModelHub
from agents.state import RunState
from core.backends import MockBackend
from core.config import load_factor_ontology
from core.plan_spec import load_plan_ontology, load_roles, plan_requirements
from test_train_tasks import ONTO, make_record
from train.tasks import rubric_recommendation, target

NAMES = list(ONTO["factors"])


def _extract_answer(record):
    return json.dumps({"factors": {f: {"level": record["factors"][f]["level"],
                                       "evidence": record["factors"][f]["evidence"]} for f in NAMES}})


def _plan_for(state, drop_element=True):
    """A plan built from the requirements, optionally missing one mandatory element."""
    req = plan_requirements(state.factors, state.recommendation, load_plan_ontology(), load_roles())
    dropped = req["mandatory"][0]["id"] if drop_element and req["mandatory"] else None
    keywords = [k for m in req["mandatory"] if m["id"] != dropped for k in m["keywords"]]
    phases = []
    for i, name in enumerate(req["phases"]):
        phases.append({"name": name, "objective": "o", "activities": [" ".join(keywords)] if i == 0 else ["work"],
                       "roles": ["Developer"], "deliverables": [f"artefact{i}"], "security_activities": [],
                       "testing": [], "compliance_checkpoints": [],
                       "approval_gate": {"approver": "Project Manager", "criteria": "met"},
                       "entry_criteria": [f"artefact{i - 1} accepted"] if i else ["kickoff"],
                       "exit_criteria": [f"artefact{i} accepted"]})
    return json.dumps({"justification": "Because.", "plan": {"lifecycle": req["lifecycle"], "phases": phases}})


def _repair_payload(state, with_keywords=True):
    """A repair answer containing only one phase; the other phases must survive the merge."""
    req = plan_requirements(state.factors, state.recommendation, load_plan_ontology(), load_roles())
    keywords = [k for m in req["mandatory"] for k in m["keywords"]] if with_keywords else []
    first = dict(state.plan["phases"][0], activities=[" ".join(keywords)] if keywords else ["work"])
    return json.dumps({"justification": "Corrected.", "plan": {"lifecycle": state.plan["lifecycle"],
                                                               "phases": [first]}})


def test_runtime_loads_nothing_until_used():
    hub = ModelHub("nonexistent/model", {"extract": AdapterSpec("extract", "/no/such/path")})
    assert hub.loaded is False
    backend = hub.backend("extract")
    assert hub.loaded is False and "extract" in backend.name


def test_only_decision_relevant_factors_are_asked_about():
    record = make_record(1, random.Random(1))
    levels = {f: v["level"] for f, v in record["factors"].items()}
    unstated = [f for f, lvl in levels.items() if lvl == "not_stated"]
    relevant = decision_relevant(levels)
    assert {r["factor"] for r in relevant} <= set(unstated)
    for r in relevant:
        primaries = {rubric_recommendation({**levels, r["factor"]: t})["primary"] for t in ("low", "medium", "high")}
        assert len(primaries | {rubric_recommendation(levels)["primary"]}) > 1


def test_answers_become_levels_with_the_stakeholder_as_evidence():
    record = make_record(2, random.Random(2))
    state = RunState(description=record["description"], factors={f: {"level": "not_stated", "evidence": None}
                                                                 for f in NAMES})
    state.answers = {NAMES[0]: "we ship every week", NAMES[1]: "no idea really"}
    replies = iter(["high", "who knows"])
    nodes.apply_answers(state, MockBackend(lambda s, u: next(replies)), ONTO)
    assert state.factors[NAMES[0]]["level"] == "high"
    assert "stakeholder:" in state.factors[NAMES[0]]["evidence"]
    assert state.factors[NAMES[1]]["level"] == "not_stated"      # unusable answer changes nothing


def test_repair_loop_fixes_a_missing_element_and_is_bounded():
    record = make_record(3, random.Random(3))
    state = RunState(description=record["description"], id=record["id"])
    nodes.extract(state, MockBackend(lambda s, u: _extract_answer(record)), ONTO)
    nodes.recommend(state)
    nodes.plan(state, MockBackend(lambda s, u: _plan_for(state, drop_element=True)), ONTO)
    nodes.check(state)
    before = state.report["mandatory_recall"]
    assert before < 1.0 and state.report["missing_elements"]
    untouched = [dict(p) for p in state.plan["phases"][1:]]
    nodes.repair(state, MockBackend(lambda s, u: _repair_payload(state, with_keywords=True)), ONTO, max_passes=2, scope="all")
    assert state.report["mandatory_recall"] == 1.0 > before
    assert state.report["missing_elements"] == [] and 1 <= state.repairs <= 2
    assert state.plan["phases"][1:] == untouched                   # a splice cannot lose other phases


def test_repair_stops_when_the_model_returns_garbage():
    record = make_record(4, random.Random(4))
    state = RunState(description=record["description"])
    nodes.extract(state, MockBackend(lambda s, u: _extract_answer(record)), ONTO)
    nodes.recommend(state)
    nodes.plan(state, MockBackend(lambda s, u: _plan_for(state, drop_element=True)), ONTO)
    nodes.check(state)
    nodes.repair(state, MockBackend(lambda s, u: "sorry, no"), ONTO, max_passes=2, scope="all")
    assert state.repairs == 1
    assert any(step.node == "repair" and not step.ok for step in state.log)


def test_pipeline_runs_end_to_end_and_never_changes_the_ranking():
    record = make_record(5, random.Random(5))
    state = RunState(description=record["description"], id=record["id"])

    def planner(system, user):
        return _plan_for(state, drop_element=False)

    pipe = Pipeline(extractor=MockBackend(lambda s, u: _extract_answer(record)),
                    planner=MockBackend(planner), assistant=MockBackend(lambda s, u: "high"), max_repairs=1)
    pipe.run(state)
    # the rubric, not any agent, decides the ranking
    rubric = rubric_recommendation(state.levels())
    assert {k: state.recommendation[k] for k in rubric} == rubric
    assert state.plan["lifecycle"] == state.recommendation["primary"]
    assert [s.node for s in state.log][:5] == ["comply", "extract", "clarify", "rubric", "plan"]
    assert "Recommended lifecycle:" in state.summary
    assert json.loads(json.dumps(state.to_dict()))["id"] == record["id"]


def test_extract_survives_an_unparseable_model_reply():
    state = RunState(description="A project.")
    nodes.extract(state, MockBackend(lambda s, u: "I refuse."), ONTO)
    assert set(state.factors) == set(NAMES)
    assert all(v["level"] == "not_stated" for v in state.factors.values())
    assert state.log[-1].ok is False
    nodes.recommend(state)
    assert state.insufficient_evidence and state.recommendation["stated"] == 0
    assert state.recommendation["primary"] in load_factor_ontology() or state.recommendation["primary"]


def test_a_repair_that_makes_the_plan_worse_is_rejected():
    record = make_record(6, random.Random(6))
    state = RunState(description=record["description"])
    nodes.extract(state, MockBackend(lambda s, u: _extract_answer(record)), ONTO)
    nodes.recommend(state)
    nodes.plan(state, MockBackend(lambda s, u: _plan_for(state, drop_element=True)), ONTO)
    nodes.check(state)
    kept_plan, kept_recall = state.plan, state.report["mandatory_recall"]
    nodes.repair(state, MockBackend(lambda s, u: _repair_payload(state, with_keywords=False)), ONTO, max_passes=2, scope="all")
    assert state.report["mandatory_recall"] == kept_recall      # original kept
    assert state.plan == kept_plan
    assert state.repairs == 1
    rejected = [s for s in state.log if s.node == "repair" and not s.ok]
    assert rejected and "no better" in rejected[-1].detail["reason"]


def test_summary_does_not_claim_a_rejected_repair_as_a_repair():
    record = make_record(7, random.Random(7))
    state = RunState(description=record["description"])
    nodes.extract(state, MockBackend(lambda s, u: _extract_answer(record)), ONTO)
    nodes.recommend(state)
    nodes.plan(state, MockBackend(lambda s, u: _plan_for(state, drop_element=True)), ONTO)
    nodes.check(state)
    nodes.repair(state, MockBackend(lambda s, u: _repair_payload(state, with_keywords=False)), ONTO, max_passes=1, scope="all")
    nodes.explain(state)
    assert "rejected" in state.summary and "repaired" not in state.summary


def test_splice_replaces_by_name_inserts_missing_phases_and_ignores_junk():
    record = make_record(8, random.Random(8))
    state = RunState(description=record["description"])
    nodes.extract(state, MockBackend(lambda s, u: _extract_answer(record)), ONTO)
    nodes.recommend(state)
    req = plan_requirements(state.factors, state.recommendation, load_plan_ontology(), load_roles())
    full = json.loads(_plan_for(state, drop_element=False))["plan"]
    dropped_name = req["phases"][1]
    partial = {"lifecycle": full["lifecycle"], "phases": [p for p in full["phases"] if p["name"] != dropped_name]}

    spliced = nodes.splice_phases(partial, [
        {"name": dropped_name, "objective": "restored", "activities": ["a"], "roles": ["Developer"],
         "deliverables": ["d"], "security_activities": [], "testing": [], "compliance_checkpoints": [],
         "approval_gate": {"approver": "Project Manager", "criteria": "c"},
         "entry_criteria": ["e"], "exit_criteria": ["x"]},
        {"name": req["phases"][0], "objective": "replaced", "activities": ["a"], "roles": ["Developer"],
         "deliverables": ["d"], "security_activities": [], "testing": [], "compliance_checkpoints": [],
         "approval_gate": {"approver": "Project Manager", "criteria": "c"},
         "entry_criteria": ["e"], "exit_criteria": ["x"]},
        {"no_name": "junk"}, "not even an object"], req)

    names = [p["name"] for p in spliced["phases"]]
    assert names == [p["name"] for p in full["phases"]]          # missing phase restored, in order
    assert spliced["phases"][0]["objective"] == "replaced"       # same-name phase replaced, not duplicated
    assert spliced["phases"][1]["objective"] == "restored"
    assert len(spliced["phases"]) == len(full["phases"])         # junk ignored


def test_default_scope_only_repairs_unusable_plans():
    record = make_record(9, random.Random(9))
    state = RunState(description=record["description"])
    nodes.extract(state, MockBackend(lambda s, u: _extract_answer(record)), ONTO)
    nodes.recommend(state)
    nodes.plan(state, MockBackend(lambda s, u: _plan_for(state, drop_element=True)), ONTO)
    nodes.check(state)
    assert state.report["schema_valid"] and state.report["missing_elements"]

    called = []

    def planner(system, user):
        called.append(user)
        return _repair_payload(state, with_keywords=True)

    nodes.repair(state, MockBackend(planner), ONTO, max_passes=2)          # default scope
    assert called == [] and state.repairs == 0
    assert any(s.node == "repair" and s.detail.get("skipped") for s in state.log)

    nodes.repair(state, MockBackend(planner), ONTO, max_passes=2, scope="all")
    assert called and state.report["mandatory_recall"] == 1.0


def test_default_scope_still_repairs_a_plan_that_will_not_parse():
    record = make_record(10, random.Random(10))
    state = RunState(description=record["description"])
    nodes.extract(state, MockBackend(lambda s, u: _extract_answer(record)), ONTO)
    nodes.recommend(state)
    nodes.plan(state, MockBackend(lambda s, u: "not json at all"), ONTO)
    nodes.check(state)
    assert state.report["schema_valid"] is False

    nodes.repair(state, MockBackend(lambda s, u: _plan_for(state, drop_element=False)), ONTO, max_passes=1)
    assert state.repairs == 1 and state.report["schema_valid"] is True


def test_zero_shot_planner_uses_the_base_model_unconstrained():
    from agents.orchestrator import local_pipeline

    _, hub = local_pipeline("some/model", "runs/x/adapter", None, constrained_extract=False)
    plan, extract = hub.adapters["plan"], hub.adapters["extract"]
    assert plan.path is None and plan.task is None and plan.max_new_tokens >= 4096
    assert extract.path == "runs/x/adapter" and extract.task is None
    assert not hub.loaded

    _, hub = local_pipeline("some/model", "runs/x/adapter", "runs/p/adapter")
    assert hub.adapters["plan"].task == "plan" and hub.adapters["extract"].task == "extract"


def _levels_record(n_stated):
    """A record whose first `n_stated` factors are stated and the rest not."""
    record = make_record(5, random.Random(5))
    for i, f in enumerate(NAMES):
        if i >= n_stated:
            record["factors"][f] = {"level": "not_stated", "evidence": None}
        elif record["factors"][f]["level"] == "not_stated":
            record["factors"][f] = {"level": "high", "evidence": record["description"][:20]}
    return record


def test_no_evidence_means_no_recommendation_and_no_plan():
    record = _levels_record(0)
    state = RunState(description=record["description"])
    planned = []
    pipe = Pipeline(extractor=MockBackend(lambda s, u: _extract_answer(record)),
                    planner=MockBackend(lambda s, u: planned.append(1) or "{}"),
                    assistant=MockBackend(lambda s, u: "high"), max_repairs=1)
    pipe.run(state)
    assert state.insufficient_evidence and not planned and state.plan is None
    assert state.summary.startswith("NO RECOMMENDATION") and "Recommended lifecycle" not in state.summary
    assert state.questions
    assert [s.node for s in state.log][-3:] == ["rubric", "assess", "explain"]


def test_answers_can_lift_a_run_over_the_evidence_floor():
    record = _levels_record(2)
    state = RunState(description=record["description"])
    pipe = Pipeline(extractor=MockBackend(lambda s, u: _extract_answer(record)),
                    planner=MockBackend(lambda s, u: _plan_for(state, drop_element=False)),
                    assistant=MockBackend(lambda s, u: "high"), max_repairs=0)
    unstated = [f for f in NAMES if record["factors"][f]["level"] == "not_stated"]
    pipe.run(state, answers={unstated[0]: "yes, very much so"})
    assert not state.insufficient_evidence and state.plan is not None


def test_sparse_but_sufficient_evidence_is_labelled_provisional():
    record = _levels_record(4)
    state = RunState(description=record["description"])
    pipe = Pipeline(extractor=MockBackend(lambda s, u: _extract_answer(record)),
                    planner=MockBackend(lambda s, u: _plan_for(state, drop_element=False)),
                    assistant=MockBackend(lambda s, u: "high"), max_repairs=0)
    pipe.run(state)
    assert state.recommendation["low_evidence"] and not state.insufficient_evidence
    assert "PROVISIONAL" in state.summary.splitlines()[0] and state.plan is not None

    full = RunState(description=record["description"])
    rich = _levels_record(len(NAMES))
    Pipeline(extractor=MockBackend(lambda s, u: _extract_answer(rich)),
             planner=MockBackend(lambda s, u: _plan_for(full, drop_element=False)),
             assistant=MockBackend(lambda s, u: "high"), max_repairs=0).run(full)
    assert not full.recommendation["low_evidence"] and "PROVISIONAL" not in full.summary


def test_challenger_keeps_only_grounded_proposals_for_unstated_factors():
    description = ("The payroll engine must be certified under the national payroll statute. "
                   "It replaces a COBOL batch system that still feeds the ledger.")
    state = RunState(description=description)
    state.factors = {f: {"level": "not_stated", "evidence": None} for f in NAMES}
    state.factors["size"] = {"level": "low", "evidence": "team of four"}        # the extractor's own rating
    reply = json.dumps({
        "regulatory_criticality": {"level": "high", "evidence": "certified under the national payroll statute"},
        "legacy_dependence": {"level": "high", "evidence": "replaces a cobol batch  system"},   # case/space drift
        "security_risk": {"level": "high", "evidence": "handles card payments"},               # not in the text
        "complexity": {"level": "medium", "evidence": "ledger"},                               # too short
        "size": {"level": "high", "evidence": "It replaces a COBOL batch system"},             # was not asked
        "change_frequency": {"level": "not_stated", "evidence": None}})
    asked = []
    nodes.challenge(state, MockBackend(lambda s, u: asked.append(s) or reply), ONTO)
    assert state.factors["regulatory_criticality"]["level"] == "high"
    assert state.factors["regulatory_criticality"]["source"] == "challenger"
    assert state.factors["legacy_dependence"]["level"] == "high"
    assert state.factors["security_risk"]["level"] == "not_stated"
    assert state.factors["complexity"]["level"] == "not_stated"
    assert state.factors["size"] == {"level": "low", "evidence": "team of four"}
    assert "- size:" not in asked[0]                                  # only unstated factors are re-checked
    detail = state.log[-1].detail
    assert set(detail["accepted"]) == {"regulatory_criticality", "legacy_dependence"}
    assert "security_risk" in detail["rejected_ungrounded"]


def test_challenger_survives_garbage_and_skips_when_nothing_is_unstated():
    state = RunState(description="A project.")
    state.factors = {f: {"level": "not_stated", "evidence": None} for f in NAMES}
    nodes.challenge(state, MockBackend(lambda s, u: "no idea"), ONTO)
    assert all(v["level"] == "not_stated" for v in state.factors.values()) and state.log[-1].ok is False
    full = RunState(description="A project.")
    full.factors = {f: {"level": "low", "evidence": "x"} for f in NAMES}
    called = []
    nodes.challenge(full, MockBackend(lambda s, u: called.append(1) or "{}"), ONTO)
    assert not called and full.log[-1].detail["unstated"] == 0


def test_unsupported_primary_is_not_presented_as_a_recommendation():
    record = _levels_record(len(NAMES))
    stated = {"technical_novelty": "low", "legacy_dependence": "high", "complexity": "medium",
              "requirement_stability": "medium", "size": "medium"}
    for f in NAMES:
        record["factors"][f] = ({"level": stated[f], "evidence": record["description"][:20]} if f in stated
                                else {"level": "not_stated", "evidence": None})
    state = RunState(description=record["description"])
    Pipeline(extractor=MockBackend(lambda s, u: _extract_answer(record)),
             planner=MockBackend(lambda s, u: _plan_for(state, drop_element=False)),
             assistant=MockBackend(lambda s, u: "high"), max_repairs=0).run(state)
    rec, first = state.recommendation, state.summary.splitlines()[0]
    assert rec["primary"] == "Waterfall" and rec["primary_withheld"]
    assert "PRECONDITION_UNMET" in rec["withheld_reasons"]
    assert first.startswith("NO SINGLE LIFECYCLE") and "Recommended lifecycle" not in state.summary
    assert "What would decide it:" in state.summary and "scope rigidity high" in state.summary


def test_a_saved_run_loads_back(tmp_path):
    state = RunState(description="d", id="x", requirements=[{"id": "FR-01"}])
    state.record("extract", True, 0.0, stated=2)
    loaded = RunState.load(state.save(tmp_path / "run.json"))
    assert loaded.to_dict() == state.to_dict() and loaded.log[0].node == "extract"
