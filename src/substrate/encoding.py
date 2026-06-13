"""Canonical encoding — the bytes everything hashes over (technical spec §4).

The product promises byte-identical replay, content-hash citations, and divergence
comparison by payload hash. All three require that the same logical value always
serializes to the same bytes, on every OS and Python 3.12+ minor version. Python's
json.dumps does not promise this; RFC 8785 (JCS) does.

Pipeline (technical §4.1): value -> msgspec.to_builtins -> whitelist check -> rfc8785.dumps.
The whitelist (§4.2) is enforced HERE, before rfc8785, rather than relying on the
encoder to reject — JCS numbers are IEEE-754 doubles (integer precision is a
correctness landmine) and have no NaN/Inf form.

Two canonical forms exist per event and must be kept distinct (§3.3): B_hash is the
envelope WITHOUT the `crc` field (what content hashes are computed over); B_disk is
WITH `crc` (the on-disk frame). The crc assembly lives in the record layer; this
module provides the primitive `canonical_bytes` (= B_hash for a crc-less object) and
the content-hash helper.
"""
from __future__ import annotations

import hashlib
from typing import Any

import msgspec
import rfc8785

from .constants import JSON_SAFE_INT_MAX, JSON_SAFE_INT_MIN


class NonCanonicalValueError(ValueError):
    """A value outside the JCS type whitelist (technical §4.2). Carries the JSON path
    of the offending node so emission can become substrate.ProducerEmittedInvalidEvent
    with reason `non_canonical_value` and `at_path` (§4.3)."""

    def __init__(self, message: str, at_path: str) -> None:
        super().__init__(f"{message} (at {at_path})")
        self.at_path = at_path


def _check(node: Any, path: str = "$") -> None:
    """Recursively enforce the §4.2 type whitelist on a builtins tree."""
    # bool is a subclass of int — must be tested first.
    if node is None or isinstance(node, bool):
        return
    if isinstance(node, int):
        if not (JSON_SAFE_INT_MIN <= node <= JSON_SAFE_INT_MAX):
            raise NonCanonicalValueError(
                f"int {node} outside JCS-safe range "
                f"[-(2^53-1), 2^53-1]; declare it as a string field",
                path,
            )
        return
    if isinstance(node, float):
        if node != node or node in (float("inf"), float("-inf")):
            raise NonCanonicalValueError("non-finite float (JCS has no NaN/Inf form)", path)
        return
    if isinstance(node, str):
        return
    if isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if not isinstance(key, str):
                raise NonCanonicalValueError(f"non-str dict key {key!r}", path)
            _check(value, f"{path}.{key}")
        return
    raise NonCanonicalValueError(
        f"type {type(node).__name__} is not in the JCS whitelist", path
    )


def to_canonical_builtins(obj: Any) -> Any:
    """msgspec.to_builtins(obj) with the §4.2 whitelist enforced. Accepts a msgspec
    Struct, a dict, or any builtins tree. Raises NonCanonicalValueError on violation."""
    builtins = msgspec.to_builtins(obj)
    _check(builtins)
    return builtins


def canonical_bytes(obj: Any) -> bytes:
    """The canonical RFC-8785 bytes for a value (= B_hash for a crc-less object).
    Deterministic: the same logical value yields identical bytes everywhere."""
    return rfc8785.dumps(to_canonical_builtins(obj))


def sha256_hex(data: bytes) -> str:
    """Content hash of raw bytes, formatted `sha256:<64 lowercase hex>` (§4.2)."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    """The `sha256:<hex>` content hash over a value's canonical bytes — the identity
    used for blob ids, input_sha256, message_sha256, and D-8 comparison (§3.3)."""
    return sha256_hex(canonical_bytes(obj))
