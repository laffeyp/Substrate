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

_Factory = Callable[[], Any]


class TestRunner(Protocol):
    """Apply `model_patch` in the instance environment, optionally drop `extra_files` (e.g. the generated
    reproduction test) alongside, and run `test_command`; return (returncode, output). The real
    implementation runs in the per-instance Docker container; a stand-in is used in tests."""

    def run(self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None) -> tuple[int, str]: ...


_PASSED = re.compile(r"(\d+)\s+passed")
_FAILED = re.compile(r"\d+\s+failed")
_ERRORS = re.compile(r"\d+\s+error")


def regression_passed(returncode: int, output: str) -> bool:
    """The repo-derived regression set passed: exit 0 AND positive evidence (>= 1 passed, no failed/error).
    The same positive-evidence discipline as the held-out grade — a clean exit alone is forgeable (a patch
    that breaks collection can exit non-zero, or an `os._exit(0)` can exit clean with nothing run)."""
    if returncode != 0:
        return False
    low = output.lower()
    if _FAILED.search(low) or _ERRORS.search(low):
        return False
    m = _PASSED.search(output)
    return m is not None and int(m.group(1)) >= 1


def reproduction_status(output: str) -> Reproduction:
    """Parse the reproduction test's self-reported marker (the generated test prints exactly one of
    'Issue resolved' / 'Issue reproduced'); absence -> OTHER (no clean evidence either way)."""
    if "Issue resolved" in output:
        return Reproduction.RESOLVED
    if "Issue reproduced" in output:
        return Reproduction.REPRODUCED
    return Reproduction.OTHER


async def run_one(
    runner: TestRunner, regression_command: str, repro_code: str, slot: int, model_patch: str
) -> TestResults:
    """Run one applied patch's tests -> one TestResults. The single per-patch primitive (the assembly's
    fan-out and the standalone factory both call it). `regression_command` MUST be repo-derived (NOT the
    PASS_TO_PASS field — firewall); `repro_code` is the solver's generated reproduction test ("" to skip)."""
    rc, out = await asyncio.to_thread(runner.run, model_patch, regression_command)
    reg_ok = regression_passed(rc, out)
    repro, repro_out = Reproduction.OTHER, ""
    if repro_code:
        _, repro_out = await asyncio.to_thread(runner.run, model_patch, "python /sol/repro.py", {"repro.py": repro_code})
        repro = reproduction_status(repro_out)
    return TestResults(
        slot=slot,
        regression_passed=reg_ok,
        reproduction=repro,
        summary=(out[-400:] + ("\n--repro--\n" + repro_out[-200:] if repro_out else "")).strip(),
    )


def select_exec_validate_factory(
    runner: TestRunner,
    regression_command: str,
    repro_code: str = "",
) -> _Factory:
    """Per AppliedPatch (input carries `slot` + `model_patch`): run the tests via `run_one`, emit one
    TestResults. Host in a producer with `deterministic=False`."""

    async def select_exec(inp: Any) -> AsyncIterator[TestResults]:
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        patch = str(inp.get("model_patch", "")) if hasattr(inp, "get") else ""
        yield await run_one(runner, regression_command, repro_code, slot, patch)

    return lambda: select_exec
