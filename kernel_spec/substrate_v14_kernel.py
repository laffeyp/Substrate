#!/usr/bin/env python3
"""
substrate_v14_kernel.py — minimal executable kernel of the v14 revision
(sections 1 and 2 of substrate-v14-kernel-revision.md), run against the
exact failure cases that substrate_proof.py demonstrated for v13.

v14 append cycle:
  1. validate; invalid emissions wrapped as sequenced
     ProducerEmittedInvalidEvent control events, processed like any event
  2. assign seq, append to log
  3. update Views synchronously (snapshot is now as-of-N)
  4. evaluate Routes; stage messages              <-- before Triggers
  5. evaluate Predicates in registration order against the as-of-N
     snapshot; fire Triggers: input_builder runs NOW against the same
     snapshot + staged messages; TriggerFired goes on the CONTROL QUEUE
  6. drain control queue: each control event runs its own full cycle,
     FIFO, before the next payload event is admitted

Backpressure: bounded ADMISSION queue ahead of a single writer. The
writer drains it; space genuinely opens. The log grows; old events spill
to sealed segments (simulated as a separate list standing in for disk).
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Event:
    producer: str
    kind: str
    payload: dict
    seq: int | None = None

    def __repr__(self):
        return f"<{self.seq}:{self.kind} {self.payload}>"


@dataclass
class Trigger:
    name: str
    predicate: Callable      # (event, kernel) -> bool
    input_builder: Callable  # (kernel) -> sealed input
    firings: list = field(default_factory=list)


@dataclass
class Route:
    name: str
    source_predicate: Callable
    slot: str
    transform: Callable


class Kernel:
    HOT_TAIL = 4  # events kept in RAM; older spill to sealed segments

    def __init__(self, *, admission_bound: int, schemas: dict[str, set[str]]):
        self.schemas = schemas              # producer kind -> allowed event kinds
        self.hot: list[Event] = []          # RAM tail of the log
        self.segments: list[Event] = []     # "disk": sealed, replay-readable
        self.next_seq = 0
        self.triggers: list[Trigger] = []
        self.routes: list[Route] = []
        self.staged: dict[str, list] = {}
        self.admission: asyncio.Queue = asyncio.Queue(maxsize=admission_bound)
        self._control: list[Event] = []     # control queue (writer-internal)

    # ---- log, with owned memory ------------------------------------------
    def _log_append(self, ev: Event):
        ev.seq = self.next_seq
        self.next_seq += 1
        self.hot.append(ev)
        if len(self.hot) > self.HOT_TAIL:          # spill sealed segment
            self.segments.append(self.hot.pop(0))

    def full_log(self) -> list[Event]:              # replay path: reads
        return self.segments + self.hot             # through segments

    # ---- the v14 append cycle --------------------------------------------
    def _cycle(self, ev: Event):
        # step 1: validate
        allowed = self.schemas.get(ev.producer, set())
        if ev.producer != "runtime" and ev.kind not in allowed:
            ev = Event("runtime", "ProducerEmittedInvalidEvent",
                       {"offender": ev.producer, "declared": sorted(allowed),
                        "raw_kind": ev.kind, "raw_payload": ev.payload})
            # wrapper falls through and is processed like any event:
            # sequenced, on the log, matchable.
        self._log_append(ev)                         # step 2
        # step 3: Views update synchronously (the log/staged are our Views)
        for r in self.routes:                        # step 4: Routes FIRST
            if r.source_predicate(ev, self):
                self.staged.setdefault(r.slot, []).append(r.transform(ev))
        for t in self.triggers:                      # step 5: Predicates
            if t.predicate(ev, self):
                inp = t.input_builder(self)          # as-of-N snapshot,
                t.firings.append(inp)                # staged incl. step 4
                self._control.append(Event(
                    "runtime", "TriggerFired",
                    {"trigger": t.name, "resolved_input": inp}))
        # step 6: drain control queue, FIFO, each its own full cycle
        while self._control:
            self._cycle(self._control.pop(0))

    # ---- single writer + bounded admission --------------------------------
    async def submit(self, ev: Event):               # Producers call this;
        await self.admission.put(ev)                 # blocks when full =
                                                     # backpressure
    async def writer(self, until_idle_for: float = 0.2):
        while True:
            try:
                ev = await asyncio.wait_for(self.admission.get(),
                                            timeout=until_idle_for)
            except asyncio.TimeoutError:
                return                               # quiescent for demo
            self._cycle(ev)
            self.admission.task_done()


def banner(s):
    print("\n" + "=" * 72 + f"\n{s}\n" + "=" * 72)


# ---------------------------------------------------------------------------
# CHECK 1 — Retry pattern now works as written:
# the Trigger fired by ProducerFailed sees the failure reason staged
# from the SAME event (Routes at step 4, Triggers at step 5).
# ---------------------------------------------------------------------------
async def check1():
    banner("CHECK 1  Retry receives the failure reason from the triggering event")
    k = Kernel(admission_bound=8, schemas={"worker-1": {"ProducerFailed"}})
    k.routes.append(Route(
        "inject-failure-reason",
        lambda ev, _: ev.kind == "ProducerFailed",
        "failure_context",
        lambda ev: ev.payload["error"]))
    k.triggers.append(Trigger(
        "retry-worker",
        lambda ev, _: ev.kind == "ProducerFailed",
        lambda kk: {"task": "same input",
                    "failure_context": list(kk.staged.get("failure_context", []))}))
    await k.submit(Event("worker-1", "ProducerFailed",
                         {"error": "ImportError: no module named foo"}))
    await k.writer()
    sealed = k.triggers[0].firings[0]
    print(f"  retry Producer's sealed input: {sealed}")
    assert sealed["failure_context"] == ["ImportError: no module named foo"]
    print("  PASS — v13 sealed this as [] in both readings; v14 delivers it.")


# ---------------------------------------------------------------------------
# CHECK 2 — The demo-2 topology now has exactly ONE legal outcome.
# Control appends are deferred (step 6), so T2 (matching TriggerFired)
# runs after the task event's Route staging: ctx is populated, and there
# is no second faithful reading to disagree with.
# ---------------------------------------------------------------------------
async def check2():
    banner("CHECK 2  One defined semantics for the v13-ambiguous topology")
    k = Kernel(admission_bound=8, schemas={"planner": {"task"}})
    k.triggers.append(Trigger(
        "T1-on-task",
        lambda ev, _: ev.kind == "task",
        lambda kk: {"work": "spawn worker"}))
    k.triggers.append(Trigger(
        "T2-on-TriggerFired",
        lambda ev, _: (ev.kind == "TriggerFired"
                       and ev.payload["trigger"] == "T1-on-task"),
        lambda kk: {"ctx": list(kk.staged.get("ctx", []))}))
    k.routes.append(Route(
        "R-stage-task-payload",
        lambda ev, _: ev.kind == "task",
        "ctx",
        lambda ev: ev.payload["data"]))
    await k.submit(Event("planner", "task", {"data": "module A spec"}))
    await k.writer()
    print(f"  log: {k.full_log()}")
    sealed = k.triggers[1].firings[0]
    print(f"  T2's sealed input: {sealed}")
    assert sealed == {"ctx": ["module A spec"]}
    print("  PASS — single outcome; resolved input recorded in TriggerFired;")
    print("  Level 2 replay reconstructs exactly what T2's Producer was given.")


# ---------------------------------------------------------------------------
# CHECK 3 — Backpressure releases; no deadlock; log retains everything.
# Six events through a bound-5 admission queue: submits block only while
# the writer is busy, then proceed. Old events spill to sealed segments,
# hot RAM tail stays bounded, full log remains replay-readable.
# ---------------------------------------------------------------------------
async def check3():
    banner("CHECK 3  Bound-5 admission, 6 appends: completes; v13 deadlocked here")
    k = Kernel(admission_bound=5, schemas={"p": {"chunk"}})

    async def producer():
        for i in range(6):
            await k.submit(Event("p", "chunk", {"i": i}))
            print(f"  submitted event {i}")

    await asyncio.wait_for(
        asyncio.gather(producer(), k.writer()), timeout=5.0)
    log = k.full_log()
    print(f"  events on log: {len(log)}  "
          f"(hot RAM tail: {len(k.hot)}, sealed segments: {len(k.segments)})")
    assert len(log) == 6 and [e.payload["i"] for e in log] == list(range(6))
    print("  PASS — admission queue drains (space genuinely opens); the log")
    print("  is untouched by backpressure; memory owned via segment spill.")


# ---------------------------------------------------------------------------
# CHECK 4 — Invalid emission: sequenced, on the log, matchable.
# An undeclared kind from worker-1 becomes ProducerEmittedInvalidEvent,
# gets a seq number, and FIRES a predicate (joins the error cascade).
# ---------------------------------------------------------------------------
async def check4():
    banner("CHECK 4  Invalid emission is a first-class, matchable log event")
    k = Kernel(admission_bound=8, schemas={"worker-1": {"CodeChunk"}})
    k.triggers.append(Trigger(
        "escalate-on-invalid",
        lambda ev, _: ev.kind == "ProducerEmittedInvalidEvent",
        lambda kk: {"action": "pause-await-input",
                    "offender": kk.full_log()[-1].payload["offender"]}))
    await k.submit(Event("worker-1", "TotallyUndeclaredKind", {"x": 1}))
    await k.writer()
    log = k.full_log()
    print(f"  log: {log}")
    assert log[0].kind == "ProducerEmittedInvalidEvent" and log[0].seq == 0
    assert k.triggers[0].firings, "predicate on invalid-event did not fire"
    print(f"  escalation input: {k.triggers[0].firings[0]}")
    print("  PASS — sequenced, replay-visible, audit payload preserved on the")
    print("  log, and the structured error cascade can gate on it. The v13")
    print("  contradiction (first-class vs no-seq-number) is gone.")


async def main():
    await check1()
    await check2()
    await check3()
    await check4()
    print("\n" + "=" * 72)
    print("All four v14 conformance checks PASS on the same cases that")
    print("failed (or were undefined) under the v13 text.")

if __name__ == "__main__":
    asyncio.run(main())
