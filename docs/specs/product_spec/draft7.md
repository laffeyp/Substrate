# Substrate — Product Specification

**DRAFT 7.** Builds on: Horizon: Substrate v15 (kernel semantics). The
v15 document defines *what the substrate is*; this document defines
*the product that ships it*. First of three artifacts: product spec
(this document), technical spec (DRAFT 5 exists), design spec (last;
thin at first — the surface is a library and a CLI).

**Stack (decided):** Python 3.12+ only (D-6), asyncio. Schema
validation and encoding via msgspec (D-3). Run record: framed/CRC
JSONL segments + manifest (D-4), canonical encoding per RFC 8785
(D-7). **Quality bar:** open source from day one, Apache-2.0 (D-1).

**Changes from DRAFT 6:** dropped §0.4 ("why this exists" historical
case), dropped §0.5 ("substrates of substrates" theory), dropped
principle 8 ("semantic observability"), dropped R-4 ("resident
reader") from reference topologies, dropped F-OBS-7
(record-legibility evaluation harness) and the corresponding
conformance check, dropped F-API-4 comparison-report schema (the
test helpers stay), fixed §0.1 worked example to use the v15
flattened-event form, tightened N-PERF-1 to a defensible perf gate.
The runtime is the product; positioning material and
LLM-specific deliverables move to user-land. Inspection APIs,
provenance closure, structured records — all stay, because they're
useful for any reader, human or machine.

---

# Part I — The grounding

Substrate is an abstract project, and abstraction is where readers
drown. So this document starts at the bottom: one concrete run, the
eight words you need, what the log physically is, and only then the
specification. Nothing in Part I is normative.

## 0.1 One run, start to finish

You have a CSV of customer orders in a legacy format and you want it
translated to a new schema. On your own machine, with local models,
you set up a small system: three cheap models each translate rows
concurrently, a deterministic validator checks every translated row,
and a policy ends the run when all rows are done.

You run it. Here is what the substrate recorded — not prose, not a
debug log, but a sequence of typed events, each with a number:

```
seq  kind                          producer            what
───  ────────────────────────────  ──────────────────  ────────────────────────────────
0    substrate.RunStarted          —                   topology=csv-translate; schemas, seeds, fixtures
1    substrate.TriggerFired        —                   trigger=spawn-workers; input={file: orders.csv}
2    substrate.ProducerStarted     —                   worker-1
3    substrate.ProducerStarted     —                   worker-2
4    substrate.ProducerStarted     —                   worker-3
5    RowTranslated                 worker-1            row=1
6    RowTranslated                 worker-2            row=2
7    substrate.ProducerEmittedInvalidEvent  worker-3   reason: missing required field "price"
8    substrate.TriggerFired        —                   trigger=retry-row;
                                                       input={row: 3, failure_context: "missing field: price"}
9    substrate.ProducerStarted     —                   worker-3-retry
10   RowTranslated                 worker-3-retry      row=3
...
41   substrate.TerminationMatched  —                   policy=all-completed; decision=finalise-run
42   substrate.RunFinalised        —                   output=orders.translated.csv
```

Application events (`RowTranslated`) and runtime events
(`substrate.*`) live on the same log, distinguished by the kind
namespace. Every event carries its producer (or none, for runtime
events).

Now ask questions of it.

*Why did `worker-3-retry` exist?* Because of the firing at seq 8 —
and seq 8 tells you the exact input it was given, including the
failure reason from seq 7. *What did worker-3 actually emit?* Seq 7
has the raw payload, preserved. *Why did the run end?* Seq 41 names
the policy and the decision.

Every question about this run is answerable from these lines — by
you, by a program, by a tool. Nothing consequential happened off the
page. That is the product. Everything else in this document is what
it takes to make that guarantee rigorous: exact ordering rules,
replay, crash behavior, schema evolution, conformance tests that
prove the implementation does what this document says.

## 0.2 The eight words

The substrate has eight primitives. Each gets one plain sentence here
and a formal definition in the kernel spec. In the example above:

- **Producer** — anything that takes a typed input and emits a stream
  of typed events. The three translator models, the validator, even
  an embedded run of another substrate: all Producers. Not
  "agents" — a Producer can be an LLM, a parser, a simulator, a
  sensor, a shell command.
- **Event** — one typed, numbered fact on the record. `RowTranslated
  row=2` at seq 6.
- **Bus** — the single, totally-ordered, append-only log every event
  goes through. There is exactly one; no Producer talks to another
  except through it. The numbers in the left column are bus sequence
  numbers.
- **View** — a running summary the bus maintains incrementally, like
  "how many rows are done" or "everything worker-1 has said so far."
  Cheap to read; updated on every append.
- **Predicate** — a small, fast yes/no question asked of the Views
  when an event lands: "is this a failure?", "are at least three
  answers in?"
- **Trigger** — the only way new Producers come into existence: when
  its Predicate says yes, the Trigger builds an input and starts a
  Producer. Seq 8 is a Trigger firing; the record keeps the exact
  input it resolved.
- **Route** — a rule that carries data from events into the inputs of
  *future* Producers. The failure reason from seq 7 reached the
  retry's input at seq 8 through a Route. Routes never touch a
  running Producer — inputs are sealed at start.
- **TerminationPolicy** — the judge of when things stop: cancel the
  others, let them finish, pause and wait for outside input, or
  finalise. Seq 41.

Two more words that aren't primitives but recur: a **topology** is
the arrangement you wrote — which Producer kinds exist, which
Triggers and Routes connect them (it is ordinary Python, not a
diagram or a DSL); the **run record** is the persisted bus log plus
its manifest — the artifact the whole product is organized around.

## 0.3 What the bus actually is

"A shared log" invites the wrong pictures: Kafka clusters, database
servers, message brokers. The bus is none of these. For the duration
of a run it is an in-process data structure — an ordinary in-memory
sequence owned by a single writer. Its persisted form, the run
record, is a directory of plain files: numbered, append-only segment
files where each line is one event in a canonical JSON encoding (RFC
8785: sorted keys, normalized numbers — the same logical event always
yields identical bytes), carrying its own sequence number and a
checksum so a crash-torn tail can be detected and trimmed; a small
manifest naming which segments are sealed and therefore immutable;
and a content-addressed blob directory beside them for oversized
payloads (an image, a long document), referenced from events by
hash.

No server. No broker. No daemon. Nothing to deploy. The right analogy
is SQLite, not Postgres: an embedded artifact owned by the process
that writes it, which any other program — `tail -f`, a future UI, a
replay tool — opens read-only while the run is live. The format
follows well-worn prior art deliberately: Kafka's sealed-segment
design, the CRC-framed write-ahead logs of LevelDB/RocksDB, the
Redis menu of fsync policies. The preference for plain inspectable
files over an embedded database is itself a decision (D-4, where
SQLite was the runner-up): every distinctive promise of this product
is about *bytes* — byte-identical replay, content-hash citations,
diffable records — and the file should *be* the canonical bytes, not
contain them.

---

# Part II — The specification

Part II is written for an implementer — dense on purpose, because
ambiguity in a requirement is more expensive than density.

## 1. Product statement

Substrate is a concurrent streaming dataflow runtime, shipped as an
importable Python library plus a CLI runner. You bring computations —
LLMs, ML models, deterministic transforms, subprocesses, simulators,
parsers, test runners, sensors — and the substrate runs them
concurrently, coordinates them through a single totally-ordered
append-only event log, and creates new computations dynamically when
predicates over the log are satisfied.

The product is the runtime, not a topology catalogue. Topologies are
user code. The product succeeds when a topology author can express
any pattern in the v15 "What this enables" section — ensembles,
adversarial pairs, recursive decomposition, simulations, code teams
with live verification — in ordinary Python against a stable,
documented, conformance-tested kernel, and replay any run from its
log.

The run record is the canonical account of what happened during a
run — every consequential runtime decision (trigger firings with
resolved inputs, injections, quarantines, terminations, invalid
emissions) is a typed, sequence-numbered event. Records are designed
to be read by programs, by debugging tools, by other substrates, by
people. The runtime takes no position on which reader is privileged.

## 2. Scope position

One build, fully realized. There is no thin-slice MVP that ships half
a substrate — half a substrate orchestrates nothing. v1.0 is the
complete runtime: all eight primitives, the full v15 append cycle,
admission/backpressure, both persistence modes, composition with
export maps, replay Levels 1–3(b), the lifecycle event vocabulary,
the CLI, and the conformance suite. What v1.0 deliberately does
**not** include is the demonstration catalogue ("What this enables"
topologies as shipped artifacts) and a UI — but v1.0 must make both
*rapidly reachable*: each catalogue topology should be an afternoon
of user code, and any UI must be buildable on public surfaces alone
(§4 principle 8).

The commitment is argued, not asserted: the kernel's value is
conjunctive. Replay without full append-cycle semantics is a log
viewer; composition without replay is unverifiable nesting;
persistence without schema versioning corrupts silently; the
conformance checks each span several subsystems (check 6 alone
touches admission ordering, canonical encoding, replay, and
substitution). A slice that drops a subsystem invalidates every
check that spans it.

What the all-at-once commitment does **not** require is zero external
exposure before 1.0. Pre-1.0 checkpoint releases (0.x) stage the
*same full build* for early validation: 0.x ships the kernel +
library API with explicit instability warnings as soon as the
kernel-level conformance checks (1–5, 7, 8, 10, 11, 13) pass, so a
real topology author outside the project can build against it while
CLI, replay tooling, and persistence harden.

## 3. Users

One user: a software engineer. The same person occupies four roles at
different moments, and the concerns are cumulative, not disjoint:

- **Authoring** (writing Producers, Predicates, Triggers, Routes,
  TerminationPolicies against the library API): expressiveness,
  debuggability via the log, replay, not being lied to by the
  runtime.
- **Operating** (running topologies from the CLI, inspecting and
  replaying runs): everything above, plus run records, exit
  semantics, resumability (halt-with-resume), persistent-bus hygiene.
- **Adopting** (discovering the repo, evaluating whether to embed or
  contribute): everything above — an evaluation *is* a dry run of
  authoring and operating — plus the trust layer: the spec being
  real (conformance suite proves the implementation matches the
  document), API stability, license clarity, no hidden coupling to
  any model provider.
- **Maintaining the spec** (owning the kernel spec, this document,
  and the technical spec as one connected corpus): the authority of
  last resort. When code and spec disagree — a release blocker per
  principle 1 — the maintainer decides which is wrong and in which
  document the fix lands first. When the kernel needs a v16, the
  maintainer cuts it.

There is no "end user" persona who never touches code in v1.0.
Substrate has no GUI, no hosted service, and no opinion about what
runs on it — but see principle 8: the absence of a UI is a scope
decision, not an architectural one.

## 4. Product principles

1. **The spec is the contract.** The v15 document and this one are
   normative. The implementation passes the conformance suite or it
   is wrong. Disagreement between code and spec is a release blocker,
   resolved in whichever direction is decided *in the spec first*.
2. **All state lives on the log.** Every runtime decision — trigger
   firings with resolved inputs, injections, quarantines,
   terminations, invalid emissions — is a sequenced event. Nothing
   consequential is silent.
3. **Honest replay.** The runtime never claims more determinism than
   it has. Wall-clock cooldowns demote the run's replay ceiling and
   say so in run metadata.
4. **Untrusted Producers are first-class.** Schema validation at the
   bus boundary is mandatory and non-configurable. A misbehaving
   Producer becomes evidence on the log (seq 7 in §0.1), never
   corruption in the run.
5. **Not LLM-specific, not provider-coupled.** The core library
   imports no model SDK. LLM Producers live in user code or optional
   extras.
6. **Vocabulary discipline.** Producer, Bus, View, Predicate,
   Trigger, Route, TerminationPolicy, Topology. Public API, docs,
   CLI output, and log fields use these words and no anthropomorphic
   synonyms.
7. **Open source from day one.** Public repo, Apache-2.0, semver,
   typed public API, CI running the conformance suite on every
   commit. Trust here is mechanical — the spec is canonical, the
   conformance suite is public, anyone can verify the implementation
   matches the document.
8. **No UI, UI-ready.** v1.0 ships no UI — and treats "anyone can
   build a UI of any shape on top, without asking" as a requirement
   rather than an aspiration. Everything a UI needs is a public,
   documented surface: the run-record file format (§0.3), live
   read-only attach to a running bus (F-PERS-4), the inspection API
   (F-OBS-3), the lifecycle vocabulary. The CLI is the existence
   proof: it is implemented exclusively against those public
   surfaces, with no private hooks (F-API-6). If a UI would need a
   kernel change, the kernel is wrong.

## 5. Functional requirements

Requirement IDs are stable and will be cross-referenced by the
technical spec and the conformance suite. MUST/SHOULD per RFC 2119.

### 5.1 Kernel and bus

- **F-BUS-1** The runtime MUST implement the v15 append cycle
  exactly: validate → sequence+append → update Views → evaluate
  Routes → evaluate Predicates/fire Triggers → drain control queue,
  with the orderings and snapshot semantics defined in v15.
- **F-BUS-2** A single writer MUST serialize all appends. Reentrant
  appends from inside Predicate, input_builder, or View evaluation
  MUST raise.
- **F-BUS-3** Producers MUST submit emissions through a bounded
  admission queue; `submit()` blocks when full. Control-plane events
  MUST bypass admission.
- **F-BUS-4** Every event on the log MUST carry a monotonically
  increasing sequence number assigned at append; wall-clock timestamp
  is supplementary metadata.
- **F-BUS-5** The log MUST be append-only for the duration of a run.
  Hot tail in RAM; sealed segments spill to disk past an
  implementation threshold. The hot path (Views, Predicates, Route
  staging) MUST NOT read spilled segments.
- **F-BUS-6** Invalid emissions MUST be wrapped as
  `substrate.ProducerEmittedInvalidEvent`, sequenced, logged, and
  matchable by Predicates, with raw payload preserved and a typed
  reason.

### 5.2 Producers

- **F-PROD-1** A Producer is anything implementing `start(input) ->
  AsyncIterable[Event]`. The runtime MUST consume until completion,
  failure, or cancellation, emitting the corresponding lifecycle
  events.
- **F-PROD-2** Producer kinds MUST declare their emittable event
  schemas at registration, as msgspec Structs (D-3) or schemas
  convertible to them. Emission of an undeclared kind triggers
  F-BUS-6. Producer-declared kinds MUST NOT use the reserved
  `substrate.` prefix.
- **F-PROD-3** Input immutability MUST be enforced **by construction,
  not convention**: a Producer input is composed of immutable types —
  frozen msgspec.Struct (the kernel-native form), frozen Pydantic
  models (accepted at the boundary, converted at registration),
  tuples, frozensets, primitives, and content-hash blob references
  (F-PERS-3) — and the runtime rejects any other type at instantiation
  with a typed error.
- **F-PROD-4** ProducerId is typed: `{kind, instance_id, parent_id,
  metadata}`. instance_id unique per run; persistent-bus mode
  prefixes run-id.

### 5.3 Views

- **F-VIEW-1** Views are deterministic incremental projections,
  updated synchronously in cycle step 3, keyed by subscription
  (event kinds and/or ProducerIds).
- **F-VIEW-2** The library MUST ship standard Views: buffer
  (accumulated payloads per Producer), kind-count, per-kind-latest,
  started/completed counts per kind (for progress gating). Custom
  Views implement a documented `update(event) -> None` / `value()`
  protocol.
- **F-VIEW-3** A Predicate evaluated at sequence N MUST observe View
  state reflecting exactly events ≤ N.

### 5.4 Predicates and Triggers

- **F-PRED-1** Predicates are host-language callables over (event,
  views) — v15 Decision #5. Every Predicate MUST declare a
  **subscription** (event kinds and/or ProducerIds); the writer
  consults only subscribed Predicates on each append. Subscription
  filtering is what makes N-PERF-1's stated shape achievable, and it
  is a requirement, not an optimization. Budget enforcement (D-9):
  the writer measures each call by wall-time; a Predicate exceeding
  the budget accumulates violations, and at k consecutive violations
  (default k=3) it is quarantined via a sequenced
  `substrate.PredicateQuarantined` event. Silent disablement is
  prohibited; enforcement MUST NOT corrupt writer state. The
  accepted, documented limitation: a first stall cannot be aborted —
  a runaway Predicate holds the writer for its own duration, bounded
  thereafter by hysteresis.
- **F-TRIG-1** Triggers are `(predicate, producer_factory,
  firing_policy, input_builder)`. All four firing policies (Once,
  PerEvent, PerKey, WhileTrue) MUST ship.
- **F-TRIG-2** Resolved inputs are recorded in
  `substrate.TriggerFired` events under the D-5 rule: inline when the
  canonical encoding is at or below the F-PERS-3 threshold, by
  content-hash blob reference above it — and in both cases
  `TriggerFired` carries the canonical-bytes hash of the resolved
  input, so citations and cross-run comparisons (D-8) are stable
  regardless of inlining.
- **F-TRIG-3** Cooldowns are logical (append-counted) by default.
  Wall-clock cooldown is opt-in, flagged at registration, recorded
  in run metadata, and demotes the replay ceiling to Level 3(b).
- **F-TRIG-4** Trigger predicates MAY match events from descendants
  of their own firings; the runtime imposes no depth limit and
  performs no divergence detection.
- **F-TRIG-5** When a Trigger's `input_builder` raises, the firing
  produces a `substrate.InputBuildFailed` event recording trigger,
  firing key, and error. No Producer starts; the failure is on the
  log instead of silent.

### 5.5 Routes

- **F-ROUTE-1** Routes are `(source_predicate, target_input_slot,
  transform)`, one-event-in/one-message-out. Push staging happens in
  cycle step 4; staged messages are visible to Trigger firings in
  the same cycle and later. Pull queries from input_builders MUST be
  supported.
- **F-ROUTE-2** Route contributions to a Producer's input MUST be
  recorded as `substrate.InjectionApplied` events.

### 5.6 Termination and lifecycle

- **F-TERM-1** TerminationPolicy callbacks receive termination
  signals, completions, failures, cancellations, quarantines, and
  quiescence; they return cancel-others / let-finish / finalise-run
  / pause-await-input / continue. Per-Producer and per-run scoping
  compose per v15.
- **F-TERM-2** Quiescence MUST be computed per the v15 definition:
  no running Producers, empty admission and control queues, no
  true-and-unfired Trigger, no pending wall-clock cooldown.
- **F-TERM-3** `pause-await-input` MUST emit
  `substrate.TerminationMatched` with a typed `resume_condition`; a
  Trigger on the resume event continues the run. Paused
  persistent-bus runs MUST be resumable across process restarts.
- **F-LIFE-1** All thirteen v15 lifecycle kinds MUST be emitted as
  specified, sequenced and matchable: `RunStarted`, `TriggerFired`,
  `InputBuildFailed`, `ProducerStarted`,
  `ProducerEmittedInvalidEvent`, `ProducerCompleted`,
  `ProducerFailed`, `ProducerCancelled`, `InjectionApplied`,
  `PredicateQuarantined`, `TerminationMatched`, `RunFinalised`, plus
  the reserved namespace rule (F-OBS-5).
- **F-LIFE-2** The standard policy recipes (cancel-all-others,
  let-finish, quiescence-with-watchdog, threshold-count,
  all-completed, subtree-cancellation) ship as named library
  functions.

### 5.7 Persistence and replay

- **F-PERS-1** Per-run mode (default): in-memory bus, persisted
  incrementally to the D-4 run-record format (framed/CRC JSONL
  segments + manifest); the record MUST be complete on any exit
  path, including crash, to the last fsynced frame, with the torn
  tail detected by CRC scan and trimmed — never guessed at.
- **F-PERS-2** Persistent mode (opt-in): bus survives across runs at
  a named root; exclusive file lock (flock) acquired before any run
  starts against that root.
- **F-PERS-3** Event encoding is canonical JSONL per D-7 (RFC 8785),
  versioned, pluggable for binary. Oversized payloads are stored by
  content-hash reference in the blob directory; the inline/reference
  threshold is a technical-spec constant.
- **F-PERS-4** A run's log MUST be readable, read-only, by another
  process while the run is live — the attach path used by `substrate
  tail` and by any UI. Readers need no coordination with the writer
  beyond ignoring an incomplete final frame; sealed segments are
  immutable and safe to read, copy, or ship at any time.
- **F-RPLY-1** Replay Level 1 (Views/derivations from the log) and
  Level 2 (all runtime decisions, including exact resolved inputs)
  MUST work for every recorded run. Level 3(b) substitution
  re-execution MUST work for every recorded run — where substitution
  means every nondeterministic Producer is replaced by a
  **log-backed deterministic emitter** replaying its recorded
  emissions under the recorded admission order; byte-identical
  re-execution (conformance check 6) is achievable precisely because
  substitution is constrained to record playback, not arbitrary
  substitute code. Level 3(a) native re-execution works when
  Producers are deterministic and no wall-clock cooldowns were
  registered; the runtime MUST verify the preconditions from run
  metadata before attempting it.
- **F-RPLY-2** Replay is exposed both as a library API and as
  `substrate replay` (§5.11).

### 5.8 Schema versioning

- **F-SCHEMA-1** Every Producer kind declares a `schema_version` for
  its event schemas, recorded in the `RunStarted` manifest (F-OBS-1).
  The manifest records **schema descriptors sufficient for decoding
  and validation** — not merely version labels; the descriptor format
  is a technical-spec decision — making every run record
  self-describing: replay Levels 1 and 2 read the schemas the run was
  *written with*, not the schemas the current codebase has, so
  replay survives code evolution by construction.
- **F-SCHEMA-2** Schemas are fixed for the duration of a run. A
  persistent bus (F-PERS-2) MAY hold runs written at different
  schema versions, because every event's interpretation routes
  through its own run's manifest.
- **F-SCHEMA-3** Code reading a persistent bus MUST either support
  every schema version present or fail with a typed error naming the
  unsupported (kind, version). Silent reinterpretation across
  versions is prohibited. Migration tooling (rewriting old segments
  to new schemas) is explicitly post-1.0; v1.0's contract is honest
  refusal, not translation.

### 5.9 Observability and provenance

- **F-OBS-1** At run start the runtime MUST append a
  `substrate.RunStarted` event carrying the topology manifest:
  registered Producer kinds with schema descriptors (F-SCHEMA-1);
  Trigger/Route/View/policy identifiers with implementation
  fingerprints (qualified name where available, source hash where
  inspectable, author-supplied version where given); cooldown flags;
  and run metadata including topology-supplied baseline metadata
  (fixtures, seeds, environment identifiers). Initial
  (topology-declared) Producers attribute their provenance to it.
- **F-OBS-2** Decision provenance MUST be closed: every Producer in a
  run is causally attributable to exactly one of
  `substrate.TriggerFired` (with resolved input), a resume event, or
  `substrate.RunStarted`. The library MUST support provenance
  queries from any ProducerId back through its full causal chain.
- **F-OBS-3** An inspection API MUST ship as deterministic queries
  over the run record, returning structured records that cite
  sequence numbers — never natural language:
  `explain_producer(id)`, `trace_ancestry(id)`, `view_at(seq, view)`
  (Level 1 reconstruction), `decisions_between(seq_a, seq_b)`,
  `first_divergence(record_a, record_b)` (under the D-8 equivalence
  relation).
- **F-OBS-4** `substrate inspect <run-record> [--producer <id>]
  [--seq <n>] [--why]` exposes F-OBS-3 from the CLI. This is a
  structured query surface, not a UI.
- **F-OBS-5** Kernel-generated control-plane kinds live in a reserved
  namespace (`substrate.`); Producer-declared kinds MUST NOT collide
  with it. Runtime events and application events are distinguishable
  by inspection of the kind alone.
- **F-OBS-6** Diagnostic predicate-evaluation records (non-firing
  evaluations, with result, elapsed time, View version) are an
  opt-in **off-bus sidecar keyed by sequence number** — never
  sequenced bus events. Rationale: sequenced diagnostic events would
  change sequence assignment between diagnostic and production runs
  of the same topology, destroying cross-run comparability, and
  Predicates could match them, making observation change behavior.
  Enabling diagnostics MUST leave the bus log bit-identical
  (conformance check 14).

### 5.10 Composition

- **F-COMP-1** An embedded substrate instance is a Producer. Its kind
  declaration MUST include an export map `{inner kind → outer
  schema}`; only mapped kinds cross, translated and validated at the
  outer boundary. Default export: inner `RunFinalised` only. The
  inner run's chatter stays inner; the outer bus sees only what the
  boundary declares.
- **F-COMP-2** Outer-bus congestion blocks the embedded Producer's
  exports at its boundary; the inner run is not throttled
  internally.
- **F-COMP-3** Nesting depth is unbounded; each embedded instance
  has its own writer, admission queue, and log — which is a real
  per-level RAM and task cost. Unbounded depth is a semantic
  guarantee, not a claim that depth is free.

### 5.11 CLI

- **F-CLI-1** `substrate run --topology <name> | --topology-module
  <path.py> [topology-specific flags]` — run a topology from the
  registry or a user module; exit code reflects `RunFinalised` vs
  failure vs pause.
- **F-CLI-2** `substrate replay <run-record> [--level 1|2|3a|3b]` —
  reconstruct and verify; `--diff` compares two run records by
  sequence-aligned decisions.
- **F-CLI-3** `substrate validate --topology-module <path.py>` —
  static topology lint: undeclared event kinds referenced by
  Predicates/Routes, unreachable Triggers, missing
  TerminationPolicy, wall-clock-cooldown flags.
- **F-CLI-4** `substrate conformance` — run the conformance suite
  against the installed kernel.
- **F-CLI-5** `substrate tail <run-root> [--kind <k>] [--producer
  <id>] [--since <seq>]` — stream the log of a live or recorded run
  as human-readable lines, over the F-PERS-4 attach path. The filters
  are required: a tail without them is unusable at bus volumes.

### 5.12 Library API

- **F-API-1** The eight primitives, the runtime entry point
  (`Runtime`, `run(topology)`), standard Views, standard policies,
  and the conformance helpers are the public API; everything else is
  private. Public API is fully typed (`py.typed`).
- **F-API-2** A topology is a factory function receiving a
  `TopologyBuilder` (registers Producer kinds + schemas, Triggers,
  Routes, Views, policies). A registry maps names to factories for
  the CLI.
- **F-API-3** No model-provider SDK in core dependencies. Core
  dependencies are pinned in the lockfile and audited on upgrade —
  standard professional Python practice. The current set is
  msgspec, rfc8785, python-ulid, click, rich (technical spec §22.2).
  Optional extras (e.g. `[openai-compat]`) MAY ship thin Producer
  adapters for OpenAI-compatible local endpoints (llama.cpp, vLLM,
  Ollama).
- **F-API-4** The library ships **record-assertion test helpers** —
  `assert_event(kind, **partial_payload)`, `assert_no_event(...)`,
  `assert_sequence([...])` — operating uniformly over live buses and
  recorded run records, so a confirmed-good run record is directly
  usable as a regression fixture.
- **F-API-5** Placement: walkthrough LLM adapters live in the
  optional extras package (F-API-3); reference-topology code lives
  in-repo under `examples/`, versioned with the kernel and exercised
  by CI in deterministic mode.
- **F-API-6** **UI buildability.** A third-party UI of any form MUST
  be buildable against public surfaces alone — the run-record format,
  the F-PERS-4 live attach path, the F-OBS-3 inspection API, and the
  lifecycle vocabulary — with no kernel modifications and no private
  hooks. The CLI MUST itself be implemented exclusively against
  those public surfaces; it is the standing existence proof that the
  requirement holds.

## 6. Non-functional requirements

- **N-PERF-1** Sustained ≥ 100,000 appends/sec on commodity hardware
  under a stated topology shape: 50 registered Predicates and 10
  Views, where subscription filtering (F-PRED-1) reduces substantive
  evaluations to ≤ 5 Predicates per append. Rationale: the D-9
  prototype measured ~800K appends/sec at this shape with budget
  enforcement on; the floor is set at ~1/8 of that to absorb real-
  cycle costs the prototype didn't model (asyncio scheduling, real
  fsync amortization, real View bodies, GC). Appends where many
  Predicates evaluate substantively are governed by the per-call
  budget, not this target.
