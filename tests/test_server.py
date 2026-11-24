"""server/app.py on the CPU-only lexicon backend."""
import importlib
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(monkeypatch_module):
    monkeypatch_module.setenv("SDLC_BACKEND", "lexicon")
    import server.app as app_module
    app_module = importlib.reload(app_module)
    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def _events(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_meta_reports_the_backend_and_the_v13_preconditions(client):
    meta = client.get("/api/meta").json()
    assert meta["backend"] == "lexicon" and not meta["model_loaded"]
    assert len(meta["factors"]) == 14 and meta["rubric_version"] == "1.3"
    assert meta["preconditions"]["Waterfall"] == {"requirement_stability": ["high"], "scope_rigidity": ["high"]}


def test_score_withholds_an_unsupported_primary_and_names_what_would_change_it(client):
    thin = {"technical_novelty": "low", "legacy_dependence": "high", "complexity": "medium"}
    out = client.post("/api/score", json={"levels": thin}).json()
    assert out["rubric"]["primary"] == "Waterfall" and out["rubric"]["primary_withheld"]
    assert "PRECONDITION_UNMET" in out["rubric"]["triggered_rules"]
    assert out["stated"] == 3 and out["questions"]
    q = out["questions"][0]
    assert set(q["outcomes"]) == {"low", "medium", "high"} and q["could_lead_to"]


def test_score_rejects_unknown_factors(client):
    assert client.post("/api/score", json={"levels": {"vibes": "high"}}).status_code == 422


def test_analyze_streams_accepted_first_then_steps_then_a_result(client):
    text = ("A hospital builds infusion pump firmware. The regulator audits it under IEC 62304 Class C "
            "and every requirement must be traceable to tests. A dosing error could kill a patient.")
    events = _events(client.post("/api/analyze", json={"description": text}))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "accepted" and kinds[1] == "start" and kinds[-1] == "result"
    assert [e["node"] for e in events if e["type"] == "step"] == ["extract", "clarify", "rubric", "comply", "assess", "explain"]
    result = events[-1]
    assert len(result["state"]["factors"]) == 14 and len(result["rubric"]["scores"]) == 5
    assert result["rubric"]["rubric_version"] == "1.3"


def test_replan_keeps_the_reviewers_levels(client):
    factors = {"scope_rigidity": {"level": "high", "evidence": "set by the reviewer"},
               "requirement_stability": {"level": "high", "evidence": "set by the reviewer"},
               "technical_novelty": {"level": "low", "evidence": None}}
    events = _events(client.post("/api/replan", json={"description": "A council replaces its payroll engine.",
                                                      "factors": factors}))
    result = events[-1]
    assert result["type"] == "result"
    assert "extract" not in [e["node"] for e in events if e["type"] == "step"]
    assert result["state"]["factors"]["scope_rigidity"]["level"] == "high"
    assert result["rubric"]["primary"] == "Waterfall" and not result["rubric"]["primary_withheld"]


def test_too_short_a_description_is_refused(client):
    assert client.post("/api/analyze", json={"description": "an app"}).status_code == 422


def test_assess_maps_named_standards_to_obligations_and_builds_a_risk_register(client):
    text = ("The infusion pump firmware is IEC 62304 Class C. The FDA will review the 510(k) submission, "
            "and a dosing error could harm a patient.")
    factors = {"failure_consequence": {"level": "high", "evidence": "a dosing error could harm a patient"},
               "regulatory_criticality": {"level": "high", "evidence": "The FDA will review"}}
    plan = {"lifecycle": "V-Model", "phases": [
        {"name": "Planning", "activities": ["Write the software development plan", "Assign software safety class C"]},
        {"name": "Verification", "testing": ["Unit test every module", "Hazard analysis review"]}]}
    out = client.post("/api/assess", json={"description": text, "factors": factors, "plan": plan}).json()
    named = {s["standard"]: s for s in out["compliance"]["standards"] if s["how"] == "named"}
    assert {"iec62304", "fda_design_controls"} <= set(named)
    assert named["iec62304"]["evidence"].lower().startswith("62304") or "62304" in named["iec62304"]["evidence"]
    rows = {o["id"]: o for o in out["compliance"]["obligations"]}
    assert rows["iec62304-5.1"]["covered_by"] == ["Planning"]            # "development plan"
    assert rows["iec62304-4.3"]["covered_by"] == ["Planning"]            # "safety class"
    assert 0 < out["compliance"]["coverage"] < 1 and out["compliance"]["missing"]
    risks = {r["id"]: r for r in out["risks"]}
    assert risks["harm_from_failure"]["impact"] == "high"
    assert risks["harm_from_failure"]["evidence"][0]["evidence"] == "a dosing error could harm a patient"
    # missing obligations raise the regulatory risk's likelihood
    assert risks["regulatory_findings"]["likelihood"] == "high" and risks["regulatory_findings"]["note"]


def test_analyze_result_carries_compliance_and_risks(client):
    text = ("A council builds a parking permit website that must work for blind residents using screen "
            "readers. It stores residents' names and addresses.")
    events = _events(client.post("/api/analyze", json={"description": text}))
    nodes = [e["node"] for e in events if e["type"] == "step"]
    assert nodes == ["extract", "clarify", "rubric", "comply", "assess", "explain"]
    state = events[-1]["state"]
    assert state["compliance"] is not None and isinstance(state["risks"], list)


def test_srs_is_drafted_from_a_finished_run(client):
    text = ("A hospital builds infusion pump firmware. The regulator audits it under IEC 62304 Class C "
            "and every requirement must be traceable to tests. A dosing error could kill a patient.")
    state = _events(client.post("/api/analyze", json={"description": text}))[-1]["state"]
    state["requirements"] = [{"id": "FR-01", "statement": "The system shall calculate doses.", "type": "functional",
                              "category": "functional", "basis": "stated", "source": "infusion pump firmware",
                              "citation": None}]
    body = client.post("/api/srs", json={"state": state}).json()
    assert body["srs"]["functional"][0]["id"] == "FR-01"
    assert body["srs"]["traceability"][0]["verification"] == "Test"
    assert "## 3. Requirements" in body["markdown"] and "FR-01" in body["markdown"]
