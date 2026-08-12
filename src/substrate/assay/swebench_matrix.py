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
import os

from ..adapters import OllamaResponder, ProviderQuota, RateLimitedResponder, Responder
from ..adapters.rate_limit import OllamaQuota
from ..topologies.swebench_solver.records import SelectedPatch
from .suite import Arm, Case, Suite
from .swebench import FirewallViolation, firewall_check, swebench_record_oracle
from .swebench_agent import solve_in_container
from .swebench_host import solve_on_host
from ..topologies.swebench_solver.assemble import swebench_repair_topology
from .swebench_suite import PreparedPayload, safe_case_id

_Factory = Callable[[], Any]


def _ollama_quota_from_env() -> ProviderQuota:
    """Read SWEBENCH_OLLAMA_TIER and return the matching ProviderQuota. Default `local`
    (16 concurrent per model) because unset env means "no cloud tier declared, we're
    running locally." Cloud fires MUST set SWEBENCH_OLLAMA_TIER=pro|max explicitly so
    the shim caps concurrency at the paid tier's actual limit. Design step 4."""
    tier = os.environ.get("SWEBENCH_OLLAMA_TIER", "local").lower()
    if tier == "free":
        return OllamaQuota.free()
    if tier == "pro":
        return OllamaQuota.pro()
    if tier == "max":
        return OllamaQuota.max_tier()
    if tier == "local":
        return OllamaQuota.local()
    raise SystemExit(
        f"SWEBENCH_OLLAMA_TIER={tier!r} unknown — must be one of free | pro | max | local."
    )


def _wrap_ollama(model: str, quota: ProviderQuota, max_tokens: int) -> Responder:
    """Return an OllamaResponder wrapped in RateLimitedResponder so the per-(provider,
    model) semaphore caps concurrent in-flight requests at the tier's declared limit.
    Every arm's construction routes through here so wrappers for the same model share
    one gate — design DESIGN-2026-08-11-responder-rate-limit-shim.md §"Two things the
    shim must do"."""
    inner = OllamaResponder(model, max_tokens=max_tokens)
    return RateLimitedResponder(inner, key=f"ollama:{model}", quota=quota)


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
    repro_k: int = 1,
    include_test_selection: bool = False,
) -> Callable[[api.TopologyBuilder], None]:
    """Common body for every sprint-159 matrix arm.

    Design v3 §"The five-arm matrix" (ratified 2026-08-10): every arm builds
    `swebench_repair_topology` — the LIGHT topology (localize + best-of-N repair + emit the
    first patch that applied). `select_exec` and the whole test-execution SELECT apparatus
    are OUT: they duplicated the grader's work in-topology, doubled per-cell Docker minutes,
    and produced the 517-silent-fails shape the 2026-08-10 postmortem records. The graded
    verdict for the matrix is what the OFFICIAL swebench harness reports; the topology's job
    is producing a candidate patch, not grading it.

    `include_test_selection=True` opts back into the heavy
    `swebench_solver_topology_with_test_selection` for a caller that genuinely wants
    in-topology reranking (a follow-up two-phase runner, not the confirmatory). Default False.
    The five confirmatory arm factories pass False explicitly; a matrix test asserts
    every built topology's producer_kinds omit `select_exec`.

    Requires the Case to have gone through `prepare_swebench_case` upstream so `case.payload`
    is a populated PreparedPayload. Firewall check at build is belt-and-braces on top of
    the upstream `prepare_swebench_case` firewall pass; no cost, third defense layer.
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
    quota = _ollama_quota_from_env()
    responders: list[Responder] = [
        _wrap_ollama(models[i % len(models)], quota, max_tokens) for i in range(n)
    ]
    if include_test_selection:
        # Heavy path: kept behind an explicit opt-in for a future two-phase runner. The
        # confirmatory never takes this branch.
        from .swebench_suite import solver_topology_from_payload

        return solver_topology_from_payload(
            payload, responders, n=n, max_rounds=max_rounds, repro_k=repro_k
        )
    return swebench_repair_topology(
        responders=responders,
        base_checkout=str(payload["base_checkout"]),
        issue=str(payload["issue"]),
        repo_skeleton=str(payload["repo_skeleton"]),
        known_files=set(payload["known_files"]),
        n=n,
        max_rounds=max_rounds,
        watchdog_seconds=900.0,
    )


def swebench_repair_arm(
    name: str,
    *,
    models: Sequence[str],
    n: int,
    max_rounds: int,
    role: str = "full",
    max_tokens: int = 2048,
    repro_k: int = 1,
    include_test_selection: bool = False,
) -> Arm:
    """The parametric SWE-bench arm factory (Move 2, holistic review 2026-08-10; ratified
    2026-08-11). Every arm that wraps `swebench_repair_topology` at different (models, n,
    max_rounds) is a call to this factory. Different-topology arms (`container_arm`,
    `host_arm`) get their own factories because they build a structurally distinct topology.

    Pre-collapse the module carried five near-identical factories (single_draft_baseline,
    n_drafts_no_correction, n_drafts_repair, n_drafts_repair_ensemble, baseline_matched_compute)
    that each closed over `_build_solver_arm_from_payload` with different constants; the runner
    composed them by name into the Sprint 160 matrix. The factories now stand as thin wrappers
    below for backward-compat; new arms of the same shape should call this factory directly
    (or add a row to the confirmatory runner's ARMS table).

    `n` must be >= 1 — a zero-slot arm has nothing to draft. `repro_k` is the parallel
    reproduction-sample count per candidate (F4 fix, review 2026-08-08). `include_test_selection`
    opts into the heavy `swebench_solver_topology_with_test_selection` (not what any Sprint 160
    confirmatory arm takes; kept for a future two-phase runner)."""
    if n < 1:
        raise ValueError(f"n must be >= 1; got {n}")

    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        return _build_solver_arm_from_payload(
            case,
            list(models),
            n=n,
            max_rounds=max_rounds,
            max_tokens=max_tokens,
            repro_k=repro_k,
            include_test_selection=include_test_selection,
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
    "container_arm",
    "host_arm",
    "swebench_matrix_suite",
    "swebench_repair_arm",
]