- **N-PERF-2** Default Predicate budget: 100 µs/call (configurable);
  hysteresis k=3 (configurable). Budget violations quarantine via
  the D-9 mechanism; the writer is never stalled by enforcement
  itself (~100ns/call measured).
- **N-MEM-1** RAM is bounded by (admission bound + hot tail + Views).
  Log growth goes to disk. A run that emits 10M events MUST NOT
  exhaust memory because of the log.
- **N-DET-1** Two replays of the same run record at Level 1/2 MUST
  produce byte-identical View states and decision sequences, across
  OS and Python minor versions — scoped to Views whose state is
  composed of RFC 8785-encodable types (D-7). A custom View holding
  arbitrary objects is outside the guarantee and is flagged as such
  at registration.
- **N-REL-1** Crash of any Producer task never corrupts the bus.
  Crash of the writer process loses at most the events after the
  last fsynced frame; CRC framing (D-4) makes the surviving record's
  end exact — scan, verify, truncate — rather than heuristic.
- **N-SEC-1** Producer emissions are data, never code: no eval of
  payloads, no pickle in the default encoding. Subprocess Producers
  run with no inherited credentials beyond what the topology
  explicitly passes.
- **N-PORT-1** Linux and macOS at v1.0. Windows: per-run mode
  best-effort; **persistent buses (F-PERS-2) are unsupported on
  Windows in v1.0** — a PID-file fallback with a TOCTOU window is
  not an acceptable mechanism for a correctness primitive. On macOS,
  durable fsync uses `F_FULLFSYNC`.
