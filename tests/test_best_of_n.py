"""Observation contract for the extracted best-of-N + correction loop (sprint 136, Wave-0).

Proves the SHARED builder works standalone with deterministic stand-in factories — select-passing,
correction-then-pass, exhausted — and the validator-extra-schema path (swebench's AppliedPatch is emitted
by the validator alongside the Verdict; this proves an extra validator schema reaches the record).
Mirrors coding_flow's CI-outcome tests on the extracted module; the record is the observable (#24/#38).
"""

from collections.abc import AsyncIterator
from typing import Any

from msgspec import Struct

from substrate.api import Runtime, read_record
from substrate.topologies.best_of_n import best_of_n_correction
from substrate.topologies.coding_flow import Candidate, Verdict


def _outcome(events: list[dict]) -> dict | None:
    return next((e for e in events if e["kind"] in ("Solved", "Exhausted")), None)


def _kinds(events: list[dict], kind: str) -> list[dict]:
    return [e["payload"] for e in events if e["kind"] == kind]


def _draft_factory(good_from_round: int):  # type: ignore[no-untyped-def]
    async def draft(inp: Any) -> AsyncIterator[Candidate]:
        rnd, slot = int(inp.get("round", 1)), int(inp.get("slot", 0))
        yield Candidate(
            round=rnd, slot=slot, response=("GOOD" if rnd >= good_from_round else "BAD")
        )

    return lambda: draft


def _validate_factory(pass_slots: set[int]):  # type: ignore[no-untyped-def]
    async def validate(inp: Any) -> AsyncIterator[Verdict]:
        rnd, slot, resp = (
            int(inp.get("round", 1)),
            int(inp.get("slot", 0)),
            str(inp.get("response", "")),
        )
        ok = resp == "GOOD" and slot in pass_slots
        yield Verdict(
            round=rnd,
            slot=slot,
            passed=ok,
            returncode=0 if ok else 1,
            summary="ok" if ok else "fail",
        )

    return lambda: validate


async def _run(tmp_path, **kw):  # type: ignore[no-untyped-def]
    await Runtime(tmp_path / "run").run(lambda b: best_of_n_correction(b, **kw))
    return list(read_record(tmp_path / "run"))


async def test_selects_the_passing_candidate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    events = await _run(
        tmp_path,
        n=3,
        max_rounds=2,
        draft_factory=_draft_factory(1),
        validate_factory=_validate_factory({2}),
    )
    verdicts = _kinds(events, "Verdict")
    assert (
        len(verdicts) == 3 and sum(v["passed"] for v in verdicts) == 1
    )  # full best-of-N on the record
    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved" and out["payload"]["slot"] == 2


async def test_correction_then_pass(tmp_path) -> None:  # type: ignore[no-untyped-def]
    events = await _run(
        tmp_path,
        n=3,
        max_rounds=2,
        draft_factory=_draft_factory(2),
        validate_factory=_validate_factory({0, 1, 2}),
    )
    out = _outcome(events)
    assert (
        out is not None and out["kind"] == "Solved" and out["payload"]["round"] == 2
    )  # round 1 failed, 2 passed
    assert len(_kinds(events, "Verdict")) == 6  # 3 per round, both rounds on the record


async def test_exhausted_when_all_fail(tmp_path) -> None:  # type: ignore[no-untyped-def]
    events = await _run(
        tmp_path,
        n=3,
        max_rounds=1,
        draft_factory=_draft_factory(2),
        validate_factory=_validate_factory({0, 1, 2}),
    )
    out = _outcome(events)
    assert out is not None and out["kind"] == "Exhausted"


class Extra(Struct, frozen=True):
    slot: int
    note: str


def _validate_with_extra():  # type: ignore[no-untyped-def]
    async def validate(inp: Any) -> AsyncIterator[Any]:
        rnd, slot = int(inp.get("round", 1)), int(inp.get("slot", 0))
        yield Verdict(round=rnd, slot=slot, passed=True, returncode=0, summary="ok")
        yield Extra(slot=slot, note="bridge")  # the swebench AppliedPatch emission path

    return lambda: validate


async def test_validator_extra_schema_reaches_the_record(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # swebench's validator emits Verdict AND AppliedPatch; prove an extra validator schema lands on the log.
    events = await _run(
        tmp_path,
        n=1,
        max_rounds=1,
        draft_factory=_draft_factory(1),
        validate_factory=_validate_with_extra(),
        validator_schemas=[Verdict, Extra],
    )
    extras = _kinds(events, "Extra")
    assert len(extras) == 1 and extras[0]["note"] == "bridge"
    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved"
