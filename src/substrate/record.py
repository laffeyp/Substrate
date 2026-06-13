"""The run record on disk: the writer, the reader, recovery, and the manifest
(technical spec §3, §5).

Directory layout (§3.1):

    <run-root>/
      manifest.json            advisory index; rebuildable from segments
      events-000001.jsonl      sealed segment — immutable forever
      events-000002.open.jsonl hot segment — append-only, exactly one
      blobs/sha256/...         content-addressed payloads
      sidecar/                 off-bus diagnostics / writer stats

Sealing happens on ROLL (a segment exceeding SEGMENT_MAX_BYTES), not on close: a
COMPLETE record is signalled by a terminal `substrate.RunFinalised` frame, and
recovery always runs on the single `.open` segment. (Reconciliation: design spec
§3.2 shows a finalised single-segment record whose hot segment is still `.open`;
technical §2 prose says "seal on finalise". We follow the design-spec invariant —
seal-on-roll only — because it keeps "completeness == terminal RunFinalised" and
"recovery operates on the .open segment" both true. Logged in BLACKBOARD.)

The manifest is ADVISORY; segments are AUTHORITATIVE. Every reader operates with the
manifest missing or stale (§3.5): the segment list is recoverable by globbing.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from msgspec import Struct

from .blobstore import BlobStore, _fsync_dir
from .constants import SEGMENT_MAX_BYTES
from .errors import FsyncError
from .types import BlobRef
from . import framing


# ── fsync policies (technical §5.1; design §4.8) ───────────────────────────────
class NoFsync(Struct, frozen=True):
    """OS page cache only; the disk never bottlenecks (loss = whatever the OS last flushed)."""


class Interval(Struct, frozen=True):
    """fsync at most every `milliseconds` (default 100); amortized throughput."""

    milliseconds: int = 100


class Always(Struct, frozen=True):
    """fsync after every frame; zero complete frames lost, capped at device fsync rate."""


FsyncPolicy = NoFsync | Interval | Always


def _fullfsync_const() -> int | None:
    """macOS F_FULLFSYNC constant if available (durable flush THROUGH the drive cache,
    not just to it — technical §5.2). None on platforms without it (use os.fsync)."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows
        return None
    const = getattr(fcntl, "F_FULLFSYNC", None)
    return const if isinstance(const, int) else None


