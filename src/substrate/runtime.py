"""The Runtime: the single writer, the append cycle, lifecycle emission (technical §6, §7).

One asyncio event loop. Exactly one writer driving the append cycle; N Producer tasks
that emit by submitting to a credit-gated inbox (the credit pool = the admission bound;
control/lifecycle messages bypass credits, so a full admission queue cannot starve
them — technical §6.1). The append cycle is synchronous per event with no awaits
inside, so every Predicate and input_builder sees one consistent as-of-N snapshot.

Cascade-generated control events (TriggerFired, InjectionApplied, InputBuildFailed,
PredicateQuarantined) go to an internal control deque drained in step 6 with their own
full cycles, in FIFO order — making cascade order total and recorded (Decision #25).
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import msgspec
from msgspec import Struct
from ulid import ULID

from .constants import BUDGET_US, HYSTERESIS_K, is_reserved
from .encoding import NonCanonicalValueError, content_hash, to_canonical_builtins
from .errors import ReentrantAppendError
from .policies import Decision, TermContext, quiescence_with_watchdog
from .record import FsyncPolicy, Interval, RecordWriter
from .sealing import seal
from .topology import Registration, TopologyBuilder
from .types import Event, ProducerRef

_QUIESCENCE_POLL_S = 0.01  # writer idle-poll for the quiescence/watchdog check


@dataclass(frozen=True)
class _Emission:
    """A Producer payload emission (credit-gated)."""

    producer: dict[str, Any]
    obj: Any


@dataclass(frozen=True)
class _Lifecycle:
    """A runtime control-plane event (bypasses credits)."""

    kind: str
    payload: dict[str, Any]


class RunResult(Struct, frozen=True):
    run_id: str
    record_root: str
    status: Literal["finalised", "paused", "failed"]
    final_event: Event | None
    elapsed_seconds: float
    finalisation_payload: Any | None


class Runtime:
    """Executes one topology and produces one run record (single-use)."""

    def __init__(
        self,
        record_root: Path | str,
        *,
        persistent: bool = False,
        fsync: FsyncPolicy = Interval(100),
        admission: int = 1024,
        budget_us: int = BUDGET_US,
        hysteresis_k: int = HYSTERESIS_K,
        writer_stats: bool = False,
    ) -> None:
        if admission <= 0:
            raise ValueError("admission bound must be > 0")
        self._record_root = Path(record_root)
        self._persistent = persistent
        self._fsync = fsync
        self._admission_bound = admission
        self._budget_us = budget_us
        self._hysteresis_k = hysteresis_k
        self._used = False

    async def run(self, topology: Callable[[TopologyBuilder], None]) -> RunResult:
        if self._used:
            raise RuntimeError("RuntimeAlreadyUsedError: a Runtime is single-use")
        self._used = True
        started = time.monotonic()

        builder = TopologyBuilder()
        topology(builder)
        reg = builder.build()
        self._reg = reg

        # runtime state
        self._record = RecordWriter(self._record_root, fsync=self._fsync)
        self._inbox: asyncio.Queue[_Emission | _Lifecycle] = asyncio.Queue()
        self._credits = asyncio.Semaphore(self._admission_bound)
        self._control: deque[_Lifecycle] = deque()
        self._scheduled: list[tuple[str, Any, str, str | None]] = []
        self._tasks: set[asyncio.Task[None]] = set()
        self._next_seq = 0
        self._in_cycle = False
        self._counts: dict[str, int] = {}
        # _staged PERSISTS across cycles by design — a Route's message is visible to the
        # staging cycle AND all later cycles (kernel Decision #8); do NOT clear per-cycle.
        self._staged: dict[str, Any] = {}
        self._inflight = 0
        self._started_total = 0
        self._ended_total = 0
        self._quarantined: set[int] = set()
        self._pred_violations: dict[int, int] = {}
        self._terminated = False
        self._paused = False
        self._last_event: Event | None = None
        self._final_event: Event | None = None
        self._final_payload: Any | None = None
        self._replay_ceiling = "3b" if reg.has_wall_clock_cooldown else "3a"
        self._termination = reg.termination or quiescence_with_watchdog()
        self._run_id = str(ULID())

        self._bootstrap(reg)
        self._flush_scheduled()
        await self._writer_loop()

        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._record.write_manifest(replay_ceiling=self._replay_ceiling,
                                    extra={"run_id": self._run_id})
        self._record.close()

        status: Literal["finalised", "paused", "failed"] = (
            "paused" if self._paused else "finalised" if self._terminated else "finalised"
        )
        return RunResult(
            run_id=self._run_id,
            record_root=str(self._record_root),
            status=status,
            final_event=self._final_event,
            elapsed_seconds=time.monotonic() - started,
            finalisation_payload=self._final_payload,
        )

    # ── bootstrap ────────────────────────────────────────────────────────────--
    def _bootstrap(self, reg: Registration) -> None:
        self._cycle(_Lifecycle("substrate.RunStarted", self._manifest(reg)))  # seq 0
        for init in reg.initials:
            instance = str(ULID())
            self._cycle(
                _Lifecycle(
                    "substrate.TriggerFired",
                    {
                        "trigger_id": "__initial__",
                        "firing_key": "__initial__",
                        "factory": init.kind,
                        "resolved_input": _builtins_or_none(init.input),
                        "input_sha256": content_hash(init.input),
                    },
                )
            )
            self._scheduled.append((init.kind, seal(init.input), instance, None))

    def _manifest(self, reg: Registration) -> dict[str, Any]:
        producer_kinds = []
        for pk in reg.producer_kinds.values():
            schemas = {name: msgspec.json.schema(t) for name, (t, _v) in pk.schemas.items()}
            version = next(iter(pk.schemas.values()))[1] if pk.schemas else 1
            producer_kinds.append(
                {
                    "kind": pk.kind,
                    "schema_version": version,
                    "schemas": schemas,
                    "fingerprint": {"qualname": getattr(pk.factory, "__qualname__", repr(pk.factory)),
                                    "author_version": pk.author_version},
                }
            )
        return {
            "run_id": self._run_id,
            "topology": {
                "producer_kinds": producer_kinds,
                "triggers": [{"id": t.id, "subscription": sorted(t.subscription.kinds),
                              "firing_policy": type(t.policy).__name__, "starts": t.starts}
                             for t in reg.triggers],
                "routes": [{"id": r.id, "slot": r.slot} for r in reg.routes],
                "views": sorted(reg.views),
                "policies": [self._termination.name],
            },
            "baseline": reg.baseline,
            "config": {
                "fsync": type(self._fsync).__name__,
                "admission": self._admission_bound,
                "budget_us": self._budget_us,
                "hysteresis_k": self._hysteresis_k,
                "replay_ceiling": self._replay_ceiling,
            },
        }

    # ── the append cycle (technical §6.2) ───────────────────────────────────────
    def _cycle(self, pending: _Emission | _Lifecycle) -> None:
        self._in_cycle = True
        try:
            kind, schema, env_producer, payload = self._resolve(pending)  # step 1
            seq = self._next_seq
            self._next_seq += 1
            envelope = {"seq": seq, "kind": kind, "schema": schema,
                        "producer": env_producer, "t": time.time(), "payload": payload}
            self._record.append(envelope)                                  # step 2
            event = Event(seq=seq, kind=kind, schema=schema,
                          producer=ProducerRef(**env_producer) if env_producer else None,
                          t=envelope["t"], payload=payload)
            self._counts[kind] = self._counts.get(kind, 0) + 1
            self._track_lifecycle(event)
            self._last_event = event
            self._final_event = event
            for view in self._reg.views.values():                          # step 3
                if _subscribed(view.subscription, event):
                    view.update(event)
            self._stage_routes(event)                                      # step 4
            self._eval_triggers(event, seq)                                # step 5
        finally:
            self._in_cycle = False
        while self._control:                                               # step 6
            self._cycle(self._control.popleft())

    def _resolve(self, pending: _Emission | _Lifecycle) -> tuple[str, str, dict[str, Any] | None, Any]:
        if isinstance(pending, _Lifecycle):
            return pending.kind, f"{pending.kind}@1", None, pending.payload
        # a Producer emission — validate at the bus boundary (technical §8.1)
        ref = pending.producer
        obj = pending.obj
        reg = self._reg.producer_kinds.get(ref["kind"])
        event_kind = type(obj).__name__
        invalid: str | None = None
        at_path: str | None = None
        if reg is None or not isinstance(obj, Struct) or is_reserved(event_kind):
            invalid = "unknown_kind"
        elif event_kind not in reg.schemas or not isinstance(obj, reg.schemas[event_kind][0]):
            invalid = "unknown_kind" if event_kind not in reg.schemas else "schema_violation"
        if invalid is None:
            try:
                payload = to_canonical_builtins(obj)
            except NonCanonicalValueError as exc:
                invalid, at_path = "non_canonical_value", exc.at_path
            else:
                version = reg.schemas[event_kind][1]  # type: ignore[union-attr]
                return event_kind, f"{event_kind}@{version}", ref, payload
        wrapper = {"reason": invalid, "raw_payload": _safe_raw(obj), "producer": ref}
        if at_path is not None:
            wrapper["at_path"] = at_path
        return ("substrate.ProducerEmittedInvalidEvent",
                "substrate.ProducerEmittedInvalidEvent@1", None, wrapper)

    def _track_lifecycle(self, event: Event) -> None:
        if event.kind == "substrate.ProducerStarted":
            self._started_total += 1
        elif event.kind in ("substrate.ProducerCompleted", "substrate.ProducerFailed",
                             "substrate.ProducerCancelled"):
            self._ended_total += 1
            self._inflight = max(0, self._inflight - 1)

    def _stage_routes(self, event: Event) -> None:
        for r in self._reg.routes:
            if not _subscribed(r.subscription, event):
                continue
            try:
                message = r.transform(event)
            except Exception as exc:  # design §6.3: route transform raises -> InputBuildFailed
                self._control.append(_Lifecycle(
                    "substrate.InputBuildFailed",
                    {"route_id": r.id, "firing_key": None, "error": repr(exc)}))
                continue
            self._staged[r.slot] = message
            self._control.append(_Lifecycle(
                "substrate.InjectionApplied",
                {"route_id": r.id, "target_input_slot": r.slot,
                 "message_sha256": content_hash(message)}))

    def _eval_triggers(self, event: Event, append_index: int) -> None:
        for idx, t in enumerate(self._reg.triggers):
            if idx in self._quarantined or not _subscribed(t.subscription, event):
                continue
            t0 = time.perf_counter()
            try:
                fired = t.predicate(event, self._reg.views)
            except Exception as exc:  # design §6.3: predicate raises -> immediate quarantine
                self._quarantine(idx, t.id, reason="exception", error=repr(exc))
                continue
            elapsed_us = (time.perf_counter() - t0) * 1e6
            if elapsed_us > self._budget_us:
                self._pred_violations[idx] = self._pred_violations.get(idx, 0) + 1
                if self._pred_violations[idx] >= self._hysteresis_k:
                    self._quarantine(idx, t.id, reason="budget", measured_us=elapsed_us)
                    continue
            else:
                self._pred_violations[idx] = 0
            if not fired:
                continue
            do_fire, firing_key = t.policy.admit(event, append_index)
            if not do_fire:
                continue
            try:
                resolved = t.input_builder(self._reg.views, self._staged, event)
                sealed = seal(resolved)  # immutability by construction (§8.3); raises -> InputBuildFailed
            except Exception as exc:  # technical §6.2 step 5 / F-TRIG-5 (incl. seal failure)
                self._control.append(_Lifecycle(
                    "substrate.InputBuildFailed",
                    {"trigger_id": t.id, "firing_key": firing_key, "error": repr(exc)}))
                continue
            instance = str(ULID())
            parent = event.producer.instance if event.producer else None
            self._control.append(_Lifecycle(
                "substrate.TriggerFired",
                {"trigger_id": t.id, "firing_key": firing_key, "factory": t.starts,
                 "resolved_input": _builtins_or_none(resolved),
                 "input_sha256": content_hash(resolved)}))
            self._scheduled.append((t.starts, sealed, instance, parent))

    def _quarantine(self, idx: int, trigger_id: str, *, reason: str,
                    measured_us: float = 0.0, error: str | None = None) -> None:
        self._quarantined.add(idx)
        self._pred_violations[idx] = 0
        payload: dict[str, Any] = {"predicate_id": trigger_id, "trigger_id": trigger_id,
                                   "reason": reason, "measured_us": measured_us, "k": self._hysteresis_k}
        if error is not None:
            payload["error"] = error
        self._control.append(_Lifecycle("substrate.PredicateQuarantined", payload))

    # ── producer tasks & the writer loop ─────────────────────────────────────--
    def _flush_scheduled(self) -> None:
        while self._scheduled:
            kind, inp, instance, parent = self._scheduled.pop(0)
            self._inflight += 1
            task = asyncio.create_task(self._producer_task(kind, inp, instance, parent))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _producer_task(self, kind: str, inp: Any, instance: str, parent: str | None) -> None:
        ref = {"kind": kind, "instance": instance, "parent": parent}
        self._inbox.put_nowait(_Lifecycle("substrate.ProducerStarted", {"producer": ref}))
        try:
            start = self._reg.producer_kinds[kind].factory()
            async for obj in start(inp):
                await self._submit_emission(ref, obj)
            self._inbox.put_nowait(_Lifecycle("substrate.ProducerCompleted", {"producer": ref}))
        except asyncio.CancelledError:
            self._inbox.put_nowait(_Lifecycle("substrate.ProducerCancelled", {"producer": ref}))
            raise
        except Exception as exc:
            self._inbox.put_nowait(_Lifecycle(
                "substrate.ProducerFailed", {"producer": ref, "error": repr(exc)}))

    async def _submit_emission(self, ref: dict[str, Any], obj: Any) -> None:
        if self._in_cycle:  # reentrancy guard (technical §6.2)
            raise ReentrantAppendError("submit() reached synchronously from inside the append cycle")
        await self._credits.acquire()
        self._inbox.put_nowait(_Emission(ref, obj))

    async def _writer_loop(self) -> None:
        while not self._terminated and not self._paused:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=_QUIESCENCE_POLL_S)
            except asyncio.TimeoutError:
                # Quiescence (kernel §"Quiescence, defined"): no running Producers, empty
                # admission + control queues, no true-and-unfired Trigger, no pending
                # wall-clock cooldown. With logical cooldowns (v0.1 default) the
                # true-and-unfired clause is vacuous — Triggers fire only on appends, and
                # with no Producers and empty queues no further append can occur, so none
                # can mature. Wall-clock-cooldown pending-timer quiescence is deferred.
                if self._inflight == 0 and self._inbox.empty() and not self._control:
                    self._consult_termination(None, quiescent=True)
                continue
            if isinstance(msg, _Emission):
                self._credits.release()
            self._cycle(msg)
            self._flush_scheduled()
            if self._last_event is not None:
                self._consult_termination(self._last_event, quiescent=False)

    def _consult_termination(self, event: Event | None, *, quiescent: bool) -> None:
        if self._terminated or self._paused:
            return
        ctx = TermContext(
            event=event, quiescent=quiescent, running=self._inflight,
            started=self._started_total, completed=self._ended_total,
            counts=lambda k: self._counts.get(k, 0),
        )
        decision = self._termination.decide(ctx)
        if decision is Decision.FINALISE_RUN:
            self._cycle(_Lifecycle("substrate.TerminationMatched",
                                   {"policy": self._termination.name, "decision": decision.value}))
            self._cycle(_Lifecycle("substrate.RunFinalised", {}))
            self._terminated = True
        elif decision is Decision.PAUSE_AWAIT_INPUT:
            self._cycle(_Lifecycle(
                "substrate.TerminationMatched",
                {"policy": self._termination.name, "decision": decision.value,
                 "resume_condition": self._termination.resume_condition}))
            self._paused = True


# ── helpers ──────────────────────────────────────────────────────────────────--
def _subscribed(sub: Any, event: Event) -> bool:
    if event.kind in sub.kinds:
        return True
    if event.producer is not None and sub.producers:
        if event.producer.kind in sub.producers or event.producer.instance in sub.producers:
            return True
    return False


def _builtins_or_none(obj: Any) -> Any:
    return None if obj is None else to_canonical_builtins(obj)


def _safe_raw(obj: Any) -> Any:
    try:
        return msgspec.to_builtins(obj)
    except Exception:
        return repr(obj)
