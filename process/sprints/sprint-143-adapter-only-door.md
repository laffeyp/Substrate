# Sprint 143 — Adapter is the only door

---

```yaml
---
id: 143
status: pending
phase: swebench-close-the-loop
cadence_band: auto-within-phase
pass_kind: functional
---
```

---

## why (revised after reading the code)

`docs/swebench-assay-roadmap.md:24, 31, 53` says the firewall lives at the Adapter and every arm consumes Adapter output. `docs/swebench-solver-design.md:44` calls the firewall structural. Reading the real code, that door is already MOSTLY closed: `prepare_swebench_case` (in `assay/swebench_suite.py:64`, not `swebench.py` as my earlier review guessed) already firewall-checks the raw instance, raises on fail, clones the repo, discovers regression modules, and hands the solver a typed payload via `Case.payload`. The topology builders (`swebench_solver_topology`, `swebench_repair_topology`) do NOT take a raw instance dict — they take typed kwargs (`base_checkout`, `known_files`, `runner`, `regression_command`, etc.) already downstream of the Adapter. The real "second door" is script-level: `scripts/assay_full_run.py` bypasses the harness and stitches the payload by hand. That door is killed in Sprint 144.

What Sprint 143 adds is defense-in-depth around the door that already exists:
1. A typed exception (`FirewallViolation`) instead of a bare `ValueError` so a bypass surfaces categorically, not stringily.
2. A `TypedDict` for `Case.payload` (`PreparedPayload`) so mypy refuses a hand-rolled dict at the topology-consumer boundary — no runtime cost, but a mypy wall that catches a future second-door attempt at check time.

## the seam

The generic `Case.payload` is `dict[str, Any]` by the harness contract; the SWE-bench payload has a specific shape (`base_checkout`, `repo_skeleton`, `known_files`, `regression_files`, `exclude`, `spec`, `passed_at_base`, `image`, `issue` — enumerated at swebench_suite.py:92-102). Type it with a `TypedDict` in `swebench_suite.py`; keep the runtime dict semantics (no msgspec Struct — the harness passes payloads through as opaque dicts). `solver_topology_from_payload` takes `PreparedPayload` instead of `dict[str, Any]`. Any future callsite building a payload by hand fails mypy unless it constructs a `PreparedPayload`.

## scope

- Add `class FirewallViolation(ValueError)` in `src/substrate/assay/swebench.py`; change `prepare_swebench_case` (in `swebench_suite.py`) to raise `FirewallViolation` on failure.
- Add `class PreparedPayload(TypedDict)` in `swebench_suite.py`; annotate `prepare_swebench_case` return + `solver_topology_from_payload`'s payload argument.
- Update existing tests that assert on `ValueError` to catch `FirewallViolation` (`FirewallViolation` IS-A `ValueError`, so most catches keep working; explicit assertions get tightened).

## signal contract

### Emits

No new events.

### Invariants

- `swebench_repair_topology.build(...)` mypy-refuses a raw `dict` in place of `PreparedCase`.
- `prepare_swebench_case` remains the only function in the tree that constructs a `PreparedCase`.
- `firewall_check` is called inside `prepare_swebench_case` and its failure raises — no `firewall_clean=False` `PreparedCase` can exist.

## artifact contract

### Files modified

- `src/substrate/assay/swebench.py` — add `PreparedCase`, change `prepare_swebench_case` to return it.
- `src/substrate/topologies/swebench_solver/assemble.py` — both topology builders take `case: PreparedCase`.
- `src/substrate/assay/swebench_matrix.py` — pass `PreparedCase`.
- `src/substrate/assay/swebench_suite.py` — pass `PreparedCase`.
- `tests/test_assay_swebench.py`, `tests/test_swebench_solver.py`, `tests/test_assay_swebench_agent.py`, `tests/test_assay_swebench_matrix.py`, `tests/test_assay_swebench_workspace.py`, `tests/test_assay_swebench_host.py`, `tests/test_assay_swebench_suite.py` — updated to construct via the Adapter.

### Content assertions

- `PreparedCase` is a frozen msgspec Struct.
- No caller of the topology builders passes a raw instance dict.

### Command exit codes

- `uv run python -m pytest tests/test_assay_swebench.py tests/test_swebench_solver.py tests/test_assay_swebench_matrix.py tests/test_assay_swebench_host.py tests/test_assay_swebench_workspace.py tests/test_assay_swebench_suite.py -q` → 0
- `uv run mypy src/substrate/assay/swebench.py src/substrate/topologies/swebench_solver/assemble.py` → 0
- `uv run ruff check src/substrate/assay src/substrate/topologies/swebench_solver` → 0
- `PATH="$PWD/.venv/bin:$PATH" uv run python -m pytest -q` → 0 (full suite)

## observation contract

`pass_kind: functional`. Behavior change: the topology builders refuse a raw dict.

### Input fixture

- Attempting `swebench_repair_topology(instance=raw_dict, ...)` raises `TypeError` (or is a mypy error at check time).
- `prepare_swebench_case(leaky_instance)` raises `FirewallViolation` before a `PreparedCase` is returned; the topology never sees it.
- Round-trip: a valid instance → `prepare_swebench_case` → `PreparedCase` → topology.build → runs green on the smoke slice.
