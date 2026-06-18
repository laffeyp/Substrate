# Sprint 132 — Recursive decomposition topology (planner spawning solvers spawning solvers)

---

```yaml
---
id: 132
status: pending
phase: 2
pass_kind: functional
cadence_band: auto-within-phase
---
```

---

## scope

Build `substrate.topologies.recursive_decomposition` — a planner Producer emits N subtask events; a Trigger with PerEvent firing fires N solver Producers; each solver may itself emit further subtask events that the same Trigger matches at any depth. The substrate's recursive-Triggers property (kernel Decision #17) makes this fall out without per-depth registration. Bounded by a depth-budget predicate (counts depth from `producer.parent_id` ancestry) to prevent runaway.

This is the demo that LangGraph structurally cannot do — its graph is declared statically. The TUI's `tree` mode (Sprint 120) renders this beautifully: a tree of Producers visibly growing as the run unfolds.

---

## prerequisites

- Sprint 100 closed; on the ratified top-6 list.
- Sprint 110 closed (TUI design exists; tree mode designed to render this topology).
- Runtime v1.0 ships, including recursive Triggers (Decision #17 — verified in conformance check 13 or equivalent).

---

## context_files

- `kernel_spec/v15.md` §What this enables — "Recursive decomposition" example; §The primitives §6 (Trigger) for the recursive-matching semantics.
- `kernel_spec/v15.md` §Where this points — adjacent self-modifying / meta-orchestration directions (these inform the depth-bound design but are out of scope here).
- `product_spec/draft7.md` D-17 — the arbitrary-depth Trigger decision.
- `design_spec/draft1.md` §6.4 — "Diagnosing slowness" journey (relevant: a runaway recursive Trigger is the failure mode this topology must prevent).
- `docs/application-catalogue.md` — Sprint 100's entry.
- `docs/tui-design-spec.md` §3 — tree mode design.

---

## signal contract

### Emits

- `SubtaskProposed` — emitted by planner or solver; payload: `{task: str, parent_task_id: str | None, depth: int}`.
- `SolutionReached` — emitted by solver when its subtask is solved (no further decomposition needed); payload: `{task_id: str, solution: str}`.
- `DepthBudgetExceeded` — emitted by the runtime via a typed event when the depth predicate would fire; payload: `{at_task_id: str, depth: int, budget: int}`.

Plus substrate.* lifecycle.

### Consumes

- Input event: `{root_task: str, max_depth: int}` (default `max_depth=4`).

### Invariants

- Exactly one Trigger handles all SubtaskProposed events at any depth — the same Trigger, no per-depth duplicate.
- Depth is computed from `producer.parent_id` ancestry traced back to the root planner; recorded as a field on each spawned solver's input.
- The depth-budget predicate fires `DepthBudgetExceeded` when a SubtaskProposed event would create a solver at depth > max_depth; that subtree does not spawn.
- Replay: the recursive cascade reconstructs exactly from `TriggerFired` events; conformance check 13 (divergence localization) catches any drift between two runs of the same topology with the same seed.
- CI mode uses a deterministic planner that emits a fixed-shape tree (e.g. depth 3, fan-out 2 = 14 solvers). Walkthrough mode uses a real LLM that produces a variable-shape tree.

---

## artifact contract

### Files created

- `src/substrate/topologies/recursive_decomposition.py` — the topology factory:
  - `recursive_decomposition_topology(max_depth: int = 4, walkthrough: bool = False)`.
  - Planner Producer factory: takes a root task, emits SubtaskProposed events.
  - Solver Producer factory: takes a task, either emits SolutionReached (leaf) or further SubtaskProposed events (internal node). Decision is by the LLM in walkthrough mode; by a deterministic depth-rule in CI mode.
  - The single Trigger on SubtaskProposed with `PerEvent` firing policy, `input_builder` deriving depth from ancestry, depth-budget predicate gating spawn.
  - TerminationPolicy: `quiescence-with-watchdog(180s)` — finalises when no more Producers running and no more SubtaskProposed events queued.
- `src/substrate/topologies/recursive_decomposition/prompts/planner.md` and `solver.md`.
- `src/substrate/topologies/recursive_decomposition/records/ci_mode.record/`.
- `src/substrate/topologies/recursive_decomposition/records/walkthrough.record/` + `walkthrough.txt`.
- `tests/test_recursive_decomposition_topology.py`:
  - `test_single_trigger_handles_all_depths`
  - `test_depth_budget_prevents_overflow`
  - `test_ancestry_depth_correctly_computed`
  - `test_ci_record_replays_level_2`
  - `test_walkthrough_record_replays_level_2`
  - `test_runaway_recursion_terminates_via_budget` (deliberate adversarial test: a topology with `max_depth=2` halts even if the LLM tries to recurse deeper)
- `docs/walkthroughs/recursive-decomposition.md` — user-facing; explicitly addresses the LangGraph structural impossibility.

### Files modified

- `src/substrate/topologies/__init__.py` — register `recursive_decomposition`.
- `BLACKBOARD.md` — append Sprint-132 close; surface the depth-budget UX (should `DepthBudgetExceeded` be a `substrate.*` reserved kind or an application-level one?) for ratification.

### Content assertions

- The topology declares: 2 Producer kinds (planner, solver — solver is recursive via the Trigger), 1 Trigger (recursive, PerEvent), 0 Routes (depth flows via `producer.parent_id` ancestry, not via Routes), 1 TerminationPolicy.
- The CI record at default depth=4 contains: 1 planner started + 14 solvers started + ≥1 DepthBudgetExceeded if any deeper subtask was proposed + N SolutionReached events at the leaves + 1 RunFinalised on quiescence.
- The TUI tree mode renders the spawn ancestry correctly when given the CI record (verified by a snapshot test if possible).

### Command exit codes

- `uv run pytest tests/test_recursive_decomposition_topology.py` returns 0.
- `uv run substrate replay …/ci_mode.record --level 2` returns 0 (decisions reconstructed).
- `uv run substrate replay …/walkthrough.record --level 2` returns 0.
- `uv run substrate run --topology recursive-decomposition --max-depth 2` with a deliberately overflowing input completes (does not hang) and the record contains `DepthBudgetExceeded`.

---

## done criteria

- All files exist and assertions hold.
- The walkthrough doc explicitly notes "LangGraph cannot do this because…" — honest competitive framing, not marketing.
- The TUI tree mode (Sprint 120 output) renders this topology's records correctly — verified by manual inspection AND a snapshot test if Textual snapshot testing is available.
- Conformance check 13 (divergence localization) passes against a deliberately-perturbed solver — proving recursive divergence is correctly localized by sequence.
- Rubber Duck Pass clean — the runaway-prevention is verified by READING the record (the DepthBudgetExceeded event landed at the right place), not by trusting the test name.
