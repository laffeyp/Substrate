# The Three-Way Intersection — Cradle × Scenario Research × Substrate

**Date:** 2026-08-12
**Status:** Draft 1.0
**Related papers:**
- `docs/research/02_substrate_candidate_scenario_research.md` (Draft 1.2) — the scenario substrate candidacy inside Cradle
- ADR-037 (multi-substrate framework), ADR-036 (SDD instrumentation), ADR-031 amended, ADR-009 (SDD foundational), ADR-001 (Cradle ↔ substrate boundary)

---

## What this paper is

Three projects sit on one disk. Each solves a piece of the same problem. The pieces do not currently know about each other in code, though they share `sdd-kit-2` as the discipline layer and one author.

- **Cradle** (`/Users/peterlaffey/Documents/Claude/Projects/Trading System 1/`) is a trading substrate framework — Postgres-backed operators, sqrt-time-scaled outcome thresholds, ten hard constraints, three-slot falsification verdict, currently thirteen sprints in.
- **The scenario-research workstream** (`/Users/peterlaffey/Documents/Claude/Projects/Ongoing Trading Research/`) is ~450 KB of Markdown across twenty-five files produced August 1-12: a Day 161 Hormuz dossier, thirteen versions of a Convexity Basket, forty Devil's Advocate counterarguments, portfolio payoff matrices across six crisis tiers.
- **Substrate** (`/Users/peterlaffey/Documents/Claude/Projects/Agent Orchestration/substrate/`) is a general-purpose Python runtime — `substrate-kernel` on PyPI — that coordinates arbitrary computations through one totally-ordered append-only log via eight primitives (Producer, Event, Bus, View, Predicate, Trigger, Route, TerminationPolicy).

The paper asks: what should live where. Its answer runs against my earlier draft. Draft 1.2 of the substrate-candidacy paper argued the scenario workstream could become Cradle's substrate #3 with 1,640 LOC of friction. This paper argues the same workstream fits Substrate's shape at ~500 LOC with no friction, and that Cradle's own runtime layer is a candidate to migrate onto Substrate — leaving Cradle's domain layer (contracts, operators, promotion logic) intact.

## What this paper is not

- Not a proposal to rewrite Cradle. The trading substrate is 8,389 LOC of operators across twenty-seven files, thirteen sprints of promotion machinery, sqrt-time-scaled thresholds, and a Postgres schema that stays wanted on the day Sprint 6.7 closes. None of that moves.
- Not a claim that Substrate's primitives are richer than Cradle's. They are more general. Cradle's are more opinionated. Both stances are correct for their domains.
- Not a claim the scenario thesis is right or the SWE-bench run will confirm T5. Those are separate questions.

## Grounding — the code read for this paper

Cradle read is in `docs/research/02_substrate_candidate_scenario_research.md` §Grounding. New reads for this paper:

Substrate (paths relative to `/Users/peterlaffey/Documents/Claude/Projects/Agent Orchestration/substrate/`):

- `README.md` (177 lines) — the eight primitives, the shape, the status
- `docs/NORTH-STAR-2026-08-10-v5.md` (474 lines) — the five themes, the vocabulary claim
- `docs/specs/kernel_spec/v15.md` (1,067 lines; read pages 1-800) — canonical semantics: bus, append cycle, replay levels, primitives, patterns
- `docs/adding-a-topology.md` (163 lines) — the on-ramp; the `review_poll` template
- `src/substrate/types.py` (78 lines) — `Event`, `ProducerRef`, `BlobRef`, `Subscription`
- `src/substrate/protocols.py` (95 lines) — `Producer`, `Responder`, `View`, `TriggerContext` structural protocols
- `src/substrate/kernel/topology.py` (336 lines) — `TopologyBuilder`, `Registration`, `register_topology`
- `src/substrate/kernel/triggers.py` (109 lines) — `Once`, `PerEvent`, `PerKey`, `WhileTrue`; `Logical`, `WallClock` cooldowns
- `src/substrate/kernel/views.py` (124 lines) — `BufferView`, `KindBuffer`, `KindCount`, `PerKindLatest`, `StartedCompletedCounts`
- `src/substrate/kernel/policies.py` (190 lines) — `TerminationPolicy`, `Decision`, `threshold_count`, `all_completed`, `quiescence_with_watchdog`, `pause_await_input`, `any_of`, `all_of`
- `src/substrate/kernel/runtime.py` (777 lines) — the `Runtime` class, run/resume, writer loop, producer tasks, termination consultation, stuck-quiescence guard
- `src/substrate/kernel/sequencer.py` (427 lines) — `AppendCycle`, the six-step append cycle, view failure terminal, quarantine, blob offload
- `src/substrate/kernel/composition.py` (236 lines) — `embedded_substrate`, `EmbeddedRunFailed`, `InnerRootRequired`
- `src/substrate/topologies/best_of_n/{__init__.py,contracts.py}` (184 + 62 lines) — a complete reference topology: `Draft`, `Candidate`, `Verdict`, `Solved`, `Exhausted`

