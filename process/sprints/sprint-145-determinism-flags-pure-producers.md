# Sprint 145 — deterministic=True on pure producers

---

```yaml
---
id: 145
status: pending
phase: swebench-close-the-loop
cadence_band: auto-within-phase
pass_kind: functional
---
```

---

## why

`topologies/swebench_solver/assemble.py` declares every producer `deterministic=False`. Four of them — `applier`, `validator`, `judge`, `selector` — are pure functions of the log. The applier's own docstring at applier.py:17 claims determinism. Consequence today: the entire solver is L1-unreplayable and every event must be re-derived (L2). Fix is one line per producer; unlocks L1 replay for the non-model portion.

## the seam

The `Producer(deterministic=...)` flag governs replay class. Model calls (`localizer`, `drafter`, `repro_gen`) stay `deterministic=False` — they run models. Test-execution seams (`validator` when it runs Docker, `select_exec`/`select_docker`) stay `deterministic=False` — they run external processes. What flips: the pure post-processing producers whose entire input is the record and whose entire output is derivable from that record.

Read carefully before flipping — the current `validator` (repair.py:88) clones `base_checkout` per candidate and runs `git apply`; that's I/O, not pure. It stays `False`. The pure candidates are:
- `applier` — pure text splice given a diff (applier.py). Model-independent given inputs.
- `judge` — reads verdicts, decides Solved/Exhausted. Pure over the record.
- `selector` — reads TestResults, picks a patch. Pure over the record.

`validator` runs subprocess; leave alone. Re-inspect each candidate's actual body before flipping.

## scope

Flip `deterministic=True` on `applier`, `judge`, `selector` in `topologies/swebench_solver/assemble.py`. Re-inspect `validator` and confirm it stays `False` (documented in the sprint's close entry). Regenerate any committed solver record if the currency gate flags it.

## signal contract

### Emits

No new events. Existing kinds; existing payloads.

### Invariants

- `applier`, `judge`, `selector` declared `deterministic=True`.
- `validator` remains `deterministic=False` (subprocess).
- Currency gate (`test_committed_record_is_current`) green after the flip.

## artifact contract

### Files modified

- `src/substrate/topologies/swebench_solver/assemble.py` — three flag flips.
- Regenerated committed records if the currency gate demands.

### Content assertions

- The three named producers carry `deterministic=True` in their `producer_kind(...)` construction.
- Any committed solver record regenerates byte-identically (`test_committed_record_is_current`).

### Command exit codes

- `uv run python -m pytest tests/test_swebench_solver.py tests/test_committed_records.py -q` → 0
- `uv run mypy src/substrate/topologies/swebench_solver/assemble.py` → 0
- `uv run ruff check src/substrate/topologies/swebench_solver` → 0
- `PATH="$PWD/.venv/bin:$PATH" uv run python -m pytest -q` → 0 (full suite)

## observation contract

`pass_kind: functional`. Behavior change: three producers now claim L1 determinism.

### Input fixture

- Run the deterministic solver smoke record twice; the two records diff to zero.
- The three flipped producers appear in the record's `RunStarted.topology` manifest with `deterministic=true`.
