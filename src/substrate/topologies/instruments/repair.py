"""Repair instrument — other-initiated repair as an emergence move.

Conversation analysis (Schegloff) names other-initiated repair: an interlocutor flags that the
prior turn needs clarification before the conversation continues. Stateless LLMs have no native
repair signal. This instrument supplies it: a side Producer fired on each Turn scans the
transcript for misalignment and emits a typed Repair event; on a non-ok status a Route prepends
a requires-repair cue to the next speaker's input. Repair dynamics EMERGE from the detector
firing, not from a prescription in a speaker's system prompt. Non-load-bearing (soft-fail).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ...reference._models import Responder, call_responder

_Factory = Callable[[], Any]

REPAIR_OK = "ok"
REPAIR_MISALIGNED = "misaligned"
REPAIR_CONTRADICTION = "contradiction"


class Repair(Struct, frozen=True):
    """A misalignment verdict on the just-landed turn. status: ok | misaligned | contradiction;
    note is one line when non-ok, empty when ok."""

    status: str
    note: str
    round: int


def repair_factory(
    responder: Responder, *, ci_status: str = REPAIR_OK, alternate: bool = False
) -> _Factory:
    async def detect(inp: Any) -> AsyncIterator[Repair]:
        rnd = int(inp.get("round", 0)) if hasattr(inp, "get") else 0
        _ = await call_responder(responder, "scan the latest turn for misalignment")
        # walkthrough: the LLM judges. CI: a deterministic status — `alternate` discriminates by
        # round parity so the record shows the detector both FIRING and staying quiet (not firing
        # every turn, which reads as "is it doing anything?"); else the fixed `ci_status`.
        status = (REPAIR_MISALIGNED if rnd % 2 == 0 else REPAIR_OK) if alternate else ci_status
        note = "" if status == REPAIR_OK else "deterministic misalignment cue (round parity)"
        yield Repair(status=status, note=note, round=rnd)

    return lambda: detect
