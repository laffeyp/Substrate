"""R-1 — Ensemble + adjudicator (product §8).

N candidate Producers stream answers to one question; a Bus-view Predicate ("≥ K
candidates") fires a single adjudicator (Once); on the adjudicator's completion,
cancel-all-others cancels the still-running candidates; all-completed finalises.

Exercises: concurrency (N candidates run at once), Bus-view Predicates (the "≥K answers"
gate reads a View over the bus), the Once firing policy, TerminationPolicy (cancel-others +
all-completed), and Level 3(a) replay with seeds (CI mode flags every Producer kind
deterministic, so the record's replay_ceiling stays "3a").

Dual-mode: hand it a DeterministicResponder (CI — proves the wiring; every kind flagged
deterministic) or a real local LLM per member (walkthrough — proves the adjudication claim).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
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


def _candidate_factory(member: str, question: str, responder: Responder) -> _Factory:
    async def candidate(_input: Any) -> AsyncIterator[Candidate]:
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
    members: dict[str, Responder],
    adjudicator: Responder,
    quorum: int = 3,
    deterministic: bool = True,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the R-1 topology. `members` maps member-name -> its Responder (N candidates);
    `adjudicator` is the judging Responder. `quorum` is the Bus-view threshold (≥K answers)
    that fires the adjudicator. `deterministic` flags the Producer kinds for Level-3(a) replay
    (True in CI; False in the walkthrough since a real LLM is not author-deterministic)."""

    def topo(b: api.TopologyBuilder) -> None:
        for name, responder in members.items():
            b.producer_kind(
                f"member-{name}",
                schemas=[Candidate],
                schema_version=1,
                factory=_candidate_factory(name, question, responder),
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
            predicate=lambda event, views: len(views["candidates"].value()) >= quorum,
            starts="adjudicator",
            input_builder=lambda views, staged, event: {
                "candidates": list(views["candidates"].value())
            },
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
