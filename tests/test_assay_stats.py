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
    SCORE_TOST_ZERO_DISCORDANT,
    SUPERIOR,
    UNDERPOWERED,
    benjamini_hochberg,
    bootstrap_delta_pass_k,
    equivalence_power_floor,
    equivalence_verdict,
    equivalence_verdict_score_tost,
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
    big = equivalence_power_floor(m)  # cases needed to CLAIM equivalence at this margin (~360)
    # SUPERIOR / INFERIOR require the CI to CLEAR the margin — not merely exclude 0. Fire regardless of n.
    assert equivalence_verdict(0.15, 0.30, margin=m, n_pairs=10) == SUPERIOR
    assert equivalence_verdict(-0.30, -0.15, margin=m, n_pairs=10) == INFERIOR
    # EQUIVALENT needs the whole CI inside ±margin AND enough cases for the margin (the power gate).
    assert equivalence_verdict(-0.05, 0.05, margin=m, n_pairs=big) == EQUIVALENT
    # THE CARGO-CULT TRAP: same tight CI, too few cases -> underpowered, NOT a manufactured tie.
    assert equivalence_verdict(-0.05, 0.05, margin=m, n_pairs=big - 1) == UNDERPOWERED
    assert equivalence_verdict(-0.05, 0.05, margin=m, n_pairs=59) == UNDERPOWERED
    # 'significantly worse/better' (excludes 0) is NOT a margin verdict if it straddles the boundary.
    assert equivalence_verdict(0.05, 0.20, margin=m, n_pairs=big) == INCONCLUSIVE
    assert (
        equivalence_verdict(-0.18, -0.06, margin=m, n_pairs=big) == INCONCLUSIVE
    )  # the full pass@1 case
    assert equivalence_verdict(-0.30, 0.30, margin=m, n_pairs=big) == INCONCLUSIVE
    # degenerate zero-width: within the margin -> the false-equivalence trap -> inconclusive; clearing it
    # -> a genuine maximal difference (n-independent).
    assert equivalence_verdict(0.0, 0.0, margin=m, n_pairs=big) == INCONCLUSIVE
    assert equivalence_verdict(1.0, 1.0, margin=m, n_pairs=10) == SUPERIOR
    assert equivalence_verdict(-1.0, -1.0, margin=m, n_pairs=10) == INFERIOR


def test_equivalence_power_floor_scales_with_margin():
    # a TIGHTER equivalence claim needs MORE cases; the figures match the power analysis (~90/160/360).
    assert equivalence_power_floor(0.20) == 90
    assert equivalence_power_floor(0.15) == 160
    assert equivalence_power_floor(0.10) == 360
    assert equivalence_power_floor(0.20) < equivalence_power_floor(0.10)


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


def test_bootstrap_equal_arms_not_called_superior_or_equivalent_on_few_cases():
    # identical arms -> delta ~ 0; must NOT be superior. And on only 10 cases it must NOT print a real
    # tie either — the power gate makes it underpowered (or inconclusive), never a manufactured EQUIVALENT.
    same = {f"c{i}": [True, False] for i in range(10)}
    d = bootstrap_delta_pass_k(same, dict(same), k=1, margin=0.25, n_boot=2000, seed=1)
    assert d.delta == pytest.approx(0.0, abs=1e-9)
    assert d.verdict in (UNDERPOWERED, INCONCLUSIVE) and d.verdict not in (SUPERIOR, EQUIVALENT)


def test_bootstrap_degenerate_zero_variance_is_inconclusive_not_equivalent():
    # both arms solve EVERY trial of every case -> Δ is exactly 0 on every replicate -> a zero-width
    # [0,0] CI. That tightness is an ARTIFACT (no variability to resample), not power: it must read
    # INCONCLUSIVE, never EQUIVALENT — the false-equivalence-at-the-boundary trap the power analysis
    # named, resurfacing through a degenerate bootstrap.
    allpass = {f"c{i}": [True, True, True] for i in range(6)}
    d = bootstrap_delta_pass_k(allpass, dict(allpass), k=1, margin=0.1, n_boot=1000, seed=3)
    assert d.ci_low == d.ci_high == pytest.approx(0.0)
    assert d.verdict == INCONCLUSIVE


def test_bootstrap_maximal_difference_survives_degenerate_guard():
    # arm solves everything, control nothing -> Δ is exactly +1 on every replicate -> zero-width [1,1].
    # This is GENUINE maximal superiority, not an artifact: the degenerate guard must NOT swallow it.
    d = bootstrap_delta_pass_k(
        {f"c{i}": [True, True] for i in range(6)},
        {f"c{i}": [False, False] for i in range(6)},
        k=1,
        margin=0.1,
        n_boot=1000,
        seed=4,
    )
    assert d.ci_low == d.ci_high == pytest.approx(1.0)
    assert d.verdict == SUPERIOR


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


