"""The SWE-bench matrix — run the backends as Arms over a frozen set and compare them with the real stats.

Each backend (host / container) becomes a one-producer substrate topology: a producer runs the backend's
solve and emits its patch as a `SelectedPatch`. That makes them genuine Arms, so the existing assay control
plane drives everything unchanged — `run_suite` runs each (Arm × Case × Trial), `swebench_record_oracle`
grades the SelectedPatch via the official harness, and `build_report` gives the paired McNemar / two-level
bootstrap + the equivalence power floor (n<~90 can't claim equivalence). The first DEFENSIBLE comparison,
not n=5 anecdotes.

Token/time note: these arms call the model directly (not the metered Responder path), so no `ModelUsage`
lands on the record yet — the report's token totals are 0 for them; the real wall-clock (`elapsed_ms`) IS
measured (it times the whole solve). Wiring metered calls is a later refinement.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from .. import api
from ..adapters import OllamaResponder, Responder
from ..topologies.swebench_solver.assemble import swebench_repair_topology
from ..topologies.swebench_solver.records import SelectedPatch
from .suite import Arm, Case, Suite
from .swebench import FirewallViolation, firewall_check, swebench_record_oracle
from .swebench_agent import solve_in_container
from .swebench_host import solve_on_host
from .swebench_suite import safe_case_id
from .swebench_workspace import host_clone

_Factory = Callable[[], Any]


def _solve_factory(solve: Callable[[], str]) -> _Factory:
    """A producer that runs `solve()` (a blocking backend call, off-thread) and emits its patch as a
    SelectedPatch. The same factory shape the swebench_solver producers use."""

    async def produce(_inp: Any) -> AsyncIterator[SelectedPatch]:
        patch = await asyncio.to_thread(solve)
        yield SelectedPatch(slot=0, model_patch=patch, reason="backend")

    return lambda: produce


def _backend_topology(solve: Callable[[], str]) -> Callable[[api.TopologyBuilder], None]:
    """A trivial one-producer topology that emits the backend's patch as a SelectedPatch. Terminates the
    instant the patch lands; a watchdog backstops a wedge."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "solve",
            schemas=[SelectedPatch],
            schema_version=1,
            factory=_solve_factory(solve),
            deterministic=False,
        )
        b.initial("solve", input=None)
        b.termination(
            api.any_of(
                api.threshold_count("SelectedPatch", 1),
                api.quiescence_with_watchdog(seconds=3600.0),
            )
        )

    return topo


def host_arm(name: str, role: str, *, model: str, max_tokens: int = 2048) -> Arm:
    """Host backend as an Arm (model picks a file, edits it, host_clone -> workspace_diff)."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst, resp = case.ground_truth, OllamaResponder(model, max_tokens=max_tokens)
        return _backend_topology(lambda: solve_on_host(inst, resp))

    return Arm(name=name, role=role, build=build)


def container_arm(
    name: str, role: str, *, model: str, max_steps: int = 8, max_tokens: int = 2048
) -> Arm:
    """Container backend as an Arm (read/edit/bash agent loop in the locked eval container)."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst, resp = case.ground_truth, OllamaResponder(model, max_tokens=max_tokens)
        return _backend_topology(lambda: solve_in_container(inst, resp, max_steps=max_steps))

    return Arm(name=name, role=role, build=build)


def _build_repair_arm_from_models(
    case: Case,
    models: Sequence[str],
    *,
    n: int,
    max_rounds: int,
    max_tokens: int,
) -> Callable[[api.TopologyBuilder], None]:
    """Common body for every repair-topology-based arm (sprint 159). Firewall-checks the instance,
    clones the base repo, builds one `OllamaResponder` per slot (models cycled round-robin), and
    returns the wired `swebench_repair_topology`. Sole seam so a new arm shape (ensemble, matched
    compute, no-correction) is one factory call over the four levers — models, n, max_rounds,
    max_tokens — never a re-implementation of the firewall/clone/wire boilerplate."""
    inst = case.ground_truth
    ok, reason = firewall_check(inst)
    if not ok:
        raise FirewallViolation(str(inst.get("instance_id", "?")), reason)
    clone = host_clone(f"https://github.com/{inst['repo']}", inst["base_commit"])
    files = subprocess.run(
        ["git", "-C", clone, "ls-files"], capture_output=True, text=True
    ).stdout.split()
    responders: list[Responder] = [
        OllamaResponder(models[i % len(models)], max_tokens=max_tokens) for i in range(n)
    ]
    return swebench_repair_topology(
        responders=responders,
        base_checkout=clone,
        issue=str(inst["problem_statement"]),
        repo_skeleton="\n".join(files),
        known_files=set(files),
        n=n,
        max_rounds=max_rounds,
    )


def single_draft_baseline_arm(
    name: str, role: str = "baseline", *, model: str, max_tokens: int = 2048
) -> Arm:
    """Arm #1 of the sprint 159 five-arm matrix — one model, N=1, no correction (max_rounds=1).
    The floor: what a single draft from a single model produces without any of the substrate's
    machinery. Every gain over this is a substrate contribution."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_repair_arm_from_models(
            case, [model], n=1, max_rounds=1, max_tokens=max_tokens
        )

    return Arm(name=name, role=role, build=build)


def n_drafts_no_correction_arm(
    name: str,
    role: str = "ablation",
    *,
    model: str,
    n: int = 3,
    max_tokens: int = 2048,
) -> Arm:
    """Arm #2 — one model, N drafts, NO correction round. Isolates the value of drawing multiple
    candidates from a single model (temperature diversity) from the value of the correction
    loop. Delta vs. `single_draft_baseline_arm` = value of best-of-N; delta vs.
    `n_drafts_repair_arm` = value of the correction round."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_repair_arm_from_models(
            case, [model], n=n, max_rounds=1, max_tokens=max_tokens
        )

    return Arm(name=name, role=role, build=build)


