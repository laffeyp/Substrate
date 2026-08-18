# Proposal — Cradle-on-Substrate under SDD

**Date:** 2026-08-12
**Status:** Draft 1.0 — architecture proposal
**Companion papers:**
- `docs/research/02_substrate_candidate_scenario_research.md` (Draft 1.2) — scenario substrate candidacy inside Cradle
- `docs/research/03_three_way_intersection.md` (Draft 1.0) — the three-way analysis this proposal acts on

---

## What this proposes

One runtime, one vocabulary discipline, one persistence rule. Substrate is the runtime under everything. SDD kit-2 is the vocabulary discipline for every producer_kind on every topology. A `cradle-domain` Python library holds the parts of Cradle that were never runtime — the Pydantic contracts, the sqrt-time-scaled outcome thresholds, the ten hard constraints, the promotion mechanics, the content-derived ID helpers, the six-component setup_key with fail-loud on fully-degraded keys. Three topologies sit on top: `basket_evaluation`, `trading_intraday`, `forecasting`. Postgres persists what needs to outlive a run, written by a `PostgresProjector` Producer whose only input is the bus.

Four decisions that decide everything else. Two pilots that de-risk the rest. A migration sequence. One retirement.

## The four decisions

**Decision 1. The log is truth. Postgres is a projection.** Cradle currently treats Postgres as authoritative; the SDD capture is derived. Substrate's kernel spec v15 §"The load-bearing commitment" says the opposite: all state lives on the log, sealed inputs and content-hashed IDs make it so. The reconciliation cannot be split — pick one. This proposal picks the log. A `PostgresProjector` Producer subscribes to every persisted-contract event kind (`ProcedurePromoted`, `AntipatternPromoted`, `EpisodeRecorded`, `PositionOpened`, `PositionClosed`) and writes the corresponding row. Postgres becomes a materialized view — dropped and rebuilt from the log without loss. Cross-run queries hit Postgres for speed; correctness reconstruction reads the log.

Why this way. Sprint 6.6 Task 6.6.1's PortfolioState multi-file per-Run isolation retrofit exists because Postgres was authoritative and a single row was read globally. Substrate's per-run bus makes the isolation structural — no `run_id` filter is needed on any read, because Producers only see their own run's events unless the persistent-bus mode is opted in. Move this way and the retrofit disappears; keep Postgres authoritative and the retrofit repeats every time a new operator lands.

**Decision 2. Cradle's runtime layer retires. Its domain layer becomes a library.** `cradle.runtime.substrate_registry`, `cradle.eval.grid_runner`, `cradle.eval.verdict_composer` (the driving), `cradle.eval.report_renderer`, `cradle.sdd.capture` — all sunset. `cradle.substrates.trading.operators.*`, `cradle.contracts.*`, `cradle.substrates.trading.contracts.*`, `cradle.eval.verdict_composer` (the pure logic), the sqrt-time-scaled outcome thresholds (`_outcome_labeling.py`), the six-component setup_key construction (`_setup_key_construction.py`), the content-derived ID helper (`_derive_memory_id` from `retrospective_compressor.py` lines 112-131) — all promoted to a standalone `cradle-domain` package. The domain code is Cradle's real invention; the runtime code is what Substrate already ships.

**Decision 3. SDD kit-2 is a versioned Python package, imported by both projects.** Currently vendored into `/Trading System 1/sdd-kit-2/` and `/Agent Orchestration/sdd-kit-2/` as separate copies. Publish it as `sdd-kit==2.x` on internal PyPI (or as a git submodule if PyPI is not ready). Both projects import from one source. The eleven-layer PRINCIPLES doc becomes an authoring guide referenced from `substrate/CONTRIBUTING.md` and `cradle-domain/README.md`.

**Decision 4. Every Cradle operator becomes a Substrate Producer against a Responder seam.** Concrete rule: an operator's `_run` body becomes the `start` async callable; `self._emit.emit(TAG, **payload)` becomes `yield SomeTypedStruct(...)`; `_run_end_extras` disappears (Substrate emits `substrate.ProducerCompleted` with latency in the envelope). The ADR-036 `output_count`/`output_reason` state machine (Sprint 6.7 Task 6.7.1, ~15 LOC per operator) deletes — a Producer that yields nothing is quiescence, and quiescence with no path to termination fires `substrate.RunFinalised{reason:stuck_quiescent}` via the runtime guard at `substrate/kernel/runtime.py` lines 321-355.

