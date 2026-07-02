"""Power simulation for the equivalence verdict — checkable, not asserted.

Question (the builder's plan): does "10 problems + trials>1" let `full` EARN `equivalent`? Run synthetic
experiments through the REAL stats (`bootstrap_delta_pass_k` + the TOST verdict), sweeping problems n,
trials, and the equivalence margin, under a true-null topology (arm == control on average), and report
P(equivalent). Also a true-difference scenario, to show superiority is earned at smaller n than
equivalence (equivalence is the harder claim).

Two null shapes, because the answer DEPENDS on the variance decomposition:
  - heterogeneous null: per-problem true effect varies (the structure helps on some problems, hurts on
    others, mean ~0) — the realistic "full ~ strong overall, problem-by-problem they differ". Here the
    between-problem variance is irreducible by trials; only n shrinks the CI.
  - homogeneous null: identical per-problem difficulty; the arm/control difference is PURE sampling
    noise — here trials DO shrink the CI. (Unrealistic for real topologies, included for contrast.)

    uv run python scripts/power_sim.py
"""

from __future__ import annotations

import random

from substrate.assay.stats import EQUIVALENT, bootstrap_delta_pass_k

N_SIM = 150
N_BOOT = 300


def _experiment(scenario: str, n: int, trials: int, margin: float, rng: random.Random) -> str:
    arm: dict[str, list[bool]] = {}
    control: dict[str, list[bool]] = {}
    for i in range(n):
        c = rng.uniform(0.1, 0.9)  # control's per-problem solve probability
        if scenario == "het_null":
            a = min(
                1.0, max(0.0, c + rng.gauss(0.0, 0.2))
            )  # arm differs per problem; mean effect ~0
        elif scenario == "hom_null":
            a = c  # identical difficulty -> difference is pure sampling noise
        else:  # "diff": a real +0.15 effect
            a = min(1.0, c + 0.15)
        cid = f"p{i}"
        control[cid] = [rng.random() < c for _ in range(trials)]
        arm[cid] = [rng.random() < a for _ in range(trials)]
    dci = bootstrap_delta_pass_k(
        arm, control, k=1, margin=margin, n_boot=N_BOOT, seed=rng.randint(0, 1 << 30)
    )
    return dci.verdict


def _rate(scenario: str, n: int, trials: int, margin: float, verdict: str, seed: int) -> float:
    rng = random.Random(seed)
    hits = sum(1 for _ in range(N_SIM) if _experiment(scenario, n, trials, margin, rng) == verdict)
    return hits / N_SIM


def main() -> None:
    ns = [10, 20, 40, 80]
    trials_grid = [1, 5, 20]
    print(f"P(earn 'equivalent') under a TRUE NULL, by problems n x trials  (N_sim={N_SIM})\n")
    for scenario in ("het_null", "hom_null"):
        for margin in (0.25, 0.10):
            label = "heterogeneous" if scenario == "het_null" else "homogeneous"
            print(f"--- {label} null, margin=±{margin:.2f} ---")
            print("   n  | " + "  ".join(f"trials={t:<2d}" for t in trials_grid))
            for n in ns:
                cells = [
                    _rate(scenario, n, t, margin, EQUIVALENT, seed=1000 + n + t)
                    for t in trials_grid
                ]
                print(f"  {n:3d} | " + "  ".join(f"   {c:4.2f}  " for c in cells))
            print()

    print(
        "For contrast — P(earn 'superior') under a TRUE +0.15 effect, margin=±0.10 (equivalence's mirror):"
    )
    print("   n  | " + "  ".join(f"trials={t:<2d}" for t in trials_grid))
    for n in ns:
        cells = [_rate("diff", n, t, 0.10, "superior", seed=2000 + n + t) for t in trials_grid]
        print(f"  {n:3d} | " + "  ".join(f"   {c:4.2f}  " for c in cells))


if __name__ == "__main__":
    main()
