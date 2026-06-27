"""ASSEMBLE — the full swebench_solver topology (sprint 141): LOCALIZE -> REPAIR -> SELECT, one
event-sourced graph terminating on SelectedPatch.

Reuses the shared best_of_n factories (seeder, select-first judge) + records + the swebench phase
factories (localizer, repair drafter/validator, select logic + the run-and-observe test-exec). The wiring
is bespoke — swebench has pre/post phases the all-in-one `best_of_n_correction` builder doesn't model:
LOCALIZE seeds the loop (instead of an `initial` seeder), and SELECT runs after the loop's Solved.

  localizer(initial) -EditLocations-> seed -> [best-of-N: drafter -> validator(applier) -> judge] -Solved->
  select_exec(run-and-observe: tests per applied patch) -TestResults-> selector(rerank) -> SelectedPatch
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

from ... import api
from ...reference._models import ModelUsage, Responder
from ..best_of_n import seeder_factory, select_first_judge_factory
from ..best_of_n.contracts import Candidate, Draft, Exhausted, Solved, Verdict
from .localize import localizer_factory
from .records import (
    AppliedPatch,
    EditLocations,
    Reproduction,
    ReproductionTest,
    SelectedPatch,
    SuspectFiles,
    TestResults,
)
from .repair import repair_drafter_factory, repair_validate_factory
from .reproduction import repro_generator_factory
from .select import select_patch
from .select_exec import TestRunner, run_one

_Factory = Callable[[], Any]


def _build_edit_context(base_checkout: str, targets: tuple[str, ...]) -> str:
    """Inline the localized files' current content so the drafter edits against real bytes (the
    read_declared_files_for_diff idea). v1: targets are file paths (`file` or `file::elem` / `file:line`)."""
    parts: list[str] = []
    for t in targets:
        path = t.split("::")[0].split(":")[0]
        full = os.path.join(base_checkout, path)
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            content = "(file not found)"
        parts.append(f"# path: {path}\n```\n{content}\n```")
    return "\n\n".join(parts)


def _round_verdicts(ctx: api.TriggerContext, rnd: int) -> list[dict[str, Any]]:
    return [v for v in ctx.views["verdicts"].value() if int(v["round"]) == rnd]


def _round_applied(ctx: api.TriggerContext, rnd: int) -> list[dict[str, Any]]:
    return [a for a in ctx.views["applied"].value() if int(a["round"]) == rnd]


def _select_exec_factory(
    runner: TestRunner,
    regression: str | Callable[[str], Any],
    passed_at_base: frozenset[str] | None,
) -> _Factory:
    """Triggered on Solved: run the tests for EVERY applied patch of the solved round, concurrently; yield
    a TestResults per patch. The run-and-observe Docker seam (deterministic=False). The generated
    reproduction test (`repro_code`, from the input) is run per patch too. `passed_at_base` (the instance's
    base-passing test ids) switches the signal to `regression_held` — None falls back to whole-run
    `regression_passed`. ALWAYS yields exactly len(patches): a single patch's runner failure (the real
    DockerTestRunner WILL raise — container error, OOM, timeout) becomes a FAILED TestResults, never an
    unraised gather exception that emits ZERO results and stalls the barrier (review #62)."""

    async def run_all(inp: Any) -> AsyncIterator[TestResults]:
        patches = list(inp.get("applied", [])) if hasattr(inp, "get") else []
        repro_code = str(inp.get("repro_code", "")) if hasattr(inp, "get") else ""
        outcomes = await asyncio.gather(
            *[
                run_one(
                    runner,
                    regression,
                    repro_code,
                    int(p["slot"]),
                    str(p["model_patch"]),
                    passed_at_base=passed_at_base,
                )
                for p in patches
            ],
            return_exceptions=True,
        )
        for p, res in zip(patches, outcomes):
            if isinstance(res, BaseException):
                yield TestResults(
                    slot=int(p["slot"]),
                    regression_passed=False,
                    reproduction=Reproduction.OTHER,
                    summary=f"runner error: {type(res).__name__}: {str(res)[:160]}",
                )
            else:
                yield res

    return lambda: run_all


def _selector_factory() -> _Factory:
    """The deterministic rerank (pure given the recorded results): reconstruct the AppliedPatches +
    TestResults from the trigger input and emit the SelectedPatch."""

    async def select(inp: Any) -> AsyncIterator[SelectedPatch]:
        applied = [
            AppliedPatch(round=int(a["round"]), slot=int(a["slot"]), model_patch=str(a["model_patch"]), creates_file=bool(a["creates_file"]))
            for a in (inp.get("applied", []) if hasattr(inp, "get") else [])
        ]
        results = {
            int(r["slot"]): TestResults(
                slot=int(r["slot"]),
                regression_passed=bool(r["regression_passed"]),
                reproduction=Reproduction(r["reproduction"]),
                summary=str(r["summary"]),
            )
            for r in (inp.get("results", []) if hasattr(inp, "get") else [])
        }
        sel = select_patch(applied, results)
        if sel is not None:
            yield sel

    return lambda: select


def swebench_solver_topology(
    *,
    responders: list[Responder],
    base_checkout: str,
    issue: str,
    repo_skeleton: str,
    known_files: set[str],
    runner: TestRunner,
    regression_command: str | Callable[[str], Any],
    passed_at_base: frozenset[str] | None = None,
    n: int = 3,
    max_rounds: int = 2,
    top_k: int = 5,
    watchdog_seconds: float = 60.0,
) -> Callable[[api.TopologyBuilder], None]:
    """The whole solver. `responders[0]` localizes; `responders` (per slot) draft. `runner` runs tests in
    the instance env (the real DockerTestRunner, or a stand-in). `regression_command` is a static command
    (same set for every candidate) OR a per-candidate planner (model_patch -> firewall-clean command, e.g.
    `make_regression_planner` — the proximity picker over the checkout). `passed_at_base` (the instance's
    base-passing test ids, from one base run) switches SELECT to the passed-at-base filter — required on
    repos with pre-existing base failures (flask). Terminates on SelectedPatch or Exhausted."""

    def topo(b: api.TopologyBuilder) -> None:
        # LOCALIZE
        b.producer_kind("localizer", schemas=[SuspectFiles, EditLocations, ModelUsage], schema_version=1,
                        factory=localizer_factory(responders[0], issue, repo_skeleton, known_files, top_k=top_k),
                        deterministic=False)
        b.initial("localizer", input=None)
        # the reproduction-test generator runs once at the start (it only needs the issue); SELECT reads
        # its output to check which patches resolve the issue.
        b.producer_kind("repro_gen", schemas=[ReproductionTest, ModelUsage], schema_version=1,
                        factory=repro_generator_factory(responders[0], issue), deterministic=False)
        b.initial("repro_gen", input=None)
        b.view("reproduction", api.KindBuffer("ReproductionTest"))
        b.view("edit_locations", api.KindBuffer("EditLocations"))
        b.view("verdicts", api.KindBuffer("Verdict"))
        b.view("applied", api.KindBuffer("AppliedPatch"))
        b.view("test_results", api.KindBuffer("TestResults"))
        b.view("solved", api.KindBuffer("Solved"))

        # REPAIR (shared loop factories, swebench-seeded)
        b.producer_kind("seeder", schemas=[Draft], schema_version=1, factory=seeder_factory(n), deterministic=False)
        b.producer_kind("drafter", schemas=[Candidate, ModelUsage], schema_version=1,
                        factory=repair_drafter_factory(responders, spec=issue), deterministic=False)
        b.producer_kind("validator", schemas=[Verdict, AppliedPatch], schema_version=1,
                        factory=repair_validate_factory(base_checkout), deterministic=False)
        b.producer_kind("judge", schemas=[Solved, Draft, Exhausted], schema_version=1,
                        factory=select_first_judge_factory(n, max_rounds), deterministic=False)

        # SELECT
        b.producer_kind("select_exec", schemas=[TestResults], schema_version=1,
                        factory=_select_exec_factory(runner, regression_command, passed_at_base),
                        deterministic=False)
        b.producer_kind("selector", schemas=[SelectedPatch], schema_version=1, factory=_selector_factory(),
                        deterministic=False)

        # LOCALIZE -> seed the loop
        b.trigger("seed", subscription=api.Subscription(kinds=frozenset({"EditLocations"})),
                  predicate=lambda ctx: True, starts="seeder", input_builder=lambda ctx: None, policy=api.PerEvent())
        # draft per Draft, with edit_context built from the localized targets + the repo
        b.trigger("draft", subscription=api.Subscription(kinds=frozenset({"Draft"})), predicate=lambda ctx: True,
                  starts="drafter",
                  input_builder=lambda ctx: {
                      "round": int(ctx.event.payload["round"]),
                      "slot": int(ctx.event.payload["slot"]),
                      "context": ctx.event.payload["context"],
                      "edit_context": _build_edit_context(
                          base_checkout,
                          tuple(ctx.views["edit_locations"].value()[-1]["targets"]) if ctx.views["edit_locations"].value() else (),
                      ),
                  }, policy=api.PerEvent())
        b.trigger("validate", subscription=api.Subscription(kinds=frozenset({"Candidate"})), predicate=lambda ctx: True,
                  starts="validator",
                  input_builder=lambda ctx: {"round": int(ctx.event.payload["round"]), "slot": int(ctx.event.payload["slot"]), "response": ctx.event.payload["response"]},
                  policy=api.PerEvent())
        b.trigger("judge", subscription=api.Subscription(kinds=frozenset({"Verdict"})),
                  predicate=lambda ctx: len(_round_verdicts(ctx, int(ctx.event.payload["round"]))) >= n, starts="judge",
                  input_builder=lambda ctx: {"round": int(ctx.event.payload["round"]), "verdicts": _round_verdicts(ctx, int(ctx.event.payload["round"]))},
                  policy=api.PerEvent())
        # Solved -> run tests for every applied patch of that round
        b.trigger("select_exec", subscription=api.Subscription(kinds=frozenset({"Solved"})), predicate=lambda ctx: True,
                  starts="select_exec",
                  input_builder=lambda ctx: {
                      "round": int(ctx.event.payload["round"]),
                      "applied": _round_applied(ctx, int(ctx.event.payload["round"])),
                      "repro_code": (ctx.views["reproduction"].value()[-1]["code"]
                                     if ctx.views["reproduction"].value() else ""),
                  },
                  policy=api.PerEvent())
        # all TestResults in for the round -> rerank
        b.trigger("selector", subscription=api.Subscription(kinds=frozenset({"TestResults"})),
                  predicate=lambda ctx: _solved_round(ctx) is not None
                  and len([r for r in ctx.views["test_results"].value()]) >= len(_round_applied(ctx, _solved_round(ctx))),  # type: ignore[arg-type]
                  starts="selector",
                  input_builder=lambda ctx: {
                      "applied": _round_applied(ctx, _solved_round(ctx)),  # type: ignore[arg-type]
                      "results": list(ctx.views["test_results"].value()),
                  }, policy=api.PerEvent())

        b.termination(api.any_of(
            api.threshold_count("SelectedPatch", 1),
            api.threshold_count("Exhausted", 1),
            api.quiescence_with_watchdog(seconds=watchdog_seconds),
        ))

    return topo


def _solved_round(ctx: api.TriggerContext) -> int | None:
    """The round that emitted Solved (the only round whose applied patches get tested), or None."""
    solved = ctx.views["solved"].value()
    return int(solved[-1]["round"]) if solved else None