## The three projects, in one paragraph each

**Cradle.** A framework for building trading substrates that promote Procedures from Episode evidence. Every operator wraps `_run` in `OPERATOR_RUN_BEGIN`/`OPERATOR_RUN_END`/`OPERATOR_FAILED` envelopes per `substrates/trading/operators/base.py` lines 88-135. Every signal validates at the mouth against a pinned vocabulary (`signals/versions/0.1.json`). Every persisted memory row has content-derived IDs (`retrospective_compressor.py` lines 112-131), Run-scoped isolation (`constraint_projector.py` lines 138-143), and freshness gates (`joint_state_composer.py` lines 95-97). ADR-037 partitioned trading-specific concerns into `substrates/trading/` and left Cradle-core (contracts, runtime, eval) meant-to-be substrate-agnostic. Forecasting was the second substrate; scenario research is the candidate third.

**Scenario research.** Prose SDD. The Day 161 Hormuz dossier is a `WorldState` snapshot with 157 named sources; the Convexity Basket v9→v13 lineage is a Procedure evolution with ablation history in prose ("META and WEAT are dropped because Alpha Vantage prices diverged"); the forty-item Devil's Advocate is a pre-registered falsification battery; the Portfolio Payoff Analysis is a `(Scenario × Position) → intrinsic_payoff` matrix. None of this runs. All of it follows the same discipline Cradle's code follows — vocabulary, typed states, versioned procedures, adversarial verdicts, replay via re-reading — because both draw from `sdd-kit-2`.

**Substrate.** A runtime whose whole load-bearing commitment is "all state lives on the log" (kernel spec v15 §"The load-bearing commitment"). Eight primitives. One bus per run. Producers emit typed events; Views project deterministically; Predicates gate on Views; Triggers fire Producers when Predicates hold; Routes carry data forward; TerminationPolicy decides when it ends; every runtime decision is itself an event on the same log (`substrate.RunStarted`, `substrate.TriggerFired`, `substrate.InputBuildFailed`, `substrate.PredicateQuarantined`, `substrate.RunFinalised`). Ships v1.0 with three replay levels, seventeen conformance checks, nine bundled topologies, cross-run composition via `embedded_substrate`.

## The one thing under all three

`sdd-kit-2` is checked into both `/Trading System 1/sdd-kit-2/` and `/Agent Orchestration/sdd-kit-2/` (verified by directory listing). The scenario research folder does not vendor it but its practices trace to it. The kit's `grammar/PRINCIPLES.md` is the source of "vocabulary designed before code, validated at the mouth, evolved through supervised proposals." That eleven-layer discipline is the same one Cradle's `SignalVocabulary` implements at line-of-code detail and Substrate's `TopologyBuilder.producer_kind(schemas=...)` implements at type-checked runtime detail. The scenario research implements it in prose — every basket document opens with a version stamp and a "What Changed" section, every counterargument is graded `rebutted`/`open`/`partial` before the verdict resolves.

This is not shared code. It is shared discipline. The three projects are the same person's answer to "how does verifiable coordination work" applied to three different substrates: trading, general orchestration, financial scenario evaluation.

## Where each project's primitives sit

Both Cradle and Substrate offer a topology layer. Cradle's is domain-shaped; Substrate's is general. Setting them side-by-side:

