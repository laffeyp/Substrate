# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-topology vocabulary — named constants for the eight kind strings.

the tech spec locks session-vocabulary.md as the topology's kind surface;
this module is the runtime enforcement layer that closes the "kind-name
typo drifts silently" class the Markdown-only vocabulary cannot catch
(REVIEW-2026-08-28 F5). The msgspec Structs at the top of `__init__.py`
type-check payload fields at the speaker's mouth; msgspec cannot check
the kind-name STRING itself, so a `"SessionEndeed"` typo in a
subscription filter or a trigger declaration would land silently.

Every reference to a session-vocabulary kind name inside
`substrate.topologies.session.*` must import from here. Grep of the
package after the F5 adoption pass returns zero raw literals of the
eight names outside this file and the committed CI records.

The kernel-side reserved lifecycle kinds (RunStarted, RunFinalised, …)
live in `substrate.constants`; that side is enforced by the same rule
via `is_reserved(kind)`. The two vocabularies do not overlap by design.
"""

from __future__ import annotations


# Session-vocabulary kind names (session-vocabulary.md, ratified 2026-08-25).
SESSION_STARTED = "SessionStarted"
USER_MESSAGE = "UserMessage"
MODEL_REPLY = "ModelReply"
PARK = "Park"
SESSION_ENDED = "SessionEnded"
SESSION_END_REQUESTED = "SessionEndRequested"
TRANSCRIPT_COMPACTED = "TranscriptCompacted"
SESSION_WARNING = "SessionWarning"

# v0.2 additions (session-vocabulary.md § I, sprint 058, 2026-09-01).
PROMPT_FRAGMENT = "PromptFragment"
PROMPT_COMPOSED = "PromptComposed"


SESSION_KINDS: frozenset[str] = frozenset(
    {
        SESSION_STARTED,
        USER_MESSAGE,
        MODEL_REPLY,
        PARK,
        SESSION_ENDED,
        SESSION_END_REQUESTED,
        TRANSCRIPT_COMPACTED,
        SESSION_WARNING,
        PROMPT_FRAGMENT,
        PROMPT_COMPOSED,
    }
)


# v0.2 additions — `PromptSource` enum values for `PromptFragment.source`.
# String enum (not `enum.Enum`) so the wire representation is the string itself;
# msgspec serializes without extra glue. Extending the enum bumps the session
# vocabulary version (v0.2 → v0.2.1 → v0.3 as sources land).
PROMPT_SOURCE_PER_TURN = "per_turn"
PROMPT_SOURCE_ROLE = "role"
PROMPT_SOURCE_BUNDLE_METHODOLOGY = "bundle_methodology"
PROMPT_SOURCE_BUNDLE_PERSONALITY = "bundle_personality"
PROMPT_SOURCE_PARENT_CONTEXT = "parent_context"
PROMPT_SOURCE_TOOLS_SUITE = "tools_suite"
PROMPT_SOURCE_USER_MESSAGE = "user_message"


PROMPT_SOURCES: frozenset[str] = frozenset(
    {
        PROMPT_SOURCE_PER_TURN,
        PROMPT_SOURCE_ROLE,
        PROMPT_SOURCE_BUNDLE_METHODOLOGY,
        PROMPT_SOURCE_BUNDLE_PERSONALITY,
        PROMPT_SOURCE_PARENT_CONTEXT,
        PROMPT_SOURCE_TOOLS_SUITE,
        PROMPT_SOURCE_USER_MESSAGE,
    }
)


def is_prompt_source(source: str) -> bool:
    """Whether `source` is one of the seven v0.2 PromptSource enum values.
    Callers use this the way `is_session_kind` gates kind names — at the
    fragment producer's yield seam, not deep in the composer body."""
    return source in PROMPT_SOURCES


def is_session_kind(kind: str) -> bool:
    """Whether `kind` is one of the eight session-vocabulary names.
    Callers use this at receipt boundaries the way `constants.is_reserved`
    is used at kernel receipt boundaries."""
    return kind in SESSION_KINDS


__all__ = [
    "MODEL_REPLY",
    "PARK",
    "PROMPT_COMPOSED",
    "PROMPT_FRAGMENT",
    "PROMPT_SOURCES",
    "PROMPT_SOURCE_BUNDLE_METHODOLOGY",
    "PROMPT_SOURCE_BUNDLE_PERSONALITY",
    "PROMPT_SOURCE_PARENT_CONTEXT",
    "PROMPT_SOURCE_PER_TURN",
    "PROMPT_SOURCE_ROLE",
    "PROMPT_SOURCE_TOOLS_SUITE",
    "PROMPT_SOURCE_USER_MESSAGE",
    "SESSION_ENDED",
    "SESSION_END_REQUESTED",
    "SESSION_KINDS",
    "SESSION_STARTED",
    "SESSION_WARNING",
    "TRANSCRIPT_COMPACTED",
    "USER_MESSAGE",
    "is_prompt_source",
    "is_session_kind",
]

# spec-audit: 2026-09-01
