"""Input sealing — immutability by construction (technical spec §8.3 / F-PROD-3).

When a Trigger fires, the resolved input is sealed by a recursive structural walk so a
running Producer's input cannot be mutated by anyone. The technical spec's accepted set
is {frozen msgspec.Struct, tuple, frozenset, §4.2 scalars, fixed-size byte types,
BlobRef}; anything else raises InputTypeError naming the path.

Reconciliation (design §3.3 ⇆ technical §8.3): the design-spec examples pass dict/list
inputs (`{"n": ...}`) and read them ergonomically, while §8.3's accepted set is
frozen-only. We honor both: the seal CONVERTS mutable containers to immutable
equivalents (list/tuple → tuple, dict → read-only MappingProxyType) rather than
rejecting them, so the result is immutable-by-construction AND the ergonomic dict input
works (a MappingProxyType still supports `inp["n"]`). Truly un-sealable values — raw
bytes, open handles, arbitrary objects — still raise. Flow-back: technical §8.3 should
list immutable-sealed dict/list among the accepted forms. Execution resources
(connections, handles) belong in topology configuration, not Producer input.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any

from msgspec import Struct

from .errors import InputTypeError
from .types import BlobRef


def seal(obj: Any, path: str = "$") -> Any:
    """Return an immutable, structurally-sealed copy of `obj`. Raises InputTypeError
    (with the offending path) on a value that cannot be made immutable by construction."""
    # bool is a subclass of int — the scalar clause covers it; order doesn't matter here.
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    if isinstance(obj, BlobRef):
        return obj
    if isinstance(obj, Struct):
        if not getattr(type(obj), "__struct_config__").frozen:
            raise InputTypeError(f"non-frozen Struct {type(obj).__name__} at {path} (§8.3)")
        return obj
    if isinstance(obj, (list, tuple)):
        return tuple(seal(item, f"{path}[{i}]") for i, item in enumerate(obj))
    if isinstance(obj, (set, frozenset)):
        return frozenset(seal(item, f"{path}{{}}") for item in obj)
    if isinstance(obj, (dict, MappingProxyType)):
        sealed: dict[str, Any] = {}
        for key, value in obj.items():
            if not isinstance(key, str):
                raise InputTypeError(f"non-str mapping key {key!r} at {path} (§8.3)")
            sealed[key] = seal(value, f"{path}.{key}")
        return MappingProxyType(sealed)
    if isinstance(obj, (bytes, bytearray)):
        raise InputTypeError(
            f"raw bytes at {path}: use a content-hash BlobRef or a fixed-size hex field (§4.2/§8.3)"
        )
    raise InputTypeError(
        f"value of type {type(obj).__name__} at {path} is not sealable — Producer input "
        f"must be immutable by construction (§8.3); put execution resources in topology config"
    )