## The layer stack

Three layers, drawn plainly.

**Layer 1: Substrate runtime.** `substrate-kernel` on PyPI, v1.0. Nothing changes. Nine primitives (Producer, Event, Bus, View, Predicate, Trigger, Route, TerminationPolicy, run record). Seventeen conformance checks. Three replay levels. The `Runtime` class at `substrate/kernel/runtime.py` (777 LOC), the `AppendCycle` at `substrate/kernel/sequencer.py` (427 LOC), and `embedded_substrate` at `substrate/kernel/composition.py` (236 LOC) are the whole runtime surface Cradle uses.

**Layer 2: `cradle-domain` library.** Pure Python, no runtime dependencies beyond `substrate-kernel` and `sdd-kit`. Contents:

- `cradle_domain.contracts` — every Pydantic model in `cradle/contracts/` and `cradle/substrates/trading/contracts/` promoted to frozen `msgspec.Struct` for Substrate compatibility. Two shapes ship in parallel during migration: a Pydantic shape (Cradle-compatible) and a msgspec shape (Substrate-compatible). Post-migration, drop the Pydantic shape.
- `cradle_domain.outcome_labeling` — sqrt-time-scaled thresholds, cold-start fallback, triple-barrier label. Pure functions. Lifts from `substrates/trading/operators/_outcome_labeling.py` (491 LOC) unchanged.
- `cradle_domain.constraint_rules` — the ten hard constraints in fixed order, `CONSTRAINT_NAMES` drift assertion, pure-Python helpers. Lifts from `substrates/trading/operators/_constraint_rules.py`.
- `cradle_domain.setup_key` — six-component construction with fail-loud on fully-degraded keys. Lifts from `_setup_key_construction.py` (198 LOC).
- `cradle_domain.compression` — content-derived ID helper (SHA-256 of setup_key + sorted episode_ids), promotion direction classifier, outcome distribution, demotion sweep. Lifts from `retrospective_compressor.py` (559 LOC) minus the Substrate-shaped orchestration.
- `cradle_domain.verdict` — amended ADR-031 test logic. Trading substrate's verdict composer produces a list of `TestResult` (per Draft 1.2's proposal to refactor `EvalVerdict` list-shaped). Scenario substrate's produces its own list of forty. The pure logic is shared.
- `cradle_domain.freshness` — the composer's freshness-gate pattern generalized. A `FreshnessGate(kind, max_age)` returns a Predicate closure. Reused across substrates with different time scales.
- `cradle_domain.persistence.postgres_projector` — the `PostgresProjector` Producer factory. Takes a mapping `{event_kind: (SqlAlchemyModel, transform_fn)}` and returns a Substrate Producer that writes each matching event to Postgres. Idempotent by primary key (content-derived IDs make re-runs safe).

Total `cradle-domain` LOC estimate: ~3,500. Roughly 40% of Cradle's current 8,389 LOC in `substrates/trading/operators/`. The other 60% is orchestration code that Substrate absorbs.

**Layer 3: topologies.** Each is a `topology(b: TopologyBuilder) -> None` factory. Three ship:

- `basket_evaluation` — the scenario workstream. ~500 LOC per Draft 1.0 intersection paper. Four producer_kinds (WorldStateLoader, TransmissionAsserter, ScenarioScorer, AdversarialVerdicter), five typed event kinds, four Views (all stock KindBuffer / PerKindLatest), three Triggers, one TerminationPolicy. No Postgres.
- `trading_intraday` — the Cradle trading substrate. ~2,500 LOC estimated (see below). Eleven producer_kinds mirroring the current operator surface, thirty-two typed event kinds mirroring the current `trading_v0` vocabulary, seven Views (KindBuffer for price/news/portfolio, KindCount for episodes, custom View for BootstrapState cache), fifteen Triggers, TerminationPolicy = fixture-exhaustion. Postgres persistence via `PostgresProjector` subscribed to twelve persisted kinds.
- `forecasting` — the existing spike. ~600 LOC estimated (current 887, minus what the runtime absorbs). Two producer_kinds, four event kinds, two Triggers.

