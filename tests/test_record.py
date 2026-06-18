"""Tests for the run record writer/reader/recovery (technical §3, §5).

Covers conformance check 16 (torn-tail recovery) in miniature and the
manifest-is-advisory / segments-are-authoritative invariant (§3.5)."""

import pytest

import substrate.record as record
from substrate.errors import RecordGapError
from substrate.record import Always, RecordWriter, read_record, recover_open_segment


def _env(seq, kind="K"):
    return {
        "seq": seq,
        "kind": kind,
        "schema": f"{kind}@1",
        "producer": None,
        "t": float(seq),
        "payload": {"n": seq},
    }


def test_write_then_read_roundtrip(tmp_path):
    w = RecordWriter(tmp_path, fsync=Always())
    for i in range(5):
        w.append(_env(i))
    w.close()
    got = list(read_record(tmp_path))
    assert [e["seq"] for e in got] == [0, 1, 2, 3, 4]
    assert (tmp_path / "events-000001.open.jsonl").exists()  # seal-on-roll only
    assert (tmp_path / "manifest.json").exists()


def test_segment_rolls_and_seals(tmp_path, monkeypatch):
    monkeypatch.setattr(record, "SEGMENT_MAX_BYTES", 150)  # force rolls
    w = RecordWriter(tmp_path, fsync=Always())
    for i in range(6):
        w.append(_env(i))
    w.close()
    sealed = sorted(
        p.name for p in tmp_path.glob("events-*.jsonl") if not p.name.endswith(".open.jsonl")
    )
    assert sealed, "expected at least one sealed segment after rolling"
    assert [e["seq"] for e in read_record(tmp_path)] == [0, 1, 2, 3, 4, 5]


def test_read_is_independent_of_manifest(tmp_path):
    w = RecordWriter(tmp_path, fsync=Always())
    for i in range(3):
        w.append(_env(i))
    w.close()
    (tmp_path / "manifest.json").unlink()  # manifest is advisory
    assert [e["seq"] for e in read_record(tmp_path)] == [0, 1, 2]


def test_torn_tail_recovery_is_exact(tmp_path):
    # conformance check 16: a crash-torn tail recovers by CRC scan to the last
    # complete frame; no heuristic recovery paths.
    w = RecordWriter(tmp_path, fsync=Always())
    for i in range(4):
        w.append(_env(i))
    w.close()
    hot = tmp_path / "events-000001.open.jsonl"
    with open(hot, "ab") as fh:  # simulate a torn write
        fh.write(b'{"seq":4,"kind":"K","schema":"K@1","produc')
    kept = recover_open_segment(tmp_path)
    assert kept == 4
    assert [e["seq"] for e in read_record(tmp_path)] == [0, 1, 2, 3]
    # the torn bytes are physically gone, not merely ignored
    assert hot.read_bytes().endswith(b"\n")


def _sealed(tmp_path):
    return sorted(p for p in tmp_path.glob("events-*.jsonl") if not p.name.endswith(".open.jsonl"))


def test_truncated_sealed_segment_is_detected(tmp_path, monkeypatch):
    # §3.5/§3.6: a SEALED segment must be complete. If it loses its tail (corruption, a partial copy),
    # that is data loss — the read path reports it, it does NOT silently drop the tail line.
    monkeypatch.setattr(record, "SEGMENT_MAX_BYTES", 150)  # force seals
    w = RecordWriter(tmp_path, fsync=Always())
    for i in range(6):
        w.append(_env(i))
    w.close()
    sealed = _sealed(tmp_path)
    assert sealed, "expected a sealed segment"
    sealed[0].write_bytes(sealed[0].read_bytes()[:-5])  # lop the trailing newline + part of the frame
    with pytest.raises(RecordGapError):
        list(read_record(tmp_path))


def test_lost_sealed_segment_is_detected(tmp_path, monkeypatch):
    # a whole deleted/lost sealed segment yields a non-contiguous stream — caught by the seq check
    # (was silently folded as if the missing events never existed).
    monkeypatch.setattr(record, "SEGMENT_MAX_BYTES", 150)
    w = RecordWriter(tmp_path, fsync=Always())
    for i in range(8):
        w.append(_env(i))
    w.close()
    sealed = _sealed(tmp_path)
    assert len(sealed) >= 2, "expected multiple sealed segments"
    sealed[0].unlink()  # lose an entire sealed segment
    with pytest.raises(RecordGapError):
        list(read_record(tmp_path))