| Concept | Cradle | Substrate |
|---|---|---|
| Unit of work | `Operator` subclass with `_run` and `_run_end_extras` | `Producer` — a callable `(input) -> AsyncIterable[Event]` |
| Typed event | `SignalEmitter.emit(tag, **payload)` validated against pinned vocabulary | frozen `msgspec.Struct` validated at the bus boundary |
| Coordination | Postgres tables per contract + per-Run `run_id` filter | one bus, one totally-ordered log, subscription-matching Views |
| Persistent state | `Procedure`, `AntiPattern`, `Episode`, `Run` in Postgres | derived by replay from the log; opt-in persistent bus for cross-run |
| Dispatch | fixed phase order per substrate (`ingest → decide` etc.) | Trigger fires when Predicate over Views holds |
| Termination | runner exhausts the fixture, writes `EVAL_RUN_END` | `TerminationPolicy` returns `FINALISE_RUN`/`CANCEL_OTHERS`/`PAUSE_AWAIT_INPUT`/`CONTINUE` |
| Falsification | `EvalVerdict` — three hardcoded slots for tests 7.1/7.2/7.3 (`eval_report.py` lines 90-112) | none — user builds it as an adjudicator Producer per topology |
| Failure mode | `OPERATOR_FAILED` with `exception_class`/`exception_message` (ADR-036, Sprint 6.7) | `substrate.ProducerFailed` + `substrate.ProducerEmittedInvalidEvent` on schema violation, per kernel spec §Lifecycle |
| Replay | logged captures + `cradle inspect-cell` narrative (Sprint 6.7 Task 6.7.3) | three levels — event replay always possible; schedule replay via `TriggerFired.resolved_input`; L3(a) native re-execution when `deterministic=True` on every Producer |
| Storage escape | forecasting spike raw-SQL insert to `runs` table (`runner.py` lines 240-272) | `BlobRef` payloads written write-ahead when > threshold (`sequencer.py` `_maybe_offload`) |

Cradle is what you build when the domain constrains the shape. Substrate is what you build when it does not.

## How the scenario workstream maps into Substrate

Draft 1.2 of the substrate-candidacy paper mapped the workstream into Cradle. The mapping fit — Procedure, AntiPattern, DecisionTrace, EvalVerdict were the anchors. It also predicted ~1,640 LOC and named six friction points (DecisionTrace generalization, EvalVerdict list-shape, RunORM NOT NULL, ADR-036 boilerplate, per-Run isolation, replay-runner trading coupling).

The mapping into Substrate is different. Below is the topology, in the shape of `best_of_n/__init__.py` — a callable of `TopologyBuilder` that names producer kinds, wires triggers, and sets a termination.

**Event contracts** (frozen `msgspec.Struct`, ~120 LOC total in `contracts.py`):

```python
class WorldStateLoaded(Struct, frozen=True):
    version: str                # "day_161_v2"
    evidence_count: int         # 157
    source_hash: str
    loaded_at: float

class TransmissionAsserted(Struct, frozen=True):
    world_state_version: str
    channel: str                # "OIL_PHYSICAL" | "CARRY_TRADE" | "CREDIT" | ...
    position_type: str          # "OPTION_LONG_CALL" | ...
    evidence_ids: tuple[str, ...]
    conviction: float           # [0, 1]

class ScenarioScored(Struct, frozen=True):
    scenario_tier: str          # "PARTIAL" | "FULL" | "ESCALATION" | "HYPERCRISIS" | ...
    position_id: str
    intrinsic_payoff_multiple: float
    scoring_method: str         # "black_scholes" | "path_dep_lookback" | ...

class CounterargumentEvaluated(Struct, frozen=True):
    counterargument_id: str     # "DA_17_bpc_default_prob_overstated"
    grade: str                  # "rebutted" | "open" | "partial"
    rebuttal_evidence_ids: tuple[str, ...]

class BasketVerdict(Struct, frozen=True):
    basket_version: str         # "convexity_v14"
    open_counterarguments: int
    weighted_expected_multiple: float
    finalized_at: float
```

**Producers** (~90 LOC each with the Responder seam, ~360 LOC total):