## The two pilots

**Pilot 1: `basket_evaluation`.** Runs during Sprint 6.7 in parallel — does not compete for Cradle developer attention.

Deliverable:
- `substrate/topologies/basket_evaluation/{__init__.py, contracts.py}` — the topology as described in the intersection paper §"How the scenario workstream maps into Substrate"
- One committed CI record produced by a `DeterministicResponder`-backed `TransmissionAsserter`
- One gated real-model walkthrough with an `OllamaResponder`-backed asserter (`llama3.2:1b` or similar)
- Rendered narration output showing the pipeline: `WorldStateLoaded → TransmissionAsserted × N → ScenarioScored × M → CounterargumentEvaluated × 40 → BasketVerdict`

Success criterion: the topology falls out at 400-600 LOC, matches the intersection paper's estimate. Failure criterion: it hits walls Substrate cannot express, and the wall list becomes the input to Pilot 2 sizing.

No Cradle coupling — the pilot runs entirely inside the `substrate/` repo.

**Pilot 2: `trading_intraday` decision-window slice.** Starts after Sprint 6.7 closes.

Deliverable:
- Extract `cradle-domain` v0.1 with the four modules the pilot needs (`outcome_labeling`, `constraint_rules`, `setup_key`, `contracts`)
- `substrate/topologies/trading_intraday/decision_window.py` — a Substrate topology that reimplements one Cradle decision window: news arrives, composer fires, memory analogizer fires, proposer fires, constraint projector fires, executor fires or rejects
- The pilot uses in-memory storage only (no PostgresProjector yet); assert-only integration test against a synthetic fixture
- Byte-identical determinism test against `q1_2025_baseline_oneday` fixture — same input, same events on the bus, same final decision as Cradle produces today

Success criterion: the pilot fires the six operators in the same order, with the same intermediate state, producing the same final decision for at least one fixture symbol. LOC estimate holds within 25%. Failure criterion: the topology cannot express something Cradle's runner does (e.g., a phase-ordering constraint that Substrate's Predicate model does not capture), and the finding becomes an ADR ruling for how to close it.

Work: reads Cradle's `decision_pass.py` and the six operators once, drops the operators as Producers, writes the topology, runs the determinism test.

## The event vocabulary

SDD kit-2 discipline says the vocabulary is designed before the code. For `trading_intraday`, the vocabulary is Cradle's current `trading_v0` — thirty-two tags in `signals/versions/trading_v0.json`. The migration is mechanical: each tag becomes a frozen `msgspec.Struct` named the same. Payload fields become Struct fields with the same names and types.

Concrete example. Cradle's current `JOINT_SETUP_COMPOSED` emit at `joint_state_composer.py` lines 409-417:

```python
self._emit.emit(
    "JOINT_SETUP_COMPOSED",
    symbol=joint_setup.symbol,
    joint_setup_id=joint_setup.id,
    setup_class=joint_setup.setup_class,
    horizon_bias=joint_setup.horizon_bias,
    confidence=joint_setup.confidence,
    setup_key=joint_setup.setup_key,
)
```

Becomes:

```python
class JointSetupComposed(Struct, frozen=True):
    symbol: str
    joint_setup_id: str
    setup_class: str
    horizon_bias: str
    confidence: float
    setup_key: str

# in the topology:
b.producer_kind("joint_state_composer",
                schemas=[JointSetupComposed, CompositionDeferred],
                schema_version=1,
                factory=composer_factory,
                deterministic=True)

# in the composer's start callable:
yield JointSetupComposed(
    symbol=joint_setup.symbol,
    joint_setup_id=joint_setup.id,
    setup_class=joint_setup.setup_class,
    horizon_bias=joint_setup.horizon_bias,
    confidence=joint_setup.confidence,
    setup_key=joint_setup.setup_key,
)
```

Validation moves from Cradle's runtime `SignalValidator` (per-tag payload extras allowlist) to Substrate's bus-boundary check (per-kind msgspec schema). A schema violation becomes `substrate.ProducerEmittedInvalidEvent` on the log, not a silent skip. The ADR-036 `output_reason` state machine is unnecessary — the frame is either a valid `JointSetupComposed` or a valid `CompositionDeferred` or a `ProducerEmittedInvalidEvent`, and each is a citable event.

