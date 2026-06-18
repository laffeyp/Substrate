# Sprint 131 — Pair coding topology (driver + navigator concurrent from t=0)

---

```yaml
---
id: 131
status: pending
phase: 2
pass_kind: functional
cadence_band: auto-within-phase
---
```

---

## scope

Build `substrate.topologies.pair_coding` — a driver Producer that streams code while a navigator Producer subscribed to a View of the driver's buffer emits typed suggestions. A Route stages suggestions for the driver's next chunked instantiation, so the driver "learns" from the navigator across instantiations. This is the user-named "software ritual" — the topology that makes the kernel's concurrent-streaming + route-into-future-instantiation pattern visible.

The honest constraint from the kernel: routes stage into the *next* instantiation, not into a running Producer. So the driver runs in chunked instantiations (one chunk per file or per function), with navigator suggestions accumulated and routed into the next chunk's input. That's not human pair-coding's continuous live feel, but it's what LLMs actually allow given that context is bound at instantiation time. The walkthrough doc must say this honestly.

---

## prerequisites

- Sprint 100 closed; on the ratified top-6 list.
- Sprint 110 closed (TUI design exists so this topology's record renders well).
- Runtime v1.0 ships (all primitives + composition + replay).

---

## context_files

- `kernel_spec/v15.md` §What this enables — "Pair coding" example.
- `kernel_spec/v15.md` §The primitives §7 (Route) and §The primitives §1 (Producer input immutability) — the constraints that force chunked instantiation.
- `product_spec/draft7.md` §0.1 — the worked example (the row-translation pipeline) has the same retry-with-context shape this topology uses.
- `design_spec/draft1.md` §6.4 (pair coding journey) and §4.5 (Routes API).
- `docs/application-catalogue.md` — Sprint 100's entry.
- `docs/tui-design-spec.md` — for rendering considerations (two streams running concurrently).
- `src/substrate/topologies/code_review.py` (Sprint 130 output) — for the Producer-factory pattern to follow.

---

## signal contract

### Emits

- `CodeChunk` — emitted by the driver; payload: `{file_path: str, text: str, chunk_index: int}`.
- `Suggestion` — emitted by the navigator; payload: `{file_path: str, anchor_seq: int, rationale: str, suggested_text: str | None}`.
- `ChunkBoundary` — emitted by the driver when a meaningful unit (function, class, file) is complete; payload: `{file_path: str, kind: Literal["function", "class", "file"]}`.

Plus the substrate.* lifecycle events.

### Consumes

- Input event: `{task: str, file_paths: tuple[str, ...]}`.

### Invariants

- Navigator's subscription is to the buffer View of the driver's `CodeChunk` events only. It does NOT subscribe to its own emissions (no self-feedback).
- Routes stage navigator Suggestions for the driver's NEXT instantiation, never for the running one (per kernel input-immutability).
- The driver runs in chunked instantiations fired by a Trigger on `ChunkBoundary`. The Trigger's `input_builder` reads any staged Suggestions for that file path and includes them in the next chunk's prompt.
- Replay determinism: in CI mode, both Producers are deterministic stand-ins (canned chunks + canned suggestions); the record replays Level 2 (every decision reconstructed). Level-3(b) byte-identity is deferred post-v1.0 (amendment A1.1).
- Walkthrough mode uses two local model instances (could be the same model, different system prompts — driver writes, navigator reviews).

---

## artifact contract

### Files created

- `src/substrate/topologies/pair_coding.py` — the topology factory:
  - `pair_coding_topology(task: str, walkthrough: bool = False)` returns a topology function.
  - Driver Producer factory: in walkthrough mode, an OpenAI-compat streaming call; in CI mode, replays canned chunks.
  - Navigator Producer factory: subscribed to the driver's `CodeChunk` View; emits Suggestions at each ChunkBoundary the driver signals.
  - The Trigger that fires the driver's next chunk reads staged Suggestions via the `staged` dict in its `input_builder`.
  - TerminationPolicy: `all-completed()` (driver and navigator both complete) or `quiescence-with-watchdog(120s)`.
- `src/substrate/topologies/pair_coding/prompts/driver.md` and `navigator.md` — plain-text system prompts.
- `src/substrate/topologies/pair_coding/records/ci_mode.record/` — committed CI-mode record.
- `src/substrate/topologies/pair_coding/records/walkthrough.record/` — committed walkthrough-mode record + `walkthrough.txt` narration.
- `tests/test_pair_coding_topology.py`:
  - `test_suggestion_reaches_next_chunk_input` (the Route staging + Trigger input_builder verified by reading the record)
  - `test_navigator_does_not_subscribe_to_self` (subscription correctness)
  - `test_chunked_instantiation_count` (driver fires once per ChunkBoundary; no over-firing)
  - `test_ci_record_replays_level_2`
  - `test_walkthrough_record_replays_level_2`
- `docs/walkthroughs/pair-coding.md` — user-facing walkthrough; explicitly addresses the "chunked, not continuous" honesty.

### Files modified

- `src/substrate/topologies/__init__.py` — register `pair_coding`.
- `BLACKBOARD.md` — append Sprint-131 close; surface the honesty-of-chunking point for documentation review.

### Content assertions

- The topology declares: 2 Producer kinds (driver, navigator) + 2 Triggers (one fires the navigator on `CodeChunk`, one fires the next driver chunk on `ChunkBoundary`) + 1 Route (Suggestion → driver's next-chunk input slot) + 1 TerminationPolicy.
- The CI record contains: ≥2 CodeChunk events, ≥1 Suggestion event between them, ≥1 InjectionApplied event recording the Suggestion's staging into the next driver chunk's input.
- The walkthrough record validates the same shape with real LLM-emitted content.

### Command exit codes

- `uv run pytest tests/test_pair_coding_topology.py` returns 0.
- `uv run substrate replay src/substrate/topologies/pair_coding/records/ci_mode.record --level 2` returns 0 (every decision reconstructed).
- `uv run substrate replay src/substrate/topologies/pair_coding/records/walkthrough.record --level 2` returns 0.

---

## done criteria

- All files in the artifact contract exist and pass their assertions.
- The walkthrough doc honestly states the chunked-instantiation constraint (not live pair coding; chunked pair coding).
- The CI record demonstrably shows InjectionApplied between Suggestion and next CodeChunk — verified by reading the record back, not by trusting the test name.
- Conformance suite still passes.
- Rubber Duck Pass clean.
