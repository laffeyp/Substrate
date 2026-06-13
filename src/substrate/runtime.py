"""The Runtime: run lifecycle, the writer loop, Producer tasks, termination (technical §6, §7).

One asyncio event loop. Exactly one writer driving the append cycle; N Producer tasks
that emit by submitting to a credit-gated inbox (the credit pool = the admission bound;
control/lifecycle messages bypass credits, so a full admission queue cannot starve them
— technical §6.1). The append cycle itself lives in substrate.sequencer.AppendCycle (the
single-writer sequencer); the Runtime owns the run lifecycle, locking, the writer loop,
Producer tasks, and termination, and delegates each event to the cycle.

Per-run mutable state lives in a substrate.runstate.RunState constructed once per run()
call (no two-phase construction on the Runtime instance); the run's lifecycle phase is a
RunPhase enum (no ad-hoc booleans).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import msgspec
from msgspec import Struct
from ulid import ULID

from . import locking
from .constants import BUDGET_US, HYSTERESIS_K, VOCAB_VERSION
from .encoding import content_hash, try_canonical
from .errors import FsyncError, ReentrantAppendError
from .policies import Decision, TermContext, quiescence_with_watchdog
from .record import FsyncPolicy, Interval, RecordWriter
from .runstate import RunPhase, RunState
from .sealing import seal
from .sequencer import AppendCycle, _Emission, _Lifecycle
from .sidecar import DiagnosticSidecar, WriterStatsSidecar
from .topology import Registration, TopologyBuilder
from .types import Event

_QUIESCENCE_POLL_S = 0.01  # writer idle-poll for the quiescence/watchdog check


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
        diagnostics: bool = False,
    ) -> None:
        if admission <= 0:
            raise ValueError("admission bound must be > 0")
        self._record_root = Path(record_root)
        self._persistent = persistent
        self._fsync = fsync
        self._admission_bound = admission
        self._budget_us = budget_us
        self._hysteresis_k = hysteresis_k
        # Off-bus sidecars (§3.8 / §6.4). Both default OFF; enabling either MUST leave the
        # bus log bit-identical (conformance check 14) — guaranteed because the sidecar
        # sinks are fed off-cycle and are simply absent (never called) when disabled.
        self._writer_stats = writer_stats
        self._diagnostics = diagnostics
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
        self._termination = reg.termination or quiescence_with_watchdog()

        lock_fd: int | None = None
        record: RecordWriter | None = None
        st: RunState | None = None
        self._diag = None  # set after the record exists; None-safe in the finally
        self._stats = None

        # Pre-run SETUP — the lock and the record writer — happens BEFORE the run try and
        # PROPAGATES on failure (a config-time / setup refusal, NOT a failed run): a caller
        # can then distinguish "never started" (setup raised) from "started and failed"
        # (status="failed" with a record on disk). BusLockedError/UnsupportedPlatformError
        # (lock) and an OSError (record-root creation) both propagate. If the record writer
        # fails after the lock was taken, the lock is released before re-raising — no fd
        # leak / self-deadlock.
        if self._persistent:
            lock_fd = locking.acquire_lock(self._record_root, start_time=time.time())
        try:
            record = RecordWriter(self._record_root, fsync=self._fsync)
        except BaseException:
            if lock_fd is not None:
                locking.release_lock(lock_fd)
            raise
        self._record = record
        # Off-bus sidecars (created only when enabled; absent => never fed => bus
        # bit-identical, check 14). Live for the run; flushed off-cycle and at close.
        self._diag = DiagnosticSidecar(self._record_root) if self._diagnostics else None
        self._stats = WriterStatsSidecar(self._record_root) if self._writer_stats else None
        try:
            st = self._new_run_state(reg)
            self._st = st
            self._cyc = AppendCycle(
                reg,
                record,
                st,
                budget_us=self._budget_us,
                hysteresis_k=self._hysteresis_k,
                diagnostics=self._diag,
            )
            self._bootstrap(reg)
            self._flush_scheduled()
            await self._writer_loop()
        except FsyncError:
            # fsyncgate (§5.2): the medium is untrustworthy. The writer MUST NOT append
            # RunFinalised; the torn tail (absence of RunFinalised) is the correct encoding
            # of medium failure. The record is already closed by _do_fsync.
            if st is not None:
                st.phase = RunPhase.FAILED
                st.record_closed = True  # _do_fsync already closed the fd; do not re-close
        except Exception as exc:
            # The writer itself raised (a kernel bug, §6.3 "the writer itself raises"). The
            # run did not finalise normally; record the kernel error on the log if the record
            # exists and is still open, so the failure is not silent.
            if st is not None:
                st.phase = RunPhase.FAILED
                st.kernel_error = repr(exc)
                self._try_record_kernel_error(exc)
        finally:
            # Cancellation + record close + lock release ALWAYS run, even if the writer
            # raised — tasks must not leak, the record must be finalised, the lock freed.
            if st is not None:
                for t in st.tasks:
                    t.cancel()
                if st.tasks:
                    await asyncio.gather(*st.tasks, return_exceptions=True)
            if record is not None and (st is None or not st.record_closed):
                try:
                    record.write_manifest(
                        replay_ceiling=st.replay_ceiling if st else "3a",
                        extra={"run_id": st.run_id if st else ""},
                    )
                    record.close()
                except FsyncError:
                    # A close-time fsync failure is itself the §5.2 path: no clean
                    # finalisation. Surface as a failed run rather than re-raising.
                    if st is not None:
                        st.phase = RunPhase.FAILED
            # Flush off-bus sidecars (never coupled to the bus writer; bus already closed).
            # A sidecar flush failure (e.g. disk full) must NOT turn an already-finalised bus
            # into an exception at the API boundary, nor block the lock release — the bus is
            # the record, the sidecars are advisory. Swallow with the run outcome intact.
            for sink in (self._diag, self._stats):
                if sink is not None:
                    try:
                        sink.flush()
                    except OSError:
                        pass
            if lock_fd is not None:
                locking.release_lock(lock_fd)

        status = self._status(st)
        return RunResult(
            run_id=st.run_id if st else "",
            record_root=str(self._record_root),
            status=status,
            final_event=st.final_event if st else None,
            elapsed_seconds=time.monotonic() - started,
            finalisation_payload=st.final_payload if st else None,
        )

    @staticmethod
    def _status(st: RunState | None) -> Literal["finalised", "paused", "failed"]:
        if st is None or st.phase is RunPhase.FAILED:
            return "failed"
        if st.phase is RunPhase.PAUSED:
            return "paused"
        return "finalised"

    def _new_run_state(self, reg: Registration) -> RunState:
        """Construct the per-run mutable state. quiescence_with_watchdog(seconds=) drives
        the writer idle-poll window: the writer wakes at least every `seconds` to test
        quiescence when the inbox is idle, bounded by the fine-grained default so a large
        watchdog window never delays prompt quiescence detection (detection is immediate
        once the queues are empty); a smaller `seconds` polls faster. None → default poll."""
        ws = self._termination.watchdog_seconds
        poll_s = min(_QUIESCENCE_POLL_S, ws) if ws is not None else _QUIESCENCE_POLL_S
        st = RunState(
            run_id=str(ULID()),
            replay_ceiling="3b" if reg.has_wall_clock_cooldown else "3a",
            poll_s=poll_s,
            admission_bound=self._admission_bound,
        )
        st.credits = asyncio.Semaphore(self._admission_bound)
        return st

    def _try_record_kernel_error(self, exc: Exception) -> None:
        """On a writer-internal raise (§6.3 "the writer itself raises"), record the failure
        on the log if the record exists and is still open — so a kernel bug is not silent.
        Best-effort: a further failure here is swallowed (the run is already failing; the
        finally will still close the record)."""
        st = getattr(self, "_st", None)
        record = getattr(self, "_record", None)
        if st is None or record is None or st.record_closed:
            return
        try:
            seq = st.next_seq
            st.next_seq += 1
            record.append(
                {
                    "seq": seq,
                    "kind": "substrate.RunFinalised",
                    "schema": "substrate.RunFinalised@1",
                    "producer": None,
                    "t": time.time(),
                    "payload": {"reason": "kernel_error", "error": repr(exc)},
                }
            )
        except Exception:
            pass  # already failing; do not mask the original error or block the finally

    # ── bootstrap ────────────────────────────────────────────────────────────--
    def _bootstrap(self, reg: Registration) -> None:
        self._cyc.cycle(_Lifecycle("substrate.RunStarted", self._manifest(reg)))  # seq 0
        for init in reg.initials:
            instance = str(ULID())
            # Guard initial-input canonicalization/sealing: a non-canonical or non-sealable
            # initial input becomes a recorded InputBuildFailed (no Producer starts) rather
            # than crashing the writer at startup.
            try:
                sealed = seal(init.input)
                # Hash + canonicalize the pre-seal object: seal() normalizes
                # dict→MappingProxyType / list→tuple (which msgspec.to_builtins cannot
                # encode), but canonical encoding of the pre-seal value folds to exactly the
                # same bytes the sealed value represents, so input_sha256 is stable and over
                # the logical value the Producer runs with (D-5).
                input_fields = self._cyc._resolved_input_fields(init.input)
                input_hash = content_hash(init.input)
            except Exception as exc:
                self._cyc.cycle(
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
            self._cyc.cycle(
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
            self._st.scheduled.append((init.kind, sealed, instance, None))

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
                    # the author's determinism flag — load-bearing for the Level-3(a) replay
                    # precondition (F-RPLY-1; replay._producer_kinds_deterministic).
                    "deterministic": pk.deterministic,
                    "fingerprint": {
                        "qualname": getattr(pk.factory, "__qualname__", repr(pk.factory)),
                        "author_version": pk.author_version,
                    },
                }
            )
        return {
            "run_id": self._st.run_id,
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
                # composition export map (F-COMP-1 / §20): the {inner_kind -> outer_schema}
                # the topology declared via b.export, recorded so an embedded substrate's
                # boundary is OBSERVABLE in the record (conformance check 7 "the kind
                # declaration MUST include an export map"). Each value is the outer schema's
                # name; empty when the topology embeds no substrate.
                "exports": {
                    inner: getattr(outer, "__name__", str(outer))
                    for inner, outer in reg.exports.items()
                },
            },
            "baseline": reg.baseline,
            "config": {
                "fsync": type(self._fsync).__name__,
                "admission": self._admission_bound,
                "budget_us": self._budget_us,
                "hysteresis_k": self._hysteresis_k,
                "replay_ceiling": self._st.replay_ceiling,
                # the signal-vocabulary version this record was written against — distinct
                # from a per-kind wire schema; lets replay/inspection self-describe (v0.2
                # added TriggerFired.instance/factory + input_blob).
                "vocab_version": VOCAB_VERSION,
            },
        }

    # ── producer tasks & the writer loop ─────────────────────────────────────--
    def _flush_scheduled(self) -> None:
        st = self._st
        while st.scheduled:
            kind, inp, instance, parent = st.scheduled.pop(0)
            st.inflight += 1
            task = asyncio.create_task(self._producer_task(kind, inp, instance, parent))
            st.tasks.add(task)
            st.task_by_instance[instance] = task

            def _done(t: asyncio.Task[None], inst: str = instance) -> None:
                st.tasks.discard(t)
                st.task_by_instance.pop(inst, None)

            task.add_done_callback(_done)

    async def _producer_task(self, kind: str, inp: Any, instance: str, parent: str | None) -> None:
        ref = {"kind": kind, "instance": instance, "parent": parent}
        inbox = self._st.inbox
        inbox.put_nowait(_Lifecycle("substrate.ProducerStarted", {"producer": ref}))
        try:
            start = self._reg.producer_kinds[kind].factory()
            async for obj in start(inp):
                await self._submit_emission(ref, obj)
            inbox.put_nowait(_Lifecycle("substrate.ProducerCompleted", {"producer": ref}))
        except asyncio.CancelledError:
            inbox.put_nowait(_Lifecycle("substrate.ProducerCancelled", {"producer": ref}))
            raise
        except Exception as exc:
            payload: dict[str, Any] = {"producer": ref, "error": repr(exc)}
            # Composition (§20): an embedded substrate's inner-run failure surfaces as ONE
            # outer ProducerFailed carrying the inner run_id (the exception carries it).
            inner = getattr(exc, "inner_run_id", None)
            if isinstance(inner, str) and inner:
                payload["inner_run_id"] = inner
            inbox.put_nowait(_Lifecycle("substrate.ProducerFailed", payload))

    async def _submit_emission(self, ref: dict[str, Any], obj: Any) -> None:
        st = self._st
        if st.in_cycle:  # reentrancy guard (technical §6.2)
            raise ReentrantAppendError(
                "submit() reached synchronously from inside the append cycle"
            )
        await st.credits.acquire()
        st.inbox.put_nowait(_Emission(ref, obj))

    async def _writer_loop(self) -> None:
        st = self._st
        while st.phase is RunPhase.RUNNING:
            try:
                msg = await asyncio.wait_for(st.inbox.get(), timeout=st.poll_s)
            except asyncio.TimeoutError:
                # Quiescence (kernel §"Quiescence, defined"): no running Producers, empty
                # admission + control queues, no true-and-unfired Trigger, no pending
                # wall-clock cooldown. With logical cooldowns (v0.1 default) the
                # true-and-unfired clause is vacuous — Triggers fire only on appends, and
                # with no Producers and empty queues no further append can occur, so none can
                # mature. Wall-clock-cooldown pending-timer quiescence is deferred.
                if st.inflight == 0 and st.inbox.empty() and not st.control:
                    self._consult_termination(None, quiescent=True)
                continue
            if isinstance(msg, _Emission):
                st.credits.release()
            self._cyc.cycle(msg)
            self._flush_scheduled()
            if st.last_event is not None:
                self._consult_termination(st.last_event, quiescent=False)
            # Writer-stats sample: BETWEEN cycles (off the hot path), only when enabled.
            # Sampling/I/O here never touches the appended frame's bytes (check 14).
            if self._stats is not None:
                self._stats.sample(
                    {
                        "at_seq": st.next_seq - 1,
                        "admission_depth": st.inbox.qsize(),
                        "control_queue_depth": len(st.control),
                        "started_total": st.started_total,
                        "ended_total": st.ended_total,
                        "quarantined_count": len(st.quarantined),
                    }
                )

    def _consult_termination(self, event: Event | None, *, quiescent: bool) -> None:
        st = self._st
        if st.phase is not RunPhase.RUNNING:
            return
        ctx = TermContext(
            event=event,
            quiescent=quiescent,
            running=st.inflight,
            started=st.started_total,
            completed=st.ended_total,
            counts=lambda k: st.counts.get(k, 0),
        )
        decision = self._termination.decide(ctx)
        if decision is Decision.FINALISE_RUN:
            self._cyc.cycle(
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
                    final_builtins = self._cyc._maybe_offload(sc)
                    payload["finalisation_payload"] = final_builtins
                    st.final_payload = final_builtins
                else:
                    drop_reason = f"finalisation payload not canonical: {sc.reason} at {sc.at_path}"
            if drop_reason is not None:
                payload["finalisation_payload_dropped"] = drop_reason
            self._cyc.cycle(_Lifecycle("substrate.RunFinalised", payload))
            # A view-failure mid-cascade may already have set FAILED; do not override it.
            if st.phase is RunPhase.RUNNING:
                st.phase = RunPhase.FINALISED
        elif decision is Decision.PAUSE_AWAIT_INPUT:
            self._cyc.cycle(
                _Lifecycle(
                    "substrate.TerminationMatched",
                    {
                        "policy": self._termination.name,
                        "decision": decision.value,
                        "resume_condition": self._termination.resume_condition,
                    },
                )
            )
            st.phase = RunPhase.PAUSED
        elif decision is Decision.CANCEL_OTHERS:
            self._cancel_others(event)

    def _cancel_others(self, event: Event | None) -> None:
        """Cancel every live Producer EXCEPT the subject (the producer of `event`) — kernel §8
        cancel-others. The run does NOT terminate: the cancelled tasks emit
        substrate.ProducerCancelled (drained by the still-running writer loop) and the run
        continues to quiescence. Idempotent — fires once per still-cancellable cohort; a
        repeat call with everyone already cancelled is a no-op (so a CANCEL_OTHERS policy that
        keeps matching does not thrash)."""
        st = self._st
        # The subject is the Producer this decision is "about" — for a lifecycle event
        # (ProducerCompleted/…) the subject rides the PAYLOAD's producer ref (P-SUBJECT-ID),
        # not the envelope `producer` (null for substrate.* events); for an application event
        # it is the envelope producer. Check both.
        subject: str | None = None
        if event is not None:
            if event.producer is not None:
                subject = event.producer.instance
            elif isinstance(event.payload, dict):
                ref = event.payload.get("producer")
                if isinstance(ref, dict):
                    subject = ref.get("instance")
        victims = [
            (inst, task)
            for inst, task in list(st.task_by_instance.items())
            if inst != subject and not task.done()
        ]
        if not victims:
            return  # nothing left to cancel — do not emit a vacuous TerminationMatched
        self._cyc.cycle(
            _Lifecycle(
                "substrate.TerminationMatched",
                {"policy": self._termination.name, "decision": Decision.CANCEL_OTHERS.value},
            )
        )
        for _inst, task in victims:
            task.cancel()  # the task's CancelledError handler enqueues ProducerCancelled
