"""Plan ontology coverage and deterministic plan requirements."""
import pytest

from core.config import load_factor_ontology
from core.plan_spec import load_plan_ontology, load_roles, plan_requirements
from rubric.scorer import load_rubric

PLAN, ROLES, RUBRIC = load_plan_ontology(), load_roles(), load_rubric()
NAMES = list(load_factor_ontology()["factors"])


def _levels(**overrides):
    return {f: overrides.get(f, "medium") for f in NAMES}


def test_ontology_covers_every_model_overlay_and_factor():
    assert set(PLAN["lifecycles"]) == set(RUBRIC["models"])
    rubric_overlays = set(RUBRIC["overlay_names"].values()) | {RUBRIC["rules"]["C1_overlay"],
                                                               RUBRIC["rules"]["C2_overlay"]}
    assert set(PLAN["overlays"]) == rubric_overlays
    for overlay, ids in PLAN["overlays"].items():
        assert ids and all(i in PLAN["elements"] for i in ids), overlay
    for eid, el in PLAN["elements"].items():
        assert el["keywords"] and all(k == k.lower() for k in el["keywords"]), eid
        for cond in el.get("when", []) + el.get("discouraged_when", []):
            assert set(cond) <= set(NAMES), eid
    vmodel = {p["name"]: p for p in PLAN["lifecycles"]["V-Model"]["phases"]}
    assert all(p["pairs_with"] in vmodel for p in vmodel.values() if "pairs_with" in p)
    assert len({r.lower() for r in ROLES["roles"]}) == len(ROLES["roles"])


def test_factor_triggers_and_discouraged_elements():
    req = plan_requirements(_levels(security_risk="high", regulatory_criticality="high", legacy_dependence="low",
                                    continuous_delivery_need="low"), {"primary": "V-Model", "hybrid": []})
    ids = {m["id"] for m in req["mandatory"]}
    assert {"threat_modelling", "sast", "penetration_test", "security_signoff",
            "compliance_checkpoints", "audit_trail", "compliance_approval"} <= ids
    assert "migration_plan" not in ids
    discouraged = {d["id"] for d in req["discouraged"]}
    assert {"migration_plan", "automated_deployment"} <= discouraged
    assert req["pairings"]["User Requirements"] == "Acceptance Testing"
    assert req["phases"][0] == "User Requirements" and len(req["phases"]) == 9


def test_alternative_conditions_and_overlays_merge_reasons():
    req = plan_requirements(_levels(failure_consequence="high", verification_rigor="low"),
                            {"primary": "Agile", "hybrid": ["V-Model verification gates"]})
    by_id = {m["id"]: m for m in req["mandatory"]}
    assert by_id["traceability_matrix"]["reasons"] == ["overlay: V-Model verification gates",
                                                       "failure_consequence=high"]
    assert "independent_vv" in by_id and "verification_gate" in by_id
    assert req["phases"] == ["Inception", "Iterations", "Release", "Operate and Improve"]


def test_medium_everywhere_needs_only_medium_triggers_and_errors_are_clear():
    req = plan_requirements(_levels(), {"primary": "Waterfall", "hybrid": []})
    assert {m["id"] for m in req["mandatory"]} == {"dependency_scanning", "compliance_review_release",
                                                    "interface_analysis"}
    assert req["discouraged"] == []
    with pytest.raises(ValueError):
        plan_requirements(_levels(), {"primary": "Scrum", "hybrid": []})
    with pytest.raises(ValueError):
        plan_requirements(_levels(), {"primary": "Agile", "hybrid": ["mystery overlay"]})
