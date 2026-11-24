"""Keyword-lexicon factor reader."""
from baselines.lexicon import lexicon_predict
from test_train_tasks import NAMES


def test_lexicon_cues_and_evidence():
    desc = ("No regulator reviews the portal. The team is 40 engineers. Developers test their own code. "
            "Grid feeds are a target for attackers. It must read the 1998 billing database.")
    pred = lexicon_predict(desc, NAMES)
    assert pred["regulatory_criticality"]["level"] == "low"
    assert pred["size"]["level"] == "high"
    assert pred["verification_rigor"]["level"] == "low"
    assert pred["security_risk"]["level"] == "high"
    assert pred["legacy_dependence"]["level"] == "high"
    assert pred["scope_rigidity"] == {"level": "not_stated", "evidence": None}
    assert all(v["evidence"] in desc for v in pred.values() if v["evidence"])
    assert lexicon_predict("Two developers build it.", NAMES)["size"]["level"] == "low"
    assert lexicon_predict("A proven engine that's new to us.", NAMES)["technical_novelty"]["level"] == "medium"
