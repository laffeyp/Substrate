# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 230 — bundle slot declaration + binding + fallback tests.

Four ways the binding resolves a slot value:
  1. Caller value wins over default.
  2. `default = "bundle:<field>"` falls back to the loaded bundle.
  3. `default = "none"` + required=true raises `SlotUnfilledError`.
  4. Literal default (bool/int/str) resolves to the literal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.bundles import (
    Bundle,
    SlotKindMismatchError,
    SlotUnfilledError,
    bind_slots,
)
from substrate.topologies.applications.registry import ManifestError, SlotSpec, load_manifests


def _make_default_bundle(methodology: str = "DEFAULT-METHODOLOGY") -> Bundle:
    return Bundle(
        name="default",
        description="",
        schema_version=1,
        extends=(),
        methodology=methodology,
        personality="",
        per_turn="",
        corpus_paths=(),
        retrieval_kind="none",
        tools_enabled=(),
    )


def test_caller_value_wins_over_default() -> None:
    slots = {
        "rubric": SlotSpec(kind="prose", required=False, default="bundle:methodology"),
    }
    resolved = bind_slots(
        "code_review",
        {"rubric": "focus on auth changes"},
        slots=slots,
        default_bundle=_make_default_bundle(),
    )
    assert resolved["rubric"] == "focus on auth changes"


def test_bundle_field_fallback_when_caller_omits() -> None:
    slots = {
        "rubric": SlotSpec(kind="prose", required=False, default="bundle:methodology"),
    }
    resolved = bind_slots(
        "code_review",
        {},
        slots=slots,
        default_bundle=_make_default_bundle("DEFAULT-METHODOLOGY"),
    )
    assert resolved["rubric"] == "DEFAULT-METHODOLOGY"


def test_none_default_required_raises_slot_unfilled() -> None:
    slots = {
        "rubric": SlotSpec(kind="prose", required=True, default="none"),
    }
    with pytest.raises(SlotUnfilledError, match="rubric"):
        bind_slots("code_review", {}, slots=slots, default_bundle=_make_default_bundle())


def test_none_default_optional_resolves_to_none() -> None:
    slots = {
        "rubric": SlotSpec(kind="prose", required=False, default="none"),
    }
    resolved = bind_slots("code_review", {}, slots=slots, default_bundle=_make_default_bundle())
    assert resolved["rubric"] is None


def test_literal_defaults_pass_through() -> None:
    slots = {
        "security_posture": SlotSpec(kind="bool", required=False, default=False),
        "n_reviewers": SlotSpec(kind="int", required=False, default=5),
        "addressee": SlotSpec(kind="line", required=False, default="you"),
    }
    resolved = bind_slots("code_review", {}, slots=slots)
    assert resolved == {"security_posture": False, "n_reviewers": 5, "addressee": "you"}


def test_kind_mismatch_raises() -> None:
    slots = {"n_reviewers": SlotSpec(kind="int", required=False, default=5)}
    with pytest.raises(SlotKindMismatchError, match="n_reviewers"):
        bind_slots("code_review", {"n_reviewers": "not-an-int"}, slots=slots)


def test_choice_slot_validates_against_choices() -> None:
    slots = {
        "posture": SlotSpec(
            kind="choice", required=False, default="strict", choices=("strict", "lenient")
        )
    }
    resolved = bind_slots("code_review", {"posture": "lenient"}, slots=slots)
    assert resolved["posture"] == "lenient"
    with pytest.raises(SlotKindMismatchError):
        bind_slots("code_review", {"posture": "banana"}, slots=slots)


def test_manifest_slots_parse_into_typed_slotspecs(tmp_path: Path) -> None:
    (tmp_path / "code_review.manifest.toml").write_text(
        'name = "code_review"\n'
        'description = "test"\n'
        'runs = "one-shot"\n'
        "\n"
        "[slots]\n"
        'rubric = {kind = "prose", required = false, default = "bundle:methodology"}\n'
        'n_reviewers = {kind = "int", required = false, default = 5}\n',
        encoding="utf-8",
    )
    specs = load_manifests(root=tmp_path, on_error="raise")
    slots = specs["code_review"].slots
    assert isinstance(slots["rubric"], SlotSpec)
    assert slots["rubric"].kind == "prose"
    assert slots["rubric"].default == "bundle:methodology"
    assert slots["n_reviewers"].kind == "int"
    assert slots["n_reviewers"].default == 5


def test_manifest_bad_slot_kind_raises(tmp_path: Path) -> None:
    (tmp_path / "bad.manifest.toml").write_text(
        'name = "bad"\ndescription = "x"\nruns = "one-shot"\n'
        '\n[slots]\nfoo = {kind = "unknown-kind"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="kind"):
        load_manifests(root=tmp_path, on_error="raise")
