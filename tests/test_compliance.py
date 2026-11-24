"""Compliance knowledge base, retrieval and risk register."""
import re

import yaml

from compliance.analysis import risk_register
from compliance.retrieve import load_kb, named
from core.config import ROOT

KB = yaml.safe_load(open(ROOT / "ontology" / "standards.yaml", encoding="utf-8"))
PLAN_ELEMENTS = yaml.safe_load(open(ROOT / "ontology" / "plan_skeletons.yaml", encoding="utf-8"))["elements"]
RISKS = yaml.safe_load(open(ROOT / "ontology" / "risks.yaml", encoding="utf-8"))["risks"]


def test_every_obligation_is_whole():
    # an unquoted comma inside YAML's inline {...} form silently ends the value
    for s in KB["standards"]:
        for o in s["obligations"]:
            assert set(o) == {"id", "ref", "phase", "text", "keywords"}, o["id"]
            assert o["text"].rstrip().endswith((".", ")")), o["id"]
            assert o["phase"] in KB["phases"] and o["keywords"], o["id"]


def test_ids_are_unique_and_triggers_compile():
    ids = [o["id"] for s in KB["standards"] for o in s["obligations"]]
    assert len(ids) == len(set(ids))
    for s in KB["standards"]:
        assert s.get("triggers") or s.get("triggers_all"), s["id"]
        for t in s.get("triggers", []) + s.get("triggers_all", []):
            re.compile(t)


def test_named_hits_carry_the_matching_span():
    hits = {h.standard: h for h in named("Certified to DO-178C level A; card data is in PCI DSS scope.")}
    assert hits["do178c"].evidence == "DO-178" and hits["do178c"].how == "named"
    assert "pci_dss" in hits
    assert not named("A bakery wants a rota app for its staff.")


def test_indian_standards_need_an_indian_marker():
    hits = {h.standard for h in named("Sahyadri Bank, regulated by the RBI, will run video KYC in its app.")}
    assert {"rbi_kyc", "rbi_it_governance"} <= hits
    assert "rbi_digital_lending" in {h.standard for h in named("An NBFC launches a mobile app for personal loans.")}
    assert not {h.standard for h in named("A bank in Ohio runs KYC checks in its mobile app.")} & {
        "rbi_kyc", "rbi_it_governance", "rbi_digital_lending", "dpdp", "certin", "gigw"}


def test_jurisdiction_blocks_inference_outside_india(monkeypatch):
    import numpy as np
    from compliance import retrieve

    kb = load_kb()["standards"]
    j = next(i for i, s in enumerate(kb) if s["id"] == "rbi_kyc")
    sim = np.zeros((1, len(kb)))
    sim[0, j] = 0.9
    monkeypatch.setattr(retrieve, "similarities", lambda text, method: ([text], sim))
    assert not retrieve.inferred("A bank in Ohio runs KYC checks.", "dense", 0.5)
    assert [h.standard for h in retrieve.inferred("A bank in India runs KYC checks.", "dense", 0.5)] == ["rbi_kyc"]


def test_risk_templates_reference_real_plan_elements():
    for r in RISKS:
        for m in r["mitigations"]:
            assert m in PLAN_ELEMENTS, (r["id"], m)


def test_risk_register_cites_evidence_and_marks_assumptions():
    factors = {f: {"level": "not_stated", "evidence": None} for f in load_kb() and PLAN_ELEMENTS and
               ["security_risk", "failure_consequence", "complexity", "technical_novelty"]}
    factors["failure_consequence"] = {"level": "high", "evidence": "a crash could injure a worker"}
    risks = {r["id"]: r for r in risk_register(factors)}
    harm = risks["harm_from_failure"]
    assert harm["evidence"] == [{"factor": "failure_consequence", "level": "high",
                                 "evidence": "a crash could injure a worker"}]
    assert harm["assumed"] and harm["likelihood"] == "medium"      # complexity, novelty unstated
    assert harm["mitigated"] is None                               # no plan to check against