Reserved-namespace guard: Substrate refuses any event kind starting with `substrate.` (`substrate/kernel/topology.py` lines 123-127). Cradle's `substrate.RunStarted`/`substrate.RunFinalised` collision — Cradle has no such tag, but any future Cradle tag beginning with `substrate` will trip the guard. Not an issue today.

## The four topologies' Producer surface

`basket_evaluation` — 4 Producers. All shown in the intersection paper.

`trading_intraday` — 11 Producers, one per current operator:

| Producer | Current Cradle file | Deterministic? | Responder-backed? |
|---|---|---|---|
| `price_state_encoder` | `price_state_encoder.py` (572) | yes | no |
| `news_state_encoder` | `news_state_encoder.py` (361) | yes | via FinBERT `Responder` |
| `market_context_builder` | `market_context_builder.py` (215) | yes | no |
| `joint_state_composer` | `joint_state_composer.py` (439) | yes | no |
| `memory_analogizer` | `memory_analogizer.py` (180) | yes | no |
| `proposal_generator_rule_v1` | `proposal_generator/rule_v1.py` (396) | yes | no |
| `proposal_generator_llm_qwen_v1` | `proposal_generator/llm_qwen_v1.py` (786) | no (LLM) | yes — `OllamaResponder` |
| `constraint_projector` | `constraint_projector.py` (372) | yes | no |
| `paper_executor` | `paper_executor.py` (740) | yes | no |
| `outcome_assimilator` | `outcome_assimilator.py` (657) | yes | no |
| `retrospective_compressor` | `retrospective_compressor.py` (559) | yes | no |

Plus:
- `postgres_projector` — writes twelve persisted event kinds to Postgres (Procedures, Antipatterns, Episodes, JointSetups, CandidateTrades, ConstraintResults, PriceStates, NewsStates, MarketContexts, PortfolioStates, BootstrapStates, Runs)
- `bootstrap_loader` — one-shot initial Producer, reads BootstrapState from Postgres at run start, emits `BootstrapLoaded` events per symbol

Total: 13 Producers. The `postgres_projector` and `bootstrap_loader` are the runtime-boundary Producers; the other eleven are pure domain-code Producers importing `cradle-domain`.

`forecasting` — 2-3 Producers. Same as the current spike, simplified.

## Persistence — how `PostgresProjector` works

Concrete design. The Producer takes a mapping at construction time:

```python
POSTGRES_PROJECTIONS: dict[str, tuple[type, Callable[[Any], Any]]] = {
    "ProcedurePromoted": (ProcedureORM, procedure_from_event),
    "AntipatternPromoted": (AntipatternORM, antipattern_from_event),
    "EpisodeRecorded": (EpisodeORM, episode_from_event),
    "JointSetupComposed": (JointSetupORM, joint_setup_from_event),
    "CandidateTradeGenerated": (CandidateTradeORM, candidate_trade_from_event),
    "ConstraintProjectionCompleted": (ConstraintResultORM, constraint_result_from_event),
    "PriceStateEncoded": (PriceStateORM, price_state_from_event),
    "NewsStateEncoded": (NewsStateORM, news_state_from_event),
    "MarketContextRefreshed": (MarketContextORM, market_context_from_event),
    "PortfolioStateChanged": (PortfolioStateORM, portfolio_state_from_event),
    "BootstrapStateLoaded": (BootstrapStateORM, bootstrap_state_from_event),
    "RunStarted": (RunORM, run_from_event),
}

def postgres_projector_factory(session_factory, projections=POSTGRES_PROJECTIONS):
    async def project(input):
        # Subscribed to every kind in projections via topology-level trigger.
        # Each invocation persists exactly one event to exactly one row.
        event = input["event"]
        orm_cls, transform = projections[event.kind]
        row = transform(event.payload)
        async with session_factory() as session:
            await session.merge(row)  # merge = upsert by PK; idempotent
            await session.commit()
        yield PostgresRowPersisted(kind=event.kind, id=row.id)
    return lambda: project
```

Wired via a topology-level Trigger per kind:

