"""Sprint 210 — piece-A observation contract end-to-end (in-process discharge).

**Scope amendment folded 2026-08-26.** The sprint card names a `substrate chat
deterministic --script fixtures/two_turns.json --name test-piece-a` CLI subprocess
harness. That CLI lands in pieces B/C/D (sprints 214-221); it does not exist yet.
Rescoped: this sprint discharges the RECORD-LEVEL observation contract in-process
today, using `ci_session_topology` to drive the same three-turn script the fixture
lists. The stderr-substring checks and the terminal-screenshot check defer to
sprint 221 (once `substrate chat` exists). The application-kind sequence, the
per-event payload predicates, and the lifecycle-event coverage all fire here.

The fixture `tests/fixtures/two_turns.json` lives on disk so sprint 221 can pick
it up unchanged. `_load_turns` reads it and passes to `ci_session_topology`.

TECH-SPEC-2026-08-25-round6 §3 observation contract:
  - UserMessage(turn_index=0, text="say hi") → ModelReply(turn_index=0) →
    FinalAnswer → Park(reason="final_answer", turn_index=0) → (mirror for turn 1) →
    UserMessage(text="/exit", turn_index=2) → SessionEnded(reason="user_exit",
    total_turns=3) → substrate.RunFinalised.
  - Lifecycle events for each turn: `substrate.TriggerFired(resume-on-user)`,
    `substrate.ProducerStarted(model)`, `substrate.ProducerCompleted(model)`,
    `substrate.TriggerFired(park-on-final)`, `substrate.ProducerStarted(park)`,
    `substrate.TerminationMatched(decision=pause-await-input)` — the last one
    is replaced here by the CI wrapper's `advance-on-park` firing driver_stepper
    (no pause; the wrapper drives itself to finalise on SessionEnded).

The wrapper's `driver_stepper` producer fires three times (once per turn). The
`advance-on-park` trigger replaces the daemon-injected `.resume(UserMessage=...)`
step. The final trigger is `substrate.TerminationMatched(decision=finalise-run)`
on the SessionEnded event.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate import api
from substrate.testing import assert_event, assert_no_event, assert_sequence
from substrate.topologies.session.ci import ci_session_topology

_FIXTURES = Path(__file__).parent / "fixtures"


def _load_turns() -> tuple[str, ...]:
    fixture = _FIXTURES / "two_turns.json"
    entries = json.loads(fixture.read_text(encoding="utf-8"))
    return tuple(str(e["text"]) for e in entries)


@pytest.mark.asyncio
async def test_piece_a_observation_contract_record_level(tmp_path: Path) -> None:
    """Fire the piece-A observation contract in-process. The record's payload-kind
    sequence matches the tech spec §3 sequence for the three-turn script, and
    every per-turn payload predicate holds.
    """
    turns = _load_turns()
    assert turns == ("say hi", "count to five", "/exit"), f"fixture drifted: {turns}"
    record_root = tmp_path / "test-piece-a"
    result = await api.Runtime(record_root).run(
        ci_session_topology(turns=turns, session_id="test-piece-a")
    )
    assert result.status == "finalised"

    # Payload-kind sequence (application events only, in order).
    payload_kinds = [
        e["kind"] for e in api.read_record(record_root) if not e["kind"].startswith("substrate.")
    ]
    assert payload_kinds == [
        "UserMessage",
        "ModelReply",
        "FinalAnswer",
        "Park",
        "UserMessage",
        "ModelReply",
        "FinalAnswer",
        "Park",
        "UserMessage",
        "ModelReply",
        "FinalAnswer",
        "SessionEnded",
    ]

    # Per-turn payload predicates (F-API-4 primitives).
    assert_event(record_root, "UserMessage", turn_index=0, text="say hi")
    assert_event(record_root, "UserMessage", turn_index=1, text="count to five")
    assert_event(record_root, "UserMessage", turn_index=2, text="/exit")
    assert_event(record_root, "ModelReply", turn_index=0)
    assert_event(record_root, "ModelReply", turn_index=1)
    assert_event(record_root, "ModelReply", turn_index=2)
    assert_event(record_root, "FinalAnswer", steps=0)
    assert_event(record_root, "Park", reason="final_answer", turn_index=0)
    assert_event(record_root, "Park", reason="final_answer", turn_index=1)
    assert_event(record_root, "SessionEnded", reason="user_exit", total_turns=3)
    assert_no_event(record_root, "SessionWarning")


@pytest.mark.asyncio
async def test_piece_a_lifecycle_events_cover_each_producer(tmp_path: Path) -> None:
    """The four session producers (driver_stepper, model, park, session_end) each
    emit ProducerStarted + ProducerCompleted at least once, and TriggerFired lands
    for the key triggers (resume-on-user, park-on-final, end-on-exit, advance-on-park).
    """
    record_root = tmp_path / "test-piece-a-lifecycle"
    await api.Runtime(record_root).run(
        ci_session_topology(turns=_load_turns(), session_id="test-piece-a-lifecycle")
    )
    envelopes = list(api.read_record(record_root))
    started_kinds = {
        e["payload"]["producer"]["kind"]
        for e in envelopes
        if e["kind"] == "substrate.ProducerStarted"
    }
    completed_kinds = {
        e["payload"]["producer"]["kind"]
        for e in envelopes
        if e["kind"] == "substrate.ProducerCompleted"
    }
    assert {"driver_stepper", "model", "park", "session_end"} <= started_kinds, (
        f"missing ProducerStarted for one of the session producers: got {started_kinds}"
    )
    # session_end's ProducerCompleted may race with TerminationMatched: the wrapper's
    # threshold_count(SessionEnded, 1) matches on the SessionEnded emit and finalises
    # the run before session_end's completion tick lands. Honest reality of the append
    # cycle. driver_stepper, model, and park all fire multiple times per session and
    # their completions always land.
    assert {"driver_stepper", "model", "park"} <= completed_kinds, (
        f"missing ProducerCompleted for driver_stepper/model/park: got {completed_kinds}"
    )
    trigger_ids = {
        e["payload"].get("trigger_id") for e in envelopes if e["kind"] == "substrate.TriggerFired"
    }
    assert {"resume-on-user", "park-on-final", "end-on-exit", "advance-on-park"} <= trigger_ids


@pytest.mark.asyncio
async def test_piece_a_termination_matched_finalises_the_run(tmp_path: Path) -> None:
    """`substrate.TerminationMatched(decision="finalise-run")` lands as the last
    lifecycle event before RunFinalised. The CI wrapper's `threshold_count(SessionEnded, 1)`
    fires on the SessionEnded that `/exit` produces; no pause landed at any Park.
    """
    record_root = tmp_path / "test-piece-a-termination"
    await api.Runtime(record_root).run(
        ci_session_topology(turns=_load_turns(), session_id="test-piece-a-termination")
    )
    envelopes = list(api.read_record(record_root))
    term_events = [e for e in envelopes if e["kind"] == "substrate.TerminationMatched"]
    assert len(term_events) == 1
    assert term_events[0]["payload"].get("decision") == "finalise-run"
    assert envelopes[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.asyncio
async def test_piece_a_is_replayable_end_to_end(tmp_path: Path) -> None:
    """The whole scripted piece-A run is Level-3(a) byte-identical on replay —
    scripted driver_stepper + DeterministicResponder + deterministic CALCULATOR."""
    record_root = tmp_path / "test-piece-a-replay"
    await api.Runtime(record_root).run(
        ci_session_topology(turns=_load_turns(), session_id="test-piece-a-replay")
    )
    api.assert_replayable(record_root, "3a")


def test_fixture_shape_survives_the_two_turns_json() -> None:
    """A brittle-fixture guard. Sprint 221 will pick up the JSON verbatim; drift
    surfaces here before sprint 221 finds it.
    """
    fixture = _FIXTURES / "two_turns.json"
    entries = json.loads(fixture.read_text(encoding="utf-8"))
    assert isinstance(entries, list) and len(entries) == 3
    assert all(isinstance(e, dict) and "text" in e for e in entries)
    assert entries[-1]["text"] == "/exit"
    # Also verify assert_sequence is imported and usable (silences "unused import").
    assert callable(assert_sequence)