- **N-DOC-1** Shipped docs: the v15 spec, this spec, API reference
  generated from docstrings, a "first topology" tutorial, and one
  worked walkthrough per reference topology. A reader who knows
  asyncio builds a working two-Producer topology from the tutorial
  in under an hour.
- **N-OSS-1** Repo public from first release; semver with documented
  pre-1.0 breakage policy; CHANGELOG; license Apache-2.0 (D-1); CI
  runs conformance + type-check + lint on every PR.

## 7. Conformance suite (release gate)

v1.0 does not ship unless all pass:

1. **Retry enrichment** — Trigger fired by `ProducerFailed` sees the
   failure reason staged from the same event.
2. **Single legal cascade** — the cascade-ambiguous topology has
   exactly one outcome; resolved inputs recorded in `TriggerFired`.
3. **Backpressure liveness** — N+1 appends through a bound-N
   admission queue complete; log intact; hot tail bounded with
   spill.
4. **Invalid-emission cascade** — undeclared kind becomes a sequenced
   `ProducerEmittedInvalidEvent` that fires a Predicate.
5. **Quiescence** — a run with logical cooldowns finalises via
   quiescence-with-watchdog; the same topology with a wall-clock
   cooldown reports the pending timer instead.
6. **Replay round-trip** — record a run with concurrent stochastic
   Producers; Level 2 replay reproduces every decision and resolved
   input; Level 3(b) substitution, replaying the recorded admission
   order, re-executes to a byte-identical log under the D-7
   canonical encoding.
