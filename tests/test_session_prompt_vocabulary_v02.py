# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-vocabulary v0.2 lock — PromptFragment + PromptComposed + PromptSource enum.

Locks the Struct field shape, msgspec round-trip, and the kind-name/enum
constant integrity. No producer emits either kind yet; sprint 059 ships the
composer that emits PromptComposed and sprints 060-064 ship the fragment
sources.
"""

from __future__ import annotations

import msgspec

from substrate.topologies.session import PromptComposed, PromptFragment
from substrate.topologies.session.vocabulary import (
    PROMPT_COMPOSED,
    PROMPT_FRAGMENT,
    PROMPT_SOURCES,
    PROMPT_SOURCE_BUNDLE_METHODOLOGY,
    PROMPT_SOURCE_BUNDLE_PERSONALITY,
    PROMPT_SOURCE_PARENT_CONTEXT,
    PROMPT_SOURCE_PER_TURN,
    PROMPT_SOURCE_ROLE,
    PROMPT_SOURCE_TOOLS_SUITE,
    PROMPT_SOURCE_USER_MESSAGE,
    SESSION_KINDS,
    is_prompt_source,
    is_session_kind,
)


def test_prompt_fragment_round_trips_through_msgspec() -> None:
    """A PromptFragment survives msgspec.to_builtins + msgspec.convert with
    every field intact. Provenance carries arbitrary jsonable dicts."""
    f = PromptFragment(
        source=PROMPT_SOURCE_ROLE,
        text="You are a code reviewer.",
        precedence=0,
        provenance={"role_name": "reviewer", "resolved_from": "/tmp/prompts/reviewer.md"},
    )
    raw = msgspec.to_builtins(f)
    assert raw == {
        "source": "role",
        "text": "You are a code reviewer.",
        "precedence": 0,
        "provenance": {"role_name": "reviewer", "resolved_from": "/tmp/prompts/reviewer.md"},
    }
    rebuilt = msgspec.convert(raw, PromptFragment)
    assert rebuilt == f


def test_prompt_composed_round_trips_through_msgspec() -> None:
    """A PromptComposed survives msgspec.to_builtins + msgspec.convert.
    msgspec preserves the tuple in the builtins form; JSON encoding
    (msgspec.json.encode) lands it as an array; convert reads either
    shape back to a tuple. Round-trip via encode/decode keeps every
    field intact."""
    c = PromptComposed(
        text="alpha\n\nbravo\n\ncharlie",
        fragment_seqs=(3, 7, 12),
        total_tokens=6,
        strategy="precedence_join",
    )
    encoded = msgspec.json.encode(c)
    rebuilt = msgspec.json.decode(encoded, type=PromptComposed)
    assert rebuilt == c
    # to_builtins keeps the tuple; convert accepts tuple or list.
    raw = msgspec.to_builtins(c)
    assert raw["text"] == "alpha\n\nbravo\n\ncharlie"
    assert tuple(raw["fragment_seqs"]) == (3, 7, 12)
    assert raw["total_tokens"] == 6
    assert raw["strategy"] == "precedence_join"


def test_prompt_composed_empty_cohort_shape() -> None:
    """An empty cohort composes to empty text and empty fragment_seqs.
    The composer emits this rather than skipping — the record shows the
    turn had no fragments (see sprint 059's observation contract)."""
    c = PromptComposed(text="", fragment_seqs=(), total_tokens=0, strategy="precedence_join")
    raw = msgspec.to_builtins(c)
    assert tuple(raw["fragment_seqs"]) == ()
    assert raw["text"] == ""
    assert raw["total_tokens"] == 0
    # JSON round-trip lands empty list; decode restores empty tuple.
    encoded = msgspec.json.encode(c)
    rebuilt = msgspec.json.decode(encoded, type=PromptComposed)
    assert rebuilt.fragment_seqs == ()


def test_kind_name_constants_match_struct_qualnames() -> None:
    """PROMPT_FRAGMENT and PROMPT_COMPOSED constants match the msgspec
    Struct class names. A drift here would let the topology declare a
    subscription filter on one string and the Struct emit under a different
    name — the exact silent-typo class this constants module exists to
    catch (see the vocabulary.py module docstring)."""
    assert PROMPT_FRAGMENT == PromptFragment.__name__
    assert PROMPT_COMPOSED == PromptComposed.__name__


def test_session_kinds_frozenset_includes_the_two_v02_names() -> None:
    """SESSION_KINDS is the union of every kind the session vocabulary
    covers. Post-v0.2 that is ten names: the eight from v0.1 plus the two
    from v0.2. is_session_kind returns True for each."""
    assert PROMPT_FRAGMENT in SESSION_KINDS
    assert PROMPT_COMPOSED in SESSION_KINDS
    assert is_session_kind(PROMPT_FRAGMENT)
    assert is_session_kind(PROMPT_COMPOSED)
    # v0.1 kinds still present (byte-preservation of §§ A-H).
    assert "SessionStarted" in SESSION_KINDS
    assert "UserMessage" in SESSION_KINDS


def test_prompt_source_enum_has_the_seven_v02_values() -> None:
    """PROMPT_SOURCES is the enum. Every v0.2 source name is in it;
    is_prompt_source returns True for each; a bogus name returns False."""
    expected = {
        PROMPT_SOURCE_PER_TURN,
        PROMPT_SOURCE_ROLE,
        PROMPT_SOURCE_BUNDLE_METHODOLOGY,
        PROMPT_SOURCE_BUNDLE_PERSONALITY,
        PROMPT_SOURCE_PARENT_CONTEXT,
        PROMPT_SOURCE_TOOLS_SUITE,
        PROMPT_SOURCE_USER_MESSAGE,
    }
    assert PROMPT_SOURCES == expected
    for source in expected:
        assert is_prompt_source(source)
    assert not is_prompt_source("bogus_source_name")
    assert not is_prompt_source("")


def test_prompt_source_string_values_are_the_documented_values() -> None:
    """The wire representation of a PromptSource is the string itself,
    not an enum ordinal. Session-vocabulary.md § I documents each string;
    a drift here would silently rename the source on the wire and break
    every downstream reader keying on the value."""
    assert PROMPT_SOURCE_PER_TURN == "per_turn"
    assert PROMPT_SOURCE_ROLE == "role"
    assert PROMPT_SOURCE_BUNDLE_METHODOLOGY == "bundle_methodology"
    assert PROMPT_SOURCE_BUNDLE_PERSONALITY == "bundle_personality"
    assert PROMPT_SOURCE_PARENT_CONTEXT == "parent_context"
    assert PROMPT_SOURCE_TOOLS_SUITE == "tools_suite"
    assert PROMPT_SOURCE_USER_MESSAGE == "user_message"
