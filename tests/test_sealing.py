"""Input sealing — immutability by construction (technical §8.3)."""

from types import MappingProxyType

import pytest
from msgspec import Struct

from substrate.errors import InputTypeError
from substrate.sealing import seal
from substrate.types import BlobRef


class Frozen(Struct, frozen=True):
    n: int


class Mutable(Struct):
    n: int


def test_scalars_pass_through():
    assert seal(None) is None
    assert seal(True) is True
    assert seal(3) == 3
    assert seal("x") == "x"


def test_dict_becomes_readonly_mapping_supporting_index():
    s = seal({"n": 2, "nested": {"a": 1}})
    assert isinstance(s, MappingProxyType)
    assert s["n"] == 2 and s["nested"]["a"] == 1  # ergonomic dict access still works
    with pytest.raises(TypeError):
        s["n"] = 9  # immutable by construction


def test_list_becomes_tuple_recursively():
    assert seal([1, [2, 3]]) == (1, (2, 3))


def test_frozen_struct_passes_mutable_struct_rejected():
    assert seal(Frozen(1)).n == 1
    with pytest.raises(InputTypeError):
        seal(Mutable(1))


def test_raw_bytes_and_arbitrary_objects_rejected():
    with pytest.raises(InputTypeError):
        seal(b"raw")
    with pytest.raises(InputTypeError):
        seal(object())


def test_non_str_mapping_key_rejected():
    with pytest.raises(InputTypeError):
        seal({1: "a"})


def test_blobref_passes_through():
    assert seal(BlobRef(sha256="sha256:" + "0" * 64, bytes=1)).bytes == 1
