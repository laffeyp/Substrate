"""The frame format and torn-tail recovery (technical spec §3.3).

One event = one frame = one line. Two canonical forms exist per event and MUST be
kept distinct (§3.3):

  B_hash  — canonical bytes of the envelope WITHOUT `crc`. What content hashes and
            the crc are computed over.
  B_disk  — canonical bytes of the envelope WITH `crc` added. What lands on disk,
            what readers see, what `tail` displays. Under JCS key ordering `crc`
            lands at a deterministic position.

CRC32 (zlib polynomial, 8 lowercase hex digits) is a torn-write integrity check,
NOT authenticity; content hashes (sha256) do identity work. Recovery proves each
line independently: the first line that is unterminated, unparseable, or
crc-mismatched is the cut point, and everything before it is intact by construction.
"""
from __future__ import annotations

import json
import zlib
from typing import Any

import rfc8785

from .constants import FRAME_MAX_BYTES
from .encoding import to_canonical_builtins
from .errors import CRCMismatchError, FrameTooLargeError, TornFrameError


def _crc8(data: bytes) -> str:
    """zlib crc32 rendered as exactly 8 lowercase hex digits (technical §3.3)."""
    return format(zlib.crc32(data) & 0xFFFFFFFF, "08x")


def frame(envelope: dict[str, Any]) -> bytes:
    """Build the on-disk frame (B_disk + b"\\n") for an envelope WITHOUT a crc field.

    Raises NonCanonicalValueError (via the whitelist) on a non-canonical payload,
    FrameTooLargeError if the framed line exceeds FRAME_MAX_BYTES, and ValueError if
    a `crc` is already present (the caller must pass the crc-less envelope).
    """
    if "crc" in envelope:
        raise ValueError("frame() expects an envelope WITHOUT a crc field (§3.3)")
    builtins = to_canonical_builtins(envelope)
    b_hash = rfc8785.dumps(builtins)
    crc = _crc8(b_hash)
    b_disk = rfc8785.dumps({**builtins, "crc": crc})
    line = b_disk + b"\n"
    if len(line) > FRAME_MAX_BYTES:
        raise FrameTooLargeError(
            f"frame is {len(line)} bytes > FRAME_MAX_BYTES ({FRAME_MAX_BYTES}); "
            f"oversized payloads belong in the blob store (§3.7)"
        )
    return line


def verify_line(line: bytes) -> dict[str, Any]:
    """Verify one frame line (no trailing newline) and return its crc-less envelope.

    Per §3.3 recovery: parse as JSON; strip `crc`; re-serialize the remainder per §4
    to recover B_hash; recompute crc32; compare. Raises TornFrameError (unparseable /
    no crc) or CRCMismatchError.
    """
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError) as exc:
        raise TornFrameError(f"unparseable frame line: {exc}") from exc
    if not isinstance(obj, dict) or "crc" not in obj:
        raise TornFrameError("frame line is not an object or has no crc field")
    stored_crc = obj["crc"]
    rest = {k: v for k, v in obj.items() if k != "crc"}
    recomputed = _crc8(rfc8785.dumps(to_canonical_builtins(rest)))
    if recomputed != stored_crc:
        raise CRCMismatchError(f"crc mismatch: stored {stored_crc!r}, recomputed {recomputed!r}")
    return rest


def recover(data: bytes) -> tuple[list[dict[str, Any]], int]:
    """Scan the bytes of a hot (.open) segment. Return (good_envelopes, cut_offset).

    cut_offset is the number of leading bytes that are intact, complete frames — the
    point to ftruncate to. Everything from cut_offset onward is a torn / partial tail.
    The first unterminated, unparseable, or crc-mismatched line is the cut point.
    """
    frames: list[dict[str, Any]] = []
    offset = 0
    n = len(data)
    while offset < n:
        nl = data.find(b"\n", offset)
        if nl == -1:
            break  # incomplete final line — torn tail
        try:
            frames.append(verify_line(data[offset:nl]))
        except (TornFrameError, CRCMismatchError):
            break  # corrupt frame — cut here
        offset = nl + 1
    return frames, offset
