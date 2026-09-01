# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Tests for the core envelope types (src/substrate/types.py)."""

import msgspec
import pytest

from substrate.types import BlobRef, Event, ProducerRef, Subscription


def test_event_constructs_with_producer_ref():
    ev = Event(
        seq=3,
        kind="CountReached",
        schema="CountReached@1",
        producer=ProducerRef(kind="counter", instance="01ABC", parent=None),
        t=1718000000.2,
        payload={"n": 1},
    )
    assert ev.seq == 3
    assert ev.producer.kind == "counter"
    assert ev.payload == {"n": 1}


def test_runtime_event_has_null_producer():
    ev = Event(
        seq=0,
        kind="substrate.RunStarted",
        schema="substrate.RunStarted@1",
        producer=None,
        t=0.0,
        payload={},
    )
    assert ev.producer is None


def test_frozen_event_is_immutable():
    # F-PROD-3: immutability by construction; mutation raises AttributeError (msgspec 0.21).
    ev = Event(seq=1, kind="K", schema="K@1", producer=None, t=0.0, payload={})
    with pytest.raises(AttributeError):
        ev.seq = 2  # type: ignore[misc]


def test_blobref_shape():
    b = BlobRef(sha256="sha256:" + "0" * 64, bytes=2048)
    assert b.bytes == 2048


def test_subscription_defaults_empty_and_is_empty():
    s = Subscription()
    assert s.kinds == frozenset() and s.producers == frozenset()
    assert s.is_empty()
    assert not Subscription(kinds=frozenset({"CountReached"})).is_empty()


def test_decode_validation_raises_validationerror():
    # Wrong-typed field rejected by the bus-boundary decoder (msgspec.ValidationError).
    dec = msgspec.json.Decoder(ProducerRef)
    with pytest.raises(msgspec.ValidationError):
        dec.decode(b'{"kind":"counter","instance":123}')