7. **Export boundary** — embedded substrate exports only mapped
   kinds; inner control-plane events do not cross; outer congestion
   blocks at the boundary.
8. **Quarantine visibility** — an over-budget Predicate yields
   `PredicateQuarantined` on the log (after k=3 hysteresis
   violations per D-9) and a TerminationPolicy that escalates on it.
9. **Determinism** — same run record replayed twice at Level 1/2 is
   byte-identical (N-DET-1).
10. **Persistent-bus locking** — second runtime against a locked
    root fails fast with a clear error.
11. **Provenance closure** — every Producer in a recorded run traces
    to `TriggerFired`, a resume event, or `RunStarted`; no dangling
    ProducerIds.
12. **View-at-sequence fidelity** — `view_at(N, v)` reconstructed
    from the record equals the View state a Predicate observed at
    sequence N during the run.
13. **Divergence localization** — `first_divergence` on two records
    of the same topology with one perturbed Producer identifies the
    first divergent runtime decision, by sequence, under the D-8
    equivalence relation.
14. **Diagnostic invariance** — the same seeded topology run with
    the diagnostic sidecar on and off produces bit-identical bus
    logs.
15. **Performance regression** — the N-PERF-1 benchmark runs against
    the previous release tag; throughput regression beyond 20%
    blocks release.
