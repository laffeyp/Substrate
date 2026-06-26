"""Corrected statistics — pass^k, paired bootstrap Δ-CI, TOST equivalence, BH-FDR.

Deterministic (the bootstrap is seeded, so the Report is repeatable). These pin the properties the
external review demanded: pass^k is the subset estimator; non-significance is NOT equivalence (a TOST
verdict against a margin); the bootstrap carries trial variance; FDR controls the arm matrix.
"""

import math

import pytest

from substrate.assay.stats import (
    EQUIVALENT,
    INCONCLUSIVE,
    INFERIOR,
    SUPERIOR,
    benjamini_hochberg,
    bootstrap_delta_pass_k,
    equivalence_verdict,
    pass_hat_k,
)


def test_pass_hat_k_subset_estimator():
    # all trials pass -> 1.0; none -> 0.0; passes<k -> 0.0 (math.comb is 0).
    assert pass_hat_k(3, 3, 3) == 1.0
    assert pass_hat_k(0, 3, 1) == 0.0
    assert pass_hat_k(2, 3, 3) == 0.0  # can't have 3 of 3 pass with only 2 passing
    # 2 of 3 passing, k=1: P(a random single attempt passes) = 2/3.
    assert pass_hat_k(2, 3, 1) == pytest.approx(2 / 3)
    # 2 of 4 passing, k=2: C(2,2)/C(4,2) = 1/6.
    assert pass_hat_k(2, 4, 2) == pytest.approx(1 / 6)
    with pytest.raises(ValueError):
        pass_hat_k(5, 3, 2)  # passes > trials
    with pytest.raises(ValueError):
        pass_hat_k(2, 3, 0)  # k < 1


def test_equivalence_verdict_tost():
    m = 0.1
    assert equivalence_verdict(0.05, 0.20, margin=m) == SUPERIOR  # CI entirely > 0
    assert equivalence_verdict(-0.20, -0.05, margin=m) == INFERIOR  # CI entirely < 0
    assert equivalence_verdict(-0.05, 0.05, margin=m) == EQUIVALENT  # inside ±margin
    assert equivalence_verdict(-0.30, 0.30, margin=m) == INCONCLUSIVE  # wide, spans margins
    # the crux: a CI that includes 0 but is WIDER than the margin is NOT equivalence — non-significance
    # is not evidence of no effect.
    assert equivalence_verdict(-0.15, 0.02, margin=m) == INCONCLUSIVE


def test_bootstrap_delta_is_repeatable_and_directional():
    # arm clearly beats control on every case; the CI should sit above 0 -> superior, and be identical
    # on a re-run (seeded -> repeatable).
    arm = {f"c{i}": [True, True, True] for i in range(8)}
    control = {f"c{i}": [False, False, False] for i in range(8)}
    a = bootstrap_delta_pass_k(arm, control, k=1, margin=0.1, n_boot=2000, seed=0)
    b = bootstrap_delta_pass_k(arm, control, k=1, margin=0.1, n_boot=2000, seed=0)
    assert a == b  # repeatable
    assert a.delta == pytest.approx(1.0)
    assert a.ci_low > 0 and a.verdict == SUPERIOR


def test_bootstrap_equal_arms_not_called_superior():
    # identical arms -> delta ~ 0; must NOT be superior, and with a generous margin reads equivalent.
    same = {f"c{i}": [True, False] for i in range(10)}
    d = bootstrap_delta_pass_k(same, dict(same), k=1, margin=0.25, n_boot=2000, seed=1)
    assert d.delta == pytest.approx(0.0, abs=1e-9)
    assert d.verdict in (EQUIVALENT, INCONCLUSIVE) and d.verdict != SUPERIOR


def test_bootstrap_carries_trial_variance():
    # a single noisy case (one trial difference) must NOT produce a tight CI claiming superiority — the
    # two-level bootstrap reflects how little is known. With one case, the CI should include 0.
    arm = {"only": [True, True, False]}
    control = {"only": [False, True, False]}
    d = bootstrap_delta_pass_k(arm, control, k=1, margin=0.1, n_boot=2000, seed=2)
    assert d.ci_low <= 0 <= d.ci_high  # not enough to claim anything
    assert d.verdict in (EQUIVALENT, INCONCLUSIVE)


def test_benjamini_hochberg():
    assert benjamini_hochberg([]) == []
    # one clearly-significant, rest null: BH should reject the small one.
    flags = benjamini_hochberg([0.001, 0.5, 0.6, 0.8], alpha=0.05)
    assert flags[0] is True and not any(flags[1:])
    # all null -> none rejected.
    assert benjamini_hochberg([0.4, 0.5, 0.9], alpha=0.05) == [False, False, False]
    # BH is less conservative than Bonferroni: two moderate p's that Bonferroni (0.05/3) would keep.
    flags2 = benjamini_hochberg([0.01, 0.02, 0.9], alpha=0.05)
    assert flags2[0] and flags2[1] and not flags2[2]


def test_pass_hat_k_matches_hand_computation():
    # exhaustive cross-check of the estimator against the definition for small n.
    for n in range(1, 6):
        for passes in range(n + 1):
            for k in range(1, n + 1):
                expected = math.comb(passes, k) / math.comb(n, k)
                assert pass_hat_k(passes, n, k) == pytest.approx(expected)