- `WorldStateLoader` — reads the Day 161 dossier from disk, hashes each source, emits `WorldStateLoaded`
- `TransmissionAsserter` — for each `(world_state, position)`, cite the physical mechanism connecting one to the other; emit one `TransmissionAsserted` per (channel, position). Deterministic if the citation set is frozen; LLM-backed if the paper is asking the model to reason about a novel channel.
- `ScenarioScorer` — deterministic. Reads `TransmissionAsserted`, computes intrinsic payoff via Black-Scholes or the leveraged-ETF path model, emits `ScenarioScored` per (scenario_tier, position).
- `AdversarialVerdicter` — one Producer instance per counterargument. Reads the Views, decides `rebutted`/`open`/`partial`, emits `CounterargumentEvaluated`. Independent-family judge, per NORTH-STAR-v5 T5's small-model orchestration horizon.

**Views** (~40 LOC, all stock):

```python
b.view("world_state", api.PerKindLatest("WorldStateLoaded"))
b.view("transmissions", api.KindBuffer("TransmissionAsserted"))
b.view("scenarios", api.KindBuffer("ScenarioScored"))
b.view("verdicts", api.KindBuffer("CounterargumentEvaluated"))
```

**Triggers** (~40 LOC):

```python
b.trigger("assert_transmission",
    subscription=api.Subscription(kinds=frozenset({"WorldStateLoaded"})),
    predicate=lambda ctx: True,
    starts="transmission_asserter",
    input_builder=lambda ctx: {"world_state": ctx.event.payload},
    policy=api.Once())

b.trigger("score_scenarios",
    subscription=api.Subscription(kinds=frozenset({"TransmissionAsserted"})),
    predicate=lambda ctx: True,
    starts="scenario_scorer",
    input_builder=lambda ctx: {"assertion": ctx.event.payload},
    policy=api.PerEvent())

b.trigger("evaluate_counterarguments",
    subscription=api.Subscription(kinds=frozenset({"ScenarioScored"})),
    predicate=lambda ctx: len(ctx.views["scenarios"].value()) >= EXPECTED_SCENARIO_COUNT,
    starts="adversarial_verdicter",
    input_builder=lambda ctx: {
        "scenarios": ctx.views["scenarios"].value(),
        "counterargument_set": FORTY_ITEM_DA_LIST,
    },
    policy=api.Once())
```

**Termination** (~5 LOC):

```python
b.termination(api.any_of(
    api.threshold_count("CounterargumentEvaluated", 40),
    api.quiescence_with_watchdog(seconds=60.0),
))
```

**Total LOC estimate: ~500** — contracts 120, four Producers 360, wiring 20 — under ADR-037's ≤500 target on the first pass, because nothing in the topology has to reinvent per-Run isolation, freshness gates, or falsification-verdict structure. Substrate does not have those problems; the log has always been per-run, subscription-matching is always by kind/producer, and the "verdict" is whatever the topology says it is (a `BasketVerdict` payload).

Compare to Draft 1.2's Cradle estimate: 1,640 LOC unmitigated, 980 LOC after four proposed Cradle-core changes. The Substrate version is 500 without proposed changes. The friction list Draft 1.2 named is the answer to why: those six items are what Substrate factored earlier.

## Where each project sits on the same axis

The three projects are not in tension. They occupy different points on one axis: **how much structure the runtime imposes.**

At one end sits the scenario workstream. Pure prose. The runtime is a human reading the docs and placing trades in Interactive Brokers. Structure lives in that human's head plus SDD's discipline layer. Fast to iterate; ambiguous; not replayable.

In the middle sits Cradle. Postgres schema, ten hard constraints, three-slot falsification verdict, sqrt-time-scaled outcome thresholds, six-component setup_key with fail-loud on fully-degraded keys. Structure is in the code. Slow to iterate; unambiguous; replayable (Sprint 2 byte-identical determinism, `test_sprint_2_byte_identical_determinism_preserved`).

At the other end sits Substrate. Eight primitives. One bus. `substrate.RunStarted` at seq 0 carries the whole topology manifest. Structure is in what the topology chooses to enforce — a topology that wants Cradle's ten hard constraints writes them as a `ConstraintProjector` Producer that emits `ConstraintFired`. A topology that wants prose-shaped iteration writes producers that emit less structured events. The runtime is opinionated about the log; it is not opinionated about what the log carries.

