"""Proper scoring rules — formulas, registry, and the properness guarantee."""

import pytest

from substrate.topologies.instruments.scoring import (
    REGISTRY,
    BrierScore,
    LogLossScore,
    Outcome,
    Prediction,
    ScoringError,
    SphericalScore,
    select_scoring_rule,
)


def _p(c: float) -> Prediction:
    return Prediction(claim="x", confidence=c)


def _o(v: float) -> Outcome:
    return Outcome(claim="x", value=v)


def test_brier_endpoints():
    assert BrierScore().score(_p(1.0), _o(1.0)) == 0.0  # perfect
    assert BrierScore().score(_p(1.0), _o(0.0)) == 1.0  # perfectly wrong
    assert BrierScore().score(_p(0.7), _o(1.0)) == pytest.approx(0.09)


def test_log_loss_and_spherical_calibrated_to_zero():
    assert LogLossScore().score(_p(1.0), _o(1.0)) == pytest.approx(0.0, abs=1e-5)
    assert SphericalScore().score(_p(1.0), _o(1.0)) == pytest.approx(0.0, abs=1e-9)
    # log-loss punishes a confident wrong forecast hard (large, finite due to the eps clamp)
    assert LogLossScore().score(_p(1.0), _o(0.0)) > 10.0


def test_input_validation():
    with pytest.raises(ScoringError):
        Prediction(claim="x", confidence=1.5)
    with pytest.raises(ScoringError):
        Outcome(claim="x", value=-0.1)


def test_registry_and_selection():
    assert set(REGISTRY) == {"brier", "log_loss", "spherical"}
    assert select_scoring_rule("BRIER").name == "brier"
    with pytest.raises(ScoringError):
        select_scoring_rule("nonesuch")


@pytest.mark.parametrize("rule_name", ["brier", "log_loss", "spherical"])
@pytest.mark.parametrize("p_true", [0.2, 0.5, 0.8])
def test_rule_is_proper(rule_name, p_true):
    # PROPERNESS: under a true probability p_true, the expected score is minimised by REPORTING
    # p_true. This is the property that turns a confidence claim from cheap talk into a payoff.
    rule = select_scoring_rule(rule_name)

    def expected_loss(report: float) -> float:
        return p_true * rule.score(_p(report), _o(1.0)) + (1.0 - p_true) * rule.score(
            _p(report), _o(0.0)
        )

    truthful = expected_loss(p_true)
    grid = [i / 20 for i in range(1, 20)]  # avoid exact 0/1 for log-loss domain comfort
    assert all(truthful <= expected_loss(r) + 1e-9 for r in grid)
