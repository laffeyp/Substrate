# Substrate — Product Specification

**DRAFT 4.** Builds on: Horizon: Substrate DRAFT v14 (kernel semantics). The v14 document defines *what the substrate is*; this document defines *the product that ships it*. First of three artifacts: product spec (this document), technical spec (not yet written — the closing docket is its work order), design spec (last; thin at first — the surface is a library and a CLI).
**Stack:** Python 3.12+, asyncio. Schema validation via msgspec or Pydantic (technical spec decides). JSONL persistence, pluggable encoding. **Quality bar:** open source from day one, Apache-2.0. Document history at the end.

---

# Part I — The grounding

Substrate is an abstract project, and abstraction is where readers drown. So this document starts at the bottom: one concrete run, the eight words you need, what the log physically is, and only then the argument. Nothing in Part I is normative.

## 0.1 One run, start to finish

You have a CSV of customer orders in a legacy format and you want it translated to a new schema. On your own machine, with local models, you set up a small system: three cheap models each translate rows concurrently, a deterministic validator checks every translated row, and a policy ends the run when all rows are done.

You run it. Here is what the substrate recorded — not prose, not a debug log, but a sequence of typed events, each with a number:

```
seq  kind                          what happened
───  ────────────────────────────  ─────────────────────────────────────────────
0    RunStarted                    topology=csv-translate; schemas, seeds, fixture ids
1    TriggerFired                  trigger=spawn-workers; input={file: orders.csv}
2    ProducerStarted               worker-1
3    ProducerStarted               worker-2
4    ProducerStarted               worker-3
5    ProducerEvent                 worker-1: RowTranslated row=1
6    ProducerEvent                 worker-2: RowTranslated row=2
7    ProducerEmittedInvalidEvent   worker-3: payload missing required field "price"
8    TriggerFired                  trigger=retry-row; input={row: 3,
                                     failure_context: "missing field: price"}
9    ProducerStarted               worker-3-retry
10   ProducerEvent                 worker-3-retry: RowTranslated row=3
...
41   TerminationMatched            policy=all-completed; decision=finalise-run
42   RunFinalised                  output=orders.translated.csv
```

Now ask questions of it.

*Why did `worker-3-retry` exist?* Because of the firing at seq 8 — and seq 8 tells you the exact input it was given, including the failure reason from seq 7. *What did worker-3 actually emit?* Seq 7 has the raw payload, preserved. *Why did the run end?* Seq 41 names the policy and the decision. *Did anything happen that you didn't design for?* Scan for `ProducerEmittedInvalidEvent` — malformed output didn't crash anything or disappear into an exception; it became a numbered fact.

One more Producer makes the point sharper. Subscribe a small local model to the same bus — a *resident reader*. It has no special access; it sees exactly what any reader of the log sees, and it emits like any other Producer. As the run unfolds it watches, and after seq 42 it adds its own typed event to the record: a diagnosis, in a standard schema — observed sequence, expected sequence, delta, hypothesis — with every claim citing sequence numbers:

```
43   ProducerEvent                 reader-1: Diagnosis
                                     observed: invalid emission at seq 7 (worker-3)
                                     hypothesis: rows where "price" uses a decimal
                                       comma fail schema validation; rows 17 and 23
                                       share the format — expect identical failures
                                     cites: [7, 8, 10]
```

You can check every citation against the lines above. Observation is just another topology — nothing in the runtime knows it is being watched, and nothing had to change to allow it.

Every question about this run is answerable from these lines — by you, by a program, by a model. Nothing consequential happened off the page. That is the product. Everything else in this document is what it takes to make that guarantee rigorous: exact ordering rules, replay, crash behavior, schema evolution, conformance tests that prove the implementation does what this document says.

## 0.2 The eight words

The substrate has eight primitives. Each gets one plain sentence here and a formal definition in the kernel spec. In the example above:

- **Producer** — anything that takes a typed input and emits a stream of typed events. The three translator models, the validator, the resident reader, even an embedded run of another substrate: all Producers. Not "agents" — a Producer can be an LLM, a parser, a simulator, a sensor, a shell command.
- **Event** — one typed, numbered fact on the record. `RowTranslated row=2` at seq 6.
- **Bus** — the single, totally-ordered, append-only log every event goes through. There is exactly one; no Producer talks to another except through it. The numbers in the left column are bus sequence numbers.
- **View** — a running summary the bus maintains incrementally, like "how many rows are done" or "everything worker-1 has said so far." Cheap to read; updated on every append.
- **Predicate** — a small, fast yes/no question asked of the Views when an event lands: "is this a failure?", "are at least three answers in?"
- **Trigger** — the only way new Producers come into existence: when its Predicate says yes, the Trigger builds an input and starts a Producer. Seq 8 is a Trigger firing; the record keeps the exact input it resolved.
- **Route** — a rule that carries data from events into the inputs of *future* Producers. The failure reason from seq 7 reached the retry's input at seq 8 through a Route. Routes never touch a running Producer — inputs are sealed at start.
- **TerminationPolicy** — the judge of when things stop: cancel the others, let them finish, pause and wait for outside input, or finalise. Seq 41.

Two more words that aren't primitives but recur: a **topology** is the arrangement you wrote — which Producer kinds exist, which Triggers and Routes connect them (it is ordinary Python, not a diagram or a DSL); the **run record** is the persisted bus log plus its manifest — the artifact the whole product is organized around.

## 0.3 What the bus actually is

"A shared log" invites the wrong pictures: Kafka clusters, database servers, message brokers. The bus is none of these. For the duration of a run it is an in-process data structure — an ordinary in-memory sequence owned by a single writer. Its persisted form, the run record, is a directory of plain files: numbered, append-only segment files where each line is one event in a canonical JSON encoding, carrying its own sequence number and a checksum so a crash-torn tail can be detected and trimmed; a small manifest naming which segments are sealed and therefore immutable; and a content-addressed blob directory beside them for oversized payloads (an image, a long document), referenced from events by hash.

No server. No broker. No daemon. Nothing to deploy. The right analogy is SQLite, not Postgres: an embedded artifact owned by the process that writes it, which any other program — `tail -f`, a future UI, a replay tool, a reader model — opens read-only while the run is live. The exact framing format and fsync policy are technical-spec decisions (O-4), grounded in well-worn prior art: Kafka's sealed-segment design, the CRC-framed write-ahead logs of LevelDB/RocksDB, the fsync discipline the database literature documents. The preference for plain inspectable files over an embedded database is deliberate: every distinctive promise of this product is about *bytes* — byte-identical replay, content-hash citations, diffable records — and the file should *be* the canonical bytes, not contain them.

