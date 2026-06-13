"""Tests for the frame format and torn-tail recovery (technical §3.3)."""

import substrate.framing as framing
from hypothesis import given, strategies as st

from substrate.errors import CRCMismatchError, FrameTooLargeError, TornFrameError
import pytest


def _env(seq, payload=None):
    return {
        "seq": seq,
        "kind": "K",
        "schema": "K@1",
        "producer": None,
        "t": 0.0,
        "payload": payload if payload is not None else {"n": seq},
    }


def test_frame_is_one_terminated_line_and_verifies():
    line = framing.frame(_env(1))
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    env = framing.verify_line(line[:-1])
    assert env == _env(1)  # crc stripped; remainder is the original envelope
    assert "crc" not in env


def test_frame_rejects_preexisting_crc():
    with pytest.raises(ValueError):
        framing.frame({**_env(1), "crc": "deadbeef"})


def test_frame_too_large(monkeypatch):
    monkeypatch.setattr(framing, "FRAME_MAX_BYTES", 32)
    with pytest.raises(FrameTooLargeError):
        framing.frame(_env(1, payload={"big": "x" * 100}))


def test_verify_detects_crc_corruption():
    line = framing.frame(_env(7))[:-1]
    # flip a byte inside the payload so the recomputed crc no longer matches
    corrupt = line.replace(b'"n":7', b'"n":8')
    with pytest.raises(CRCMismatchError):
        framing.verify_line(corrupt)


def test_verify_unparseable_is_torn():
    with pytest.raises(TornFrameError):
        framing.verify_line(b"{not json")


def test_recover_keeps_whole_frames_and_cuts_torn_tail():
    good = framing.frame(_env(1)) + framing.frame(_env(2)) + framing.frame(_env(3))
    torn = good + b'{"seq":4,"kind":"K","sch'  # partial, unterminated final line
    frames, cut = framing.recover(torn)
    assert [f["seq"] for f in frames] == [1, 2, 3]
    assert cut == len(good)  # truncate point = end of the last whole frame


def test_recover_cuts_at_crc_mismatch_in_the_middle():
    f1 = framing.frame(_env(1))
    f2 = framing.frame(_env(2))
    bad = f2.replace(b'"n":2', b'"n":9')  # same length, broken crc, still newline-terminated
    frames, cut = framing.recover(f1 + bad + framing.frame(_env(3)))
    assert [f["seq"] for f in frames] == [1]
    assert cut == len(f1)


@given(seqs=st.lists(st.integers(min_value=0, max_value=2**53 - 1), min_size=0, max_size=30))
def test_property_frame_then_recover_roundtrips(seqs):
    data = b"".join(framing.frame(_env(s)) for s in seqs)
    frames, cut = framing.recover(data)
    assert [f["seq"] for f in frames] == seqs
    assert cut == len(data)
