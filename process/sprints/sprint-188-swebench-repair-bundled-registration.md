# Sprint 188 — `swebench_repair` bundled-registration + CI record (roadmap v2 S2, part 2 of 2)

---

```yaml
---
id: 188
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Second half of roadmap v2 § "Sprint 2." Sprint 187 landed the dual-mode default responders; Sprint 188 registers `swebench_repair` in `topologies/bundled.py` and commits a byte-stable `records/ci_mode.record` so `substrate run --topology swebench_repair` works, `substrate demo replay swebench_repair` matches, and the topology is discoverable via `topology list`.

The tricky piece: the topology requires `base_checkout` (a git repo path). Bundled factories in `bundled.py` today are zero-arg and produce fully-configured topologies. The swebench fixture is a tmpdir'd git repo; making the bundled record byte-stable requires a deterministic on-disk path so the same input produces the same output on regeneration.

## approach

1. `topologies/swebench_solver/__init__.py` (or a new `topologies/swebench_solver/bundled.py`) gains a `swebench_repair_ci()` zero-arg factory that creates a fixture repo at a deterministic path (`/tmp/substrate-ci/swebench_repair-fixture/` or under `TMPDIR`), writes a fixed `m.py`, initializes git idempotently, and returns `swebench_repair_topology(base_checkout=..., issue=..., repo_skeleton=..., known_files=..., n=2, max_rounds=1, watchdog_seconds=5.0)` with responders defaulting to deterministic (from Sprint 187).
2. `topologies/bundled.py` gets a `swebench_repair` entry in the `BUNDLED` dict pointing to the factory.
3. `uv run python scripts/gen_topology_records.py` regenerates the record; commit `src/substrate/topologies/swebench_solver/records/ci_mode.record`.
4. Substance test at `tests/test_bundled_swebench_repair.py` asserts `substrate run --topology swebench_repair` produces a `SelectedPatch` and the CI record matches structurally.

## files touched

- `src/substrate/topologies/swebench_solver/__init__.py` (or new `bundled.py`) — the factory.
- `src/substrate/topologies/bundled.py` — registration.
- `src/substrate/topologies/swebench_solver/records/ci_mode.record` — new committed record.
- `tests/test_bundled_swebench_repair.py` — new substance test.

Three source files + one test + one record artifact. Slightly over the ≤2 sweet spot; the concept is "make the topology a first-class bundled entry," which is one concept. Sprint 188 files a "why (revised)" note in its notes section per hard rule 6's split-if-not-truly-one-concept clause.

## prerequisites

- Sprint 187 closed (dual-mode default responders).

## contract summary

Zero-arg factory returning a runnable topology. Bundled entry. Committed record. Substance test verifies `substrate run --topology swebench_repair` reaches the CLI's happy path. `demo replay swebench_repair` produces the same event sequence as `demo run swebench_repair`.

## done

`swebench_repair` runs via `substrate run --topology swebench_repair`. The topology joins the eleven other bundled topologies as a first-class citizen.
