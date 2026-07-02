"""Corrected statistics for the assay Report (external-review folds).

Replaces "collapse k trials to a boolean, feed McNemar, accept the null on non-significance" — which
under-propagates trial variance (crack 4) and treats non-significance as equivalence (crack 3) — with
the textbook instruments, applied to agent orchestration:

  - **pass^k** as the reliability estimand (tau-bench 2024): the probability that ALL k independent
    attempts pass, estimated from n trials as the unbiased subset ratio C(passes, k) / C(n, k). This
    is distinct from pass@k (which caps an oracle selector); pass^k measures consistency.
  - a PAIRED two-level bootstrap on the per-Case Δ-pass^k (resample Cases, then resample trials within
    each Case) — carrying the trial-level uncertainty the boolean collapse discarded.
  - an EQUIVALENCE verdict against a PRE-SPECIFIED margin by CI-inclusion (the percentile-bootstrap
    analogue of TOST, Lakens 2017 — NOT the Tango/Nam score-TOST the power analysis prefers; that
    score test is the upgrade owed before any equivalence claim actually runs). The CI is the
    bootstrap percentile interval, ~0.068 coverage error (the mild variant), not the Wald ~0.20. A
    non-significant result is NOT "no effect"; to claim equivalence the whole CI must sit inside
    ±margin, and a zero-width (all-identical) bootstrap is ruled INCONCLUSIVE, never equivalent.
  - Benjamini-Hochberg FDR across the arm matrix (Benjamini & Hochberg 1995) — raw per-arm p-values
    are uncorrected; BH is less conservative than Holm for many arms.

None of this is novel (Dietterich 1998; Lakens 2017; BH 1995; Miller, "Adding Error Bars to Evals,"
2024). The layer's contribution is importing it, not inventing it.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def pass_hat_k(passes: int, trials: int, k: int) -> float:
    """pass^k reliability estimate: P(all k of k independent attempts pass), from `passes`/`trials`
    observed. The unbiased subset ratio C(passes, k) / C(trials, k) (math.comb is 0 when passes < k, so
    a cell that never reached k passes scores 0). Requires 1 <= k <= trials and 0 <= passes <= trials."""
    if not (1 <= k <= trials) or not (0 <= passes <= trials):
        raise ValueError(
            f"need 1<=k<=trials and 0<=passes<=trials; got passes={passes} k={k} trials={trials}"
        )
    return math.comb(passes, k) / math.comb(trials, k)


SUPERIOR = "superior"
EQUIVALENT = "equivalent"
INFERIOR = "inferior"
INCONCLUSIVE = "inconclusive"
UNDERPOWERED = (
    "underpowered"  # would read equivalent, but too few cases for THIS margin to claim it
)


def equivalence_power_floor(margin: float) -> int:
    """Minimum paired cases to be ALLOWED to claim equivalence within ±margin. Equivalence sample size
    scales ~1/δ²; this yields ~90 / 160 / 360 at margin 0.20 / 0.15 / 0.10 (the figures the power
    analysis fixed). A looser margin needs fewer cases — which is exactly WHY the margin must be
    pre-registered, not chosen after seeing the data (the report binds it to the run's recorded config).
    The floor only stops an underpowered run from PRINTING equivalence; it never blocks a real
    difference (superior/inferior fire regardless of n)."""
    if margin <= 0:
        return 10**9
    return math.ceil(3.6 / (margin * margin))


@dataclass(frozen=True)
class DeltaCI:
    """A paired Δ-pass^k estimate with a bootstrap CI and a TOST equivalence verdict. `delta` is the
    arm's pass^k minus the control's, averaged over paired Cases. `verdict` is one of superior /
    equivalent / inferior / inconclusive against `margin`. `p_two_sided` is the bootstrap two-sided p
    for delta != 0 (RAW — apply FDR across arms separately)."""

    delta: float
    ci_low: float
    ci_high: float
    p_two_sided: float
    verdict: str
    n_cases: int
    k: int
    n_boot: int
    margin: float


def _phk(bools: Sequence[bool], k: int, draw: list[int] | None) -> float:
    n = len(bools)
    if n == 0:
        return 0.0
    kk = min(k, n)
    sample = [bools[i] for i in draw] if draw is not None else list(bools)
    return pass_hat_k(sum(1 for x in sample if x), len(sample), kk)


def bootstrap_delta_pass_k(
    arm_by_case: Mapping[str, Sequence[bool]],
    control_by_case: Mapping[str, Sequence[bool]],
    *,
    k: int,
    margin: float,
    n_boot: int = 5000,
    alpha: float = 0.05,
    seed: int = 0,
) -> DeltaCI:
    """Paired two-level bootstrap CI + TOST verdict on Δ-pass^k. `*_by_case` maps case_id -> the
    per-trial pass booleans for that (arm, case). Cases in BOTH arms are paired; each replicate
    resamples Cases with replacement (outer) and, within each, resamples trials with replacement
    (inner), recomputing pass^k per arm and averaging the per-Case delta. Percentile CI at 1-alpha.
    Deterministic given `seed` (so the Report is repeatable — the same results reproduce the same CI)."""
    cases = sorted(set(arm_by_case) & set(control_by_case))
    if not cases:
        return DeltaCI(0.0, 0.0, 0.0, 1.0, INCONCLUSIVE, 0, k, n_boot, margin)
    rng = random.Random(seed)

    point = sum(
        _phk(arm_by_case[c], k, None) - _phk(control_by_case[c], k, None) for c in cases
    ) / len(cases)

    deltas: list[float] = []
    for _ in range(n_boot):
        picked = [cases[rng.randrange(len(cases))] for _ in range(len(cases))]
        total = 0.0
        for c in picked:
            a, ctrl = arm_by_case[c], control_by_case[c]
            da = [rng.randrange(len(a)) for _ in range(len(a))] if a else []
            dc = [rng.randrange(len(ctrl)) for _ in range(len(ctrl))] if ctrl else []
            total += _phk(a, k, da) - _phk(ctrl, k, dc)
        deltas.append(total / len(picked))
    deltas.sort()

    def _pct(a: float) -> tuple[float, float]:
        return deltas[max(0, int((a / 2) * n_boot))], deltas[
            min(n_boot - 1, int((1 - a / 2) * n_boot))
        ]

    lo, hi = _pct(alpha)  # the 1-alpha (95%) CI — reported for display + the difference (!=0) test
    # the verdict uses the 90% CI: a 5% TOST is two one-sided 5% tests, whose dual is the 90% interval,
    # NOT the 95%. Feeding the 95% CI (as before) is conservative — harder to call equivalent, the safe
    # direction — but mis-specified; this corrects the duality (review fold).
    tost_lo, tost_hi = _pct(2 * alpha)
    le = sum(1 for d in deltas if d <= 0) / n_boot
    ge = sum(1 for d in deltas if d >= 0) / n_boot
    p = min(1.0, 2 * min(le, ge))
    verdict = equivalence_verdict(tost_lo, tost_hi, margin=margin, n_pairs=len(cases))
    return DeltaCI(point, lo, hi, p, verdict, len(cases), k, n_boot, margin)


def equivalence_verdict(ci_low: float, ci_high: float, *, margin: float, n_pairs: int) -> str:
    """Margin-proper verdict from a CI on Δ against a pre-specified equivalence margin, GATED on power.
    The CI passed here should be the EQUIVALENCE interval (the 90% CI for a 5% TOST — two one-sided
    tests — NOT the 95% difference CI; see `bootstrap_delta_pass_k`).

      - equivalent: whole CI inside (-margin, margin) AND `n_pairs` >= the margin's power floor — a REAL
        'no meaningful difference', with enough cases to mean it.
      - underpowered: the CI sits inside ±margin but there are TOO FEW cases for this margin — the
        cargo-cult trap (a tight-looking CI, or a margin loose enough to swallow a wide CI, on a thin
        run); must NOT read as a real tie.
      - superior / inferior: whole CI clears +margin / -margin — a difference EXCEEDING the margin.
        Fires regardless of n (detecting a real difference needs less power than proving a tie).
      - inconclusive: the CI straddles a margin boundary (underpowered for either claim), OR is
        degenerate (zero width — an all-identical bootstrap cannot support an equivalence claim; the
        false-EQUIVALENT-at-[0,0] trap the power analysis warned about).

    The distinction the HEADLINE must respect: 'significantly worse than control' (the CI excludes 0)
    is NOT the same claim as 'inferior' here (worse by MORE than the margin). A CI of [-0.18, -0.06]
    at margin 0.10 excludes 0 (significantly worse) yet straddles -0.10 — so it is inconclusive FOR
    THE MARGIN: significantly worse, but not shown worse-by-the-margin. Report the two separately."""
    if ci_low >= margin:
        return SUPERIOR
    if ci_high <= -margin:
        return INFERIOR
    # EQUIVALENT needs the whole CI inside ±margin AND a NON-degenerate interval. A zero-width CI within
    # the margin is the false-equivalence trap: an all-identical bootstrap whose tightness is an
    # artifact of few/identical cases, not power — it falls through to INCONCLUSIVE. (A zero-width CI
    # that CLEARS a margin, e.g. [1,1] or [-1,-1], is a genuine maximal difference and is caught above.)
    if -margin <= ci_low and ci_high <= margin and ci_low != ci_high:
        return EQUIVALENT if n_pairs >= equivalence_power_floor(margin) else UNDERPOWERED
    return INCONCLUSIVE


def benjamini_hochberg(pvalues: Sequence[float], *, alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg FDR control at `alpha` across a family (the arm matrix): return a reject flag
    per p-value. Less conservative than Holm for many comparisons; the right multiplicity control when
    several arms are each compared to one control."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    kmax = 0
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= alpha * rank / m:
            kmax = rank
    reject = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= kmax:
            reject[idx] = True
    return reject
