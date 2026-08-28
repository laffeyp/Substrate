"""Session-topology vocabulary — named constants for the eight kind strings.

TECH-SPEC §3a locks session-vocabulary.md as the topology's kind surface;
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
    }
)


def is_session_kind(kind: str) -> bool:
    """Whether `kind` is one of the eight session-vocabulary names.
    Callers use this at receipt boundaries the way `constants.is_reserved`
    is used at kernel receipt boundaries."""
    return kind in SESSION_KINDS


__all__ = [
    "MODEL_REPLY",
    "PARK",
    "SESSION_ENDED",
    "SESSION_END_REQUESTED",
    "SESSION_KINDS",
    "SESSION_STARTED",
    "SESSION_WARNING",
    "TRANSCRIPT_COMPACTED",
    "USER_MESSAGE",
    "is_session_kind",
]
