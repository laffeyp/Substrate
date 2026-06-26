"""Suite / Case / Arm — what an assay run executes (Sprint 4 inputs).

A Suite is the PRE-REGISTERED benchmark: a frozen Case set, the Arm matrix (the control comparison),
the Oracle that grades every Case, the control Arm the paired comparison is measured against, and the
single pre-registered primary endpoint + the published null-acceptance rule. Pre-registration is the
anti-cherry-pick discipline (design §4.2/4.3): the Cases and the headline are fixed before any run, so
neither the task set nor the metric can be chosen after seeing results.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from msgspec import Struct

from .. import api
from .oracle import Oracle

# Arm names and Case ids become path segments when the control plane mints a run root
# (`{arm}__{case}__t{trial}`), so they must be filesystem-safe AND free of the `__` / `/` that would
# let two different (arm, case) pairs collide on one root or escape the run dir. Restrict to a safe
# token charset at construction — the enforce-in-data discipline, not a runtime surprise.
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._+-]+$")


def _check_token(value: str, what: str) -> None:
    # forbid '/' (path traversal) via the charset, and '__' (the run-root segment separator) so two
    # different (arm, case) pairs can never collide on one root.
    if not _SAFE_TOKEN.match(value) or "__" in value:
        raise ValueError(
            f"{what} must match [A-Za-z0-9._+-]+ and contain no '__' "
            f"(it becomes a '__'-joined run-root path segment); got {value!r}"
        )


# A topology is a function of the builder (the runtime calls it once at run start). Same shape every
# shipped topology uses; an Arm builds one of these per Case.
Topology = Callable[[api.TopologyBuilder], None]

# Arm roles — the control matrix (design §2): the full topology, an ablation rung, the single-model
# baseline (exactly one Arm is the control), and a placebo (a no-op variant that should NOT move the
# metric). The role is documentation + lets a reader read the matrix; the comparison is by name.
FULL = "full"
ABLATION = "ablation"
BASELINE = "baseline"
PLACEBO = "placebo"
_ROLES = frozenset({FULL, ABLATION, BASELINE, PLACEBO})


class Case(Struct, frozen=True):
    """One benchmark problem: an id, the opaque `payload` an Arm's `build` uses to configure its
    topology for this problem, and the `ground_truth` the Oracle grades the run against."""

    case_id: str
    payload: dict[str, Any]
    ground_truth: Any


@dataclass(frozen=True)
class Arm:
    """A configured topology-or-baseline run on each Case. `role` places it in the control matrix;
    `build(case)` returns the topology to run for that Case. Exactly one Arm in a Suite is the
    control (named by Suite.control_arm) — every other Arm's result is reported as a delta against it."""

    name: str
    role: str
    build: Callable[[Case], Topology]

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise ValueError(f"Arm role must be one of {sorted(_ROLES)}; got {self.role!r}")
        _check_token(self.name, "Arm.name")


@dataclass(frozen=True)
class Suite:
    """A named, versioned, pre-registered benchmark. `cases` is frozen before any run; `arms` is the
    control matrix; `oracle` grades every Case; `control_arm` names the baseline the comparison is
    paired against; `primary_metric` is the single pre-registered endpoint; `null_rule` is the
    published rule under which a null result is reported (so 'no measured benefit' is reachable, not
    hidden by degrees of freedom — design §4.3)."""

    name: str
    version: str
    cases: tuple[Case, ...]
    arms: tuple[Arm, ...]
    oracle: Oracle
    control_arm: str
    primary_metric: str
    null_rule: str
    # the TOST equivalence margin: |Δ-pass^k| inside ±margin reads as "no meaningful difference" (a
    # REAL null, not mere non-significance). Pre-registered like everything else.
    equivalence_margin: float = 0.1
    # the pass^k reliability level (1 = pass@1; k>1 needs trials >= k — the consistency estimand).
    pass_k: int = 1

    def __post_init__(self) -> None:
        if not self.cases:
            raise ValueError("a Suite needs at least one Case")
        if not self.arms:
            raise ValueError("a Suite needs at least one Arm")
        names = [a.name for a in self.arms]
        if len(set(names)) != len(names):
            raise ValueError(f"Arm names must be unique; got {names}")
        if self.control_arm not in names:
            raise ValueError(f"control_arm {self.control_arm!r} is not among arms {names}")
        for case in self.cases:
            _check_token(case.case_id, "Case.case_id")
        if self.equivalence_margin <= 0:
            raise ValueError("equivalence_margin must be > 0 (the TOST margin)")
        if self.pass_k < 1:
            raise ValueError("pass_k must be >= 1")
