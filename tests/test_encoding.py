# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Tests for canonical encoding (src/substrate/encoding.py) — technical spec §4."""

import math

import pytest

from substrate.encoding import (
    NonCanonicalValueError,
    canonical_bytes,
    content_hash,
    sha256_hex,
)
from substrate.types import Event, ProducerRef


def test_key_order_independence_is_deterministic():
    # Same logical value -> identical bytes regardless of insertion order (RFC 8785).
    a = canonical_bytes({"b": 1, "a": 2, "c": [3, 2, 1]})
    b = canonical_bytes({"c": [3, 2, 1], "a": 2, "b": 1})
    assert a == b
    assert a == b'{"a":2,"b":1,"c":[3,2,1]}'


def test_canonical_bytes_on_a_struct():
    ev = Event(
        seq=5,
        kind="RowTranslated",
        schema="RowTranslated@1",
        producer=ProducerRef(kind="worker", instance="01X"),
        t=1.0,
        payload={"row": 2},
    )
    out = canonical_bytes(ev)
    assert isinstance(out, bytes)
    # keys are sorted; supplementary fields are present but ordering is canonical
    assert out.index(b'"kind"') < out.index(b'"payload"') < out.index(b'"producer"')


def test_content_hash_prefix_and_stability():
    h1 = content_hash({"x": 1, "y": [1, 2]})
    h2 = content_hash({"y": [1, 2], "x": 1})
    assert h1 == h2
    assert h1.startswith("sha256:") and len(h1) == len("sha256:") + 64


def test_sha256_hex_of_known_bytes():
    # sha256("") well-known digest.
    assert (
        sha256_hex(b"") == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_int_out_of_safe_range_rejected():
    with pytest.raises(NonCanonicalValueError) as ei:
        canonical_bytes({"big": 2**53})
    assert ei.value.at_path == "$.big"


def test_safe_int_boundary_accepted():
    assert canonical_bytes({"n": 2**53 - 1}) == b'{"n":9007199254740991}'


def test_non_finite_floats_rejected():
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(NonCanonicalValueError):
            canonical_bytes({"f": bad})


def test_non_str_key_rejected():
    with pytest.raises(NonCanonicalValueError):
        canonical_bytes({1: "a"})


def test_bool_is_not_treated_as_int():
    # bool is a subclass of int; must serialize as JSON true/false, not be range-checked away.
    assert canonical_bytes({"ok": True, "no": False}) == b'{"no":false,"ok":true}'
