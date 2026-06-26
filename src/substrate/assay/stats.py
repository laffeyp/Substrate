"""Corrected statistics for the assay Report (external-review folds).

Replaces "collapse k trials to a boolean, feed McNemar, accept the null on non-significance" — which
under-propagates trial variance (crack 4) and treats non-significance as equivalence (crack 3) — with
the textbook instruments, applied to agent orchestration:

  - **pass^k** as the reliability estimand (tau-bench 2024): the probability that ALL k independent
    attempts pass, estimated from n trials as the unbiased subset ratio C(passes, k) / C(n, k). This
    is distinct from pass@k (which caps an oracle selector); pass^k measures consistency.
  - a PAIRED two-level bootstrap on the per-Case Δ-pass^k (resample Cases, then resample trials within
    each Case) — carrying the trial-level uncertainty the boolean collapse discarded.
  - an EQUIVALENCE verdict via TOST against a PRE-SPECIFIED margin (Lakens 2017): a non-significant
    result is NOT "no effect"; to claim equivalence the whole CI must sit inside ±margin.
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
    lo = deltas[int((alpha / 2) * n_boot)]
    hi = deltas[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    le = sum(1 for d in deltas if d <= 0) / n_boot
    ge = sum(1 for d in deltas if d >= 0) / n_boot
    p = min(1.0, 2 * min(le, ge))
    return DeltaCI(
        point, lo, hi, p, equivalence_verdict(lo, hi, margin=margin), len(cases), k, n_boot, margin
    )


def equivalence_verdict(ci_low: float, ci_high: float, *, margin: float) -> str:
    """From a CI on Δ and a pre-specified equivalence margin (TOST, Lakens 2017): whole CI above 0 ->
    superior; below 0 -> inferior; inside (-margin, +margin) -> equivalent (a REAL 'no meaningful
    difference', NOT mere non-significance); otherwise inconclusive (underpowered for either claim)."""
    if ci_low > 0:
        return SUPERIOR
    if ci_high < 0:
        return INFERIOR
    if -margin <= ci_low and ci_high <= margin:
        return EQUIVALENT
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
