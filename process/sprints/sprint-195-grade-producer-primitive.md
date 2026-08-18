# Sprint 195 — `GradeResult` event + `grade_producer_factory` (roadmap v2 S6 part 1 of 2)

Adds two primitives that Sprint 196 wires into a full solve-and-grade topology and a `LogProjectionOracle`.

## files touched

- `src/substrate/topologies/swebench_solver/records.py` — new `GradeResult(instance_id, verdict, reason)` frozen msgspec Struct per vocab v0.3 § G.6; added to `__all__`.
- `src/substrate/topologies/swebench_solver/grader.py` (new) — `grade_producer_factory(instance_id, dataset_name, model_name, run_id, report_dir, timeout_seconds, split, namespace)` returns a factory returning an async-gen producer. Producer reads `model_patch` from its sealed input, calls `run_swebench_one` via `asyncio.to_thread` (blocking subprocess wrapped for the event loop), maps `Verdict` enum → wire string, yields one `GradeResult`.

## consumer sprint (Sprint 183 primitive-plus-consumer)

Sprint 196 (roadmap v2 S6 part 2 of 2) wires this producer into a new `swebench_solve_and_grade_topology` triggered on `SelectedPatch`, terminating on `GradeResult`; adds `SwebenchLogProjectionOracle` reading `GradeResult` off the record. Card queued next.

## contracts

- 3/3 tests pass: empty-patch fast path yields one `GradeResult(verdict="fail")`; monkeypatched three-verdict mapping test proves the enum-to-wire-string mapping; export pin verifies `GradeResult` in `records.__all__`.
- Ruff clean; mypy strict clean on both new/modified source files.
- The five stderr-JSON harness events from Sprint 193 still emit at `run_swebench_one` — the record-side `GradeResult` complements them without replacing.

## design note

Producer's input is `{"model_patch": str}` — Sprint 196's trigger's `input_builder` reads `ctx.event.payload["model_patch"]` from `SelectedPatch`. Producer is `deterministic=False` in the topology registration since it makes an external subprocess call to Docker.
