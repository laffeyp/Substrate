#!/usr/bin/env python3
"""
substrate_proof.py — executable demonstrations of findings 1-3 against
Substrate DRAFT v13, plus the textual contradiction (finding 4).

The Bus below implements "The append cycle" (sec. The bus) literally:

    1. Validate the event            (all events here are valid)
    2. Assign seq number, append to log
    3. Update Views, synchronous     (the log itself serves as the View)
    4. Evaluate Predicates in stable order; each true result fires its
       Trigger: input_builder -> producer_factory -> start.
       "A TriggerFired control-plane event is appended."
    5. Evaluate Route source predicates; stage messages for
       next-Trigger consumption.

Where the spec is ambiguous -- WHEN the TriggerFired append from step 4
runs its own append cycle -- the Bus takes a `control_append` mode:

  - "reentrant": appended immediately inside step 4, nested full cycle
    (literal reading of step 4: "A TriggerFired ... is appended")
  - "deferred": staged, appended after step 5 completes
    (reading implied by "The append cycle is the atomic unit of bus
    evolution ... Predicates and Views always see consistent snapshots")

Both are faithful to the text. Demo 2 shows they produce DIFFERENT
Producer inputs for the same topology and same payload events.
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
    predicate: Callable          # (event, bus) -> bool   (event-local here)
    input_builder: Callable      # (bus) -> input          (reads staged msgs)
    firings: list = field(default_factory=list)


@dataclass
class Route:
    name: str
    source_predicate: Callable   # (event, bus) -> bool
    slot: str
    transform: Callable          # (event) -> message


class Bus:
    def __init__(self, control_append: str = "reentrant"):
        assert control_append in ("reentrant", "deferred")
        self.mode = control_append
        self.log: list[Event] = []
        self.next_seq = 0
        self.triggers: list[Trigger] = []
        self.routes: list[Route] = []
        self.staged: dict[str, list] = {}
        self._pending_control: list[Event] = []

    # ---- The append cycle, steps 2-5 (step 1 validation trivially passes) --
    def append(self, ev: Event):
        ev.seq = self.next_seq                      # step 2
        self.next_seq += 1
        self.log.append(ev)
        # step 3: Views update synchronously. Our View is the log + staged.

        for t in self.triggers:                     # step 4, stable order
            if t.predicate(ev, self):
                inp = t.input_builder(self)         # input built NOW (spec:
                t.firings.append(inp)               # input_builder, factory,
                tf = Event("runtime", "TriggerFired",  # start, then
                           {"trigger": t.name, "resolved_input": inp})
                if self.mode == "reentrant":        # "A TriggerFired
                    self.append(tf)                 #  control-plane event
                else:                               #  is appended."
                    self._pending_control.append(tf)

        for r in self.routes:                       # step 5
            if r.source_predicate(ev, self):
                self.staged.setdefault(r.slot, []).append(r.transform(ev))

        if self.mode == "deferred":                 # control appends after
            pending, self._pending_control = self._pending_control, []
            for tf in pending:
                self.append(tf)


def banner(s):
    print("\n" + "=" * 72 + f"\n{s}\n" + "=" * 72)


# ---------------------------------------------------------------------------
# DEMO 1 — Finding #1: the Retry pattern vs Decision #8 (route timing)
#
# Spec, "Topology patterns -> Retry": a Trigger fires on ProducerFailed,
# "optionally enriched via a Route that injects the failure reason."
# Spec, Decision #8: staged messages are visible "at the next Trigger
# firing AFTER the route-triggering append cycle."
# Append cycle order: Triggers fire at step 4, Routes stage at step 5.
# => The retry Trigger fired BY the failure event builds its input before
#    the failure reason is staged. The enrichment cannot happen.
#    (True in BOTH control-append modes: input_builder runs in step 4
#    either way.)
# ---------------------------------------------------------------------------
def demo1():
    banner("DEMO 1  Retry pattern: input built at step 4, reason staged at step 5")
    for mode in ("reentrant", "deferred"):
        bus = Bus(control_append=mode)
        bus.routes.append(Route(
            name="inject-failure-reason",
            source_predicate=lambda ev, b: ev.kind == "ProducerFailed",
            slot="failure_context",
            transform=lambda ev: ev.payload["error"],
        ))
        bus.triggers.append(Trigger(
            name="retry-worker",
            predicate=lambda ev, b: ev.kind == "ProducerFailed",
            input_builder=lambda b: {
                "task": "same input",
                "failure_context": list(b.staged.get("failure_context", [])),
            },
        ))
        bus.append(Event("worker-1", "ProducerFailed",
                         {"error": "ImportError: no module named foo"}))

        retry_input = bus.triggers[0].firings[0]
        print(f"\n  mode={mode}")
        print(f"  retry Producer's sealed input:    {retry_input}")
        print(f"  staged AFTER the cycle finished:  {bus.staged}")
        assert retry_input["failure_context"] == [], "spec would be fine!"
    print("\n  => The retry instantiation NEVER sees the failure reason from")
    print("     the event that triggered it. The worked pattern contradicts")
    print("     Decision #8 + append-cycle step order. (Fix: evaluate Routes")
    print("     before Triggers, or rewrite the pattern with a 1-event delay.)")


# ---------------------------------------------------------------------------
# DEMO 2 — Finding #2: TriggerFired reentrancy is underdefined, and the two
# faithful readings produce DIFFERENT Producer inputs.
#
# Topology (identical in both runs):
#   Route R:    stages payload of "task" events into slot "ctx"   (step 5)
#   Trigger T1: fires on "task" events (spawns some Producer)     (step 4)
#   Trigger T2: fires on "TriggerFired" events; its input_builder
#               reads staged slot "ctx"
#
# reentrant: T1's TriggerFired is appended INSIDE step 4 of the task
#   event's cycle -> T2 fires BEFORE the task event reaches step 5
#   -> T2's input sees staged ctx == []
# deferred:  TriggerFired is appended after step 5 -> T2 fires after
#   staging -> T2's input sees staged ctx == ["payload"]
#
# Same spec text. Same events. Different sealed inputs => different runs.
# "Level 2 - Schedule replay ... is the substrate's primary replay
# guarantee" cannot hold across implementations when the spec
# underdetermines the trace.
# ---------------------------------------------------------------------------
def demo2():
    banner("DEMO 2  Same topology, both spec-faithful readings, different inputs")
    results = {}
    for mode in ("reentrant", "deferred"):
        bus = Bus(control_append=mode)
        bus.triggers.append(Trigger(
            name="T1-on-task",
            predicate=lambda ev, b: ev.kind == "task",
            input_builder=lambda b: {"work": "spawn worker"},
        ))
        bus.triggers.append(Trigger(
            name="T2-on-TriggerFired",
            predicate=lambda ev, b: ev.kind == "TriggerFired"
                                    and ev.payload["trigger"] == "T1-on-task",
            input_builder=lambda b: {"ctx": list(b.staged.get("ctx", []))},
        ))
        bus.routes.append(Route(
            name="R-stage-task-payload",
            source_predicate=lambda ev, b: ev.kind == "task",
            slot="ctx",
            transform=lambda ev: ev.payload["data"],
        ))
        bus.append(Event("planner", "task", {"data": "module A spec"}))

        t2_input = bus.triggers[1].firings[0]
        results[mode] = t2_input
        print(f"\n  mode={mode}")
        print(f"  log: {bus.log}")
        print(f"  T2's sealed input: {t2_input}")

    print(f"\n  reentrant input: {results['reentrant']}")
    print(f"  deferred  input: {results['deferred']}")
    assert results["reentrant"] != results["deferred"]
    print("  => Two implementations, both faithful to v13's text, give the")
    print("     downstream Producer different sealed inputs. The spec must")
    print("     pick one semantics or Level 2 replay is implementation lore.")


# ---------------------------------------------------------------------------
# DEMO 3 — Finding #3: "bounded queue ... block until space opens" deadlocks,
# because the bus is an append-only LOG: nothing ever dequeues.
#
# Spec: "The bus is a bounded queue. When the queue is full, appending
# Producers block until space opens. That is the backpressure mechanism."
# But: Views are synchronous projections (reads), Predicates are reads,
# Routes are reads, replay requires the log to be retained. No operation
# defined anywhere in v13 removes an event from the bus. "Space opens"
# never happens.
# ---------------------------------------------------------------------------
async def demo3():
    banner("DEMO 3  Bounded bus + append-only log = permanent block, not backpressure")

    class BoundedBus:
        def __init__(self, bound):
            self.bound = bound
            self.log = []
            self.cond = asyncio.Condition()

        async def append(self, ev):
            async with self.cond:
                while len(self.log) >= self.bound:   # "block until space
                    await self.cond.wait()           #  opens"
                self.log.append(ev)
            # NOTE: per the spec there is no dequeue/evict/consume anywhere:
            # Views project, Predicates read, Routes read, replay retains.
            # No code path ever calls cond.notify().

    bus = BoundedBus(bound=5)

    async def producer():
        for i in range(6):
            await bus.append(Event("p", "chunk", {"i": i}))
            print(f"  appended event {i}  (log size {len(bus.log)}/{bus.bound})")

    try:
        await asyncio.wait_for(producer(), timeout=3.0)
        print("  all appends completed (spec would be fine!)")
    except asyncio.TimeoutError:
        print(f"\n  6th append BLOCKED (3s timeout; it would block forever).")
        print("  => With no consumer that removes events, the bound is not")
        print("     backpressure -- it is a run-killing deadlock at event N.")
        print("     The Reactive Streams paragraph even argues nobody can be")
        print("     a slow consumer; correct -- because there are NO consumers,")
        print("     which is exactly why 'space' never opens.")


# ---------------------------------------------------------------------------
# DEMO 4 — Finding #4: flat textual contradiction (no code required)
# ---------------------------------------------------------------------------
def demo4():
    banner("DEMO 4  ProducerEmittedInvalidEvent: the spec contradicts itself")
    print("""
  Lifecycle table preamble:
    "These are first-class bus events -- they have sequence numbers,
     they appear in the log, replay sees them."
  ...and ProducerEmittedInvalidEvent is a row in that table.

  Same row + sec. The bus, append cycle step 1:
    "Does not enter the main stream; receives no sequence number."

  Both cannot hold. If it has no sequence number and is not in the log,
  then replay -- defined as reading the recorded event log -- cannot see
  it, and "payload preserved for audit" has no defined storage location.""")


if __name__ == "__main__":
    demo1()
    demo2()
    asyncio.run(demo3())
    demo4()
    print("\n" + "=" * 72)
    print("All four demonstrations completed against the v13 text.")