16. **Torn-tail recovery** — a run record truncated mid-frame
    (simulated crash) recovers by CRC scan to exactly the last
    complete frame; replay Levels 1/2 succeed on the recovered
    record; no heuristic recovery paths exist.
17. **InputBuildFailed visibility** — a Trigger whose
    `input_builder` raises produces a sequenced
    `substrate.InputBuildFailed` event; no Producer starts; the run
    continues per its TerminationPolicy.

## 8. Reference topologies (acceptance tests, not product features)

Three, chosen to jointly exercise every primitive, both persistence
modes, and composition:

- **R-1 Ensemble + adjudicator.** N seeded Producers (deterministic
  stand-ins in CI; local LLMs in the walkthrough) stream candidates;
  a Bus-view Predicate ("≥3 final answers") fires the adjudicator;
  cancel-all-others on adjudication. Exercises: concurrency,
  Bus-view predicates, Once policy, TerminationPolicy, Level 3(a)
  replay with seeds.
- **R-2 Pipeline with structured error cascade.** Parser → transform
  → validator chain via PerEvent Triggers; injected faults exercise
  Retry-with-enrichment, RetryExhausted escalation, invalid-emission
  quarantine, InputBuildFailed, and halt-with-resume (human-input
  event resumes the run). Exercises: Routes, retry pattern, error
  cascade, pause/resume, persistent bus. (§0.1 is a miniature of
  this topology.)