def test_exact_mcnemar_discordant_boundary():
    # the discordant boundary the power argument rests on (b≈c, small counts) — previously unexercised.
    from substrate.assay.report import exact_mcnemar_p

    # cross-check against the definition: two-sided = 2 * P(Binom(b+c, 0.5) <= min(b,c)), capped at 1.
    for b, c in [(5, 6), (5, 5), (0, 11), (1, 10), (3, 8), (2, 2)]:
        n, kk = b + c, min(b, c)
        expected = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(kk + 1)) * 0.5**n)
        assert exact_mcnemar_p(b, c) == pytest.approx(expected)
    assert exact_mcnemar_p(0, 0) == 1.0  # no discordant pairs -> no evidence
    # a near-balanced 5-vs-6 split is NOT significant — a near-tie must never read as a real difference.
    assert exact_mcnemar_p(5, 6) > 0.05
    # a lopsided split IS significant (this is where a real arm/control difference shows).
    assert exact_mcnemar_p(0, 12) < 0.05


def test_score_tost_zero_discordant_fallback_is_inconclusive():
    # b == c == 0 hits the restricted-MLE boundary; per roadmap round-3 sprint 150 the answer is
    # INCONCLUSIVE with `zero_discordant`, not a manufactured equivalence claim from a run with no
    # discordant pairs to measure — same conservative posture as the bootstrap's zero-width-CI
    # fallback at stats.py:172-177. This is the specific pin the roadmap called for.
    verdict, note = equivalence_verdict_score_tost(b=0, c=0, n=100, margin=0.10)
    assert verdict == INCONCLUSIVE
    assert note == SCORE_TOST_ZERO_DISCORDANT
    # n == 0 is inherently INCONCLUSIVE too, distinct note so a caller can tell the two apart.
    verdict0, note0 = equivalence_verdict_score_tost(b=0, c=0, n=0, margin=0.10)
    assert verdict0 == INCONCLUSIVE
    assert note0 == "n=0"


def test_score_tost_equivalent_with_enough_pairs_and_tight_delta():
    # near-perfect concordance on a large paired run: b = c = 3 out of n = 400 discordant, Delta_hat
    # exactly 0. The margin (0.20) admits 90 pairs by the power floor — 400 clears it — and the
    # score test's null-restricted variance places the CI safely inside +/-0.20 -> EQUIVALENT.
    verdict, note = equivalence_verdict_score_tost(b=3, c=3, n=400, margin=0.20)
    assert verdict == EQUIVALENT
    assert note == "score-tost"


def test_score_tost_underpowered_downgrades_equivalent():
    # same Delta_hat = 0 shape as above but at n = 50 — well below the ~90-pair floor for margin
    # 0.20. Would read EQUIVALENT on the math alone; the power gate downgrades to UNDERPOWERED so
    # a thin run cannot manufacture the claim (mirrors the bootstrap-side gate at stats.py:177).
    verdict, _ = equivalence_verdict_score_tost(b=1, c=1, n=50, margin=0.20)
    assert verdict == UNDERPOWERED


def test_score_tost_superior_and_inferior_fire_regardless_of_n():
    # a lopsided discordant split at small n: c >> b -> arm wins by a wide margin -> SUPERIOR
    # (Delta > margin) even without the power gate; a difference test needs less power than a tie.
    v_sup, _ = equivalence_verdict_score_tost(b=1, c=20, n=25, margin=0.10)
    assert v_sup == SUPERIOR
    # mirror: control wins big -> INFERIOR (Delta < -margin).
    v_inf, _ = equivalence_verdict_score_tost(b=20, c=1, n=25, margin=0.10)
    assert v_inf == INFERIOR


def test_score_tost_inconclusive_when_delta_hat_straddles_margin():
    # Delta_hat = (c - b)/n = 5/50 = 0.10 exactly ON the margin boundary — a real gap the run
    # cannot resolve. Neither one-sided test can reject at 5% -> INCONCLUSIVE (not EQUIVALENT, not
    # SUPERIOR): the honest state a matched-pair equivalence trial ends in when the data straddles.
    v, _ = equivalence_verdict_score_tost(b=5, c=10, n=50, margin=0.10)
    assert v == INCONCLUSIVE


def test_score_tost_matches_bootstrap_in_the_easy_case():
    # sanity check: a clear-difference arm at ample n reads SUPERIOR on both methods. Not an exact
    # numerical equivalence — score-TOST and percentile-CI bootstrap are different tests — just a
    # co-verdict on a case where both should agree, so a caller who consults both never sees a
    # nonsense divergence on the loud signals.
    arm = {f"c{i}": [True, True, True] for i in range(120)}
    control = {f"c{i}": [False, False, False] for i in range(120)}
    dci = bootstrap_delta_pass_k(arm, control, k=1, margin=0.10, n_boot=1000, seed=0)
    # b=0 (control failed everywhere), c=120 (arm passed everywhere), n=120
    v_score, _ = equivalence_verdict_score_tost(b=0, c=120, n=120, margin=0.10)
    assert dci.verdict == SUPERIOR
    assert v_score == SUPERIOR


def test_pass_hat_k_matches_hand_computation():
    # exhaustive cross-check of the estimator against the definition for small n.
    for n in range(1, 6):
        for passes in range(n + 1):
            for k in range(1, n + 1):
                expected = math.comb(passes, k) / math.comb(n, k)
                assert pass_hat_k(passes, n, k) == pytest.approx(expected)
