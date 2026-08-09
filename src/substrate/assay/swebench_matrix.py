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
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, cast

from .. import api
from ..adapters import OllamaResponder, Responder
from ..topologies.swebench_solver.records import SelectedPatch
from .suite import Arm, Case, Suite
from .swebench import FirewallViolation, firewall_check, swebench_record_oracle
from .swebench_agent import solve_in_container
from .swebench_host import solve_on_host
from .swebench_suite import PreparedPayload, safe_case_id, solver_topology_from_payload

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


def _build_solver_arm_from_payload(
    case: Case,
    models: Sequence[str],
    *,
    n: int,
    max_rounds: int,
    max_tokens: int,
) -> Callable[[api.TopologyBuilder], None]:
    """Common body for every sprint-159 matrix arm. F1 fix (review 2026-08-08): reads the
    `PreparedPayload` off `case.payload` and builds the FULL `swebench_solver_topology` via
    `solver_topology_from_payload` — so sprint 155's base-fails-first repro validator, sprint
    158's repro 2x2, and the whole `select_exec` + `select.select_patch` rerank ARE ACTIVE on
    every matrix arm. Pre-F1 the helper called `swebench_repair_topology` (no test execution,
    no reranking), making the confirmatory measure repair alone; that machinery was dead code
    in the planned Pass 2.

    Requires the Case to have gone through `prepare_swebench_case` upstream so `case.payload`
    is a populated PreparedPayload — the confirmatory runner already does this at line 303-310.
    A caller of `swebench_matrix_suite` that passes raw Cases with empty payload will get a
    KeyError at build time (fail loud rather than silently degrade to the pre-F1 behaviour).

    Firewall check remains at build time — the payload already came from a firewall-clean
    upstream call, but callers can be belt-and-braces without cost.
    """
    inst = case.ground_truth
    ok, reason = firewall_check(inst)
    if not ok:
        raise FirewallViolation(str(inst.get("instance_id", "?")), reason)
    payload = cast(PreparedPayload, case.payload)
    if "base_checkout" not in payload:
        raise ValueError(
            f"matrix arm on case {case.case_id!r}: `case.payload` is empty. Cases fed into a "
            "sprint-159 matrix arm must go through `prepare_swebench_case` upstream so the "
            "PreparedPayload is populated (image, spec, regression_files, passed_at_base, ...)."
        )
    responders: list[Responder] = [
        OllamaResponder(models[i % len(models)], max_tokens=max_tokens) for i in range(n)
    ]
    return solver_topology_from_payload(payload, responders, n=n, max_rounds=max_rounds)


def single_draft_baseline_arm(
    name: str, role: str = "baseline", *, model: str, max_tokens: int = 2048
) -> Arm:
    """Arm #1 of the sprint 159 five-arm matrix — one model, N=1, no correction (max_rounds=1).
    The floor: what a single draft from a single model produces without any of the substrate's
    machinery. Every gain over this is a substrate contribution."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_solver_arm_from_payload(
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
        return _build_solver_arm_from_payload(
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
        return _build_solver_arm_from_payload(
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
        return _build_solver_arm_from_payload(
            case, [model], n=k_calls, max_rounds=1, max_tokens=max_tokens
        )

    return Arm(name=name, role=role, build=build)


def repair_arm(
    name: str, role: str, *, model: str, n: int = 3, max_rounds: int = 2, max_tokens: int = 2048
) -> Arm:
    """A substrate coding topology as an Arm — one model, N slots, correction on. F1 fix (review
    2026-08-08): now routes through `_build_solver_arm_from_payload`, so the arm runs the FULL
    `swebench_solver_topology` (localize + repair + repro_gen + repro_base_validate + select_exec
    + `select.select_patch` rerank), not the pre-F1 repair-only path. Kept as the backward-compat
    entrypoint but the "repair" in the name is now historical — this is the solver at these
    settings, same as every sprint-159 matrix sibling.

    Sprint 148: firewall check at build time — parity with the other matrix arms."""

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_solver_arm_from_payload(
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
