"""R-1 — Ensemble + adjudicator (product §8).

N candidate Producers stream answers to one question; a Bus-view Predicate ("≥ K
candidates") fires a single adjudicator (Once); on the adjudicator's completion,
cancel-all-others cancels the still-running candidates; all-completed finalises.

The cancellation facet is demonstrated on R-1's OWN record (not just unit-tested elsewhere):
designate `slow_members` that linger `linger_seconds` before yielding. A quorum of fast
members fires the adjudicator, which completes while the lingerers are still asleep, so
cancel-all-others has live victims and `substrate.ProducerCancelled` lands on the log for
each lingerer.

Exercises: concurrency (N candidates run at once), Bus-view Predicates (the "≥K answers"
gate reads a View over the bus), the Once firing policy, TerminationPolicy (cancel-others +
all-completed), and Level 3(a) replay with seeds (CI mode flags every Producer kind
deterministic, so the record's replay_ceiling stays "3a").

Dual-mode: hand it a DeterministicResponder (CI — proves the wiring; every kind flagged
deterministic) or a real local LLM per member (walkthrough — proves the adjudication claim).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from msgspec import Struct

from .. import api
from ._models import Responder

# A Producer factory: a zero-arg callable returning the `start` async-generator. Typed as
# Callable[[], Any] because an async-generator function's static type does not structurally
# match the Producer Protocol's `__call__(input)->AsyncIterable[Event]` under mypy --strict,
# though it satisfies it at runtime (the runtime calls factory()(input) and async-iterates).
_Factory = Callable[[], Any]


class Candidate(Struct, frozen=True):
    member: str
    answer: str


class Verdict(Struct, frozen=True):
    chosen: str
    answer: str


def _candidate_factory(
    member: str, question: str, responder: Responder, linger_seconds: float = 0.0
) -> _Factory:
    async def candidate(_input: Any) -> AsyncIterator[Candidate]:
        # A "lingering" member (linger_seconds > 0) sleeps BEFORE yielding, so it is still
        # running — and has NOT contributed a Candidate to the bus — when the fast quorum fires
        # the adjudicator. That makes it a live victim for cancel-all-others on the adjudicator's
        # completion, which is the cancellation R-1 exists to demonstrate on its own record.
        # Sleeping before the yield keeps it out of the quorum count, so the linger count never
        # changes how many fast Candidates are needed to fire.
        if linger_seconds > 0:
            await asyncio.sleep(linger_seconds)
        yield Candidate(member=member, answer=responder.respond(question))

    return lambda: candidate


def _adjudicator_factory(question: str, responder: Responder) -> _Factory:
    async def adjudicate(inp: Any) -> AsyncIterator[Verdict]:
        # inp carries the accumulated candidates (the input_builder reads the BufferView).
        cands = inp.get("candidates", []) if hasattr(inp, "get") else []
        if not cands:
            yield Verdict(chosen="<none>", answer="")
            return
        # the adjudicator judges; in CI the deterministic responder picks a stable member,
        # in the walkthrough the real model reasons over the candidate answers.
        listing = "\n".join(f"{c['member']}: {c['answer']}" for c in cands)
        prompt = f"Question: {question}\nCandidate answers:\n{listing}\nWhich member is best? Reply with just the member name."
        choice = responder.respond(prompt).strip()
        chosen = next((c for c in cands if c["member"] in choice), cands[0])
        yield Verdict(chosen=chosen["member"], answer=chosen["answer"])

    return lambda: adjudicate


def ensemble_topology(
    question: str,
    *,
    members: Mapping[str, Responder],
    adjudicator: Responder,
    quorum: int = 3,
    deterministic: bool = True,
    slow_members: frozenset[str] = frozenset(),
    linger_seconds: float = 0.0,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the R-1 topology. `members` maps member-name -> its Responder (N candidates);
    `adjudicator` is the judging Responder. `quorum` is the Bus-view threshold (≥K answers)
    that fires the adjudicator. `deterministic` flags the Producer kinds for Level-3(a) replay
    (True in CI; False in the walkthrough since a real LLM is not author-deterministic).

    `slow_members` names members that LINGER (sleep `linger_seconds` before yielding their
    Candidate). With a quorum of fast members, the adjudicator fires and completes while the
    lingering members are still running, so cancel-all-others has real victims to cancel —
    `substrate.ProducerCancelled` lands on the record for each lingerer. This makes R-1
    demonstrate its cancellation facet on its own log rather than merely wiring it.

    Lingering members are still flagged with `deterministic` (the sleep is a fixed-duration
    wait, not a source of nondeterministic *output*; their Candidate, if they ever yielded one,
    is seed-derived). In CI the lingerers never complete — they are cancelled — so they emit no
    Candidate to the record; flagging them deterministic keeps the record's replay_ceiling at
    "3a" exactly as the fast members do."""

    def topo(b: api.TopologyBuilder) -> None:
        for name, responder in members.items():
            linger = linger_seconds if name in slow_members else 0.0
            b.producer_kind(
                f"member-{name}",
                schemas=[Candidate],
                schema_version=1,
                factory=_candidate_factory(name, question, responder, linger),
                deterministic=deterministic,
            )
            b.initial(f"member-{name}", input=None)
        b.producer_kind(
            "adjudicator",
            schemas=[Verdict],
            schema_version=1,
            factory=_adjudicator_factory(question, adjudicator),
            deterministic=deterministic,
        )
        # a Bus-view of all Candidate answers (a KindBuffer over the Candidate KIND, since the
        # N members are distinct Producer kinds all emitting Candidate); the predicate gates on
        # its size — the Bus-view predicate the R-1 topology exists to demonstrate.
        b.view("candidates", api.KindBuffer("Candidate"))
        b.trigger(
            "adjudicate",
            subscription=api.Subscription(kinds=frozenset({"Candidate"})),
            predicate=lambda ctx: len(ctx.views["candidates"].value()) >= quorum,
            starts="adjudicator",
            input_builder=lambda ctx: {"candidates": list(ctx.views["candidates"].value())},
            policy=api.Once(),  # exactly one adjudication
        )
        # cancel the still-running candidates when the adjudicator completes; then
        # all-completed finalises once everything (cancelled candidates + done adjudicator) ends.
        b.termination(
            api.any_of(
                api.cancel_all_others(
                    lambda c: (
                        c.event is not None
                        and getattr(c.event, "kind", "") == "substrate.ProducerCompleted"
                        and isinstance(getattr(c.event, "payload", None), dict)
                        and c.event.payload.get("producer", {}).get("kind") == "adjudicator"
                    )
                ),
                api.all_completed(),
            )
        )

    return topo
