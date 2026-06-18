"""Persistent-bus locking (technical spec §11).

Persistent mode acquires an exclusive, non-blocking advisory file lock on
`<root>/.lock` before any read-modify of the root; failure raises BusLockedError
carrying the advisory contents. The lock is advisory and same-machine. Per-run mode
needs no lock (the run root is freshly created under a ULID run_id). Windows raises
UnsupportedPlatformError at configuration time — a PID-file fallback with a TOCTOU
window is not acceptable for a correctness primitive (N-PORT-1).
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

from ..errors import BusLockedError, UnsupportedPlatformError


def acquire_lock(root: Path, *, start_time: float) -> int:
    """Acquire the exclusive lock on <root>/.lock. Returns the held fd (keep it open
    for the run; pass to release_lock at the end). Raises BusLockedError if another
    runtime holds it, UnsupportedPlatformError on Windows."""
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI only
        raise UnsupportedPlatformError(
            "persistent buses are unsupported on Windows in v1.0 (N-PORT-1)"
        )
    import fcntl  # POSIX-only; imported here so the module loads on Windows for the raise

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        advisory = _read_advisory(lock_path)
        os.close(fd)
        raise BusLockedError(
            f"persistent-bus root {root} is locked by another runtime", advisory
        ) from exc
    os.ftruncate(fd, 0)
    os.write(
        fd,
        json.dumps(
            {"pid": os.getpid(), "hostname": socket.gethostname(), "start_time": start_time}
        ).encode(),
    )
    os.fsync(fd)
    return fd


def release_lock(fd: int) -> None:
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_advisory(lock_path: Path) -> dict[str, object]:
    try:
        with open(lock_path, "rb") as fh:
            data = fh.read()
        parsed = json.loads(data) if data else {}
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, ValueError):
        return {}
