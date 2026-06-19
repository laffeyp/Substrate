"""Narration projection tests (Wave 14).

Narration is a pure, deterministic, read-only projection over a run record: same log ->
same prose, no mutation, no wall-clock leakage. These tests pin (a) the lifecycle-noise
suppression contract, (b) the per-kind beat renderings (including every authoring
failure), (c) the summary tally, and (d) that it accepts both a root path and an iterable
of envelopes — the inspect-surface contract.
"""

from substrate import api
from substrate.projections.narrate import narrate, narration_summary
from substrate.topologies import bundled

REC = bundled.record_path("code_review")  # the committed, deterministic CI record


# ── the projection over a real committed record ─────────────────────────────────────────────
def test_narrate_suppresses_lifecycle_noise_by_default() -> None:
    kinds = {line.kind for line in narrate(REC)}
    # the plot beats + the work are present...
    assert "substrate.RunStarted" in kinds
    assert "substrate.TriggerFired" in kinds
    assert "substrate.TerminationMatched" in kinds
    assert "substrate.RunFinalised" in kinds
    assert "CritiquePosted" in kinds  # an application event (the work)
    # ...but the lifecycle bracketing is suppressed.
    assert "substrate.ProducerStarted" not in kinds
    assert "substrate.ProducerCompleted" not in kinds
    assert "substrate.InjectionApplied" not in kinds


def test_lifecycle_flag_restores_the_bracketing() -> None:
    kinds = {line.kind for line in narrate(REC, lifecycle=True)}
    assert "substrate.ProducerStarted" in kinds
    assert "substrate.ProducerCompleted" in kinds
    # every-frame account: the lifecycle run is a strict superset of the default run.
    default_seqs = {line.seq for line in narrate(REC)}
    full_seqs = {line.seq for line in narrate(REC, lifecycle=True)}
    assert default_seqs < full_seqs


def test_seqs_are_in_log_order() -> None:
    seqs = [line.seq for line in narrate(REC, lifecycle=True)]
    assert seqs == sorted(seqs)


def test_application_event_renders_producer_kind_and_fields() -> None:
    crit = next(line for line in narrate(REC) if line.kind == "CritiquePosted")
    # "<producer kind> -> CritiquePosted (role=..., severity=...)"
    assert crit.text.startswith("reviewer-")
    assert "-> CritiquePosted" in crit.text
    assert "role=" in crit.text and "severity=" in crit.text


def test_trigger_and_termination_and_finalise_prose() -> None:
    texts = {line.kind: line.text for line in narrate(REC)}
    assert texts["substrate.RunStarted"].startswith("Run started")
    assert "starts " in texts["substrate.TriggerFired"]  # causal beat
    assert texts["substrate.TerminationMatched"].startswith("Termination matched:")
    assert texts["substrate.RunFinalised"] == "Run finalised."
    cancel = next(line for line in narrate(REC) if line.kind == "substrate.ProducerCancelled")
    assert cancel.text.endswith("cancelled.") and cancel.text.startswith("reviewer-")


def test_determinism_no_wallclock_leak() -> None:
    a = [(line.seq, line.text) for line in narrate(REC, lifecycle=True)]
    b = [(line.seq, line.text) for line in narrate(REC, lifecycle=True)]
    assert a == b
    # the supplementary wall-clock `t` must never enter the prose.
    assert all("'t':" not in text and "t=" not in text for _, text in a)


def test_accepts_root_path_and_iterable_equivalently() -> None:
    from_path = [(line.seq, line.text) for line in narrate(REC)]
    envelopes = list(api.read_record(REC))
    from_iter = [(line.seq, line.text) for line in narrate(envelopes)]
    assert from_path == from_iter


def test_narrate_does_not_mutate_input_envelopes() -> None:
    envelopes = list(api.read_record(REC))
    import copy

    before = copy.deepcopy(envelopes)
    _ = list(narrate(envelopes, lifecycle=True))
    assert envelopes == before


# ── the summary tally ───────────────────────────────────────────────────────────────────────
def test_summary_tally_matches_the_record() -> None:
    s = narration_summary(REC)
    assert s.finalised is True
    assert s.final_reason is None  # an ordinary, clean finalise
    assert s.producers_started == s.producers_completed + s.producers_cancelled
    assert s.producers_failed == 0
    assert s.input_build_failures == 0
    assert s.predicate_quarantines == 0
    assert s.invalid_emissions == 0
    assert s.application_events.get("CritiquePosted", 0) >= 1
    assert s.application_events.get("VerdictRendered", 0) >= 1


# ── failure renderings (hand-built envelopes — the all-green record has none) ────────────────
def _ref(kind: str) -> dict[str, object]:
    return {"kind": kind, "instance": "01ABC", "parent": None}


def test_producer_failed_renders_prominently() -> None:
    env = [
        {
            "seq": 3,
            "kind": "substrate.ProducerFailed",
            "payload": {"producer": _ref("solver"), "error": "RuntimeError('boom')"},
        }
    ]
    (line,) = list(narrate(env))
    assert line.text == "solver FAILED: RuntimeError('boom')"