def n_drafts_repair_ensemble_arm(
    name: str,
    role: str = "full",
    *,
    models: Sequence[str],
    max_rounds: int = 2,
    max_tokens: int = 2048,
) -> Arm:
    """Arm #4 — N drafts (N = len(models)) from a HETEROGENEOUS ensemble, correction on. The
    hypothesis: distinct models make distinct mistakes, so an ensemble's best-of-N samples a
    wider hypothesis space than N temperature-samples from one model (per KIT_DIARY finding on
    the R-19 thinking trio). Compared against `n_drafts_repair_arm` (one model at N=len(models))
    to isolate the ensemble contribution — same N, same rounds, only the model set differs."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_repair_arm_from_models(
            case, list(models), n=len(models), max_rounds=max_rounds, max_tokens=max_tokens
        )

    return Arm(name=name, role=role, build=build)


def baseline_matched_compute_arm(
    name: str,
    role: str = "baseline",
    *,
    model: str,
    k_calls: int,
    max_tokens: int = 2048,
) -> Arm:
    """Arm #5 — the compute-matched baseline (per Kapoor & Narayanan 2024 "AI Agents That
    Matter"). Runs a SINGLE STRONG MODEL at K attempts where K is chosen so total model_calls
    roughly matches the ensemble arm's median. If the ensemble arm beats the single-model
    baseline while consuming the same compute, that's a mechanism win; if the compute-matched
    baseline catches up, the ensemble's advantage was compute-purchased, not mechanism-driven.

    Operationalisation: N=K single-model best-of-N with no correction — K attempts, first
    applyable wins, same SELECT pipeline as every other arm. NOT literally "oracle picks best of
    K" (which would require an oracle-in-arm pattern the current Suite contract doesn't
    support); Sprint 160's writeup names the operational choice alongside the number. `k_calls`
    is passed in — the confirmatory runner derives it from the ensemble arm's median model_calls
    per case, so it's a data-driven pre-reg parameter (Sprint 160 freezes it)."""
    if k_calls < 1:
        raise ValueError(f"k_calls must be >= 1; got {k_calls}")

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_repair_arm_from_models(
            case, [model], n=k_calls, max_rounds=1, max_tokens=max_tokens
        )

    return Arm(name=name, role=role, build=build)


def repair_arm(
    name: str, role: str, *, model: str, n: int = 3, max_rounds: int = 2, max_tokens: int = 2048
) -> Arm:
    """A REAL substrate coding topology as an Arm: localize -> best-of-N SEARCH/REPLACE repair -> emit the
    first patch that applied (`swebench_repair_topology`). The substrate producers DO the coding — this is
    not a function in a shell. `build` clones the repo at base_commit (I/O at build, env-gated) and wires
    the topology; the per-candidate validator clones from it and produces the git diff.

    Sprint 148 — the firewall is called at build. Every other arm in this module hits its firewall via the
    backend it wraps (`solve_on_host` at swebench_host.py:58, `solve_in_container` at
    swebench_agent.py:88); this one wraps the topology directly, so the guard has to live here or a leaky
    instance silently reaches the drafters. Parity with the other arm-building paths — same discipline."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        # Sprint 159: kept as-is (backward-compat entrypoint) but body now delegates to the
        # shared `_build_repair_arm_from_models` factory. Semantically identical to the
        # pre-159 shape: one model, N slots, correction on.
        return _build_repair_arm_from_models(
            case, [model], n=n, max_rounds=max_rounds, max_tokens=max_tokens
        )

    return Arm(name=name, role=role, build=build)


def swebench_matrix_suite(
    instances: Sequence[dict[str, Any]],
    arms: Sequence[Arm],
    *,
    report_root: str,
    dataset_name: str,
    control_arm: str,
    name: str = "swebench-matrix",
    version: str = "0.1",
    equivalence_margin: float = 0.2,
    pass_k: int = 1,
) -> Suite:
    """A frozen SWE-bench Suite over the backend Arms, graded by the record oracle. Cases carry the instance
    as ground_truth; the case_id is the path-safe label."""
    cases = tuple(
        Case(case_id=safe_case_id(inst["instance_id"]), payload={}, ground_truth=inst)
        for inst in instances
    )
    return Suite(
        name=name,
        version=version,
        cases=cases,
        arms=tuple(arms),
        oracle=swebench_record_oracle(report_root=report_root, dataset_name=dataset_name),
        control_arm=control_arm,
        primary_metric="resolved",
        null_rule=(
            "primary endpoint = instances resolved (official held-out grade). A non-control Arm is "
            "compared to the control by paired McNemar + a two-level bootstrap on Delta-pass^k; "
            "'equivalent' requires the CI inside +/-margin AND n at the power floor (~90 at margin .20) — "
            "below it the verdict is 'underpowered', never read as equivalence."
        ),
        equivalence_margin=equivalence_margin,
        pass_k=pass_k,
    )


__all__ = [
    "baseline_matched_compute_arm",
    "container_arm",
    "host_arm",
    "n_drafts_no_correction_arm",
    "n_drafts_repair_ensemble_arm",
    "repair_arm",
    "single_draft_baseline_arm",
    "swebench_matrix_suite",
]
