"""Narration — the legible prose projection of a run record (Wave 14).

A pure, deterministic projection from the immutable log to a human-readable account of
what happened (F-OBS-6: read-only, no bus emission, no record mutation). It is the data
layer a UI renders and the engine behind `substrate narrate`; it adds no state and no
events, and the same record always narrates identically — the wall-clock `t` and other
supplementary metadata never enter the prose (only kind, producer kind, and the salient
payload fields do).

Narration tells the STORY (the plot), not every heartbeat. By default it renders:
  - the substrate.* causal beats in prose — a TriggerFired as "starts <producer>", a
    TerminationMatched as "termination matched: <decision>", finalisation, and EVERY
    authoring failure (ProducerFailed / InputBuildFailed / PredicateQuarantined /
    ProducerEmittedInvalidEvent) — these are the load-bearing beats a reader must see;
  - every APPLICATION event (a non-substrate.* kind) as "<producer> -> <Kind> (<fields>)"
    — the actual work the topology did.
It SUPPRESSES the pure lifecycle bracketing (ProducerStarted / ProducerCompleted /
InjectionApplied) by default: the trigger beat already says a producer started and the
application event says what it did, so the brackets are noise for a human reader. Pass
`lifecycle=True` (the CLI `--lifecycle` flag) to include them and recover a complete,
every-frame account.

Like the inspect surface, every function accepts a record root path OR an iterable of
envelope dicts (the same surface the test helpers and `read_record` speak), and the
output cites sequence numbers — identification always happens by seq, never by prose
position.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from msgspec import Struct

from ..record.record import read_record

# Lifecycle bracketing suppressed by default — implied by the trigger beat + the work event.
_LIFECYCLE_NOISE = frozenset(
    {
        "substrate.ProducerStarted",
        "substrate.ProducerCompleted",
        "substrate.InjectionApplied",
    }
)

# Large / structural payload fields elided from the one-line field summary (they dominate the
# line and carry no story; the same elision the CLI's aligned `tail` view applies, plus the
# invalid-emission raw echo).
_ELIDE = frozenset({"topology", "schemas", "baseline", "config", "raw_payload", "producer"})

# Authoring-failure kinds — counted distinctly by the summary so a finalised-but-broken run
# is legible as broken (mirrors cli._FAILURE_KINDS).
_FAILURE_KINDS = frozenset(
    {
        "substrate.ProducerFailed",
        "substrate.InputBuildFailed",
        "substrate.PredicateQuarantined",
        "substrate.ProducerEmittedInvalidEvent",
    }
)


class NarrationLine(Struct, frozen=True):
    """One narrated beat. `seq` cites the event, `kind` is its raw event kind (so a consumer
    can filter or style by kind), `text` is the rendered prose."""

    seq: int
    kind: str
    text: str


class NarrationSummary(Struct, frozen=True):
    """A one-glance digest of a run record. `finalised` is whether the run reached a terminal
    substrate.RunFinalised; `final_reason` is its reason (None for an ordinary finalise, e.g.
    "view_failure" for a failed one). The failure counts are the authoring-failure tally a
    finalised-but-broken run hides behind a clean status line. `application_events` maps each
    non-substrate.* kind to its count — the work the topology actually produced."""

    finalised: bool
    final_reason: str | None
    total_events: int
    producers_started: int
    producers_completed: int
    producers_cancelled: int
    producers_failed: int
    input_build_failures: int
    predicate_quarantines: int
    invalid_emissions: int
    application_events: dict[str, int]


def _load(record: Any) -> list[dict[str, Any]]:
    """Accept a record root path or an iterable of envelopes (the inspect-surface contract)."""
    if isinstance(record, (str, Path)):
        return list(read_record(record))
    if isinstance(record, Iterable):
        return list(record)
    raise TypeError(
        f"expected a record root path or an iterable of envelopes, got {type(record)!r}"
    )


def _short(value: Any, *, limit: int = 50) -> str:
    """A compact ONE-LINE rendering of a payload value — embedded newlines/tabs escaped (a
    free-text field like a code chunk must not break the one-beat-per-line contract, which
    legibility AND grep-ability both rest on), long strings truncated, long lists shown as a
    count, so a single field never blows out or wraps the line."""
    if isinstance(value, (list, tuple)):
        # repr already escapes newlines inside contained strings, so the line stays single.
        return repr(list(value)) if len(value) <= 4 else f"[{len(value)} items]"
    text = value if isinstance(value, str) else str(value)
    text = text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _producer_kind(ref: Any) -> str:
    """The legible producer identity for narration — the kind (the role), not the instance id
    (instance ids are ULIDs; the seq citation already disambiguates two beats of one kind)."""
    if isinstance(ref, dict):
        return str(ref.get("kind", "?"))
    return "?"


def _fields(payload: dict[str, Any], *, drop: frozenset[str] = frozenset()) -> str:
    bits = [f"{k}={_short(v)}" for k, v in payload.items() if k not in _ELIDE and k not in drop]
    return ", ".join(bits)


# ── per-kind beat renderers (payload, producer_ref) -> prose ────────────────────────────────
def _run_started(p: dict[str, Any], ref: Any) -> str:
    rid = p.get("run_id")
    return f"Run started (run_id={rid})." if rid else "Run started."


def _trigger_fired(p: dict[str, Any], ref: Any) -> str:
    factory = p.get("factory", "?")
    trigger_id = p.get("trigger_id", "?")
    key = p.get("firing_key")
    if trigger_id == "__initial__":
        return f"Initial trigger starts {factory}."
    on_key = "" if key in (None, "__initial__") else f" on key={key}"
    return f"Trigger {trigger_id} fired{on_key} -> starts {factory}."


def _producer_cancelled(p: dict[str, Any], ref: Any) -> str:
    return f"{_producer_kind(p.get('producer'))} cancelled."


def _producer_failed(p: dict[str, Any], ref: Any) -> str:
    return f"{_producer_kind(p.get('producer'))} FAILED: {p.get('error', '?')}"


def _input_build_failed(p: dict[str, Any], ref: Any) -> str:
    who = p.get("trigger_id") or p.get("route_id") or "?"
    return f"Input build failed for {who}: {p.get('error', '?')}"


def _predicate_quarantined(p: dict[str, Any], ref: Any) -> str:
    tail = f" -- {p['error']}" if p.get("error") else ""
    return f"Predicate quarantined (trigger {p.get('trigger_id', '?')}): {p.get('reason', '?')}{tail}"


def _invalid_emission(p: dict[str, Any], ref: Any) -> str:
    at = f" at {p['at_path']}" if p.get("at_path") else ""
    return f"{_producer_kind(p.get('producer'))} emitted an invalid event: {p.get('reason', '?')}{at}"


def _termination_matched(p: dict[str, Any], ref: Any) -> str:
    decision = p.get("decision", "?")
    if decision == "pause-await-input":
        # the load-bearing fact about a pause is WHAT input it awaits (review #26) — render the
        # typed resume_condition, not a bare "pause-await-input".
        cond = p.get("resume_condition")
        return f"Run paused -- awaiting: {cond}." if cond else "Run paused -- awaiting input."
    return f"Termination matched: {decision}."


def _run_finalised(p: dict[str, Any], ref: Any) -> str:
    reason = p.get("reason")
    return f"Run finalised ({reason})." if reason else "Run finalised."


def _producer_started(p: dict[str, Any], ref: Any) -> str:
    return f"{_producer_kind(p.get('producer'))} started."


def _producer_completed(p: dict[str, Any], ref: Any) -> str:
    return f"{_producer_kind(p.get('producer'))} completed."


def _injection_applied(p: dict[str, Any], ref: Any) -> str:
    return f"injection -> slot {p.get('target_input_slot', '?')} (route {p.get('route_id', '?')})."


_BEATS: dict[str, Callable[[dict[str, Any], Any], str]] = {
    "substrate.RunStarted": _run_started,
    "substrate.TriggerFired": _trigger_fired,
    "substrate.ProducerCancelled": _producer_cancelled,
    "substrate.ProducerFailed": _producer_failed,
    "substrate.InputBuildFailed": _input_build_failed,
    "substrate.PredicateQuarantined": _predicate_quarantined,
    "substrate.ProducerEmittedInvalidEvent": _invalid_emission,
    "substrate.TerminationMatched": _termination_matched,
    "substrate.RunFinalised": _run_finalised,
    "substrate.ProducerStarted": _producer_started,
    "substrate.ProducerCompleted": _producer_completed,
    "substrate.InjectionApplied": _injection_applied,
}


def _render(kind: str, payload: dict[str, Any], ref: Any) -> str:
    beat = _BEATS.get(kind)
    if beat is not None:
        return beat(payload, ref)
    if kind.startswith("substrate."):
        # An unknown substrate.* kind (forward-compat): name it, summarise its payload, never
        # drop it silently.
        fields = _fields(payload)
        short = kind.removeprefix("substrate.")
        return f"{short} ({fields})" if fields else short
    # An application event — the work. "<producer> -> <Kind> (<salient fields>)".
    fields = _fields(payload)
    head = f"{_producer_kind(ref)} -> {kind}"
    return f"{head} ({fields})" if fields else head


def narrate(record: Any, *, lifecycle: bool = False) -> Iterator[NarrationLine]:
    """Narrate a run record beat by beat. By default suppresses the lifecycle bracketing
    (ProducerStarted / ProducerCompleted / InjectionApplied); `lifecycle=True` includes it.
    Yields a NarrationLine per narrated event, in seq order (the log's total order)."""
    for env in _load(record):
        kind = str(env.get("kind", ""))
        if not lifecycle and kind in _LIFECYCLE_NOISE:
            continue
        payload = env.get("payload")
        text = _render(kind, payload if isinstance(payload, dict) else {}, env.get("producer"))
        yield NarrationLine(seq=int(env.get("seq", -1)), kind=kind, text=text)


def narration_summary(record: Any) -> NarrationSummary:
    """A one-glance digest of a run record: did it finalise, how many producers ran, how many
    failed, and what application events it produced. A finalised run with a nonzero failure
    tally is a finalised-but-broken run — the count makes that legible."""
    counts = dict.fromkeys(
        (
            "substrate.ProducerStarted",
            "substrate.ProducerCompleted",
            "substrate.ProducerCancelled",
            "substrate.ProducerFailed",
            "substrate.InputBuildFailed",
            "substrate.PredicateQuarantined",
            "substrate.ProducerEmittedInvalidEvent",
        ),
        0,
    )
    app: dict[str, int] = {}
    finalised = False
    final_reason: str | None = None
    total = 0
    for env in _load(record):
        total += 1
        kind = str(env.get("kind", ""))
        if kind in counts:
            counts[kind] += 1
        elif kind == "substrate.RunFinalised":
            finalised = True
            reason = (env.get("payload") or {}).get("reason")
            final_reason = str(reason) if reason else None
        elif not kind.startswith("substrate."):
            app[kind] = app.get(kind, 0) + 1
    return NarrationSummary(
        finalised=finalised,
        final_reason=final_reason,
        total_events=total,
        producers_started=counts["substrate.ProducerStarted"],
        producers_completed=counts["substrate.ProducerCompleted"],
        producers_cancelled=counts["substrate.ProducerCancelled"],
        producers_failed=counts["substrate.ProducerFailed"],
        input_build_failures=counts["substrate.InputBuildFailed"],
        predicate_quarantines=counts["substrate.PredicateQuarantined"],
        invalid_emissions=counts["substrate.ProducerEmittedInvalidEvent"],
        application_events=app,
    )