def test_input_build_failed_renders_the_trigger_and_error() -> None:
    env = [
        {
            "seq": 4,
            "kind": "substrate.InputBuildFailed",
            "payload": {"trigger_id": "after-3", "firing_key": "k1", "error": "KeyError('x')"},
        }
    ]
    (line,) = list(narrate(env))
    assert line.text == "Input build failed for after-3: KeyError('x')"


def test_predicate_quarantined_and_invalid_emission() -> None:
    env = [
        {
            "seq": 5,
            "kind": "substrate.PredicateQuarantined",
            "payload": {"trigger_id": "t1", "reason": "slow_predicate", "error": "took 9001us"},
        },
        {
            "seq": 6,
            "kind": "substrate.ProducerEmittedInvalidEvent",
            "payload": {"reason": "schema_violation", "producer": _ref("writer"), "at_path": "$.n"},
        },
    ]
    quar, inval = list(narrate(env))
    assert quar.text == "Predicate quarantined (trigger t1): slow_predicate -- took 9001us"
    assert inval.text == "writer emitted an invalid event: schema_violation at $.n"


def test_every_beat_is_a_single_line_even_with_newline_payloads() -> None:
    # a free-text field (a code chunk, a multi-line message) must not break the one-line-per-
    # beat contract — legibility and grep-ability both rest on it.
    env = [
        {
            "seq": 1,
            "kind": "CodeChunk",
            "producer": _ref("driver"),
            "payload": {"text": "def solve(x):\n    return x\n", "chunk_index": 0},
        }
    ]
    (line,) = list(narrate(env))
    assert "\n" not in line.text  # the whole beat stays on one line
    assert "\\n" in line.text  # the newline is shown, escaped


def test_no_beat_contains_a_raw_newline_across_a_real_record() -> None:
    # pair_coding's CodeChunk.text carries real newlines — the regression this guards.
    rec = bundled.record_path("pair_coding")
    assert all("\n" not in line.text for line in narrate(rec, lifecycle=True))


def test_empty_record_narrates_to_nothing() -> None:
    assert list(narrate([])) == []
    s = narration_summary([])
    assert s.finalised is False and s.total_events == 0 and s.application_events == {}


def test_unknown_forward_compat_substrate_kind_is_named_not_dropped() -> None:
    # a substrate.* kind this version doesn't know must still render (named + payload), never
    # silently vanish — forward compatibility.
    (line,) = list(narrate([{"seq": 5, "kind": "substrate.SomethingNew", "payload": {"a": 1}}]))
    assert line.text == "SomethingNew (a=1)"


def test_degrades_on_missing_or_malformed_payload() -> None:
    envs = [
        {"seq": 1, "kind": "CritiquePosted", "producer": _ref("r"), "payload": None},
        {"seq": 2, "kind": "substrate.RunFinalised"},  # no payload key at all
        {"seq": 3, "kind": "Widget", "payload": {"x": 1}},  # application event, no producer
        {"seq": 4, "kind": "Thing", "payload": "not a dict"},
    ]
    texts = [line.text for line in narrate(envs)]
    assert texts == ["r -> CritiquePosted", "Run finalised.", "? -> Widget (x=1)", "? -> Thing"]


def test_pause_beat_renders_the_resume_condition() -> None:
    # the load-bearing fact about a pause is WHAT it awaits (review #26) — not a bare decision.
    env = [
        {
            "seq": 3,
            "kind": "substrate.TerminationMatched",
            "payload": {
                "policy": "pause_await_input",
                "decision": "pause-await-input",
                "resume_condition": "human approval of the plan",
            },
        }
    ]
    (line,) = list(narrate(env))
    assert line.text == "Run paused -- awaiting: human approval of the plan."


def test_pause_beat_without_condition_is_still_legible() -> None:
    env = [
        {
            "seq": 3,
            "kind": "substrate.TerminationMatched",
            "payload": {"decision": "pause-await-input"},
        }
    ]
    (line,) = list(narrate(env))
    assert line.text == "Run paused -- awaiting input."


def test_paused_finalise_reason_is_carried() -> None:
    env = [{"seq": 7, "kind": "substrate.RunFinalised", "payload": {"reason": "pause_await_input"}}]
    (line,) = list(narrate(env))
    assert line.text == "Run finalised (pause_await_input)."
    assert narration_summary(env).final_reason == "pause_await_input"


def test_summary_counts_failures_on_a_broken_run() -> None:
    env = [
        {"seq": 0, "kind": "substrate.RunStarted", "payload": {"run_id": "R1"}},
        {
            "seq": 1,
            "kind": "substrate.ProducerFailed",
            "payload": {"producer": _ref("a"), "error": "e"},
        },
        {"seq": 2, "kind": "substrate.RunFinalised", "payload": {}},
    ]
    s = narration_summary(env)
    assert s.finalised is True  # finalised-but-broken: the count makes that legible
    assert s.producers_failed == 1
    assert s.total_events == 3
