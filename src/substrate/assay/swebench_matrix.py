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
from ..reference._models import OllamaResponder, Responder
from ..topologies.swebench_solver.assemble import swebench_repair_topology
from ..topologies.swebench_solver.records import SelectedPatch
from .suite import Arm, Case, Suite
from .swebench import swebench_record_oracle
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
        b.producer_kind("solve", schemas=[SelectedPatch], schema_version=1,
                        factory=_solve_factory(solve), deterministic=False)
        b.initial("solve", input=None)
        b.termination(api.any_of(
            api.threshold_count("SelectedPatch", 1),
            api.quiescence_with_watchdog(seconds=3600.0),
        ))

    return topo


def host_arm(name: str, role: str, *, model: str, max_tokens: int = 2048) -> Arm:
    """Host backend as an Arm (model picks a file, edits it, host_clone -> workspace_diff)."""
    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst, resp = case.ground_truth, OllamaResponder(model, max_tokens=max_tokens)
        return _backend_topology(lambda: solve_on_host(inst, resp))
    return Arm(name=name, role=role, build=build)


def container_arm(name: str, role: str, *, model: str, max_steps: int = 8, max_tokens: int = 2048) -> Arm:
    """Container backend as an Arm (read/edit/bash agent loop in the locked eval container)."""
    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst, resp = case.ground_truth, OllamaResponder(model, max_tokens=max_tokens)
        return _backend_topology(lambda: solve_in_container(inst, resp, max_steps=max_steps))
    return Arm(name=name, role=role, build=build)


def repair_arm(name: str, role: str, *, model: str, n: int = 3, max_rounds: int = 2,
               max_tokens: int = 2048) -> Arm:
    """A REAL substrate coding topology as an Arm: localize -> best-of-N SEARCH/REPLACE repair -> emit the
    first patch that applied (`swebench_repair_topology`). The substrate producers DO the coding — this is
    not a function in a shell. `build` clones the repo at base_commit (I/O at build, env-gated) and wires
    the topology; the per-candidate validator clones from it and produces the git diff."""
    def build(case: Case) -> Callable[[api.TopologyBuilder], None]:
        inst = case.ground_truth
        clone = host_clone(f"https://github.com/{inst['repo']}", inst["base_commit"])
        files = subprocess.run(
            ["git", "-C", clone, "ls-files"], capture_output=True, text=True
        ).stdout.split()
        responders: list[Responder] = [OllamaResponder(model, max_tokens=max_tokens) for _ in range(n)]
        return swebench_repair_topology(
            responders=responders, base_checkout=clone, issue=str(inst["problem_statement"]),
            repo_skeleton="\n".join(files), known_files=set(files), n=n, max_rounds=max_rounds,
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
        Case(case_id=safe_case_id(inst["instance_id"]), payload={}, ground_truth=inst) for inst in instances
    )
    return Suite(
        name=name, version=version, cases=cases, arms=tuple(arms),
        oracle=swebench_record_oracle(report_root=report_root, dataset_name=dataset_name),
        control_arm=control_arm, primary_metric="resolved",
        null_rule=(
            "primary endpoint = instances resolved (official held-out grade). A non-control Arm is "
            "compared to the control by paired McNemar + a two-level bootstrap on Delta-pass^k; "
            "'equivalent' requires the CI inside +/-margin AND n at the power floor (~90 at margin .20) — "
            "below it the verdict is 'underpowered', never read as equivalence."
        ),
        equivalence_margin=equivalence_margin, pass_k=pass_k,
    )


__all__ = ["host_arm", "container_arm", "repair_arm", "swebench_matrix_suite"]
