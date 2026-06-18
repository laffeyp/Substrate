"""cancel-others TerminationPolicy path (kernel §8; F-LIFE-2).

Exercises the runtime CANCEL_OTHERS path: when a subject Producer (an adjudicator)
completes, cancel_all_others cancels the still-running others, which emit
substrate.ProducerCancelled on the log; the run continues to quiescence and finalises. The
subject is spared. This is the cancellation observability R-1 demonstrates."""

import asyncio

import pytest
from msgspec import Struct

from substrate.api import (
    Once,
    Runtime,
    Subscription,
    all_completed,
    any_of,
    cancel_all_others,
    read_record,
)


class Candidate(Struct, frozen=True):
    who: str


class Verdict(Struct, frozen=True):
    pass


def _slow_candidate(name: str):
    async def cand(_input):
        yield Candidate(who=name)
        await asyncio.sleep(30)  # long-running; should be CANCELLED by cancel-others
        yield Candidate(who=name + "-late")  # pragma: no cover - never reached

    return cand


async def _adjudicator(_input):
    yield Verdict()  # completes immediately on firing


def _ensemble_topo(b):
    # three slow candidates + an adjudicator that fires once a candidate appears; on the
    # adjudicator's completion, cancel-all-others cancels the still-running candidates.
    for i in range(3):
        b.producer_kind(
            f"cand{i}",
            schemas=[Candidate],
            schema_version=1,
            factory=lambda i=i: _slow_candidate(f"c{i}"),
        )
        b.initial(f"cand{i}", input=None)
    b.producer_kind("adj", schemas=[Verdict], schema_version=1, factory=lambda: _adjudicator)
    b.trigger(
        "adjudicate",
        subscription=Subscription(kinds=frozenset({"Candidate"})),
        predicate=lambda ctx: True,
        starts="adj",
        input_builder=lambda ctx: None,
        policy=Once(),  # adjudicate once
    )
    # cancel the other (candidate) Producers when the adjudicator completes; then all-completed
    # finalises once everything has ended (the cancelled candidates + the done adjudicator).
    b.termination(
        any_of(
            cancel_all_others(
                lambda c: (
                    c.event is not None
                    and getattr(c.event, "kind", "") == "substrate.ProducerCompleted"
                    and isinstance(getattr(c.event, "payload", None), dict)
                    and c.event.payload.get("producer", {}).get("kind") == "adj"
                )
            ),
            all_completed(),
        )
    )


@pytest.mark.timeout(15)
async def test_cancel_all_others_cancels_candidates_spares_adjudicator(tmp_path):
    result = await Runtime(tmp_path / "run").run(_ensemble_topo)
    assert result.status == "finalised"  # did not hang on the 30s-sleeping candidates
    envs = list(read_record(tmp_path / "run"))
    cancelled = [e for e in envs if e["kind"] == "substrate.ProducerCancelled"]
    cancelled_kinds = sorted(e["payload"]["producer"]["kind"] for e in cancelled)
    # the three candidates were cancelled (observable on the log); the adjudicator was NOT
    assert cancelled_kinds == ["cand0", "cand1", "cand2"]
    assert not any(e["payload"]["producer"]["kind"] == "adj" for e in cancelled)
    # the adjudicator completed normally
    adj_completed = [
        e
        for e in envs
        if e["kind"] == "substrate.ProducerCompleted" and e["payload"]["producer"]["kind"] == "adj"
    ]
    assert len(adj_completed) == 1
    # cancel-others is a non-terminal decision: a TerminationMatched{cancel-others} precedes
    # the eventual RunFinalised (all-completed), and RunFinalised is last.
    tm = [e for e in envs if e["kind"] == "substrate.TerminationMatched"]
    assert any(e["payload"]["decision"] == "cancel-others" for e in tm)
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_cancel_others_idempotent_no_vacuous_match(tmp_path):
    # a cancel-others policy that keeps matching must NOT thrash: once the others are
    # cancelled, repeat CANCEL_OTHERS decisions are no-ops (no extra TerminationMatched).
    await Runtime(tmp_path / "run").run(_ensemble_topo)
    envs = list(read_record(tmp_path / "run"))
    co = [
        e
        for e in envs
        if e["kind"] == "substrate.TerminationMatched"
        and e["payload"]["decision"] == "cancel-others"
    ]
    assert len(co) == 1  # exactly one cancel-others, not one-per-cycle