class RecordWriter:
    """Owns the run record's segment files. The single writer is the only code that
    appends (technical §6). Callers pass complete envelopes WITHOUT a `crc` field
    (seq already assigned by the runtime's append cycle); the writer frames, writes,
    fsyncs per policy, and seals on roll.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        fsync: FsyncPolicy = Interval(100),
        durable: bool | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sidecar").mkdir(exist_ok=True)
        self.blobs = BlobStore(self.root)
        self._fsync = fsync
        # durable fsync (macOS F_FULLFSYNC) defaults on for `always`, off otherwise (§5.2)
        self._durable = isinstance(fsync, Always) if durable is None else durable
        self._seg_index = 1
        self._open_path = self._segment_path(self._seg_index, hot=True)
        self._fd = os.open(self._open_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
        self._seg_bytes = 0
        self._last_fsync = time.monotonic()
        self._first_seq: int | None = None
        self._last_seq: int | None = None
        self._sealed: list[dict[str, Any]] = []
        _fsync_dir(self.root)

    def _segment_path(self, index: int, *, hot: bool) -> Path:
        infix = ".open" if hot else ""
        return self.root / f"events-{index:06d}{infix}.jsonl"

    def put_blob(self, data: bytes) -> BlobRef:
        """Write-ahead a payload to the content-addressed blob store and return its BlobRef
        (technical §3.7). A Law-of-Demeter passthrough so callers (the runtime) do not reach
        through `.blobs`; the blob is fsynced before this returns, so it is durable before
        the referencing frame is appended."""
        return self.blobs.put(data)

    def append(self, envelope: dict[str, Any]) -> None:
        """Frame and append one event (envelope without crc). Applies the fsync policy
        and seals+rolls the segment when it exceeds SEGMENT_MAX_BYTES."""
        line = framing.frame(envelope)
        os.write(self._fd, line)
        self._seg_bytes += len(line)
        seq = envelope.get("seq")
        if isinstance(seq, int):
            if self._first_seq is None:
                self._first_seq = seq
            self._last_seq = seq
        self._maybe_fsync()
        if self._seg_bytes > SEGMENT_MAX_BYTES:
            self._seal_and_roll()

    def _maybe_fsync(self) -> None:
        if isinstance(self._fsync, Always):
            self._do_fsync()
        elif isinstance(self._fsync, Interval):
            now = time.monotonic()
            if (now - self._last_fsync) * 1000.0 >= self._fsync.milliseconds:
                self._do_fsync()
                self._last_fsync = now
        # NoFsync: nothing

    def _do_fsync(self) -> None:
        try:
            full = _fullfsync_const() if self._durable else None
            if full is not None:  # macOS durable flush (F_FULLFSYNC), not just fsync
                import fcntl

                fcntl.fcntl(self._fd, full)
            else:
                os.fsync(self._fd)
        except OSError as exc:
            # fsyncgate (§5.2): the medium is untrustworthy. Do NOT write RunFinalised
            # on it. Close without retrying fsync; the caller crashes the process.
            try:
                os.close(self._fd)
            except OSError:
                pass
            raise FsyncError(f"fsync failed on {self._open_path}: {exc}") from exc

    def _seal_and_roll(self) -> None:
        """Seal the hot segment (durable + rename + dir fsync) and open the next one
        (technical §3.2)."""
        os.fsync(self._fd)
        os.close(self._fd)
        sealed_path = self._segment_path(self._seg_index, hot=False)
        os.replace(self._open_path, sealed_path)
        _fsync_dir(self.root)
        self._sealed.append(
            {"file": sealed_path.name, "first_seq": self._first_seq, "last_seq": self._last_seq}
        )
        self._seg_index += 1
        self._open_path = self._segment_path(self._seg_index, hot=True)
        self._fd = os.open(self._open_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
        _fsync_dir(self.root)
        self._seg_bytes = 0
        self._first_seq = None
        self._last_seq = None
        self._write_manifest()

    def write_manifest(
        self, *, replay_ceiling: str = "3a", extra: dict[str, Any] | None = None
    ) -> None:
        """Public manifest write (e.g. when the runtime updates replay_ceiling)."""
        self._write_manifest(replay_ceiling=replay_ceiling, extra=extra)

    def _write_manifest(
        self, *, replay_ceiling: str = "3a", extra: dict[str, Any] | None = None
    ) -> None:
        manifest: dict[str, Any] = {
            "sealed_segments": self._sealed,
            "hot_segment": self._open_path.name,
            "replay_ceiling": replay_ceiling,
        }
        if extra:
            manifest.update(extra)
        tmp = self.root / "manifest.json.tmp"
        tmp.write_bytes(json.dumps(manifest, sort_keys=True).encode())
        os.replace(tmp, self.root / "manifest.json")
        _fsync_dir(self.root)

    def close(self) -> None:
        """Final durable fsync + manifest write. The hot segment stays `.open`
        (seal-on-roll only); completeness is the terminal RunFinalised frame."""
        self._do_fsync()
        self._write_manifest()
        os.close(self._fd)


# ── reading & recovery ─────────────────────────────────────────────────────────
def _sealed_segments(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("events-*.jsonl") if not p.name.endswith(".open.jsonl"))


def _hot_segment(root: Path) -> Path | None:
    hot = sorted(root.glob("events-*.open.jsonl"))
    return hot[-1] if hot else None


def _read_bytes_nofollow(path: Path) -> bytes:
    """Read a file's bytes read-only and WITHOUT following a symlink (§17: readers do not
    follow symlinks inside a run root). O_NOFOLLOW where the OS has it."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def read_record(root: Path | str) -> Iterator[dict[str, Any]]:
    """Yield every recoverable envelope in seq order: sealed segments (by filename),
    then the recoverable prefix of the hot segment. Does not depend on the manifest
    (segments are authoritative, §3.5). Read-only, symlink-not-followed (§17); does not
    modify anything."""
    root = Path(root)
    for seg in _sealed_segments(root):
        for line in _read_bytes_nofollow(seg).splitlines(keepends=True):
            if line.endswith(b"\n"):
                yield framing.verify_line(line[:-1])
    hot = _hot_segment(root)
    if hot is not None:
        frames, _cut = framing.recover(_read_bytes_nofollow(hot))
        yield from frames


def recover_open_segment(root: Path | str) -> int:
    """Writer-side recovery (run at restart/attach, §3.3): truncate the hot segment to
    the last complete, crc-valid frame. Returns the number of frames kept. Sealed
    segments are never touched."""
    root = Path(root)
    hot = _hot_segment(root)
    if hot is None:
        return 0
    data = hot.read_bytes()
    frames, cut = framing.recover(data)
    if cut < len(data):
        fd = os.open(hot, os.O_RDWR)
        try:
            os.ftruncate(fd, cut)
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(root)
    return len(frames)
