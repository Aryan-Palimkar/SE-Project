"""Rubric regression tests on worked examples."""
import pytest

from rubric.scorer import load_rubric, score

RUBRIC = load_rubric()
FACTORS = list(RUBRIC["weights"])
L, M, H, NS = "low", "medium", "high", "not_stated"


def profile(*levels):
    assert len(levels) == len(FACTORS)
    return dict(zip(FACTORS, levels))


#                        stab chg cd  reg sec cons ver doc cplx size nov leg stake rigid
INFUSION_PUMP = profile(H,   L,  L,  H,  NS, H,   H,  H,  M,   M,   L,  H,  L,    H)
GROCERY_MVP   = profile(L,   H,  M,  L,  L,  L,   L,  L,  L,   L,   L,  L,  H,    L)
BANK_APP      = profile(L,   H,  H,  H,  H,  M,   M,  H,  H,   H,   L,  H,  H,    L)
PAYROLL       = profile(H,   L,  L,  M,  M,  M,   L,  H,  M,   M,   L,  H,  L,    H)
DRONE         = profile(M,   M,  L,  M,  M,  H,   M,  M,  H,   M,   H,  L,  M,    L)


@pytest.mark.parametrize("factors, scores, primary, acceptable, overlays", [
    (INFUSION_PUMP, {"Waterfall": 15, "V-Model": 19, "Spiral": -1, "Agile": -16, "DevSecOps": -6},
     "V-Model", ["V-Model"], None),
    (GROCERY_MVP, {"Waterfall": -8, "V-Model": -17, "Spiral": -7, "Agile": 14, "DevSecOps": -2},
     "Agile", ["Agile"], None),
    (BANK_APP, {"Waterfall": -5, "V-Model": 0, "Spiral": 2, "Agile": 4, "DevSecOps": 14},
     "DevSecOps", ["DevSecOps"], ["compliance gates"]),
    (PAYROLL, {"Waterfall": 12, "V-Model": 9, "Spiral": -3, "Agile": -10, "DevSecOps": -8},
     "Waterfall", ["Waterfall", "V-Model"], ["V-Model test levels"]),
    (DRONE, {"Waterfall": -4, "V-Model": 1, "Spiral": 9, "Agile": 1, "DevSecOps": 1},
     "Spiral", ["Spiral"], None),
], ids=["infusion_pump", "grocery_mvp", "bank_app", "payroll", "drone"])
def test_worked_examples(factors, scores, primary, acceptable, overlays):
    result = score(factors)
    assert result["scores"] == scores
    assert result["primary"] == primary
    assert result["acceptable_set"] == acceptable
    assert (result["hybrid"] or {}).get("overlays") == overlays


def test_ranking_ties_follow_model_order_and_r4_fires():
    result = score(DRONE)
    assert result["ranking"] == ["Spiral", "V-Model", "Agile", "DevSecOps", "Waterfall"]
    assert "R4" in result["triggered_rules"]


def test_c3_blocks_plan_driven_models_when_continuous_delivery_is_high():
    result = score({**PAYROLL, "continuous_delivery_need": H})
    assert result["scores"]["Waterfall"] == 8
    assert result["primary"] == "DevSecOps"
    assert result["acceptable_set"] == ["DevSecOps", "Spiral"]
    assert "C3" in result["triggered_rules"]


def test_c1_adds_verification_gates_to_iterative_top():
    result = score({**GROCERY_MVP, "failure_consequence": H, "verification_rigor": H})
    assert result["primary"] == "Agile"
    assert result["hybrid"] == {"backbone": "Agile", "overlays": ["V-Model verification gates"]}


def test_top_contributors_prefer_present_factors():
    assert score(INFUSION_PUMP)["top_contributors"]["V-Model"] == [
        "verification_rigor", "requirement_stability", "regulatory_criticality"]


def test_accepts_record_style_factor_dicts():
    nested = {f: {"level": lvl, "evidence": None} for f, lvl in BANK_APP.items()}
    assert score(nested) == score(BANK_APP)


def test_rejects_missing_factor_and_invalid_level():
    with pytest.raises(ValueError, match="missing"):
        score({f: lvl for f, lvl in INFUSION_PUMP.items() if f != "size"})
    with pytest.raises(ValueError, match="invalid level"):
        score({**INFUSION_PUMP, "size": "huge"})


def _levels(names, stated):
    """`stated` factors get a level, the rest are not_stated."""
    return {f: ("high" if i % 2 == 0 else "low") if i < stated else "not_stated" for i, f in enumerate(names)}


def test_low_evidence_gate_widens_the_acceptable_set_without_moving_the_primary():
    rubric = load_rubric()
    names = list(rubric["weights"])
    sparse = _levels(names, 5)                       # 5 of 14 stated, below min_coverage 0.5
    gated = score(sparse, rubric)
    ungated = score(sparse, {**rubric, "low_evidence": None})

    assert gated["low_evidence"] is True and "LOW_EVIDENCE" in gated["triggered_rules"]
    assert gated["stated_coverage"] < rubric["low_evidence"]["min_coverage"]
    assert len(gated["acceptable_set"]) == rubric["low_evidence"]["top_k"]
    assert gated["acceptable_set"][:len(ungated["acceptable_set"])] == ungated["acceptable_set"]
    assert gated["primary"] == ungated["primary"]
    assert gated["hybrid"] == ungated["hybrid"]
    assert gated["scores"] == ungated["scores"] and gated["margin"] == ungated["margin"]


def test_dense_profiles_are_unaffected_by_the_gate():
    rubric = load_rubric()
    names = list(rubric["weights"])
    dense = _levels(names, len(names))
    gated, ungated = score(dense, rubric), score(dense, {**rubric, "low_evidence": None})
    assert gated["low_evidence"] is False and "LOW_EVIDENCE" not in gated["triggered_rules"]
    assert gated["acceptable_set"] == ungated["acceptable_set"]


def test_removing_the_block_reproduces_v1_0_exactly():
    rubric = load_rubric()
    names = list(rubric["weights"])
    for stated in range(0, len(names) + 1):
        a = score(_levels(names, stated), {**rubric, "low_evidence": None})
        b = score(_levels(names, stated), {k: v for k, v in rubric.items() if k != "low_evidence"})
        assert a["acceptable_set"] == b["acceptable_set"] and a["low_evidence"] is False


def test_precondition_gate_withholds_an_unsupported_primary_without_moving_it():
    rubric = load_rubric()
    names = list(rubric["weights"])
    thin = {f: "not_stated" for f in names}
    thin.update(technical_novelty="low", legacy_dependence="high", complexity="medium")
    gated = score(thin, rubric)
    ungated = score(thin, {**rubric, "preconditions": None})
    assert gated["primary"] == ungated["primary"] == "Waterfall"
    assert gated["ranking"] == ungated["ranking"] and gated["scores"] == ungated["scores"]
    assert gated["primary_withheld"] and "PRECONDITION_UNMET" in gated["triggered_rules"]
    assert len(gated["acceptable_set"]) >= rubric["preconditions"]["top_k"]
    assert ungated["supported_models"] is None


def test_precondition_gate_names_a_supported_primary():
    rubric = load_rubric()
    names = list(rubric["weights"])
    fixed = {f: "not_stated" for f in names}
    fixed.update(technical_novelty="low", legacy_dependence="high", scope_rigidity="high",
                 requirement_stability="high")
    result = score(fixed, rubric)
    assert result["primary"] == "Waterfall" and "Waterfall" in result["supported_models"]
    assert "PRECONDITION_UNMET" not in result["triggered_rules"]
