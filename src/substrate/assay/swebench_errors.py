"""Typed exception hierarchy for the SWE-bench runner (F4, holistic review 2026-08-10).

Substrate ships its own exception hierarchy at `src/substrate/errors.py` for record + runtime
errors (`SubstrateError`, `BusLockedError`, `ProducerNotFound`, etc.); SWE-bench needs a
separate set for the boundary between the assay and the outside world (Docker, git, the
official harness). The runner's pre-F4 classifier at `scripts/assay_swebench_confirmatory.py`
string-matched `repr(exc)` for `"docker"` / `"container"` / `"git"` — the exact drift pattern
Substrate's own typed hierarchy exists to eliminate.

Every exception here IS-A `SwebenchRunnerError`, itself a `RuntimeError` so an existing
broad handler keeps working. New code catches by type. `reason` is the shared closed-set
string from `_HARNESS_REASONS` at `assay/swebench.py`, so the runner's typed row and the
oracle's `Verdict.NO_VERDICT` reason field carry the SAME wire form — one lexicon across the
whole boundary (H-3 ratified 2026-08-10)."""

from __future__ import annotations

from .swebench import (
    REASON_CONTAINER_CRASHED,
    REASON_DOCKER_ERROR,
    REASON_GIT_ERROR,
    REASON_HARNESS_ERROR,
    REASON_TIMED_OUT,
)


class SwebenchRunnerError(RuntimeError):
    """Base class for every typed boundary error the SWE-bench runner catches. `reason` is
    the wire form from the shared `_HARNESS_REASONS` closed set — a caller writing a cell
    row reads `.reason` directly instead of string-matching `repr(exc)`."""

    reason: str = ""

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail


class DockerDaemonError(SwebenchRunnerError):
    """Docker CLI or daemon failure — pull failed, daemon down, OOM eviction, container
    start refused. Maps to `REASON_DOCKER_ERROR` on the wire."""

    reason = REASON_DOCKER_ERROR


class ContainerCrashed(SwebenchRunnerError):
    """A grade container exited non-zero before `report.json` landed. Maps to
    `REASON_CONTAINER_CRASHED`."""

    reason = REASON_CONTAINER_CRASHED


class GitOperationFailed(SwebenchRunnerError):
    """`git clone`, `git apply`, or `git checkout` failed at the runner boundary (before
    the topology ran) or during prep. Maps to `REASON_GIT_ERROR`."""

    reason = REASON_GIT_ERROR


class HarnessTimeout(SwebenchRunnerError):
    """Cell exhausted its wall-clock budget — the harness or the topology took longer than
    the per-cell timeout allowed. Maps to `REASON_TIMED_OUT`."""

    reason = REASON_TIMED_OUT


class HarnessError(SwebenchRunnerError):
    """Harness raised (import failure, missing image, unexpected exception inside
    `run_evaluation`). Maps to `REASON_HARNESS_ERROR`."""

    reason = REASON_HARNESS_ERROR


__all__ = [
    "ContainerCrashed",
    "DockerDaemonError",
    "GitOperationFailed",
    "HarnessError",
    "HarnessTimeout",
    "SwebenchRunnerError",
]