```python
for event_kind in POSTGRES_PROJECTIONS:
    b.trigger(f"persist_{event_kind}",
        subscription=api.Subscription(kinds=frozenset({event_kind})),
        predicate=lambda ctx: True,
        starts="postgres_projector",
        input_builder=lambda ctx: {"event": ctx.event},
        policy=api.PerEvent())
```

`session.merge` on a row with a content-derived primary key (`retrospective_compressor._derive_memory_id`) is idempotent — re-running the topology against the same log produces the same rows. Sprint 4.7's memory-recovery machinery becomes: read the log, project into Postgres, done. No `valid_from`/`valid_to` retrofit needed — the log is the temporal record.

Failure mode. If Postgres is down, the projector Producer raises. Substrate records one `substrate.ProducerFailed` per failed event. A per-cell retry Trigger (kernel spec §"Retry pattern") fires the projector again with the same input, up to N attempts, then escalates via `pause_await_input` with a typed resume condition `"postgres_recovered"`. The run pauses; when Postgres recovers, an external event fires the resume Trigger.

This is superior to the current path: Cradle's operators write to Postgres inline; a Postgres outage crashes the operator; the outage's mid-transaction rows may leave the DB inconsistent. Substrate's model: the log is complete, the projection is best-effort, the pause is loud.

## Cross-substrate composition — how scenario feeds trading

`substrate/kernel/composition.py` (236 LOC) implements `embedded_substrate`. The pattern:

```python
# In trading_intraday topology:
from cradle_domain.topologies import basket_evaluation

class ScenarioSizingInput(Struct, frozen=True):
    basket_version: str
    weighted_expected_multiple: float
    open_counterarguments: int
    finalized_at: float

b.producer_kind("scenario_evaluator",
    schemas=[ScenarioSizingInput],
    schema_version=1,
    start=embedded_substrate(
        topology=basket_evaluation,
        exports={"BasketVerdict": (ScenarioSizingInput, verdict_to_sizing_input)},
    ))

b.trigger("run_scenario_at_session_start",
    subscription=api.Subscription(kinds=frozenset({"SessionInitialized"})),
    predicate=lambda ctx: True,
    starts="scenario_evaluator",
    input_builder=lambda ctx: {"inner_root": f"./scenario_runs/{ctx.event.payload['session_id']}"},
    policy=api.Once())

# Downstream: the constraint projector reads ctx.staged["scenario_sizing"]
# via a Route:
b.route("stage_scenario_sizing",
    subscription=api.Subscription(kinds=frozenset({"ScenarioSizingInput"})),
    slot="scenario_sizing",
    transform=lambda event: event.payload)
```

Trading session starts → scenario topology runs as an inner Substrate → its `BasketVerdict` translates to a `ScenarioSizingInput` on the outer bus → the constraint projector reads it via the `scenario_sizing` slot and adjusts `max_position_size_pct` per the basket verdict's expected multiple. The inner run's full record is at `./scenario_runs/{session_id}/` — completely inspectable, replayable, cited from the outer bus via `substrate.TriggerFired.resolved_input.inner_root`.

No current architecture allows this. Cradle's substrates cannot compose (ADR-037 partitions them; there is no boundary translator). The Substrate `embedded_substrate` primitive is exactly the boundary translator, complete with the boundary-schema validation (`_maybe_offload`, blob storage), the inner-run failure surfacing as one outer `ProducerFailed` carrying `inner_run_id`, and the per-frame provenance via the inner root recorded in `TriggerFired.resolved_input`.

## The migration sequence

Ordered by dependency, not by clock. Each sprint depends on the prior one landing; sizing is by shape of deliverable, not by wall-clock time.

**Sprint 6.7 (in flight).** Complete SDD instrumentation. Substrate work happens in parallel — Pilot 1 (basket_evaluation topology). Zero Cradle change. Deliverable: Sprint 6.7 acceptance tests pass; `basket_evaluation` topology exists and runs.

