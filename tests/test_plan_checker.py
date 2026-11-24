"""Plan checker: a plan built to the requirements scores perfectly; each defect lowers its metric."""
import copy

from core.config import load_factor_ontology
from core.plan_spec import plan_requirements
from eval.plan_checker import aggregate, canonical_phase, check_plan, named_terms, schema_errors

NAMES = list(load_factor_ontology()["factors"])
DESC = "Kestrel Health runs a dispensing service in Leeds. The ward pharmacists use the old PharmaTrack system."


def _req(primary="V-Model", **levels):
    factors = {f: levels.get(f, "medium") for f in NAMES}
    return plan_requirements(factors, {"primary": primary, "hybrid": levels.get("hybrid", [])})


def _good_plan(req: dict) -> dict:
    keywords = " ".join(k for m in req["mandatory"] for k in m["keywords"])
    phases = []
    for i, name in enumerate(req["phases"]):
        phases.append({
            "name": name, "objective": f"Deliver {name} for Kestrel Health and PharmaTrack in Leeds",
            "activities": [keywords if i == 0 else "work"], "roles": ["QA Engineer", "Software Architect"],
            "deliverables": [f"artefact{i}"], "security_activities": [], "testing": [], "compliance_checkpoints": [],
            "approval_gate": {"approver": "Project Manager + Compliance Officer", "criteria": "criteria met"},
            "entry_criteria": [f"artefact{i - 1} accepted"] if i else ["kickoff held"],
            "exit_criteria": [f"artefact{i} accepted"]})
    return {"lifecycle": req["lifecycle"], "phases": phases}


def test_plan_built_to_requirements_scores_perfectly():
    req = _req(security_risk="high", legacy_dependence="high")
    rep = check_plan(_good_plan(req), req, DESC)
    assert rep["schema_valid"] and rep["schema_errors"] == []
    for metric in ("lifecycle_conformance", "pairings_present", "mandatory_recall", "gate_completeness",
                   "role_validity", "flow_coherence", "entity_recall"):
        assert rep[metric] == 1.0, metric
    assert rep["missing_phases"] == [] and rep["missing_elements"] == []


def test_each_defect_lowers_its_metric():
    req = _req(security_risk="high", continuous_delivery_need="low")
    plan = _good_plan(req)
    bad = copy.deepcopy(plan)
    bad["phases"][0]["activities"] = ["automated deployment with rollback"]     # drop all keywords, add discouraged
    bad["phases"] = bad["phases"][:-1]                                          # drop Acceptance Testing
    bad["phases"][1]["roles"] = ["Wizard"]
    bad["phases"][2]["approval_gate"] = {"approver": "Someone", "criteria": ""}
    bad["phases"][3]["entry_criteria"] = ["unrelated condition"]
    rep = check_plan(bad, req, DESC)
    assert rep["mandatory_recall"] < 0.5 and "threat_modelling" in rep["missing_elements"]
    assert rep["overgeneration_rate"] > 0 and "automated_deployment" in rep["overgenerated_elements"]
    assert rep["missing_phases"] == ["Acceptance Testing"] and rep["pairings_present"] == 0.75
    assert rep["lifecycle_conformance"] < 1 and rep["gate_completeness"] < 1
    assert "Wizard" in rep["invalid_roles"] and rep["role_validity"] < 1
    assert rep["flow_coherence"] < 1


def test_aliases_schema_errors_and_entities():
    req = _req("Waterfall")
    assert canonical_phase("Requirements Analysis", req) == "Requirements"
    assert canonical_phase("Go-live", req) == "Deployment"
    assert canonical_phase("Party", req) is None
    assert schema_errors({"phases": []})
    assert any("approval_gate" in e for e in schema_errors({"phases": [{"name": "x", "objective": "y"}]}))
    assert check_plan({"lifecycle": "x"}, req)["schema_valid"] is False
    assert {"kestrel", "health", "leeds", "pharmatrack"} <= named_terms(DESC)
    assert "the" not in named_terms(DESC)


