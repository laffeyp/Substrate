# Substrate — v14 Kernel Semantics Revision (proposal against DRAFT v13)

Scope: this revision changes nothing about what Substrate is. Same eight primitives, same vocabulary discipline, same non-goals, same composition story, same replay ambitions. It repairs the kernel semantics where v13 is internally inconsistent or underdetermined, as demonstrated executably in `substrate_proof.py` (demos 1–4), and closes the five smaller gaps found in the same pass. Every change is to the append cycle, the admission path, or definitions — not to the primitive set.

---

## 0. The first commitment, stated

v13 implies but never states its central architectural commitment: **all state lives on the log.** Sealed inputs plus Routes-at-instantiation-boundaries mean a Producer cannot be steered mid-life and cannot checkpoint except by emitting. Long-lived stateful computations (a simulator holding a world, a model mid-generation) participate by externalising their state as events and being re-instantiated — the population-simulation example works precisely because world-state is a Producer emitting every tick. This is the design's load-bearing trade: it buys replay, cross-instantiation safety, and untrusted-Producer tolerance, and it taxes long-lived internal state. v14 states it at the top so every downstream decision can be checked against it.

---

## 1. The append cycle, revised

The v13 cycle had two defects: Routes staged *after* Triggers fired (so a Trigger fired by event N could never see messages staged from event N — breaking the spec's own Retry pattern), and "A TriggerFired control-plane event is appended" inside step 4 left reentrancy undefined (two faithful readings produce different sealed inputs for identical topologies — demo 2).

**v14 cycle.** Appends are processed by a single writer (§2). For each admitted event:

1. **Validate** against the emitting Producer kind's declared schema. An invalid emission is not dropped from the record: it is wrapped as a `ProducerEmittedInvalidEvent` control-plane event (raw payload inside, reason attached) and that wrapper is processed through steps 2–6 like any event. It is sequence-numbered, on the log, visible to replay, and matchable by Predicates — invalid emissions are now part of the structured error cascade rather than an off-log annex. Predicates on the producer's declared payload kinds never see it; predicates on `ProducerEmittedInvalidEvent` do. (Resolves the v13 contradiction between the lifecycle-table preamble and the step-1 text — demo 4.)
2. **Sequence + append.** Assign seq N, append to the log.
3. **Update Views**, synchronously. View state is now *as-of-N*.
4. **Evaluate Routes** against event N. Matching Routes stage their messages now. (Moved ahead of Trigger evaluation. This is the fix for demo 1: a Trigger fired by event N sees messages staged *from* event N.)
5. **Evaluate Predicates** in registration order against the as-of-N snapshot. Every predicate in this step sees the same snapshot: Views as-of-N, staged messages as of step 4. For each true predicate, the Trigger fires: `input_builder` runs **now**, against that same snapshot; the resolved input is recorded in a `TriggerFired` control-plane event; the Producer task is scheduled. The `TriggerFired` event is **not appended inside this step** — it is placed on the control queue.
6. **Drain the control queue.** Each queued control-plane event (TriggerFired, ProducerStarted, InjectionApplied, …) runs its own full append cycle — seq N+1, N+2, … — in FIFO generation order, before any further payload event is admitted. Cascades (a predicate matching `TriggerFired` firing another Trigger) are therefore ordered, recorded, and each step of the cascade is its own atomic cycle.

**What this buys.** The atomicity claim is now true rather than aspirational: within a cycle, every Predicate and every input_builder sees one defined snapshot. Cascade order is total and recorded. Resolved inputs are deterministic functions of (snapshot, staged messages) and are carried in `TriggerFired` events, so Level 2 replay reconstructs not just *that* a Trigger fired but *exactly what its Producer was given* — across implementations, because there is now only one legal interpretation.

**Decision #8, restated.** A Route's staged message is visible to Trigger firings evaluated in the *same* append cycle as the staging event, and all later cycles. The Retry pattern's "enriched via a Route that injects the failure reason" now works as written; no one-event delay, no pattern rewrite.

**Divergence** remains the topology author's problem, unchanged — the control queue makes self-feeding cascades *ordered and visible*, not impossible. Firing policies, keyed deduplication, and TerminationPolicy remain the tools.

---

## 2. Admission and memory: backpressure that can actually release

v13 said "the bus is a bounded queue; when full, appending Producers block until space opens" — but the bus is an append-only log and nothing in v13 ever removes an event, so "space" never opens: the bound was a run-killing deadlock at event N, not backpressure (demo 3). v13 also never owned the log's memory growth.

v14 separates three things v13 conflated:

- **The admission queue** (bounded). Producers do not append directly; they submit emissions to a bounded admission queue. The single writer drains it, running append cycles. Backpressure = blocking submit when the admission queue is full. Space opens because the writer genuinely consumes the queue. This is the credit pool; Producers compete for it; the bound is sized at implementation time. Control-plane events generated inside the writer (step 6) bypass admission — they are part of the current drain, cannot deadlock against it, and cannot be starved by payload traffic.
- **The log** (append-only, grows monotonically for the run). Its memory is owned explicitly: a hot tail of recent events stays in RAM; sealed older segments spill to disk. This is safe because the hot path never reads raw history — Predicates read Views (incrementally maintained, in RAM), Routes stage at append time, and the only consumers of deep history are pull-Routes, input_builders doing explicit historical queries, and replay — all of which may read through spilled segments at non-hot-path cost.
- **Views** (RAM-resident, incrementally maintained). Unchanged.

**Admission order is the scheduling nondeterminism, and it is recorded.** Which Producer's emission wins admission next is a race; the sequence numbers record its outcome. This is precisely why Level 2 replay works and why Level 3 for concurrent stochastic Producers requires substitution — v14 keeps v13's honest replay levels and can now actually meet them.

---

## 3. Cooldowns, logical time, and quiescence

v13's `WhileTrue` cooldown was implicitly wall-clock, which silently broke Level 3(a) (deterministic re-execution with seeded Producers becomes timing-dependent) and made quiescence underdefined (a predicate true-but-cooling is "satisfiable" with no future event).

- **Cooldown is logical by default**: measured in append cycles (sequence numbers), e.g. "fire at most once per K appends matching the predicate's subscription." Deterministic, replayable at every level the run otherwise supports.
- **Wall-clock cooldown is opt-in and demoting**: a topology that uses it is flagged at registration; the run's replay ceiling drops to Level 3(b) (substitution), and the flag appears in the run's metadata so operational expectations are set by the log, not by folklore.
- **Quiescence, defined**: no running Producers, admission queue empty, control queue empty, no Trigger whose predicate is true-now and unfired under its firing policy, and no pending wall-clock cooldown firing. With logical cooldowns the last clause is vacuous (no future appends → no maturation); with wall-clock cooldowns the TerminationPolicy's quiescence input includes pending timers. (Resolves the v13 gap where quiescence-with-watchdog could finalise a run that had a firing scheduled.)

---

## 4. Predicate quarantine is a recorded decision

v13 let the runtime "reject or quarantine" over-budget predicates — a silent topology mutation with no log record, despite being capable of changing a run's outcome more than most failures. v14 adds one control-plane kind:

| Kind | Meaning |
|---|---|
| `PredicateQuarantined` | The runtime stopped consulting a predicate; identifies the predicate, its Trigger, measured budget violation, and the enforcement decision. Sequence-numbered, on the log, matchable. |

A quarantine is consequential exactly the way a termination signal is: it is an event, and the topology (or TerminationPolicy) decides what it means — escalate, pause-await-input, finalise. Replay now reconstructs the runtime's enforcement decisions, not just its scheduling ones.

---

## 5. Composition: the export boundary

v13 said an embedded substrate "emits the embedded run's events back onto the outer bus," which is both un-typeable (the outer Producer kind must declare its emittable schemas; "whatever my internal topology produces" is not a declaration) and operationally wrong (inner control-plane chatter would consume the outer admission queue).

v14: an embedded substrate Producer declares an **export map** — `{inner event kind → outer event schema}` — as part of its kind declaration. Only mapped kinds cross the boundary, translated at the boundary and validated by the outer bus like any emission. Default export: the inner `RunFinalised` payload only. Inner control-plane events never cross unless explicitly mapped. The inner substrate remains a black box presenting `start(input) → AsyncIterable[Event]`; the export map is just the typed face of that contract. Backpressure cascade is unchanged: a congested outer admission queue blocks the substrate Producer's exports at its boundary.

---

## 6. Smaller corrections

- **Lifecycle table**: `ProducerEmittedInvalidEvent` row updated (sequence-numbered, on the log, matchable — see §1 step 1); `PredicateQuarantined` row added (§4). The preamble's claim — all listed kinds are first-class, sequenced, replay-visible — is now true of every row.
- **Retry pattern text**: unchanged in intent, now correct as written under the §1 cycle. The inner-retry/outer-retry amplification discipline (RetryExhausted as a distinct terminal kind) carries over untouched.
- **Progress gating, cultured starters, halt-with-resume, structured error cascade**: all unchanged; each was checked against the revised cycle and none requires modification. Structured error cascade is strengthened for free by §1 step 1 (invalid emissions join the cascade) and §4 (quarantines join it).

---

## 7. Prior work: two additions, one demotion

- **Linda / tuple spaces** (Gelernter, 1985). The closest kin v13 didn't cite: coordination through a shared associative space, processes spawned via `eval`, matching via templates. Substrate is, roughly, Linda with a total order, typed schemas, sealed inputs, and a replay log — the coordination-language tradition is the right shelf, and its literature on distributed tuple spaces is directly relevant to the federated-substrates direction.
- **Complex Event Processing** (Esper, Flink CEP). Twenty years of the Predicate taxonomy — event-local, windowed, cross-stream composite patterns firing actions — including the hard-won lesson Substrate re-derives: pattern matching must be cheap and semantic judgment must live elsewhere. CEP's window-and-key machinery is worth borrowing for PerKey firing policies rather than re-deriving.
- **π-calculus**: demoted from the prior-work section to a footnote. Substrate has no channels, no channel-passing, no reduction semantics; the comparison decorated rather than informed.

KPN, Naiad, SEDA, Temporal, Reactive Streams entries: unchanged, except the Reactive Streams paragraph is rewritten to match §2 — the credit-pool analogy now attaches to the admission queue, which is the thing that actually behaves like one.

---

## 8. Decision deltas (against v13's "Decisions made")

- **#8 Route timing** → staged messages visible to same-cycle Trigger firings and later (was: next firing after the cycle).
- **New: Control-plane append semantics** → deferred, FIFO, each its own cycle (step 6); reentrant appends are prohibited.
- **New: Admission queue** → bounded submission ahead of the single writer is the backpressure mechanism; the log is unbounded per run with segment spill; Views stay hot.
- **New: Cooldown basis** → logical (append cycles) by default; wall-clock opt-in demotes the run's replay ceiling and is recorded.
- **New: Export map** → embedded substrates declare typed export boundaries; default exports `RunFinalised` only.
- **#23 Bus-boundary validation** → invalid emissions are sequenced quarantine events on the log (was: no sequence number, off-log).
- **Implementation-time choices** → "single-writer queue with async handoff" is promoted from a suggestion to the model the spec's semantics assume; the v13 tension between "synchronous on the appending Producer's call" and async handoff is resolved in favour of the latter, with the admission queue as the defined synchronisation point.

Everything else stands as written.

---

## 9. Conformance

`substrate_v14_kernel.py` is a minimal executable kernel of §1–§2 semantics. It re-runs the v13 failure cases as conformance checks: the Retry pattern receives the failure reason from the triggering event; the demo-2 topology has exactly one legal outcome; six appends through a bound-5 admission queue complete without deadlock while the log retains all events; an invalid emission appears on the log, sequenced, and fires a predicate. A v14 implementation that passes these four checks has implemented the cycle correctly.