**Sprint 7.** Extract `cradle-domain` v0.1. Move `_outcome_labeling.py`, `_constraint_rules.py`, `_setup_key_construction.py`, `_compression_logic.py`, and every contract from `substrates/trading/contracts/` into a new `cradle-domain/` sibling package. Two shapes ship in parallel: Pydantic (Cradle's current import path unchanged) and msgspec (Substrate-compatible). Both dispatch to the same pure functions. Run every existing Cradle test — must pass.

**Sprint 7.5.** Build `PostgresProjector` Producer + its integration test. Run against a Substrate topology that emits a `TestProcedurePromoted` event; assert one row lands in `procedures` table; re-run the topology; assert no duplicate row (idempotency via `session.merge`). Deliverable: `cradle-domain/persistence/postgres_projector.py` (~250 LOC) with unit + integration tests.

**Sprint 8.** Port `trading_intraday` decision window — Pilot 2. Reads `cradle-domain` primitives, wires them as Substrate Producers, uses `PostgresProjector` for persistence. Runs against `q1_2025_baseline_oneday` fixture. Byte-identical determinism test passes. Deliverable: `substrate/topologies/trading_intraday/decision_window.py` (~1,500 LOC), one committed CI record, the determinism test in `substrate/tests/`.

**Sprint 8.5.** Port the compressor and outcome assimilator. These are the promotion machinery. Wire them as separate Substrate topologies (`trading_compression`, `trading_outcome_labeling`) or as additional Producers in `trading_intraday` depending on Pilot 2's finding on topology size. Deliverable: `trading_intraday` handles the full decision-window + outcome-labeling + compression cycle.

**Sprint 9.** Port `forecasting`. The spike is already close to Substrate's shape — the port is mostly rewiring the two operators as Producers, dropping the raw-SQL escape hatch (replaced by `PostgresProjector`), and running the mini-grid as parallel Producer instances. Deliverable: `substrate/topologies/forecasting/` runs the current spike's fixture and produces the same numeric output.

**Sprint 9.5.** Cross-substrate composition: wire `basket_evaluation` as an embedded Producer inside `trading_intraday`. Run one full session with scenario sizing feeding the constraint projector. Deliverable: `trading_intraday` topology with scenario embedding, one committed CI record, an integration test showing the constraint projector's `max_position_size_pct` responds to the embedded basket's `weighted_expected_multiple`.

**Sprint 10.** Retire `cradle.runtime.substrate_registry`, `cradle.eval.grid_runner`, `cradle.eval.verdict_composer` (driving only; pure logic moved to `cradle-domain`), `cradle.eval.report_renderer`, `cradle.sdd.capture`. Delete `signals/versions/*.json` — replaced by per-topology msgspec schema registration. Every test still passes because the pure logic is unchanged; only the orchestration changes. Deliverable: `cradle` shrinks from ~15,000 LOC to ~2,000 LOC (the Postgres schema + migration history + the CLI wrapper that dispatches to Substrate topologies).

**Sprint 10.5.** Integration testing. Run the full Sprint 6.7 acceptance test suite against the new Substrate-backed implementation. Every ADR-031 test passes. Sprint 2 byte-identical determinism preserved on `q1_2025_baseline_oneday`. Every ADR (001, 009, 011, 020, 021, 023, 024, 031 amended, 034, 035, 036, 037) still holds by construction. Deliverable: green matrix.

Sprint 6.7 must close first; Pilot 1 runs in parallel with 6.7 so it does not sit on the critical path.

## The SDD discipline — how it lands across both projects

SDD kit-2's `grammar/PRINCIPLES.md` names eleven layers:

1. Vocabulary designed before code
2. Validated at the speaker's mouth
3. Versioned per-namespace
4. Semantic contracts declared, not inferred
5. Migration proposals through supervised review
6. Payload extras through validator-extras pattern
7. Reserved namespaces protected
8. Emission auditable per operator
9. Failure typed, never swallowed
10. Determinism declared per producer
11. Replay validated per level

Cradle currently implements 1-10 via its `SignalVocabulary` + `SignalValidator` + `SignalEmitter` triad. Substrate implements 1, 2, 3, 4, 7, 9, 10, 11 via `msgspec.Struct` frozen + `producer_kind(schemas=..., schema_version=1, deterministic=True)` + `ProducerEmittedInvalidEvent` + `substrate.*` reserved prefix + the three-level replay contract. Layers 5 (migration proposals) and 6 (payload extras) become authoring conventions rather than code-enforced.

Rule that lands SDD across both: **every producer_kind in every Substrate topology declares its full event-schema set at registration; every field on every Struct is typed; every schema is versioned; and any payload extension bumps `schema_version` and requires a new committed CI record.** This is stricter than Cradle's current validator-extras pattern — under Cradle, `output_reason` can be added as an extra on `OPERATOR_RUN_END` without a version bump because the validator ignores unknown fields. Under Substrate, an unknown field on a frozen Struct raises at deserialization. This is the right tightening: the Sprint 6.6.5 18/18 silent cells trace ultimately to Cradle's tolerance of payload-shape drift; Substrate's frozen-Struct discipline eliminates it structurally.

## What testing looks like

Substrate ships 17 conformance checks in `substrate/src/substrate/conformance/`. They validate the runtime — the append cycle, the bus, replay levels, admission backpressure, the reentrancy guard.

`cradle-domain` adds a property-test suite for the domain invariants:

- Six-component setup_key: any fully-degraded key raises; any partially-degraded key succeeds; token order is stable across permutations of the input dict
- Sqrt-time-scaled thresholds: for symbols with ATR ∈ [10, 1000] bps and windows ∈ [5, 60] minutes, the win/loss threshold scales as √(window/390) × N_win × ATR
- Content-derived IDs: `_derive_memory_id(setup_key, source_episode_ids)` is stable under permutation of `source_episode_ids`, deterministic across Python versions
- Ten hard constraints: `CONSTRAINT_NAMES` tuple order matches the canonical list; each constraint's helper returns a `ConstraintCheck` shape; a constraint that would raise on missing input returns `ConstraintCheck.pass(details="not_applicable")` for out-of-scope actions

Each topology adds an integration-test file that runs the topology against a synthetic fixture and asserts the final events on the bus. `basket_evaluation` asserts `BasketVerdict.open_counterarguments == 3` (matching the current Devil's Advocate three-open-item state). `trading_intraday` asserts byte-identical determinism against `q1_2025_baseline_oneday`.

One test runner: `pytest` at the workspace root. Both `substrate/tests/` and `cradle-domain/tests/` run in the same invocation. Sprint 10.5 gates the migration on green matrix across Python 3.12/3.13/3.14 per Substrate's current CI matrix (`README.md` line 133).

## What each project keeps and what each retires

**Substrate keeps everything.** No proposed changes to `substrate-kernel`. The proposal uses only currently-shipping primitives. If the pilot surfaces a missing primitive, that's a Substrate issue filed against v1.1, not a blocker for the migration.

**Cradle keeps its Postgres schema, its migration history, and its CLI.** The schema stays because it is the projection target for `PostgresProjector`; the migration history stays because existing Cradle deployments need continuity; the CLI stays as a wrapper that dispatches to `substrate run --topology trading_intraday --fixture <name>`.

**Cradle retires: `cradle.runtime.*`, `cradle.eval.grid_runner`, `cradle.eval.report_renderer`, `cradle.sdd.capture`, `signals/versions/*.json`, most of `cradle.substrates.trading.operators.*` (the orchestration; the pure logic moves to `cradle-domain`).**

**`cradle-domain` is new. It is what Cradle's real contribution was all along.**

## Payoff

Some risk of Substrate v1.0 bugs that need fixing at the `substrate-kernel` level.

- Scenario research becomes replayable and inspectable at v1 without waiting for Cradle Sprint 8 or 9. `substrate inspect --producer transmission_asserter --why` answers "why did we drop META and WEAT" by pointing at the exact `TransmissionAsserted` event.
- Sprint 6.7's ADR-036 output-reason state machine deletes. Not because Cradle abandoned the discipline — because Substrate enforces it structurally. -60 LOC across four operators; -N LOC across all future operators.
- Sprint 6.6's per-Run isolation retrofit becomes historical. Substrate's per-run bus is structural. Future operators that write state get isolation free.
- Sprint 6.7's per-cell capture aggregation (`captures/grid_runs/<grid_run_id>/cells/<cell_id>.jsonl`) becomes one committed record per Substrate run. No aggregation code.
- The `EvalVerdict` three-slot refactor happens by consequence — each topology composes its own verdict as a Struct with whatever fields it needs.
- The `RunORM` NOT NULL escape hatch that the forecasting spike relies on disappears. Every field is either Struct-required or absent.
- Cross-substrate composition arrives free via `embedded_substrate`. Scenario feeds trading. Trading feeds forecasting. Any combination.
- Small-model orchestration (NORTH-STAR-v5 T5) has a natural home. Every LLM Producer sits on the `Responder` seam. Swapping in a small-model ensemble under an adjudicator is a topology change, one file, no runtime edit.
- The three projects converge on one runtime, one vocabulary discipline, one persistence rule. Total LOC across the three projects post-migration: substantially less than the sum today. Cradle shrinks from ~15,000 to ~2,000; `cradle-domain` is new ~3,500; three topologies total ~3,600. Grand total ~9,100 vs. Cradle-today's ~15,000 + Substrate-today's ~10,000 + scenario-today's ~0-of-runtime = ~25,000. Substrate stays put.

## Open questions

- **Substrate's persistent-bus mode on Windows is deferred (README.md line 130).** Cradle production runs on macOS/Linux, so not blocking, but limits future portability if the team ever wants Windows.
- **The LLM proposer's streaming events (partial JSON tokens under Outlines) vs. Substrate's per-emission credit gate.** A Producer that yields 200 partial tokens against an admission bound of 1024 fits fine, but the pattern may be worth surfacing as an ADR — do we emit one `PartialTokenReceived` per token, or buffer in the Producer and emit one `CandidateTradeGenerated` at the end?
- **Compressor semantics: one Substrate run per `run_batch` invocation, or one long-lived run with a Trigger firing the compressor on schedule?** Both are expressible. Preference is per-invocation runs so each compression has its own committed record, per SDD kit-2's replay-per-run discipline.
- **The `sdd-kit-2` versioning story.** Publish as internal PyPI package, or git submodule, or vendored (current state)? Publish preferred; git submodule tolerable; vendored is what happens if no decision is made. Decide before Sprint 7.
- **Substrate is v1.0.** Nine bundled topologies, seventeen conformance checks. Not the same maturity as Postgres. If a topology hits a Substrate bug, the author is fixing it.

## What I recommend

**1. Ratify the four decisions.** They are the load-bearing choices. Every downstream item follows.

**2. Run Pilot 1 (basket_evaluation) in parallel with Sprint 6.7.** No Cradle risk. Bounded spike. Answers the "does the topology fall out at 500 LOC" question empirically.

**3. Wait for Sprint 6.7 to close before starting Sprint 7 (cradle-domain extraction).** The instrumentation work is prerequisite context.

**4. If Pilot 2 hits a wall, stop and re-scope.** Sprint 8's determinism test is the go/no-go gate. If Cradle's decision window cannot express as a Substrate topology while producing byte-identical output on the fixture, the migration path needs a rethink.

**5. Adopt this proposal, or reject it, before committing to Sprint 7 work.** Half-adoption — "extract cradle-domain but keep the Cradle runtime" — is the worst outcome. Two runtimes to maintain, twice the coupling surface. Full adoption or none.

## Sources

Cradle (paths relative to `Trading System 1/`):
- Full grounding list in `docs/research/02_substrate_candidate_scenario_research.md` §Grounding + `docs/research/03_three_way_intersection.md` §Grounding

Substrate (paths relative to `Agent Orchestration/substrate/`):
- Full grounding list in `docs/research/03_three_way_intersection.md` §Grounding

Scenario research (paths relative to `Ongoing Trading Research/`):
- Full grounding list in `docs/research/02_substrate_candidate_scenario_research.md` §Grounding

Shared discipline:
- `sdd-kit-2/grammar/PRINCIPLES.md` — the eleven-layer vocabulary discipline that governs both current runtimes and this proposal's unified runtime.

---

*Draft 1.0. Written after reading Cradle's operator surface end-to-end (Draft 1.2 grounding), Substrate's kernel spec v15 + reference topology + kernel source (Draft 1.0 intersection grounding), and this proposal's own four decisions and migration sequence. Companion to Drafts 1.2 (scenario-in-Cradle mapping) and 1.0 intersection (three-way analysis). This proposal is the action-plan version — every decision is stated, every migration sprint is named, every open question is enumerated. It asks for a yes/no on the four decisions and a yes/no on Pilot 1; the rest follows.*