def test_keywords_match_across_hyphens_and_spaces():
    req = _req(failure_consequence="high")
    plan = _good_plan(req)
    for p in plan["phases"]:
        p["activities"] = [a.replace("hazard", "").replace("failure mode", "").replace("fmea", "") for a in p["activities"]]
    plan["phases"][0]["activities"].append("Failure-mode analysis of wrong outputs")
    assert "hazard_analysis" not in check_plan(plan, req)["missing_elements"]


def test_role_names_with_ampersand_are_not_split():
    req = _req()
    plan = _good_plan(req)
    plan["phases"][0]["roles"] = ["Independent V&V Engineer"]
    plan["phases"][0]["approval_gate"]["approver"] = "Independent V&V Engineer + Compliance Officer"
    plan["phases"][1]["approval_gate"]["approver"] = "Test Lead & Project Manager"
    rep = check_plan(plan, req)
    assert rep["invalid_roles"] == [] and rep["role_validity"] == 1.0 and rep["gate_completeness"] == 1.0


def test_aggregate_ignores_missing_values():
    req = _req()
    reports = [check_plan(_good_plan(req), req), check_plan(_good_plan(req), req, DESC)]
    agg = aggregate(reports)
    assert agg["n"] == 2 and agg["schema_valid_rate"] == 1.0 and agg["entity_recall"] == 1.0


def test_malformed_model_output_does_not_crash_the_checker():
    req = _req()
    plan = {"lifecycle": "V-Model", "phases": [
        {"name": ["User", "Requirements"], "objective": 3, "activities": "not a list", "roles": [None, "Developer"],
         "deliverables": None, "security_activities": [], "testing": [], "compliance_checkpoints": [],
         "approval_gate": {"approver": ["QA Engineer", "Test Lead"], "criteria": ["met"]},
         "entry_criteria": ["start"], "exit_criteria": ["done"]},
        {"name": "Implementation", "objective": "o", "activities": ["a"], "roles": ["Developer"],
         "deliverables": ["d"], "security_activities": [], "testing": [], "compliance_checkpoints": [],
         "approval_gate": "not an object", "entry_criteria": ["done"], "exit_criteria": ["built"]}]}
    rep = check_plan(plan, req, DESC)
    assert rep["schema_valid"] is False and rep["schema_errors"]
    assert 0.0 <= rep["mandatory_recall"] <= 1.0 and 0.0 <= rep["gate_completeness"] <= 1.0
    plan["phases"][0]["exit_criteria"] = "done, as a string"
    plan["phases"][1]["entry_criteria"] = "done"
    assert check_plan(plan, req, DESC)["flow_coherence"] == 1.0


def test_absent_optional_lists_are_treated_as_empty():
    req = _req()
    plan = _good_plan(req)
    for phase in plan["phases"]:
        for field in ("security_activities", "testing", "compliance_checkpoints"):
            phase.pop(field)
    rep = check_plan(plan, req, DESC)
    assert rep["schema_valid"] and rep["schema_errors"] == []
    assert rep["mandatory_recall"] == 1.0

    plan["phases"][0].pop("deliverables")            # a required list is still required
    assert any("deliverables" in e for e in check_plan(plan, req, DESC)["schema_errors"])


def test_role_names_are_not_practices_but_the_compliance_approver_is():
    req = _req(verification_rigor="high", regulatory_criticality="high", scope_rigidity="high")
    plan = _good_plan(req)
    for phase in plan["phases"]:
        phase["activities"] = ["work"]
        phase["roles"] = ["Independent V&V Engineer", "Change Control Board"]
        phase["approval_gate"] = {"approver": "Compliance Officer + Change Control Board", "criteria": "met"}
    missing = set(check_plan(plan, req, DESC)["missing_elements"])
    assert {"independent_vv", "change_control"} <= missing
    assert "compliance_approval" not in missing

    plan["phases"][0]["activities"] = ["All rules independently tested", "Change requests logged"]
    missing = set(check_plan(plan, req, DESC)["missing_elements"])
    assert "independent_vv" not in missing and "change_control" not in missing


def test_a_bare_baseline_is_not_change_control():
    req = _req(scope_rigidity="high")
    plan = _good_plan(req)
    plan["phases"][0]["activities"] = ["Baseline the requirements"]
    assert "change_control" in check_plan(plan, req, DESC)["missing_elements"]