- **R-3 Code synthesis with overlap, composed.** A writer Producer
  streams code; a tree-sitter Producer emits AST events from a View
  on the writer's buffer; a typecheck Producer fires on
  complete-declaration predicates — and the whole thing is wrapped
  as an embedded substrate exporting only `ArtifactReady`, run
  inside an outer two-stage topology. Exercises: buffer Views,
  chunk-boundary predicates, overlap, composition/export maps,
  `substrate tail`.

Every reference topology is **dual-mode, and both modes are
required**: a CI mode with deterministic Producers (proves the
wiring; runs on every commit) and a walkthrough mode with real local
models (proves the claim — adjudication in R-1, overlap in R-3; run
and documented before each release). The CI mode alone sanitizes
away the thing each topology exists to demonstrate; the spec says so
rather than letting the CI version masquerade as the demonstration.

## 9. Out of scope for v1.0 (and where it lands)

| Item | Disposition |
|---|---|
| UI | No UI ships in v1.0 — but UI-readiness is a requirement, not a deferral (principle 8, F-API-6, F-PERS-4): any UI, any shape, buildable by anyone on public surfaces alone, with the CLI as the standing existence proof |
| Demonstration catalogue (simulations, adversarial pairs, conversations, reader topologies, …) | User-land examples repo, grown after 1.0; reachability proven by R-1..R-3 |
| Cross-run delta Predicates, cultured starters as shipped helpers | 1.x, on the persistent bus |
| Meta-orchestration, self-modifying topologies, federated substrates | Research directions; the substrate's composition primitives (F-COMP-*) make them tractable. Federation needs a transport+signing design (technical spec sketches the seam, ships nothing) |
| YAML/JSON topology loader | Post-1.0 convenience if demanded; topology is host-language code per spec |
| Distributed multi-host execution | Not planned; composition is the intended scaling path |
| Schema migration tooling | Post-1.0; v1.0 is honest refusal |
| LLM-reader-specific deliverables (comparison-report schema, record-legibility eval harness) | Topology-layer concerns; build them in user code if needed |

