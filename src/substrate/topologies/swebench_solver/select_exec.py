# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""SELECT test-execution — the run-and-observe seam that produces TestResults (sprint 140).

For each applied patch (design §4): run the repo-DERIVED regression set + the solver's GENERATED
reproduction test in the instance environment, parse pass/fail -> TestResults. The producer hosting this
factory is declared `deterministic=False` / the records are `replayable=False` — a Docker subprocess is
non-deterministic, captured once, re-derivable (L1/L2) not re-executable.

THE FIREWALL (the reviewer's hard-look item):
  - `regression_command` is REPO-DERIVED — built from tests discovered in the repo at base_commit, with
    `test_patch` files excluded (an allowlist). It is NOT the instance's `PASS_TO_PASS` field (that is
    grade metadata; handing it to the solver leaks the grade's regression set). This is the CALLER's
    precondition; the seam runs what it's given and documents the contract.
  - the reproduction test is the solver's OWN artifact (NOT the held-out `FAIL_TO_PASS`).

The test EXECUTION is abstracted behind `TestRunner` so the seam's wiring is testable with a stand-in;
the real `DockerTestRunner` (env-gated, the per-instance image) is the gate-#3 integration.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from .records import Reproduction, TestResults
from .select_regression import RegressionRun

_Factory = Callable[[], Any]


class TestRunner(Protocol):
    """Apply `model_patch` in the instance environment, optionally drop `extra_files` (e.g. the generated
    reproduction test) alongside, and run `test_command`; return (returncode, output). The real
    implementation runs in the per-instance Docker container; a stand-in is used in tests."""

    def run(
        self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]: ...


_PASSED = re.compile(r"(\d+)\s+passed")
_FAILED = re.compile(r"\d+\s+failed")
_ERRORS = re.compile(r"\d+\s+error")
# the per-test lines pytest emits under `-rA` (the repo test_cmd already carries -rA): "PASSED path::test",
# "FAILED path::test - reason", "ERROR path::test", etc. The status is the first token, the id the second.
_OUTCOME = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(\S+)", re.MULTILINE)


def parse_test_outcomes(output: str) -> dict[str, str]:
    """Per-test outcomes from a `pytest -rA` run: {test_id: status_lowercased}. The grain the passed-at-base
    filter needs — a whole-run pass/fail count can't tell a NEW failure from a PRE-EXISTING one."""
    return {tid: status.lower() for status, tid in _OUTCOME.findall(output)}


def passed_tests(output: str) -> set[str]:
    """The test ids that PASSED in a `pytest -rA` run (the base-passing set is computed from this)."""
    return {tid for tid, status in parse_test_outcomes(output).items() if status == "passed"}


def regression_passed(returncode: int, output: str) -> bool:
    """The repo-derived regression set passed: exit 0 AND positive evidence (>= 1 passed, no failed/error).
    The same positive-evidence discipline as the held-out grade — a clean exit alone is forgeable (a patch
    that breaks collection can exit non-zero, or an `os._exit(0)` can exit clean with nothing run).

    NOTE: this whole-run bool is only honest when EVERY test passes at base. On repos that don't (flask runs
    warnings-as-errors and the pinned env emits deprecations -> ~133 unrelated base failures, proven by the
    real-runner smoke #69), use `regression_held` against a passed-at-base set instead — a pre-existing
    failure must not be charged to the candidate."""
    if returncode != 0:
        return False
    low = output.lower()
    if _FAILED.search(low) or _ERRORS.search(low):
        return False
    m = _PASSED.search(output)
    return m is not None and int(m.group(1)) >= 1


def regression_held(
    passed_at_base: set[str], patched_output: str, in_scope_files: frozenset[str] | None = None
) -> bool:
    """The firewall-clean regression signal when the repo has pre-existing base failures: every base-passing
    test the candidate RAN must REAPPEAR and pass. A test failing in BOTH runs (env/deprecation noise) is not
    charged; only a base-pass -> patched-non-pass (a flip-to-fail OR a VANISH — the patch broke that test's
    module collection so it silently dropped, #70) is a regression.

    `in_scope_files` (the candidate's regression test files) makes the VANISH check correct under per-candidate
    proximity: a base-passing test whose file the candidate RAN but that's absent from the output regressed;
    a base-passing test in a file the candidate DIDN'T run is legitimately absent, not charged. None ->
    unscoped (static command, tests): only flip-to-fail among tests that reappeared is checked. Requires
    positive evidence: at least one in-scope base-passing test exists (a patch that runs nothing can't
    vacuously 'hold')."""
    outcomes = parse_test_outcomes(patched_output)
    if in_scope_files is None:
        ran = [tid for tid in passed_at_base if tid in outcomes]
        return bool(ran) and all(outcomes[tid] == "passed" for tid in ran)
    in_scope = {tid for tid in passed_at_base if tid.split("::")[0] in in_scope_files}
    if not in_scope:
        return False  # the candidate ran none of the base-passing tests -> no evidence
    return all(outcomes.get(tid) == "passed" for tid in in_scope)


def reproduction_status(output: str) -> Reproduction:
    """Parse the reproduction test's self-reported marker with MAJORITY VOTE over marker
    occurrences (F4 fix, review 2026-08-08). The pre-fix parser tested `"Issue resolved" in
    output` first and returned RESOLVED on any occurrence — one Bernoulli draw per candidate
    with a hard bias toward RESOLVED when both markers appeared. With K > 1 sampling now
    running K variants in one Docker invocation (see `combine_repro_scripts` in
    `reproduction.py`), the output can contain multiple markers; the majority reading is the
    honest signal.

    Ties break in favour of REPRODUCED — the null hypothesis on any patched candidate is that
    the bug is still present; only a clear majority of RESOLVED verdicts overturns it. This is
    the direction that respects the KIT_DIARY 21 failure mode (a repro that says RESOLVED for
    the wrong reason should not win against equal REPRODUCED signal).

    Zero occurrences of both markers -> OTHER (no clean evidence either way)."""
    n_resolved = output.count("Issue resolved")
    n_reproduced = output.count("Issue reproduced")
    if n_resolved == 0 and n_reproduced == 0:
        return Reproduction.OTHER
    if n_resolved > n_reproduced:
        return Reproduction.RESOLVED
    return Reproduction.REPRODUCED  # ties favour REPRODUCED per the tiebreak rule


async def run_one(
    runner: TestRunner,
    regression: str | Callable[[str], Any],
    repro_code: str,
    slot: int,
    model_patch: str,
    *,
    passed_at_base: frozenset[str] | None = None,
) -> TestResults:
    """Run one applied patch's tests -> one TestResults. The single per-patch primitive (the assembly's
    fan-out and the standalone factory both call it). `regression` is a static command OR a per-candidate
    planner (model_patch -> RegressionRun); either way repo-derived (NOT the PASS_TO_PASS field — firewall).
    `repro_code` is the solver's generated reproduction test ("" to skip). `passed_at_base` (the instance's
    base-passing test ids) switches the signal to the scope-aware `regression_held` — the honest filter on
    repos with pre-existing base failures; None falls back to the whole-run `regression_passed`."""
    run = resolve_regression(regression, model_patch)
    rc, out = await asyncio.to_thread(runner.run, model_patch, run.command)
    reg_ok = (
        regression_held(set(passed_at_base), out, run.files)
        if passed_at_base is not None
        else regression_passed(rc, out)
    )
    repro, repro_out = Reproduction.OTHER, ""
    if repro_code:
        _, repro_out = await asyncio.to_thread(
            runner.run, model_patch, "python /sol/repro.py", {"repro.py": repro_code}
        )
        repro = reproduction_status(repro_out)
    return TestResults(
        slot=slot,
        regression_passed=reg_ok,
        reproduction=repro,
        summary=(out[-400:] + ("\n--repro--\n" + repro_out[-200:] if repro_out else "")).strip(),
    )


def resolve_regression(regression: str | Callable[[str], Any], model_patch: str) -> RegressionRun:
    """The regression RUN for a candidate: a static string runs the same set for every patch with no scope
    (tests); a planner (Callable[model_patch -> RegressionRun]) tailors the firewall-clean set + scope to
    what THAT patch touches (the proximity picker, review #65). One seam so the assembly fan-out and the
    standalone factory agree."""
    if callable(regression):
        return regression(model_patch)  # type: ignore[no-any-return]
    return RegressionRun(regression, None)


def select_exec_validate_factory(
    runner: TestRunner,
    regression: str | Callable[[str], Any],
    repro_code: str = "",
    *,
    passed_at_base: frozenset[str] | None = None,
) -> _Factory:
    """Per AppliedPatch (input carries `slot` + `model_patch`): run the tests via `run_one`, emit one
    TestResults. `regression` is a static command OR a per-candidate planner (see `resolve_regression`);
    `passed_at_base` switches SELECT to the scope-aware regression_held. Host in a producer with
    `deterministic=False`."""

    async def select_exec(inp: Any) -> AsyncIterator[TestResults]:
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        patch = str(inp.get("model_patch", "")) if hasattr(inp, "get") else ""
        yield await run_one(
            runner, regression, repro_code, slot, patch, passed_at_base=passed_at_base
        )

    return lambda: select_exec