The axis matters because the scenario workstream is currently at the wrong end for its stage. Forty counterarguments and thirteen basket versions sit on disk. Reading them requires opening the Markdown files sequentially and holding the ablation history in memory. Substrate would let those be `WorldStateLoaded` and `CounterargumentEvaluated` events on a durable log with `substrate inspect --producer transmission_asserter --why` pointing at the exact evidence that fired each assertion. Nothing more elaborate.

Cradle is at the right end for its stage — it is the trading substrate, and trading needs the machinery. Moving trading into Substrate would delete Cradle's promotion mechanics, its Postgres persistence, its sqrt-time-scaled outcome labeling, its per-Run isolation retrofit lessons. All are load-bearing for what Cradle answers.

## What each project asks the others

**Cradle asks Substrate:** should the runtime layer (`cradle.runtime.substrate_registry`, `cradle.eval.grid_runner`, phase dispatcher, capture aggregation) migrate onto Substrate primitives while the domain layer stays? Sprint 6.7 Task 6.7.3 currently reinvents per-cell capture aggregation at `captures/grid_runs/<grid_run_id>/cells/<cell_id>.jsonl` — Substrate's bus already scopes per-run. Sprint 6.6 Task 6.6.1 spent multi-file effort retrofitting `PortfolioState` for per-Run isolation — Substrate's Producers have no shared mutable state to isolate. The 18/18 silent cells that motivated Sprint 6.6.5's hot-patch would surface differently in Substrate: `substrate.ProducerEmittedInvalidEvent` fires at the bus boundary on any schema violation (kernel spec §"validate the event"), no operator can silently return `None` without a `Verdict(passed=False)` event landing on the log first, no `output_reason` state machine is needed because every emission is either a typed event or a lifecycle failure. The ADR-036 boilerplate I quantified at ~15 LOC per operator is 0 LOC per Producer in Substrate.

**Substrate asks Cradle:** what does a domain-shaped topology look like when it has to persist state across runs beyond the persistent-bus opt-in? The kernel-spec §"Cultured-starter sessions" pattern (a `CulturedContext` Producer reading a persistent-bus View) is theoretically sufficient, but Cradle has an argument that a real domain wants named schemas for its persistent state — `Procedure`, `AntiPattern`, `Episode` as Postgres tables with content-derived IDs and per-Run isolation and `valid_from`/`valid_to` temporal columns for supersession. Substrate treats persistent state as "read the log tail on start"; Cradle treats it as "SQL query with foreign keys." Cradle has been through Sprint 4.7 memory-recovery machinery and Sprint 6.6 per-Run isolation — hard-won lessons Substrate has not yet been forced to answer because its persistent-bus feature is deferred to post-1.0 for cross-platform reasons (`README.md` line 130: "Deferred: byte-identical Level-3(b) re-execution, and the persistent bus on Windows.").

**Scenario research asks both:** where do I put my next Convexity Basket version? Right now it goes in `/Ongoing Trading Research/Convexity Baskets/Convexity_Basket_v15.md`. In Substrate, it goes in a `WorldStateLoader` update plus a `basket.evaluate_v15` topology run producing a persistent record. In Cradle (per Draft 1.2), it goes as a new `Procedure` row with `branch_id="convexity_baskets_main"`, `status="active"`, superseding v14. The prose is the fastest path to the next iteration; either code path is a step-change slower but produces an audit trail and comparable outputs across versions.

## The proposal

Three moves, ordered by dependency. Sizing is honest.

**Move 1. Run the scenario workstream as a Substrate topology first.** Do not build substrate #3 inside Cradle. The 500-LOC estimate is a bounded spike; the friction list Draft 1.2 predicted becomes the friction list the topology actually experiences (or does not); the author learns what a topology-of-the-workstream feels like before proposing to add it to a Postgres-backed framework. If the topology falls out cleanly, that is evidence for Move 3. If it hits friction Substrate cannot express, that is evidence for the Cradle path.

Deliverable: a runnable topology `basket_evaluation` bundled in `substrate/topologies/`, one committed CI record with a deterministic `TransmissionAsserter`, one gated real-model walkthrough with an LLM-backed asserter, a rendered narration.