## 10. Risks

- **R-RISK-1 Writer throughput in Python.** Substantially de-risked
  by the D-9 prototype (~800K appends/sec at the N-PERF-1 shape)
  and D-3 measurements (msgspec validation ~0.2µs/event); residual
  risk is real-cycle overhead, covered by the N-PERF-1 benchmark in
  CI from week one and conformance check 15.
- **R-RISK-2 Sealed-input ergonomics.** Construction-enforced
  immutability (F-PROD-3) is honest but restrictive: users will want
  to pass file handles, clients, mutable configs. Mitigation: the
  supported immutable input types are explicit; mutable or oversized
  artifacts travel by content-hash blob reference; non-serializable
  execution resources (connections, handles) are topology
  configuration, not Producer input.
- **R-RISK-3 First-stall exposure.** The D-9 mechanism detects but
  cannot abort a Predicate's first overrun; a pathological Predicate
  holds the writer once for its own duration, up to k times before
  quarantine. Accepted and documented; mitigations: `substrate
  validate` lints for known-slow constructs, the budget and k are
  configurable, the diagnostic sidecar records every violation with
  timings.
- **R-RISK-4 Spec drift.** Three documents and a codebase.
  Mitigation: conformance suite cross-references requirement IDs;
  CI fails on unreferenced requirements.
