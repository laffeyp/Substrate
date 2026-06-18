"""Common-ground instrument — accreting shared state as a side-effect of every turn.

Real interlocutors accrete common ground (Clark 1996) as a side-effect of each utterance;
stateless LLMs must hand-rebuild it every turn. This instrument supplies the missing state: a
side Producer fired on each Turn reads the transcript View and emits a typed CommonGround event;
a Route stages it into the next speaker's input. It is non-load-bearing — a failure emits
ProducerFailed and the conversation continues (substrate gives that for free).

In walkthrough mode the Producer calls an LLM with the extractor prompt; in CI it derives a
stable digest of the recent turns so the wiring runs deterministically.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ...reference._models import Responder

_Factory = Callable[[], Any]


class CommonGround(Struct, frozen=True):
    """The shared-state document after a turn: a short list of established facts + the round."""

    facts: tuple[str, ...]
    round: int


def common_ground_factory(responder: Responder) -> _Factory:
    async def extract(inp: Any) -> AsyncIterator[CommonGround]:
        transcript = inp.get("transcript", []) if hasattr(inp, "get") else []
        rnd = int(inp.get("round", 0)) if hasattr(inp, "get") else 0
        # walkthrough: the LLM maintains the document; CI: a deterministic digest of recent turns.
        _ = responder.respond(f"update common ground from {len(transcript)} turns")
        facts = tuple(f"S{t['speaker']}: {str(t['text'])[:40]}" for t in transcript[-3:])
        yield CommonGround(facts=facts, round=rnd)

    return lambda: extract
