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

from . import locking
from .constants import BLOB_THRESHOLD_BYTES, BUDGET_US, HYSTERESIS_K, is_reserved
from .encoding import SafeCanonical, content_hash, safe_raw, try_canonical
from .errors import FsyncError, ReentrantAppendError
from .policies import Decision, TermContext, quiescence_with_watchdog
from .record import FsyncPolicy, Interval, RecordWriter
from .sealing import seal
from .topology import Registration, TopologyBuilder
from .triggers import Logical
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

        # Persistent-bus exclusive lock (technical §11): a second runtime against the
        # same root fails fast with BusLockedError; Windows raises UnsupportedPlatformError
        # at config time. Per-run mode (fresh ULID root) needs no lock. Acquired INSIDE the
        # try below so the finally releases it even if RecordWriter construction or state
        # init then raises (otherwise the flock fd leaks and a same-process retry would
        # self-deadlock).
        self._lock_fd: int | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._record_closed = False
        self._failed = False
        self._paused = False
        self._terminated = False
        self._kernel_error: str | None = None

        # Acquire the persistent-bus lock BEFORE the try so a BusLockedError /
        # UnsupportedPlatformError propagates to the caller (a config-time refusal, not a
        # failed run). The try then covers RecordWriter construction onward, so a failure
        # there still hits the finally that releases this lock (no fd leak / self-deadlock).
        if self._persistent:
            self._lock_fd = locking.acquire_lock(self._record_root, start_time=time.time())
        try:
            self._record = RecordWriter(self._record_root, fsync=self._fsync)
            self._init_run_state(reg)
            self._bootstrap(reg)
            self._flush_scheduled()
            await self._writer_loop()
        except FsyncError:
            # fsyncgate (§5.2): the medium is untrustworthy. The writer MUST NOT append
            # RunFinalised; the torn tail (absence of RunFinalised) is the correct
            # encoding of medium failure. The record is already closed by _do_fsync.
            self._failed = True
            self._record_closed = True  # _do_fsync already closed the fd; do not re-close
        except Exception as exc:
            # The writer itself raised (a kernel bug, §6.3 "the writer itself raises").
            # The run did not finalise normally; record the kernel error on the log if the
            # record exists and is still open, so the failure is not silent.
            self._failed = True
            self._kernel_error = repr(exc)
            self._try_record_kernel_error(exc)
        finally:
            # Cancellation + record close + lock release ALWAYS run, even if the writer
            # raised — tasks must not leak, the record must be finalised, the lock freed.
            for t in self._tasks:
                t.cancel()
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)
            record = getattr(self, "_record", None)
            if record is not None and not self._record_closed:
                try:
                    record.write_manifest(
                        replay_ceiling=getattr(self, "_replay_ceiling", "3a"),
                        extra={"run_id": getattr(self, "_run_id", "")},
                    )
                    record.close()
                except FsyncError:
                    # A close-time fsync failure is itself the §5.2 path: no clean
                    # finalisation. Surface as a failed run rather than re-raising.
                    self._failed = True
            if self._lock_fd is not None:
                locking.release_lock(self._lock_fd)
                self._lock_fd = None

        status: Literal["finalised", "paused", "failed"] = (
            "failed" if self._failed else "paused" if self._paused else "finalised"
        )
        return RunResult(
            run_id=getattr(self, "_run_id", ""),
            record_root=str(self._record_root),
            status=status,
            final_event=getattr(self, "_final_event", None),
            elapsed_seconds=time.monotonic() - started,
            finalisation_payload=getattr(self, "_final_payload", None),
        )

    def _init_run_state(self, reg: Registration) -> None:
        """Initialise the per-run mutable state (called inside run()'s try so a failure
        here still hits the finally that releases the lock + closes the record). The
        Priority-C refactor will move this into a _RunState dataclass."""
        self._inbox: asyncio.Queue[_Emission | _Lifecycle] = asyncio.Queue()
        self._credits = asyncio.Semaphore(self._admission_bound)
        self._control: deque[_Lifecycle] = deque()
        self._scheduled: list[tuple[str, Any, str, str | None]] = []
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
        # Logical-cooldown bookkeeping, counted in subscription-MATCHING appends per
        # trigger (kernel §6: "fire at most once per K appends matching the predicate's
        # subscription"), not raw bus seq deltas.
        self._trigger_match_count: dict[int, int] = {}  # idx -> #subscription-matched appends
        self._trigger_last_fired_match: dict[int, int] = {}  # idx -> match-count at last firing
        self._last_event: Event | None = None
        self._final_event: Event | None = None
        self._final_payload: Any | None = None
        self._replay_ceiling = "3b" if reg.has_wall_clock_cooldown else "3a"
        self._termination = reg.termination or quiescence_with_watchdog()
        # quiescence_with_watchdog(seconds=) drives the writer idle-poll window: the
        # writer wakes at least every `seconds` to test quiescence when the inbox is
        # idle. We bound it by the fine-grained default so a large watchdog window never
        # delays prompt quiescence detection (detection is immediate once the queues are
        # empty); a smaller `seconds` polls faster. None → the default poll.
        ws = self._termination.watchdog_seconds
        self._poll_s = min(_QUIESCENCE_POLL_S, ws) if ws is not None else _QUIESCENCE_POLL_S
        self._run_id = str(ULID())

    def _try_record_kernel_error(self, exc: Exception) -> None:
        """On a writer-internal raise (§6.3 "the writer itself raises"), record the failure
        on the log if the record exists and fsync has not failed — so a kernel bug is not
        silent. Best-effort: a further failure here is swallowed (the run is already
        failing; the finally will still close the record)."""
        record = getattr(self, "_record", None)
        if record is None or self._record_closed or self._terminated:
            return
        if not hasattr(self, "_next_seq"):
            return  # state init never completed; nothing to append onto
        try:
            seq = self._next_seq
            self._next_seq += 1
            payload = {"reason": "kernel_error", "error": repr(exc)}
            record.append(
                {
                    "seq": seq,
                    "kind": "substrate.RunFinalised",
                    "schema": "substrate.RunFinalised@1",
                    "producer": None,
                    "t": time.time(),
                    "payload": payload,
                }
            )
            self._terminated = True
        except Exception:
            pass  # already failing; do not mask the original error or block the finally

    # ── bootstrap ────────────────────────────────────────────────────────────--
    def _bootstrap(self, reg: Registration) -> None:
        self._cycle(_Lifecycle("substrate.RunStarted", self._manifest(reg)))  # seq 0
        for init in reg.initials:
            instance = str(ULID())
            # Guard initial-input canonicalization/sealing: a non-canonical or
            # non-sealable initial input becomes a recorded InputBuildFailed (no
            # Producer starts) rather than crashing the writer at startup.
            try:
                sealed = seal(init.input)
                # Hash + canonicalize the pre-seal object: seal() normalizes
                # dict→MappingProxyType / list→tuple (which msgspec.to_builtins cannot
                # encode), but canonical encoding of the pre-seal value folds to exactly
                # the same bytes the sealed value represents, so input_sha256 is stable and
                # over the logical value the Producer runs with (D-5).
                input_fields = self._resolved_input_fields(init.input)
                input_hash = content_hash(init.input)
            except Exception as exc:
                self._cycle(
                    _Lifecycle(
                        "substrate.InputBuildFailed",
                        {
                            "trigger_id": "__initial__",
                            "firing_key": "__initial__",
                            "error": repr(exc),
                        },
                    )
                )
                continue
            self._cycle(
                _Lifecycle(
                    "substrate.TriggerFired",
                    {
                        "trigger_id": "__initial__",
                        "firing_key": "__initial__",
                        "factory": init.kind,
                        "instance": instance,
                        **input_fields,
                        "input_sha256": input_hash,
                    },
                )
            )
            self._scheduled.append((init.kind, sealed, instance, None))

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
                    # the author's determinism flag — load-bearing for the Level-3(a)
                    # replay precondition (F-RPLY-1; replay._producer_kinds_deterministic).
                    "deterministic": pk.deterministic,
                    "fingerprint": {
                        "qualname": getattr(pk.factory, "__qualname__", repr(pk.factory)),
                        "author_version": pk.author_version,
                    },
                }
            )
        return {
            "run_id": self._run_id,
            "topology": {
                "producer_kinds": producer_kinds,
                "triggers": [
                    {
                        "id": t.id,
                        "subscription": sorted(t.subscription.kinds),
                        "firing_policy": type(t.policy).__name__,
                        "starts": t.starts,
                    }
                    for t in reg.triggers
                ],
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
        # Once the run is finalised (terminal RunFinalised appended), no further event
        # may be appended — RunFinalised is terminal and last-if-present (state-transition
        # RUN-BOUNDARY / VIEW-FAILURE TERMINAL). A view-failure can finalise mid-cascade
        # while control events are still queued; drop them rather than append-after-terminal.
        if self._terminated:
            return
        self._in_cycle = True
        try:
            kind, schema, env_producer, payload = self._resolve(pending)  # step 1
            seq = self._next_seq
            self._next_seq += 1
            envelope = {
                "seq": seq,
                "kind": kind,
                "schema": schema,
                "producer": env_producer,
                "t": time.time(),
                "payload": payload,
            }
            self._record.append(envelope)  # step 2
            event = Event(
                seq=seq,
                kind=kind,
                schema=schema,
                producer=ProducerRef(**env_producer) if env_producer else None,
                t=envelope["t"],
                payload=payload,
            )
            self._counts[kind] = self._counts.get(kind, 0) + 1
            self._track_lifecycle(event)
            self._last_event = event
            self._final_event = event
            for vname, view in self._reg.views.items():  # step 3
                if not _subscribed(view.subscription, event):
                    continue
                try:
                    view.update(event)
                except Exception as exc:  # §6.3: a View raising in update() is fatal
                    self._view_failure(vname, seq, exc)
                    return
            self._stage_routes(event)  # step 4
            self._eval_triggers(event, seq)  # step 5
        finally:
            self._in_cycle = False
        while self._control:  # step 6
            self._cycle(self._control.popleft())

    def _resolve(
        self, pending: _Emission | _Lifecycle
    ) -> tuple[str, str, dict[str, Any] | None, Any]:
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
            # Guarded canonicalization (the shared sanitize-or-log path): a non-canonical
            # emission becomes a recorded ProducerEmittedInvalidEvent, never a crash.
            sc = try_canonical(obj)
            if sc.ok:
                version = reg.schemas[event_kind][1]  # type: ignore[union-attr]
                # Blob-offload oversized payloads BEFORE framing (technical §3.7 / §3.3):
                # write-ahead the blob, replace the payload with a BlobRef. Frames stay
                # bounded; the citable identity (the hash) is unchanged.
                payload = self._maybe_offload(sc)
                return event_kind, f"{event_kind}@{version}", ref, payload
            invalid, at_path = sc.reason, sc.at_path
            raw = sc.raw
        else:
            raw = safe_raw(obj)
        wrapper: dict[str, Any] = {"reason": invalid, "raw_payload": raw, "producer": ref}
        if at_path is not None:
            wrapper["at_path"] = at_path
        return (
            "substrate.ProducerEmittedInvalidEvent",
            "substrate.ProducerEmittedInvalidEvent@1",
            None,
            wrapper,
        )

    def _maybe_offload(self, sc: SafeCanonical) -> Any:
        """If a canonical payload exceeds BLOB_THRESHOLD_BYTES, write it write-ahead to
        the blob store and return a BlobRef builtins ({"$blob":..,"bytes":n}); else
        return the inline builtins (technical §3.7)."""
        if sc.nbytes <= BLOB_THRESHOLD_BYTES:
            return sc.builtins
        blob_ref = self._record.blobs.put(sc.raw_bytes)
        return {"$blob": blob_ref.sha256, "bytes": blob_ref.bytes}

    def _resolved_input_fields(self, resolved: Any) -> dict[str, Any]:
        """The TriggerFired input field(s): per D-5, EXACTLY ONE of `resolved_input`
        (inline, ≤ threshold) or `input_blob` (the BlobRef when oversized) is present; the
        hash is always recorded separately in input_sha256. Returns the fragment to merge
        into the payload. None resolved input → an inline resolved_input of None. Raises
        (caught by the caller as InputBuildFailed) if the input is non-canonical.

        The blob field is named `input_blob` (carrying the BlobRef object), NOT `$blob`:
        the locked v0.1 schema named it `$blob`, but that produced the footgun
        `{"$blob": {"$blob": ...}}` (the field key and the BlobRef's own key collide,
        textually indistinguishable for a reader/CLI author). Renamed to `input_blob` under
        P-TRIGGERFIRED-INPUT-BLOB (Architect-directed); carried implemented-ahead-of-
        ratification, like the instance field. The emission-payload blob case keeps the
        bare BlobRef shape ({"$blob":..,"bytes":..}) — there the payload genuinely IS a
        BlobRef (the whitelist payload type), so no field-key collision arises."""
        if resolved is None:
            return {"resolved_input": None}
        sc = try_canonical(resolved)
        if not sc.ok:
            raise ValueError(f"resolved input not canonical: {sc.reason} at {sc.at_path}")
        if sc.nbytes <= BLOB_THRESHOLD_BYTES:
            return {"resolved_input": sc.builtins}
        blob_ref = self._record.blobs.put(sc.raw_bytes)
        return {"input_blob": {"$blob": blob_ref.sha256, "bytes": blob_ref.bytes}}

    def _track_lifecycle(self, event: Event) -> None:
        if event.kind == "substrate.ProducerStarted":
            self._started_total += 1
        elif event.kind in (
            "substrate.ProducerCompleted",
            "substrate.ProducerFailed",
            "substrate.ProducerCancelled",
        ):
            self._ended_total += 1
            self._inflight = max(0, self._inflight - 1)

    def _view_failure(self, view_name: str, seq: int, exc: Exception) -> None:
        """A View raised in update() — fatal for the run (§6.3). Append the terminal
        RunFinalised{reason:view_failure} directly (no further views/triggers run) and
        mark the run failed. Called from inside step 3, so it appends straight to the
        record rather than recursing into _cycle."""
        fseq = self._next_seq
        self._next_seq += 1
        now = time.time()
        payload = {"reason": "view_failure", "view": view_name, "seq": seq, "error": repr(exc)}
        envelope = {
            "seq": fseq,
            "kind": "substrate.RunFinalised",
            "schema": "substrate.RunFinalised@1",
            "producer": None,
            "t": now,
            "payload": payload,
        }
        self._record.append(envelope)
        self._final_event = Event(
            seq=fseq,
            kind="substrate.RunFinalised",
            schema="substrate.RunFinalised@1",
            producer=None,
            t=now,
            payload=payload,
        )
        self._last_event = self._final_event
        self._counts["substrate.RunFinalised"] = self._counts.get("substrate.RunFinalised", 0) + 1
        self._control.clear()  # abandon any queued control events: nothing follows RunFinalised
        self._terminated = True
        self._failed = True

    def _stage_routes(self, event: Event) -> None:
        for r in self._reg.routes:
            if not _subscribed(r.subscription, event):
                continue
            try:
                message = r.transform(event)
            except Exception as exc:  # design §6.3: route transform raises -> InputBuildFailed
                self._control.append(
                    _Lifecycle(
                        "substrate.InputBuildFailed",
                        {"route_id": r.id, "firing_key": None, "error": repr(exc)},
                    )
                )
                continue
            self._staged[r.slot] = message
            self._control.append(
                _Lifecycle(
                    "substrate.InjectionApplied",
                    {
                        "route_id": r.id,
                        "target_input_slot": r.slot,
                        "message_sha256": content_hash(message),
                    },
                )
            )

    def _eval_triggers(self, event: Event, append_index: int) -> None:
        for idx, t in enumerate(self._reg.triggers):
            if idx in self._quarantined or not _subscribed(t.subscription, event):
                continue
            # This append matches the trigger's subscription — count it for the logical
            # cooldown (kernel §6: cooldown is measured in subscription-matching appends).
            self._trigger_match_count[idx] = self._trigger_match_count.get(idx, 0) + 1
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
            # Trigger-level logical cooldown (kernel §6 / technical §10): suppress a firing
            # within `appends` subscription-matching cycles of this trigger's last firing.
            # CHECKED BEFORE policy.admit so a cooldown-suppressed cycle does NOT consume
            # the policy's firing state — e.g. PerKey.admit mutates its seen-set, and a
            # later cooldown `continue` would permanently consume a key that never fired
            # (silent data loss). Logical cooldowns are append-counted and fully replayable;
            # wall-clock cooldowns are handled at registration (replay-ceiling demotion) —
            # pending-timer enforcement is deferred (see BLACKBOARD ## Deferred).
            cd = t.cooldown
            if isinstance(cd, Logical) and cd.appends > 0:
                last = self._trigger_last_fired_match.get(idx)
                if last is not None and self._trigger_match_count[idx] - last < cd.appends:
                    continue
            # The firing-policy admit (PerKey canonical-encodes the key for dedup) can
            # raise on a non-canonical key; treat that as an input-build failure rather
            # than crashing the writer (technical §10, §6.3).
            try:
                do_fire, firing_key = t.policy.admit(event, append_index)
            except Exception as exc:
                self._control.append(
                    _Lifecycle(
                        "substrate.InputBuildFailed",
                        {"trigger_id": t.id, "firing_key": None, "error": repr(exc)},
                    )
                )
                continue
            if not do_fire:
                continue
            # Build → seal → canonicalize the resolved input, ALL inside one guard: a
            # non-canonical builder output is an InputBuildFailed (no Producer starts),
            # never an uncaught crash (technical §6.2 step 5 / §6.3 / F-TRIG-5). The hash
            # and recorded input are taken from the pre-seal value (seal normalizes to
            # MappingProxyType/tuple, which msgspec cannot encode; the canonical bytes of
            # the pre-seal value are identical to what the sealed value represents — D-5).
            try:
                resolved = t.input_builder(self._reg.views, self._staged, event)
                sealed = seal(resolved)  # immutability by construction (§8.3)
                input_fields = self._resolved_input_fields(resolved)
                input_hash = content_hash(resolved)
            except Exception as exc:
                self._control.append(
                    _Lifecycle(
                        "substrate.InputBuildFailed",
                        {"trigger_id": t.id, "firing_key": firing_key, "error": repr(exc)},
                    )
                )
                continue
            instance = str(ULID())
            parent = event.producer.instance if event.producer else None
            self._control.append(
                _Lifecycle(
                    "substrate.TriggerFired",
                    {
                        "trigger_id": t.id,
                        "firing_key": firing_key,
                        "factory": t.starts,
                        "instance": instance,  # the spawned Producer instance — closes provenance (F-OBS-2)
                        **input_fields,
                        "input_sha256": input_hash,
                    },
                )
            )
            self._scheduled.append((t.starts, sealed, instance, parent))
            self._trigger_last_fired_match[idx] = self._trigger_match_count[idx]

    def _quarantine(
        self,
        idx: int,
        trigger_id: str,
        *,
        reason: str,
        measured_us: float = 0.0,
        error: str | None = None,
    ) -> None:
        self._quarantined.add(idx)
        self._pred_violations[idx] = 0
        payload: dict[str, Any] = {
            "predicate_id": trigger_id,
            "trigger_id": trigger_id,
            "reason": reason,
            "measured_us": measured_us,
            "k": self._hysteresis_k,
        }
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
            self._inbox.put_nowait(
                _Lifecycle("substrate.ProducerFailed", {"producer": ref, "error": repr(exc)})
            )

    async def _submit_emission(self, ref: dict[str, Any], obj: Any) -> None:
        if self._in_cycle:  # reentrancy guard (technical §6.2)
            raise ReentrantAppendError(
                "submit() reached synchronously from inside the append cycle"
            )
        await self._credits.acquire()
        self._inbox.put_nowait(_Emission(ref, obj))

    async def _writer_loop(self) -> None:
        while not self._terminated and not self._paused:
            try:
                msg = await asyncio.wait_for(self._inbox.get(), timeout=self._poll_s)
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
            event=event,
            quiescent=quiescent,
            running=self._inflight,
            started=self._started_total,
            completed=self._ended_total,
            counts=lambda k: self._counts.get(k, 0),
        )
        decision = self._termination.decide(ctx)
        if decision is Decision.FINALISE_RUN:
            self._cycle(
                _Lifecycle(
                    "substrate.TerminationMatched",
                    {"policy": self._termination.name, "decision": decision.value},
                )
            )
            # The policy may attach a final output payload (RunFinalised.finalisation_payload
            # → RunResult.finalisation_payload). Sanitize it: a non-canonical (or raising)
            # payload does not crash finalisation, but the drop is NOT silent — the reason is
            # recorded on the RunFinalised frame (nothing consequential is silent, product §1).
            payload: dict[str, Any] = {}
            fp: Any = None
            drop_reason: str | None = None
            try:
                fp = self._termination.finalisation_payload(ctx)
            except Exception as exc:
                drop_reason = f"finalisation callback raised: {exc!r}"
            if fp is not None and drop_reason is None:
                sc = try_canonical(fp)
                if sc.ok:
                    final_builtins = self._maybe_offload(sc)
                    payload["finalisation_payload"] = final_builtins
                    self._final_payload = final_builtins
                else:
                    drop_reason = f"finalisation payload not canonical: {sc.reason} at {sc.at_path}"
            if drop_reason is not None:
                payload["finalisation_payload_dropped"] = drop_reason
            self._cycle(_Lifecycle("substrate.RunFinalised", payload))
            self._terminated = True
        elif decision is Decision.PAUSE_AWAIT_INPUT:
            self._cycle(
                _Lifecycle(
                    "substrate.TerminationMatched",
                    {
                        "policy": self._termination.name,
                        "decision": decision.value,
                        "resume_condition": self._termination.resume_condition,
                    },
                )
            )
            self._paused = True


# ── helpers ──────────────────────────────────────────────────────────────────--
def _subscribed(sub: Any, event: Event) -> bool:
    if event.kind in sub.kinds:
        return True
    if event.producer is not None and sub.producers:
        if event.producer.kind in sub.producers or event.producer.instance in sub.producers:
            return True
    return False