- **R-RISK-5 Scope gravity toward agent-framework features.** The
  ecosystem will ask for prompts, roles, chat, LLM-reader tooling.
  Mitigation: §4 principle 6 and the v15 non-goals are normative;
  such requests are topology-layer by definition.

## 11. Decisions

Each former open question is closed with the evidence that closed
it. IDs preserved.

- **D-1 License: Apache-2.0.** The patent grant matters for a
  substrate others may build derivative implementations of.
- **D-2 Package name:** from a verified-available shortlist, final
  pick is the maintainer's. Checked PyPI: `substrate` and
  `substrate-runtime` are taken; `substrate-kernel`, `substrate-bus`,
  `pysubstrate`, `substrated`, `horizon-substrate`, `buskernel` are
  available.
- **D-3 Schema library: msgspec.** Benchmarked head-to-head: decode+
  validate 4.45M/s vs Pydantic 1.21M/s (3.7×); encode 8.79M/s vs
  1.08M/s (8.1×); frozen Struct mutation raises. Pydantic accepted
  at the boundary, converted at registration.
- **D-4 Run-record layout: framed/CRC JSONL segments + manifest,
  Kafka-shaped.** One hot segment; size-rolled and sealed (rename +
  dir-fsync, thereafter immutable); per-record length+CRC framing in
  the LevelDB/RocksDB WAL tradition, so a crash-torn tail is
  recovered by scan-verify-truncate; fsync policy pluggable per the
  Redis AOF menu — `interval` default, `always` for paranoid, `none`
  for speed. SQLite was rejected on the "bytes are the contract"
  argument.
- **D-5 TriggerFired resolved inputs: inline below the F-PERS-3
  threshold, content-hash blob reference above it — and the
  canonical-bytes hash is always present.** Citations and cross-run
  comparisons key on the hash, so Level 2 replay and D-8 diffs are
  insensitive to where the bytes live.
- **D-6 Python: 3.12+ only.** Matches the stack commitment.
- **D-7 Canonical encoding: RFC 8785 (JCS).** Sorted keys,
  normalized numbers, fixed string escaping. View state participating
  in determinism guarantees is restricted to JCS-encodable types.
- **D-8 Log-equivalence relation: ordered equality of (event-kind
  sequence, decision-identity sequence, canonical payload hashes),
  supplementary metadata excluded.** Wall-clock timestamps, host
  identifiers, and other supplementary metadata never participate.
- **D-9 Predicate budget enforcement: wall-time measurement with
  hysteresis quarantine, on mandatory subscriptions — prototyped,
  measured, and v15 Decision #5 (host-language callables) survives.**
  Measurements: `perf_counter` pair ~99ns; reference shape ran at
  1.40M appends/sec uninstrumented and 804K appends/sec with
  enforcement on; deliberately slow Predicate quarantined after
  exactly k=3 violations with throughput restored.

## 12. Definition of done, v1.0

All §5 requirements implemented; all seventeen conformance checks
green in CI on Linux + macOS; N-PERF-1 and N-DET-1 verified in CI;
R-1..R-3 green in CI mode and run in walkthrough mode with results
documented; docs per N-DOC-1 published; repo public under Apache-2.0
with CHANGELOG and semver tag `1.0.0`. At least one 0.x checkpoint
(§2) shipped with a topology built against it by someone outside the
project before 1.0 is cut.

---

## Document history

- **DRAFT 1** — first product spec against kernel v14.
- **DRAFT 2** — critique-notes pass: F-PRED-1 elevated to O-9, no-MVP
  argued, spec-maintainer role, F-PROD-3 tightened, schema-versioning
  added, conformance check 6 tightened, dual-mode topologies, perf
  regression gate.
- **DRAFT 3** — restructured for the reader: Part I grounding;
  changelog moved here.
- **DRAFT 4** — process change: drafts synthesized fresh, never edited
  in place. §0.3 added; principle "No UI, UI-ready" added with F-API-6
  and F-PERS-4.
- **DRAFT 5** — all open questions resolved as D-1..D-9; conformance
  check 16 (torn-tail recovery) added.
- **DRAFT 6** — added §0.5 "Substrates of substrates" theory.
- **DRAFT 7** — scope cuts on engineering merit: dropped §0.4 ("why
  now"), §0.5 ("substrates of substrates"), principle 8 ("semantic
  observability"), R-4 ("resident reader"), F-OBS-7 (record-legibility
  harness), F-API-4 comparison-report schema. The runtime is the
  product; LLM-reader-specific deliverables are topology-layer
  concerns, not kernel commitments. Inspection APIs, provenance
  closure, structured records — all stay, because they're useful for
  any reader. §0.1 worked example updated to v15 flattened-event
  form. N-PERF-1 tightened to 100K appends/sec floor with 8× headroom
  over the D-9 prototype, replacing the previous 5K floor with 160×
  headroom (suspiciously loose). Added F-TRIG-5 and conformance check
  17 for `InputBuildFailed`.