## 0.4 Why this exists

**The product is a runtime whose behavior is itself inspectable as structured evidence.** Most runtimes do things and leave you to reconstruct why from logs, traces, and guesswork. Substrate's runtime decisions — what fired, why, with what input, in what order — are themselves typed, numbered events on the record. The run record is not an audit trail bolted on; it is the canonical, machine-readable account of cause.

**This bet has been made before, and the record of those attempts is the strongest evidence for making it again now.** Three precedents, honestly read:

*Omniscient debugging.* Record every state change, query later — built at least seven times across five decades: EXDAMS (1969), Bil Lewis's Omniscient Debugger (2003, whose 31-bit address space held "about 10 million events"), Mozilla's [rr](https://rr-project.org/) (2014), Microsoft's Time Travel Debugging (2017), UndoDB, Pernosco, Replay.io. The recording always worked; adoption always stayed niche — slowdowns on the cost side, and on the payoff side a human stepping backward through a trace. The clearest evidence is [Replay.io's 2024 shutdown postmortem](https://www.replay.io/blog/a-new-direction): "most developers were not looking for more powerful devtools… once you can reproduce the problem, you don't need a time-travel debugger" — followed, in the same post, by the pivot: "at inference time, we believe replayability can offer software agents incredible tools." A funded team built this design, watched it lose with human readers, and independently concluded that the reader had to change.

*Event sourcing.* As a general application architecture it lost by [its own founder's verdict](https://www.infoq.com/news/2016/04/event-sourcing-anti-pattern/) — Greg Young, DDD Europe 2016: building a whole system on event sourcing is "a really big failure"; it is "not a top-level architecture." Where the log is the product it won and stayed won — banks on immutable-fact stores ([Nubank on Datomic](https://building.nubank.com/nubank-acquires-cognitect/)), exchanges on event-sourced cores (LMAX), Kafka in [80%+ of the Fortune 100](https://kafka.apache.org/) as a pipe between systems. The practitioner postmortems name the mechanism: the "free audit log" was "too chatty for direct use" and turned into "tedious projection writing" ([Kiehl, 2019](https://chriskiehl.com/article/event-sourcing-is-hard)); every machine consumer of the log had to be hand-coded per question; the only general-purpose reader was a human. The wider numbers agree: [~90% of telemetry is stored and never queried](https://blog.olly.garden/theres-a-lot-of-bad-telemetry-out-there); Verizon's DBIR found breach evidence sitting unread in victims' own logs in [~86% of cases](https://www.sciencedirect.com/topics/computer-science/data-breach-investigations-reports). Structured evidence was produced at real cost and consumed by approximately no one.

*Whole-system provenance.* [PASS](https://static.usenix.org/events/usenix06/tech/full_papers/muniswamy-reddy/muniswamy-reddy.pdf) (Harvard, 2006) captured complete causal ancestry at the kernel level and never left the lab; its successors [concede](https://tfjmp.org/publications/2017-socc.pdf) prior systems "were not widely adopted" — too much overhead, too much data. Provenance reached production in exactly one place: security detection, where the reader is software (EDR process-ancestry graphs). Same data — dead with human readers, alive with machine ones.

And the honest counterexample, because a fair reviewer will raise it: *the Semantic Web*, the largest typed-facts-for-machine-readers bet ever made. When capable machine readers finally arrived — LLMs — they read prose, not RDF. Three differences keep that from sinking this design. The Semantic Web needed millions of independent humans to hand-annotate truthfully — [Doctorow's "metacrap" objection](https://people.well.com/user/doctorow/metacrap.htm) — where a runtime emits typed events automatically, as a zero-marginal-cost byproduct of one trusted producer. The web's facts already existed as prose, so the new readers had something else to read; a run's causal history exists *nowhere* unless the runtime records it — there is no prose substitute. And today's machine readers demonstrably consume typed data eagerly when the production cost is borne by the system rather than the author: function calling, JSON mode, MCP. The Semantic Web failed at production economics; a runtime solves production economics by construction.

So the claim, scoped precisely: total structured records of computation have been built repeatedly for fifty years; the recording worked; adoption stalled each time at the same wall — every general-purpose reader was a human, and a human will never read ten million events. What changed is not the architecture. The marginal value of evidence was repriced, because a reader now exists that consumes typed, sequenced records at machine speed — and the fit is specific: the things that reader is bad at (inferring hidden control flow, implicit scheduling, state captured in closures, framework side effects) are exactly what the substrate eliminates, and the things it is good at (reasoning over explicit records with stable categories and citeable positions) are exactly what the substrate provides. The resident reader in §0.1 is that repricing made concrete — and because it is just a Producer, a cheap open-weights model can hold the seat permanently, on your own machine. This document makes it an acceptance test (R-4).

One boundary, held throughout: "agent" is a pattern you build *on* the substrate, never a concept *inside* it. The kernel's vocabulary is the eight words above. Naming the readers doesn't rename the primitives.

---

# Part II — The specification

Part II is written for an implementer — dense on purpose, because ambiguity in a requirement is more expensive than density.

## 1. Product statement

Substrate is a concurrent streaming dataflow runtime, shipped as an importable Python library plus a CLI runner. You bring computations — LLMs, ML models, deterministic transforms, subprocesses, simulators, parsers, test runners, sensors — and the substrate runs them concurrently, coordinates them through a single totally-ordered append-only event log, and creates new computations dynamically when predicates over the log are satisfied.

The product is the runtime, not a topology catalogue. Topologies are user code. The product succeeds when a topology author can express any pattern in the v14 "What this enables" section — ensembles, adversarial pairs, recursive decomposition, simulations, code teams with live verification — in ordinary Python against a stable, documented, conformance-tested kernel, and replay any run from its log.

**The product is a runtime whose behavior is itself inspectable as structured evidence.** The run record is the canonical, machine-readable account of runtime causality — what fired, why, with what resolved input, in what order — and the intended consumers include machines: LLM-based tools that inspect run records, reconstruct decisions, explain failures, compare executions, and propose topology changes using the kernel's own vocabulary (§4 principle 8, §5.9). "Agent" stays a topology-layer pattern rather than a kernel primitive — but agents reading the runtime's evidence is a design target, not a side effect.

## 2. Scope position

One build, fully realized. There is no thin-slice MVP that ships half a substrate — half a substrate orchestrates nothing. v1.0 is the complete runtime: all eight primitives, the full v14 append cycle (the fixed sequence of steps the runtime performs on every event — validate, number, update Views, stage Routes, evaluate Predicates, drain control events; the kernel spec defines it exactly), admission/backpressure, both persistence modes, composition with export maps, replay Levels 1–3(b), the lifecycle event vocabulary, the CLI, and the conformance suite. What v1.0 deliberately does **not** include is the demonstration catalogue ("What this enables" topologies as shipped artifacts) and a UI — but v1.0 must make both *rapidly reachable*: each catalogue topology should be an afternoon of user code, and any UI must be buildable on public surfaces alone (§4 principle 9). Reachability is tested by the reference topologies (§8), which exist as acceptance tests, not as product features.

The commitment is argued, not asserted: the kernel's value is conjunctive. Replay without full append-cycle semantics is a log viewer; composition without replay is unverifiable nesting; persistence without schema versioning corrupts silently; the conformance checks each span several subsystems (check 6 alone touches admission ordering, canonical encoding, replay, and substitution). A slice that drops a subsystem invalidates every check that spans it — "half a substrate orchestrates nothing" is a claim about the conjunction being the contract, not a claim that partial software is useless in general.

What the all-at-once commitment does **not** require is zero external exposure before 1.0. Pre-1.0 checkpoint releases (0.x) stage the *same full build* for early validation: 0.x ships the kernel + library API with explicit instability warnings as soon as the kernel-level conformance checks (1–5, 8, 9, 11, 12, 14) pass, so a real topology author outside the project can build against it while CLI, replay tooling, and persistence harden. Checkpoints are exposure milestones, not scope cuts; nothing in §5 moves out of v1.0. Open-source momentum dies in long gaps between release and validation, and the cure is staged exposure, not a thinner product.

## 3. Users

One user: a software engineer. The same person occupies four roles at different moments, and the concerns are cumulative, not disjoint:

- **Authoring** (writing Producers, Predicates, Triggers, Routes, TerminationPolicies against the library API): expressiveness, debuggability via the log, replay, not being lied to by the runtime.
- **Operating** (running topologies from the CLI, inspecting and replaying runs): everything above, plus run records, exit semantics, resumability (halt-with-resume), persistent-bus hygiene.
- **Adopting** (discovering the repo, evaluating whether to embed or contribute): everything above — an evaluation *is* a dry run of authoring and operating — plus the trust layer: the spec being real (conformance suite proves the implementation matches the document), API stability, license clarity, no hidden coupling to any model provider.
- **Maintaining the spec** (owning the kernel spec, this document, and the technical spec as one connected corpus): the authority of last resort. When code and spec disagree — a release blocker per principle 1 — the maintainer decides which is wrong and in which document the fix lands first. When the kernel needs a v15, the maintainer cuts it. When a decision must be added after release, the maintainer rules on whether it is additive or breaking. The role may be the same person as all of the above, but it must exist by name: topology authors reason from the spec, and a spec with open questions and no decider produces divergent topologies.

There is no "end user" persona who never touches code in v1.0. Substrate has no GUI, no hosted service, and no opinion about what runs on it — but see principle 9: the absence of a UI is a scope decision, not an architectural one.

## 4. Product principles

1. **The spec is the contract.** The v14 document and this one are normative. The implementation passes the conformance suite or it is wrong. Disagreement between code and spec is a release blocker, resolved in whichever direction is decided *in the spec first*.
2. **All state lives on the log.** Every runtime decision — trigger firings with resolved inputs, injections, quarantines, terminations, invalid emissions — is a sequenced event. Nothing consequential is silent.
3. **Honest replay.** The runtime never claims more determinism than it has. Wall-clock cooldowns demote the run's replay ceiling and say so in run metadata.
4. **Untrusted Producers are first-class.** Schema validation at the bus boundary is mandatory and non-configurable. A misbehaving Producer becomes evidence on the log (seq 7 in §0.1), never corruption in the run.
5. **Not LLM-specific, not provider-coupled.** The core library imports no model SDK. LLM Producers live in user code or optional extras.
6. **Vocabulary discipline.** Producer, Bus, View, Predicate, Trigger, Route, TerminationPolicy, Topology. Public API, docs, CLI output, and log fields use these words and no anthropomorphic synonyms.
7. **Open source from day one.** Public repo, Apache-2.0, semver, typed public API, CI running the conformance suite on every commit. The rationale: a substrate earns adoption through trust, and trust here is mechanical — the spec is canonical, the conformance suite is public, anyone can verify the implementation matches the document. The value that accumulates on top (topologies, vocabularies, run records) belongs to users; the project's standing comes from owning the reference implementation and the spec's evolution, which openness strengthens rather than dilutes.
8. **Semantic observability.** The runtime's causal decisions are represented as stable, typed, sequenced records that can be reconstructed, queried, and explained from the run record plus the declared topology, without access to hidden implementation state. If a consequential decision cannot be explained that way, the runtime has hidden state and the implementation is wrong — same enforcement posture as principle 1. The property is defined consumer-agnostically, but the intended consumers are named: human operators and LLM-based tools that inspect, explain, debug, compare, and synthesize topologies from run records. Designing the record for that use — stable categories, one causal spine, citeable sequence numbers, honest nondeterminism flags — is a product goal. Principle 6 governs the kernel's own vocabulary, not its audience: Producers don't become agents; naming the readers doesn't rename the primitives.
9. **No UI, UI-ready.** v1.0 ships no UI — and treats "anyone can build a UI of any shape on top, without asking" as a requirement rather than an aspiration. Everything a UI needs is a public, documented surface: the run-record file format (§0.3), live read-only attach to a running bus (F-PERS-4), the inspection API (F-OBS-3), the lifecycle vocabulary. The CLI is the existence proof: it is implemented exclusively against those public surfaces, with no private hooks (F-API-6). If a UI would need a kernel change, the kernel is wrong.

## 5. Functional requirements

Requirement IDs are stable and will be cross-referenced by the technical spec and the conformance suite. MUST/SHOULD per RFC 2119.

### 5.1 Kernel and bus

- **F-BUS-1** The runtime MUST implement the v14 append cycle exactly: validate → sequence+append → update Views → evaluate Routes → evaluate Predicates/fire Triggers → drain control queue, with the orderings and snapshot semantics defined in v14 §The append cycle.
- **F-BUS-2** A single writer MUST serialize all appends. Reentrant appends from inside Predicate, input_builder, or View evaluation MUST raise.
- **F-BUS-3** Producers MUST submit emissions through a bounded admission queue; `submit()` blocks when full. (This is the backpressure mechanism: a flooding Producer waits at the door; the log itself is never trimmed.) Control-plane events MUST bypass admission.
- **F-BUS-4** Every event on the log MUST carry a monotonically increasing sequence number assigned at append; wall-clock timestamp is supplementary metadata.
- **F-BUS-5** The log MUST be append-only for the duration of a run. Hot tail in RAM; sealed segments spill to disk past an implementation threshold. The hot path (Views, Predicates, Route staging) MUST NOT read spilled segments.
- **F-BUS-6** Invalid emissions MUST be wrapped as `ProducerEmittedInvalidEvent`, sequenced, logged, and matchable by Predicates, with raw payload preserved and a typed reason.

### 5.2 Producers

- **F-PROD-1** A Producer is anything implementing `start(input) -> AsyncIterable[Event]`. The runtime MUST consume until completion, failure, or cancellation, emitting the corresponding lifecycle events.
- **F-PROD-2** Producer kinds MUST declare their emittable event schemas at registration. Emission of an undeclared kind triggers F-BUS-6.
- **F-PROD-3** Input immutability MUST be enforced **by construction, not convention**: a Producer input is composed of immutable types — frozen msgspec.Struct / frozen Pydantic models, tuples, frozensets, primitives, and content-hash blob references (F-PERS-3) — and the runtime rejects any other type at instantiation with a typed error. No deep-freeze of arbitrary Python objects is attempted; that cannot be done honestly in CPython, and a MUST enforced "by convention" is a fiction. Mutable or oversized artifacts travel by blob reference.
- **F-PROD-4** ProducerId is typed: `{kind, instance_id, parent_id, metadata}`. instance_id unique per run; persistent-bus mode prefixes run-id.

### 5.3 Views

- **F-VIEW-1** Views are deterministic incremental projections, updated synchronously in cycle step 3, keyed by subscription (event kinds and/or ProducerIds).
- **F-VIEW-2** The library MUST ship standard Views: buffer (accumulated payloads per Producer), kind-count, per-kind-latest, started/completed counts per kind (for progress gating). Custom Views implement a documented `update(event) -> None` / `value()` protocol.
- **F-VIEW-3** A Predicate evaluated at sequence N MUST observe View state reflecting exactly events ≤ N.

### 5.4 Predicates and Triggers

- **F-PRED-1** Predicates are host-language callables over (event, views) — v14 Decision #5, held for now but explicitly at risk from O-9. Every Predicate MUST declare a **subscription** (event kinds and/or ProducerIds); the writer consults only subscribed Predicates on each append. Subscription filtering is what makes N-PERF-1's stated shape achievable, and it is a requirement, not an optimization. The runtime MUST enforce a per-call budget and quarantine violators via a sequenced `PredicateQuarantined` event; silent disablement is prohibited; enforcement MUST NOT corrupt writer state. The enforcement *mechanism* is unresolved — see O-9 — and its resolution may constrain what counts as a valid Predicate.
- **F-TRIG-1** Triggers are `(predicate, producer_factory, firing_policy, input_builder)`. All four firing policies (Once, PerEvent, PerKey, WhileTrue) MUST ship.
- **F-TRIG-2** Resolved inputs MUST be recorded in `TriggerFired` events (subject to F-PERS-3 payload-size handling).
- **F-TRIG-3** Cooldowns are logical (append-counted) by default. Wall-clock cooldown is opt-in, flagged at registration, recorded in run metadata, and demotes the replay ceiling to Level 3(b).
- **F-TRIG-4** Trigger predicates MAY match events from descendants of their own firings; the runtime imposes no depth limit and performs no divergence detection (author's responsibility, per spec).

### 5.5 Routes

- **F-ROUTE-1** Routes are `(source_predicate, target_input_slot, transform)`, one-event-in/one-message-out. Push staging happens in cycle step 4; staged messages are visible to Trigger firings in the same cycle and later. Pull queries from input_builders MUST be supported.
- **F-ROUTE-2** Route contributions to a Producer's input MUST be recorded as `InjectionApplied` events.

### 5.6 Termination and lifecycle

- **F-TERM-1** TerminationPolicy callbacks receive termination signals, completions, failures, cancellations, quarantines, and quiescence; they return cancel-others / let-finish / finalise-run / pause-await-input / continue. Per-Producer and per-run scoping compose per v14.
- **F-TERM-2** Quiescence (nothing running, nothing pending, nothing that could fire) MUST be computed per the v14 definition: no running Producers, empty admission and control queues, no true-and-unfired Trigger, no pending wall-clock cooldown.
- **F-TERM-3** `pause-await-input` MUST emit `TerminationMatched` with a typed `resume_condition`; a Trigger on the resume event continues the run. Paused persistent-bus runs MUST be resumable across process restarts.
- **F-LIFE-1** All lifecycle kinds in the active kernel spec MUST be emitted as specified, sequenced and matchable — the eleven v14 kinds plus `RunStarted` (introduced by F-OBS-1, pending v15 incorporation).
- **F-LIFE-2** The standard policy recipes (cancel-all-others, let-finish, quiescence-with-watchdog, threshold-count, all-completed, subtree-cancellation) ship as named library functions.

### 5.7 Persistence and replay

- **F-PERS-1** Per-run mode (default): in-memory bus, projected to a JSONL run record on finalisation or incrementally (technical spec decides; the record MUST be complete on any exit path, including crash, to the last fsynced segment).
- **F-PERS-2** Persistent mode (opt-in): bus survives across runs at a named root; exclusive file lock (flock; PID-file fallback) acquired before any run starts against that root.
- **F-PERS-3** Event encoding is versioned JSONL by default, pluggable for binary. Oversized payloads (e.g. image bytes) are stored by reference with content hash; the technical spec defines the threshold and blob store layout.
- **F-PERS-4** A run's log MUST be readable, read-only, by another process while the run is live — the attach path used by `substrate tail` and by any UI. Readers need no coordination with the writer beyond ignoring an incomplete final frame; sealed segments are immutable and safe to read, copy, or ship at any time.
- **F-RPLY-1** Replay Level 1 (Views/derivations from the log) and Level 2 (all runtime decisions, including exact resolved inputs) MUST work for every recorded run. Level 3(b) substitution re-execution MUST work for every recorded run — where substitution means every nondeterministic Producer is replaced by a **log-backed deterministic emitter** replaying its recorded emissions under the recorded admission order; byte-identical re-execution (conformance check 6) is achievable precisely because substitution is constrained to record playback, not arbitrary substitute code. Level 3(a) native re-execution works when Producers are deterministic and no wall-clock cooldowns were registered; the runtime MUST verify the preconditions from run metadata before attempting it.
- **F-RPLY-2** Replay is exposed both as a library API and as `substrate replay` (§5.11).

### 5.8 Schema versioning

- **F-SCHEMA-1** Every Producer kind declares a `schema_version` for its event schemas, recorded in the `RunStarted` manifest (F-OBS-1). The manifest records **schema descriptors sufficient for decoding and validation** — not merely version labels; the descriptor format is a technical-spec decision — making every run record self-describing: replay Levels 1 and 2 read the schemas the run was *written with*, not the schemas the current codebase has, so replay survives code evolution by construction.
- **F-SCHEMA-2** Schemas are fixed for the duration of a run. A persistent bus (F-PERS-2) MAY hold runs written at different schema versions, because every event's interpretation routes through its own run's manifest.
- **F-SCHEMA-3** Code reading a persistent bus MUST either support every schema version present or fail with a typed error naming the unsupported (kind, version). Silent reinterpretation across versions is prohibited. Migration tooling (rewriting old segments to new schemas) is explicitly post-1.0; v1.0's contract is honest refusal, not translation. When migration ships, schema changes follow a typed-proposal protocol — a closed taxonomy of change kinds (new kind, new payload field, kind split, kind merge, deprecation, new invariant), each proposal carrying citations to the run records that motivated it, ratified explicitly before the version bumps. Silent schema edits are the drift failure mode the protocol exists to prevent.

### 5.9 Observability and provenance

- **F-OBS-1** At run start the runtime MUST append a `RunStarted` control-plane event carrying the topology manifest: registered Producer kinds with schema descriptors (F-SCHEMA-1); Trigger/Route/View/policy identifiers with **implementation fingerprints** — qualified name where available, source hash where inspectable, author-supplied version where given; the precise composition is a technical-spec decision, and the runtime does not pretend it can hash arbitrary Python semantics (closures, decorators, and generated functions are where "code hash" becomes fake precision); cooldown flags; and run metadata including topology-supplied baseline metadata (fixtures, seeds, environment identifiers), so every record is interpretable from a known initial state rather than an unknown baseline. Initial (topology-declared) Producers attribute their provenance to it. This adds a twelfth lifecycle kind to the v14 table, pending v15 incorporation — without it, explanation closure (F-OBS-2) has dangling roots: initial Producers would have no causal attribution and Trigger identities would exist only in code.
- **F-OBS-2** Decision provenance MUST be closed: every Producer in a run is causally attributable to exactly one of `TriggerFired` (with resolved input), a resume event, or `RunStarted`. The library MUST support provenance queries from any ProducerId back through its full causal chain.
- **F-OBS-3** An inspection API MUST ship as deterministic queries over the run record, returning structured records that cite sequence numbers — never natural language: `explain_producer(id)`, `trace_ancestry(id)`, `view_at(seq, view)` (Level 1 reconstruction), `decisions_between(seq_a, seq_b)`, `first_divergence(record_a, record_b)` (requires the O-8 equivalence relation).
- **F-OBS-4** `substrate inspect <run-record> [--producer <id>] [--seq <n>] [--why]` exposes F-OBS-3 from the CLI. This is a structured query surface, not a UI.
- **F-OBS-5** Kernel-generated control-plane kinds live in a reserved namespace; Producer-declared kinds MUST NOT collide with it. Runtime events and application events are distinguishable by inspection of the kind alone.
- **F-OBS-6** Diagnostic predicate-evaluation records (non-firing evaluations, with result, elapsed time, View version) are an opt-in **off-bus sidecar keyed by sequence number** — never sequenced bus events. Rationale: sequenced diagnostic events would change sequence assignment between diagnostic and production runs of the same topology, destroying cross-run comparability, and Predicates could match them, making observation change behavior. Enabling diagnostics MUST leave the bus log bit-identical (conformance check 14).
- **F-OBS-7** The repo MUST ship a **record-legibility evaluation harness**: a question set over the reference topologies' run records ("why did Producer X start?", "what was the first invalid emission?", "where do these two runs first diverge?"), with ground truth computed deterministically via F-OBS-3, against which an LLM reader's answers — required to cite sequence numbers for every claim — are graded automatically. "A model can answer provenance questions from the record alone" is thereby a tested property of each release, not positioning. Gating is split: the deterministic ground-truth layer is a release gate; the LLM-reader baseline (run with a current local open-weights model) is published and informative, never pass/fail — model churn and hardware variance make it unsuitable as a gate.

### 5.10 Composition

- **F-COMP-1** An embedded substrate instance is a Producer. Its kind declaration MUST include an export map `{inner kind → outer schema}`; only mapped kinds cross, translated and validated at the outer boundary. Default export: inner `RunFinalised` only. (The inner run's chatter stays inner; the outer bus sees only what the boundary declares.)
- **F-COMP-2** Outer-bus congestion blocks the embedded Producer's exports at its boundary; the inner run is not throttled internally.
- **F-COMP-3** Nesting depth is unbounded; each embedded instance has its own writer, admission queue, and log — which is a real per-level RAM and task cost. Unbounded depth is a semantic guarantee, not a claim that depth is free; deep meta-orchestration topologies budget for it.

### 5.11 CLI

- **F-CLI-1** `substrate run --topology <name> | --topology-module <path.py> [topology-specific flags]` — run a topology from the registry or a user module; exit code reflects RunFinalised vs failure vs pause.
- **F-CLI-2** `substrate replay <run-record> [--level 1|2|3a|3b]` — reconstruct and verify; `--diff` compares two run records by sequence-aligned decisions.
- **F-CLI-3** `substrate validate --topology-module <path.py>` — static topology lint: undeclared event kinds referenced by Predicates/Routes, unreachable Triggers, missing TerminationPolicy, wall-clock-cooldown flags.
- **F-CLI-4** `substrate conformance` — run the conformance suite against the installed kernel.
- **F-CLI-5** `substrate tail <run-root> [--kind <k>] [--producer <id>] [--since <seq>]` — stream the log of a live or recorded run as human-readable lines, over the F-PERS-4 attach path. The filters are required: a tail without them is unusable at bus volumes.

### 5.12 Library API

- **F-API-1** The eight primitives, the runtime entry point (`Runtime`, `run(topology)`), standard Views, standard policies, and the conformance helpers are the public API; everything else is private. Public API is fully typed (`py.typed`).
- **F-API-2** A topology is a factory function receiving a `TopologyBuilder` (registers Producer kinds + schemas, Triggers, Routes, Views, policies). A registry maps names to factories for the CLI.
- **F-API-3** No model-provider SDK in core dependencies. Optional extras (e.g. `substrate[openai-compat]`) MAY ship thin Producer adapters for OpenAI-compatible local endpoints (llama.cpp, vLLM, Ollama), since open-weight models are a primary deployment target — adapters are user-convenience, not kernel.
- **F-API-4** The library ships **record-assertion test helpers** — `assert_event(kind, **partial_payload)`, `assert_no_event(...)`, `assert_sequence([...])` — operating uniformly over live buses and recorded run records, so a confirmed-good run record is directly usable as a regression fixture. An **expected-vs-observed comparison report** (observed sequence, expected sequence, delta, hypothesis slot — every entry citing sequence numbers) ships as a standard typed payload, usable both by test code and as the emission schema for diagnosis/reader Producers (R-4).
- **F-API-5** Placement: walkthrough LLM adapters live in the optional extras package (F-API-3); reference-topology code lives in-repo under `examples/`, versioned with the kernel and exercised by CI in deterministic mode.
- **F-API-6** **UI buildability.** A third-party UI of any form MUST be buildable against public surfaces alone — the run-record format, the F-PERS-4 live attach path, the F-OBS-3 inspection API, and the lifecycle vocabulary — with no kernel modifications and no private hooks. The CLI MUST itself be implemented exclusively against those public surfaces; it is the standing existence proof that the requirement holds.

## 6. Non-functional requirements

- **N-PERF-1** Sustained ≥ 5,000 appends/sec on commodity hardware under a **stated topology shape**: 50 registered Predicates and 10 Views, where subscription filtering (F-PRED-1) reduces substantive evaluations to ≤ 5 Predicates per append. The assumption is stated because the naive reading — 50 substantive evaluations at the 100µs budget — yields 10ms/cycle ≈ 100 cycles/sec, two orders of magnitude away; the throughput claim is a claim about filtering, and the spec says so. Appends where many Predicates evaluate substantively are governed by the per-call budget, not this target. Rationale: token-rate LLM Producers emit at ~10–100 events/sec each; deterministic Producers (parsers, simulators) are the pressure case and the admission queue is the relief valve.
- **N-PERF-2** Default Predicate budget: 100 µs/call (configurable). Budget violations quarantine, never stall the writer.
- **N-MEM-1** RAM is bounded by (admission bound + hot tail + Views). Log growth goes to disk. A run that emits 10M events MUST NOT exhaust memory because of the log.
- **N-DET-1** Two replays of the same run record at Level 1/2 MUST produce byte-identical View states and decision sequences, across OS and Python minor versions — scoped to Views whose state is composed of canonically encodable supported types (O-7). A custom View holding arbitrary objects is outside the guarantee and is flagged as such at registration.
- **N-REL-1** Crash of any Producer task never corrupts the bus. Crash of the writer process loses at most the events after the last fsynced segment; the run record up to that point replays cleanly.
- **N-SEC-1** Producer emissions are data, never code: no eval of payloads, no pickle in the default encoding. Subprocess Producers run with no inherited credentials beyond what the topology explicitly passes.
- **N-PORT-1** Linux and macOS at v1.0. Windows: per-run mode best-effort; **persistent buses (F-PERS-2) are unsupported on Windows in v1.0** — a PID-file fallback with a TOCTOU window is not an acceptable mechanism for a correctness primitive, and "best-effort locking" corrupts buses. Windows persistent-bus support arrives only with a real exclusive-lock mechanism.
- **N-DOC-1** Shipped docs: the v14 spec, this spec, API reference generated from docstrings, a "first topology" tutorial, and one worked walkthrough per reference topology. The tutorial is schema-first and teaches the log before advanced APIs: declare event kinds, write two Producers, add a View and a Trigger, run, inspect the log, explain why the Trigger fired (citing sequence numbers), replay, modify, compare runs. Each reference-topology walkthrough includes an annotated run record. A reader who knows asyncio builds a working two-Producer topology from the tutorial in under an hour.
- **N-OSS-1** Repo public from first release; semver with documented pre-1.0 breakage policy; CHANGELOG; license Apache-2.0 (O-1, resolved); CI runs conformance + type-check + lint on every PR.

## 7. Conformance suite (release gate)

The four v14 checks, promoted and extended. v1.0 does not ship unless all pass:

1. **Retry enrichment** — Trigger fired by `ProducerFailed` sees the failure reason staged from the same event.
2. **Single legal cascade** — the v13-ambiguous topology has exactly one outcome; resolved inputs recorded in `TriggerFired`.
3. **Backpressure liveness** — N+1 appends through a bound-N admission queue complete; log intact; hot tail bounded with spill.
4. **Invalid-emission cascade** — undeclared kind becomes a sequenced `ProducerEmittedInvalidEvent` that fires a Predicate.
5. **Quiescence** — a run with logical cooldowns finalises via quiescence-with-watchdog; the same topology with a wall-clock cooldown reports the pending timer instead.
6. **Replay round-trip** — record a run with concurrent stochastic Producers; Level 2 replay reproduces every decision and resolved input; Level 3(b) substitution, replaying the recorded admission order, re-executes to a **byte-identical** log under the canonical encoding (O-7). "Equivalent" means byte-identical, aligned with N-DET-1 — not outcome-identical, not merely causally-identical.
7. **Export boundary** — embedded substrate exports only mapped kinds; inner control-plane events do not cross; outer congestion blocks at the boundary.
8. **Quarantine visibility** — an over-budget Predicate yields `PredicateQuarantined` on the log and a TerminationPolicy that escalates on it.
9. **Determinism** — same run record replayed twice at Level 1/2 is byte-identical (N-DET-1).
10. **Persistent-bus locking** — second runtime against a locked root fails fast with a clear error.
11. **Provenance closure** — every Producer in a recorded run traces to `TriggerFired`, a resume event, or `RunStarted`; no dangling ProducerIds.
12. **View-at-sequence fidelity** — `view_at(N, v)` reconstructed from the record equals the View state a Predicate observed at sequence N during the run.
13. **Divergence localization** — `first_divergence` on two records of the same topology with one perturbed Producer identifies the first divergent runtime decision, by sequence, under the O-8 equivalence relation.
14. **Diagnostic invariance** — the same seeded topology run with the diagnostic sidecar on and off produces bit-identical bus logs.
15. **Performance regression** — the N-PERF-1 benchmark runs against the previous release tag; throughput regression beyond 20% blocks release. Functional conformance alone must not be able to ship a 5× slower kernel.

## 8. Reference topologies (acceptance tests, not product features)

Four, chosen to jointly exercise every primitive, both persistence modes, composition, and the resident-reader claim — and to prove the "What this enables" catalogue is an afternoon away, not a roadmap item:

- **R-1 Ensemble + adjudicator.** N seeded Producers (deterministic stand-ins in CI; local LLMs in the walkthrough) stream candidates; a Bus-view Predicate ("≥3 final answers") fires the adjudicator; cancel-all-others on adjudication. Exercises: concurrency, Bus-view predicates, Once policy, TerminationPolicy, Level 3(a) replay with seeds.
- **R-2 Pipeline with structured error cascade.** Parser → transform → validator chain via PerEvent Triggers; injected faults exercise Retry-with-enrichment, RetryExhausted escalation, invalid-emission quarantine, and halt-with-resume (human-input event resumes the run). Exercises: Routes, retry pattern, error cascade, pause/resume, persistent bus. (§0.1 is a miniature of this topology.)
- **R-3 Code synthesis with overlap, composed.** A writer Producer streams code; a tree-sitter Producer emits AST events from a View on the writer's buffer; a typecheck Producer fires on complete-declaration predicates — and the whole thing is wrapped as an embedded substrate exporting only `ArtifactReady`, run inside an outer two-stage topology. Exercises: buffer Views, chunk-boundary predicates, overlap, composition/export maps, `substrate tail`.
- **R-4 Resident reader.** A reader Producer subscribed to Views over another topology's bus emits typed diagnosis events in the F-API-4 comparison-report schema — observed vs expected sequence, delta, hypothesis — with every claim citing sequence numbers, exactly as sketched at seq 43 of §0.1. Deterministic rule-based reader in CI; a local open-weights model in the walkthrough, graded by the F-OBS-7 harness. Exercises: read-only machine-speed subscription via F-PERS-4, diagnosis-event schemas, the claim that observation is just another topology — no kernel changes, no special access, the reader sees only what the log says.

Every reference topology is **dual-mode, and both modes are required**: a CI mode with deterministic Producers (proves the wiring; runs on every commit) and a walkthrough mode with real local models (proves the claim — adjudication in R-1, overlap in R-3, diagnosis in R-4; run and documented before each release). The CI mode alone sanitizes away the thing each topology exists to demonstrate. Each topology ships with a walkthrough doc and annotated run record (N-DOC-1).

## 9. Out of scope for v1.0 (and where it lands)

| Item | Disposition |
|---|---|
| UI | No UI ships in v1.0 — but UI-readiness is a requirement, not a deferral (principle 9, F-API-6, F-PERS-4): any UI, any shape, buildable by anyone on public surfaces alone, with the CLI as the standing existence proof. A first-party trace/replay UI is a post-1.0 candidate that obeys the same rule |
| Demonstration catalogue (simulations, adversarial pairs, conversations, …) | User-land examples repo, grown after 1.0; reachability proven by R-1..R-3 |
| Cross-run delta Predicates, cultured starters as shipped helpers | 1.x, on the persistent bus |
| Meta-orchestration, self-modifying topologies, federated substrates | Research directions per v14 §Where this points; federation needs a transport+signing design (technical spec sketches the seam, ships nothing). Ground rule carried forward: topology-mutation proposals must cite sequence numbers from run records (F-OBS-3 makes every citation checkable), arrive as typed proposals from a closed taxonomy (add/retire/split/merge/re-route, mirroring the §5.8 schema-change kinds), and are ratified explicitly before taking effect — proposal, citation, ratification, version bump |
| YAML/JSON topology loader | Post-1.0 convenience if demanded; topology is host-language code per spec |
| Distributed multi-host execution | Not planned; composition + federation is the intended scaling path |

## 10. Risks

- **R-RISK-1 Writer throughput in Python.** The single writer does validation + Views + Predicates per cycle in pure Python. Mitigation: N-PERF-1 benchmark in CI from week one; msgspec-class validation; escape hatch is documented batching at the admission queue, never weakening cycle semantics.
- **R-RISK-2 Sealed-input ergonomics.** Construction-enforced immutability (F-PROD-3) is honest but restrictive: users will want to pass file handles, clients, mutable configs, large artifacts. Mitigation: the supported immutable input types are explicit; mutable or oversized artifacts travel by content-hash blob reference; non-serializable execution resources (connections, handles) are topology configuration, not Producer input.
- **R-RISK-3 Predicate budget enforcement.** Elevated to O-9 — the highest-stakes open question in the corpus. Wall-time hysteresis detects but cannot abort a first stall (the first runaway Predicate holds the writer for however long it runs); tracing can abort but costs ~10× and breaks N-PERF-1 by itself. Conformance check 8 gates whatever mechanism wins; a v14 Decision #5 revision is on the table.
- **R-RISK-4 Spec drift.** Three documents and a codebase. Mitigation: conformance suite cross-references requirement IDs; CI fails on unreferenced requirements.
- **R-RISK-5 Scope gravity toward agent-framework features.** The ecosystem will ask for prompts, roles, chat. Mitigation: §4 principle 6 and the v14 non-goals are normative; such requests are topology-layer by definition.

## 11. Open questions

- **O-1 — RESOLVED: Apache-2.0.** The patent grant matters for a substrate others may build derivative implementations of. Also reclassified: this was never deferrable to v1.0 — "open source from day one" requires the license before the first public commit, not before the first release.
- **O-2** Package/repo name: `substrate` is taken on PyPI in adjacent senses; candidates needed before first release.
- **O-3** Schema library: msgspec (speed, matches N-PERF-1) vs Pydantic (ubiquity). Technical spec decides with a benchmark.
- **O-4** Run-record layout — narrowed by research. Leading candidate: **framed/CRC JSONL segments + manifest, Kafka-shaped** — one hot segment receiving appends; segments roll at a size threshold and are sealed (renamed + dir-fsynced, thereafter immutable); per-record length+CRC framing in the LevelDB/RocksDB WAL tradition so a crash-torn tail is detected by scan-verify-truncate rather than heuristics; fsync policy pluggable per the Redis AOF menu (none / interval / always). Runner-up: SQLite in WAL mode (recovery and snapshot-isolated live readers pre-solved, ~80K inserts/sec measured with `synchronous=NORMAL`) — rejected so far because every distinctive promise of this product is about bytes, and SQLite hides the bytes: the canonical JSONL stream becomes an extraction product inside an opaque page-structured container, a "run record" becomes three files where naively copying one silently drops recent events, and read-only attach carries `-shm` permission caveats. Final call: technical spec.
- **O-5** Does `TriggerFired` embed full resolved inputs or hash+reference above the F-PERS-3 threshold? (Affects Level 2 replay ergonomics for large inputs.)
- **O-6** Minimum supported Python: 3.12 only, or 3.11+ if nothing requires 3.12.
- **O-7** Canonical event encoding: N-DET-1 (byte-identical replay) is untestable until the technical spec pins a canonical JSON form — RFC 8785 (JSON Canonicalization Scheme) is the obvious candidate: sorted keys, normalized numbers, fixed string escaping, same logical event → identical bytes — and restricts View state to canonically-encodable types.
- **O-8** Log-equivalence relation: with conformance check 6 pinned to byte-identical under recorded admission order, O-8 narrows to `first_divergence`'s comparison across *different* runs — candidate: equality of (event-kind sequence, decision sequence, payload hashes), supplementary metadata excluded. Technical spec decides and the conformance suite encodes it.
- **O-9** Predicate budget enforcement mechanism — elevated from F-PRED-1; the highest-stakes open question in the corpus. Wall-time measurement can detect but not abort a first stall; `sys.settrace`-class interruption can abort but costs ~10× and breaks N-PERF-1 alone; a restricted predicate algebra over fixed operators would bound cost statically but revises v14 Decision #5 (host-language callables), which is load-bearing for expressiveness. Resolution requires prototyping enforcement on real Predicates at N-PERF-1 throughput *before* the kernel implementation hardens. A v14 revision is explicitly on the table; the spec does not commit to predicate-as-arbitrary-callable surviving contact with enforcement.

## 12. Glossary

Formal definitions; §0.2 is the informal version.

- **Run record** — the persisted bus log plus `RunStarted` manifest, sidecar, and blob store for one run; the canonical account of what happened.
- **Segment** — one numbered append-only file of the run record; the hot segment receives appends, sealed segments are immutable.
- **Manifest** — the small file naming which segments are sealed and complete, updated by atomic rename.
- **Structured evidence** — runtime facts represented as typed, sequenced, citeable events rather than prose, traces, or spans.
- **Semantic observability** — the property that causal decisions are reconstructable and queryable from the run record plus declared topology, with no hidden state (§4 principle 8).
- **Runtime causality** — the chain of events and decisions by which the runtime produced a given state.
- **Provenance closure** — every Producer traces to `TriggerFired`, a resume event, or `RunStarted` (F-OBS-2); no dangling roots.
- **Resident reader** — a Producer subscribed to Views over a bus, emitting typed diagnosis events about the run it observes (§0.1 seq 43; R-4).
- **Diagnostic sidecar** — the opt-in, off-bus record of non-firing Predicate evaluations, keyed by sequence number, with no effect on the bus log (F-OBS-6).
- **Comparison report** — the standard typed payload of observed sequence, expected sequence, delta, and hypothesis, every entry citing sequence numbers (F-API-4).
- **Implementation fingerprint** — the manifest's best-effort identification of topology code: qualified name, source hash where inspectable, author-supplied version (F-OBS-1).
- **Log-equivalence relation** — the explicit definition of "the same" used when comparing two run records (O-8).
- **Canonical encoding** — the pinned byte-level event encoding that makes "byte-identical" claims testable (O-7).
- **Log-backed deterministic emitter** — the substitute Producer used in Level 3(b) replay: it replays recorded emissions under recorded admission order rather than recomputing them (F-RPLY-1).

## 13. Definition of done, v1.0

All §5 requirements implemented; all fifteen conformance checks green in CI on Linux + macOS; N-PERF-1 and N-DET-1 verified in CI; R-1..R-4 green in CI mode and run in walkthrough mode with results documented; the record-legibility ground-truth harness (F-OBS-7) green as a gate, with baseline LLM-reader results published (informative, not pass/fail); docs per N-DOC-1 published; repo public under Apache-2.0 with CHANGELOG and semver tag `1.0.0`. At least one 0.x checkpoint (§2) shipped with a topology built against it by someone outside the project before 1.0 is cut.

---

## Document history

- **DRAFT 1** — first product spec against kernel v14: requirement IDs, conformance gate, reference topologies, risks, open questions.
- **DRAFT 2, first pass** — critique-notes incorporation: F-PRED-1 elevated to O-9; no-MVP commitment argued + 0.x exposure milestones; spec-maintainer role; N-PERF-1 assumptions stated; F-PROD-3 tightened to construction-enforced immutability; schema-versioning section added; O-1 resolved (Apache-2.0); conformance check 6 tightened to byte-identical; dual-mode reference topologies; perf regression gate. Also: semantic-observability principle, F-OBS section, resident reader R-4, record-assertion helpers, typed-proposal protocol for schema and topology mutation.
- **DRAFT 2, second pass** — §5 reordered; implementation fingerprints replace "code hashes"; Level 3(b) defined as log-backed playback; N-DET-1 scoped to canonical View types; F-OBS-7 gating split; F-SCHEMA-1 tightened to schema descriptors; glossary added; consistency fixes.
- **DRAFT 3** — restructured for the reader: Part I grounding (concrete run with its record, the eight primitives in plain language, thesis and why-now); changelog moved here; inline glosses at first use of kernel terms.
- **DRAFT 4** — process change: drafts are now synthesized fresh from gathered input, never edited in place. Content: the "existed before and lost" claim researched and rewritten as a scoped, cited argument (omniscient debugging with the Replay.io pivot as primary evidence; event sourcing lost-as-architecture / won-as-ledger-and-plumbing per its founder's own verdict; whole-system provenance; the Semantic Web as the honest counterexample, answered on production economics); new §0.3 "What the bus actually is" (in-process structure + directory of framed JSONL segments; no server, no broker; SQLite-not-Postgres analogy) grounded in storage research that also narrowed O-4 and O-7; the resident reader given a concrete seat in §0.1 (seq 43) instead of a tacked-on assertion; "How to read this document" removed (it interrupted reading with instructions about reading); §1's indirect thesis framing dropped; principle 9 "No UI, UI-ready" added with F-API-6 and F-PERS-4 making UI-buildability a tested requirement rather than an intention.

---

*Next artifact (not yet written): technical specification. Its docket — kernel internals (writer loop, View/Predicate dispatch with subscription indexing, input-type validation per F-PROD-3, run-record format per the O-4 leading candidate, blob store, export-map translation, `RunStarted` manifest format, comparison-report schema, F-OBS-7 ground-truth layer), public API signatures, F-PERS-2 Windows locking, schema-version migration mechanics, and resolutions for O-2/O-3/O-4/O-5/O-6/O-7/O-8/O-9 — with O-9 prototyped first, since its outcome can reshape the kernel.*

*Flows back into the kernel spec (v15, when cut by the spec maintainer): Decision #5 if O-9 forces a predicate-language constraint; a schema-versioning note on Decision #4 (persistent bus); the `RunStarted` lifecycle kind from F-OBS-1.*