**Move 2. Migrate Cradle's runtime layer onto Substrate — domain layer intact.** This is the operational answer to ADR-037's question about whether the trading/forecasting split factored enough. Substitute `cradle.runtime.substrate_registry` with a Substrate `TopologyBuilder`; substitute `cradle.eval.grid_runner`'s per-cell aggregation with Substrate's per-run bus; substitute the ADR-036 output-reason state machine with Substrate's bus-boundary validation. Domain layer (`substrates/trading/operators/*`, contracts, promotion logic, Postgres schema) stays. Each Cradle operator becomes a Producer whose `_run` becomes the `start` callable; each `SignalEmitter.emit` becomes a `yield SomeTypedStruct(...)`.

Sprint 7 hardening candidate. Requires Sprint 6.7 to close first (the SDD instrumentation is a prerequisite to knowing what the migration preserved). Two large risks: (a) Postgres transactions across a topology boundary need care — Substrate expects the log is the truth, Cradle expects Postgres is the truth; the reconciliation is a new design decision, not a refactor. (b) Substrate's persistent-bus mode is deferred on Windows per `README.md` line 130 — Cradle assumes Postgres persistence, so this is not blocking, but the coupling between "Substrate's persistent-bus feature" and "Cradle's Postgres tables" is the design surface.

**Move 3. Adopt Substrate as the shared runtime under both.** If Move 1 succeeds and Move 2 succeeds, the scenario topology and the trading topology are both Substrate topologies, sharing the same runtime, the same observability (`substrate inspect`, `substrate tail`, `substrate narrate`), the same replay primitives, the same composition mechanism (`embedded_substrate` — the scenario topology can be embedded as a Producer inside a trading topology that uses scenario verdicts to size positions). The forty-item Devil's Advocate becomes a general capability — any Substrate topology can carry an adversarial-verdict phase — rather than a scenario-specific one. Cradle's promotion machinery becomes a library that a Substrate topology can pull in when the domain needs Postgres-backed accumulation of `Procedure` rows.

Deliverable: unified. Not "port Cradle to Substrate" (Cradle is the domain library). "Compose Cradle's domain library inside Substrate's runtime."

## What this costs and what it buys

Costs. Move 1 is a bounded spike. Move 2 waits for Sprint 6.7 to close. Move 3 is the outcome of Moves 1 and 2, not new work. Cognitive cost: Cradle developers learn Substrate's eight primitives; Substrate learns to talk to Postgres via a domain library it does not currently need. `sdd-kit-2` — the shared spine — does not change.

Buys.

- **The scenario workstream becomes replayable and inspectable at v1 without waiting for Cradle Sprint 8.** `substrate inspect --producer transmission_asserter --why` on Day 200 answers "why did we drop META and WEAT" by pointing at the `TransmissionAsserted` event whose evidence_ids reference the Alpha-Vantage-vs-broker verification event.
- **Sprint 6.7's diagnostic surface generalizes.** `cradle inspect-cell` becomes `substrate inspect --cell`, and every substrate — trading, scenario, forecasting — gets it for free.
- **ADR-036's output-reason boilerplate goes away.** Not because Cradle abandons the discipline but because Substrate enforces it structurally: an unemitted event is quiescence; quiescence with no path to termination is `substrate.RunFinalised{reason:stuck_quiescent}` fired by the runtime guard at `runtime.py` lines 321-355. The 18/18 silent cells become the loud signal at run time, not the retrofit that motivated Sprint 6.7.
- **Cross-substrate composition arrives free.** `embedded_substrate` lets the scenario topology emit `BasketVerdict` events onto a trading topology's bus, which reads them via a `TransmissionAsserted`-shaped Route into the constraint projector — a strategy composition (per NORTH-STAR-v5 T3 named strategies) that no current architecture supports.
- **Small-model orchestration (T5) has a natural home.** Each Cradle operator that currently calls an LLM proposer (`llm_qwen_v1`) becomes a Substrate Producer against the `Responder` seam. Swapping in a small-model ensemble under an adjudicator is a topology change, not a Cradle refactor.

## Risks and where they hurt

