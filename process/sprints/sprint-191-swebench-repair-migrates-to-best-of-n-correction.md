# Sprint 191 — `swebench_repair_topology` migrates to `best_of_n_correction` (roadmap v2 S3)

---

```yaml
---
id: 191
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Roadmap v2 S3: swebench_repair reuses the shared best-of-N + correction sub-topology instead of duplicating its wiring. `topologies/best_of_n/best_of_n_correction` grows two additive kwargs so it fits swebench's pre/post-phase shape; swebench_repair_topology replaces ~40 lines of inline drafter/validator/judge wiring with one call.

## files modified

- `src/substrate/topologies/best_of_n/__init__.py` — `best_of_n_correction` gains two kwargs (both default to the coding_flow shape; existing consumers unchanged):
  - `seed_on: str | None = None` — `None` registers seeder as `initial` (fires at run start). Set to a kind name (swebench: `"EditLocations"`) to trigger seeder on that kind's arrival (waits for the localizer's output).
  - `draft_input_extra: Callable[[TriggerContext], dict] | None = None` — when set, its returned dict merges into the draft trigger's input_builder result (swebench: builds `edit_context` from the EditLocations view).
- `src/substrate/topologies/swebench_solver/assemble.py` — `swebench_repair_topology` calls `best_of_n_correction(b, seed_on="EditLocations", draft_input_extra=..., ...)` instead of registering seeder / drafter / validator / judge / their three triggers / the verdicts view directly. Keeps the pre-loop `localizer` producer + `edit_locations` view; keeps the post-loop `selector` + `outcome` producers + their triggers; keeps its own `RepairSummary`-terminated `b.termination(...)`.

## contracts

- 19/19 targeted tests pass across `test_best_of_n`, `test_swebench_solver`, `test_swebench_repair`, `test_swebench_repair_topology_dual_mode`, `test_bundled_swebench_repair`.
- Ruff + mypy strict clean.
- CI record regenerated; still 39 events; still includes `substrate.RunStarted`, `substrate.RunFinalised`, `RepairSummary` terminal. Deterministic responder's SEARCH/REPLACE block still fails-to-apply on the fixture (fixture text "def f(x): return x" doesn't match), so the record's RepairSummary carries `NO_APPLICABLE_EDIT` outcome — same as the pre-Sprint-191 record.

## backward compat

- `best_of_n_correction`'s existing consumer (`topologies/applications/best_of_n_verified.py`) passes neither new kwarg; behavior identical.
- swebench_repair's pre/post phases (LOCALIZE + EMIT) unchanged — only the middle loop-wiring got extracted.

## why the additive kwargs

Two kwargs let the shared function fit swebench's shape without a rewrite. `seed_on` handles the pre-loop gate; `draft_input_extra` handles per-invocation input augmentation. Both defaults preserve coding_flow's shape.

The pre-Sprint-191 note in `assemble.py` said `best_of_n_correction`'s all-in-one shape "doesn't model swebench's pre/post phases." Two kwargs prove out that the modelling gap is closable additively. `code_evolution` (the third planned consumer per roadmap) can adopt the same pattern.

## done

Two files. Real reuse. ~40 lines of inline wiring absorbed into the shared sub-topology. Every existing test still passes.
