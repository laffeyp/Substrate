"""Live attach — the read-only follower (technical §13, F-PERS-4).

`attach(root)` opens a run record that may still be growing and lets a reader follow it
as the writer appends. The follower's contract is satisfied BY CONSTRUCTION (F-PERS-4):

  - it NEVER opens any file for writing (read-only file modes only),
  - it NEVER takes the persistent-bus lock,
  - it NEVER signals the writer.

Sealed segments are read in full (immutable forever). The hot (`.open`) segment is
tailed: read complete newline-terminated lines, CRC-verify each (the same §3.3 check as
recovery), and IGNORE the trailing partial line (a frame the writer has not finished).
Change detection is polling: the hot segment is append-only, so `stat().st_size` growth
is a complete signal that there is more to read (`POLL_INTERVAL_MS`, default 100).

This module is the read path under `substrate tail` (F-CLI-5) and the live inspection
surfaces; it emits nothing to the bus (F-OBS-6) and mutates nothing on disk.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from . import framing
from .constants import POLL_INTERVAL_MS


def _sealed_segments(root: Path) -> list[Path]:
    """Sealed segments in seq order (by filename), excluding the hot `.open` one."""
    return sorted(p for p in root.glob("events-*.jsonl") if not p.name.endswith(".open.jsonl"))


def _hot_segment(root: Path) -> Path | None:
    hot = sorted(root.glob("events-*.open.jsonl"))
    return hot[-1] if hot else None


def _segment_index(path: Path) -> int:
    """The numeric segment index from `events-NNNNNN[.open].jsonl`. ROLL-STABLE: a segment
    keeps its index when it seals (`.open` is dropped, the number is unchanged), so the
    follower's per-segment cursor must key on this — NOT the basename, which changes on
    seal and would otherwise reset the cursor to 0 and re-yield the whole segment."""
    return int(path.name.split("-", 1)[1].split(".", 1)[0])


class LiveRecord:
    """A read-only follower over a (possibly still-growing) run record (technical §13).

    Hold one per reader. `read_new()` returns every complete, CRC-valid frame appended
    since the last call (sealed segments first, then the recoverable prefix of the hot
    segment); the trailing partial line is ignored until it completes. `follow()` is a
    blocking generator that polls for growth. The follower opens files read-only, takes
    no lock, and never writes — F-PERS-4 by construction.
    """

    def __init__(self, root: Path | str, *, poll_ms: int = POLL_INTERVAL_MS) -> None:
        self.root = Path(root)
        self._poll_s = poll_ms / 1000.0
        # per-segment byte cursor, keyed by ROLL-STABLE segment INDEX (not basename): the
        # bytes of each segment we have already yielded. Keying on the index means a segment
        # tailed while hot keeps its cursor when it seals (`.open` dropped, index unchanged),
        # so frames are never re-yielded across a roll.
        self._cursors: dict[int, int] = {}

    def _read_segment_new(self, path: Path, *, hot: bool) -> Iterator[dict[str, Any]]:
        """Yield complete CRC-valid frames in `path` past our cursor. For a sealed segment
        every line is complete; for the hot segment the trailing partial line is ignored
        (it is a frame the writer has not finished — never an error)."""
        # Read-only. O_NOFOLLOW where available; never O_WRONLY/O_RDWR/O_APPEND.
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return
        try:
            data = _read_all(fd)
        finally:
            os.close(fd)
        idx = _segment_index(path)
        start = self._cursors.get(idx, 0)
        if start >= len(data):
            return
        window = data[start:]
        if hot:
            # Only consume up to the last complete frame; leave the partial tail for next poll.
            frames, consumed = framing.recover(window)
            self._cursors[idx] = start + consumed
            yield from frames
        else:
            # A sealed segment is immutable and complete: every line is a whole frame. We
            # resume at the cursor carried over from when this segment was hot (roll-stable
            # index key), so already-yielded frames are not re-emitted.
            consumed = 0
            for line in window.splitlines(keepends=True):
                if not line.endswith(b"\n"):
                    break  # should not happen on a sealed segment; be defensive
                yield framing.verify_line(line[:-1])
                consumed += len(line)
            self._cursors[idx] = start + consumed

    def read_new(self) -> list[dict[str, Any]]:
        """Every complete frame appended since the last call, in seq order: all sealed
        segments (newly-appearing ones are picked up), then the recoverable prefix of the
        hot segment. A sealed segment is read once and not re-read (its cursor saturates)."""
        out: list[dict[str, Any]] = []
        for seg in _sealed_segments(self.root):
            out.extend(self._read_segment_new(seg, hot=False))
        hot = _hot_segment(self.root)
        if hot is not None:
            out.extend(self._read_segment_new(hot, hot=True))
        return out

    def follow(self, *, until_finalised: bool = True) -> Iterator[dict[str, Any]]:
        """Blocking generator: yield frames as they appear, polling for growth. Stops after
        yielding a terminal `substrate.RunFinalised` when `until_finalised` (the default),
        else runs until the caller stops iterating. Polls `st_size` growth — the hot
        segment is append-only, so a size increase is a complete more-to-read signal."""
        while True:
            new = self.read_new()
            for env in new:
                yield env
                if until_finalised and env.get("kind") == "substrate.RunFinalised":
                    return
            time.sleep(self._poll_s)


def attach(root: Path | str, *, poll_ms: int = POLL_INTERVAL_MS) -> LiveRecord:
    """Open a read-only follower over a run record that may still be growing (technical
    §13, F-PERS-4). Read-only, lock-free, signal-free by construction."""
    return LiveRecord(root, poll_ms=poll_ms)


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