- **Substrate's persistent bus is deferred on Windows.** Not blocking today (Cradle runs on macOS + Linux), but limits future portability.
- **Substrate is v1.0 as of `README.md`.** Nine bundled topologies with committed records; conformance suite of 17 checks. Not the same maturity as, say, a Postgres. If a topology hits a Substrate bug, the author is fixing it.
- **The reconciliation between Substrate's "log is truth" and Cradle's "Postgres is truth" is a real design decision.** Options: (a) Postgres becomes a materialized view derived from the log, updated by a persistence Producer; (b) Postgres stays authoritative and the log carries only decision records; (c) both, with a reconciliation contract. Move 2 must pick one.
- **NORTH-STAR-v5 §Risks names startup latency as the cockpit's failure mode.** Substrate topologies open fast (the writer loop is asyncio, one file per run); Cradle's decision pass is slower (Postgres round trips per operator). If Move 2 lands, the topology's wall-clock latency may drop by an order of magnitude — worth measuring on the first prototype.
- **The SDD kit is checked into both repos and could drift.** Not currently a problem (one author holds both) but is architecture debt if either project grows collaborators.

## What I recommend, in order

**1. Read this paper alongside `docs/research/02_substrate_candidate_scenario_research.md` Draft 1.2 as a paired set.** 02 is the "scenario research fits inside Cradle" paper. 03 (this) is the "or fits inside Substrate more cleanly" paper. One gets picked. The two are exclusive at implementation but complementary at analysis.

**2. Run Move 1 as a spike.** `basket_evaluation` topology in `substrate/topologies/`, CI record, walkthrough. Deliverable is the friction list: does the topology fall out at ~500 LOC, or does it hit walls that would push scope back toward Cradle?

**3. If Move 1 succeeds, add this paper to Substrate's `docs/applications/` as `applications/basket_evaluation.md`.** Substrate's product spec draft7 §Applications wants domain-shaped examples that show the primitives at work; a real financial-scenario topology is a strong addition to the applications catalogue.

**4. Defer Move 2 until Sprint 6.7 closes and Move 1 either validates or falsifies the topology approach.** Do not touch Cradle's runtime layer while Sprint 6.7 is mid-flight. The migration is an option to hold, not an action to take.

**5. Whatever happens with Moves 2 and 3, the six Cradle-core improvements from Draft 1.2 stand independently.** ADR-036 decorator, per-Run repo-method linter, `DecisionTrace` generalization, `EvalVerdict` list-shape refactor, `RunORM` NOT NULL loosening, `evidence_freshness_expired` reason code. Each has independent forecasting-spike evidence. None wait on this paper.

## Sources

Cradle (paths relative to `Trading System 1/`):
- Full grounding list in `docs/research/02_substrate_candidate_scenario_research.md` §Grounding

Substrate (paths relative to `Agent Orchestration/substrate/`):
- `README.md`, `docs/NORTH-STAR-2026-08-10-v5.md`, `docs/specs/kernel_spec/v15.md` (pages 1-800), `docs/adding-a-topology.md`
- `src/substrate/{types,protocols,constants,api}.py`
- `src/substrate/kernel/{topology,triggers,views,policies,runtime,sequencer,composition}.py`
- `src/substrate/topologies/best_of_n/{__init__.py,contracts.py}`

Scenario research (paths relative to `/Users/peterlaffey/Documents/Claude/Projects/Ongoing Trading Research/`):
- Full grounding list in `docs/research/02_substrate_candidate_scenario_research.md` §Grounding

Shared discipline:
- `sdd-kit-2/` — vendored in both `Trading System 1/` and `Agent Orchestration/`

---

*Draft 1.0. Written after reading Substrate's kernel spec v15, its `TopologyBuilder`/`Registration`/`AppendCycle`/`Runtime`/`embedded_substrate`, one reference topology (`best_of_n`) end-to-end, and the NORTH-STAR v5 that names the five themes. Companion to `docs/research/02_substrate_candidate_scenario_research.md` Draft 1.2 which mapped the same workstream into Cradle. This paper argues the workstream fits Substrate more naturally and that Cradle's runtime layer (not its domain layer) is a candidate to sit on Substrate primitives when Sprint 6.7 closes.*
