# Sprint 213a — delegate dispatch paths 2, 3, 4 + provenance (substrate side)

```yaml
---
id: 213a
status: closed
phase: daily-driver-piece-C
pass_kind: functional
---
```

## scope

Split out of sprint 213 during dispatch. The original card mixed four dispatch paths + provenance + 7 test files across two repos (substrate + substrate-ui). Rule 6 (≤2 files / one concept) says split. Sprint 213a lands the substrate-side paths that don't need substrate-ui integration: path 2 (different-driver child), path 3 (same-driver child with context slice), path 4 (fresh child, unchanged from sprint 212 backwards-compat plus baseline override). Provenance rides on every child's `substrate.RunStarted.baseline`. Path 1 (standing session via `child_session_name`) raises a typed deferral `ValueError` naming sprint 213b; the tool_loop machinery surfaces the raise as `ToolResult(ok=False, error=...)` to the model.

Sprint 213b wires substrate-ui `SessionRegistry.turn()` (a new method sprint 211 did not ship) and the path 1 seam in `delegate.py`. Two additional tests (`test_delegate_session_ended_mid_delegate.py`, `test_delegate_session_queue_serialization.py`) land there.

## prerequisites

- Sprint 212 closed (delegate parses per-call args; six-property schema with `x-args-passthrough`).
- Sprint 211 closed (SessionRegistry basic surface).

## context_files

- Sprint 212 output: `substrate/src/substrate/topologies/tool_loop/delegate.py` (constructor + args parse).
- `substrate/src/substrate/topologies/tool_loop/delegate.py:130-171` — `_default_child_factory`, `_run_child_to_answer`.
- `substrate/src/substrate/kernel/topology.py:376` — `TopologyBuilder.baseline(**metadata)`.
- `substrate/src/substrate/api.py` — `read_record` for context slice.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §5 four-dispatch-paths block + §1.6.5 8 KiB slice cap.

## artifact contract

### Files

- `substrate/src/substrate/topologies/tool_loop/delegate.py` — grow constructor with `model_resolver` kwarg; grow `Tool.run` with the four-way dispatch (path 1 stubs); add `_default_model_resolver`, `_extract_context_slice`, `_format_context_event`, `_prefix_context_slice`, `_with_baseline`.

### Assertions

- **Path 2 (model swap):** `delegate(task, model="deterministic")` resolves to `DeterministicResponder` via `_default_model_resolver`, rebuilds the child_factory, runs the child. Return shape includes `via="different_driver:<name>"`. Unknown model → typed `ValueError`.
- **Path 3 (context slice):** `delegate(task, context={parent_seq_range, kinds})` reads `parent_record_root`, filters events, caps at 8 KiB with event-boundary drops per the post-review 2026-08-25 large-event rule. Single event > 8 KiB → included alone with note. Return shape includes `via="context_slice"`.
- **Path 4 (fresh child):** No per-call args (bare string or dict without model/context/child_session_name) → existing behavior. Return shape stays `{answer, child_root, steps}` — no `via` field, preserving sprint 212's backwards-compat contract.
- **Path 1 (standing session):** `delegate(task, child_session_name=...)` raises `ValueError("... sprint 213b lands SessionRegistry.turn() ...")`. tool_loop turns it into `ToolResult(ok=False, error=...)`.
- **Baseline override:** per-call `baseline={...}` merges into child's `TopologyBuilder.baseline()` via `_with_baseline` wrapper. Non-dict baseline treated as absent.
- **Provenance:** `parent_session_id` (constructor kwarg) + `parent_seq_at_call` (computed at call time as `len(list(read_record(parent_record_root))) - 1`) both land in child's baseline. Per-call baseline cannot spoof provenance keys (provenance takes precedence in the merge).

### Tests

- `tests/test_delegate_per_call_model.py` — 6 cases: default resolver deterministic/ollama mapping, per-call swap, unknown model failure, fallback resolver, bare-string still omits via.
- `tests/test_delegate_per_call_context.py` — 9 cases: filter by seq range, filter by kinds, boundary drop, single oversize event, empty slice, prefix wraps task, empty slice returns task unchanged, end-to-end slice reaches child.
- `tests/test_delegate_per_call_baseline.py` — 6 cases: per-call baseline lands, bare task empty baseline, non-dict ignored, constructor provenance lands, `parent_seq_at_call` reads parent tail, per-call and provenance merge with provenance winning.
- `tests/test_delegate_provenance.py` — 5 cases: parent ToolResult cites child; child baseline carries `parent_session_id`; child baseline carries `parent_seq_at_call`; delegate without provenance omits keys; child_root re-readable via `api.read_record`.
- `tests/test_delegate_per_call_child_session_name.py` — 2 cases: path 1 raises `ValueError` naming `child_session_name`; error message names sprint 213b.

### Command exit codes

- `uv run python -m pytest tests/test_delegate_*.py -q` exits 0 (50 passed).
- Full-suite regression clean.
- Ruff + mypy strict clean.

## observation contract

Sprint 213a discharges the record-level contract for paths 2/3/4 + provenance. The `via` field on the parent ToolResult names which path fired; the child's `substrate.RunStarted.baseline` carries the provenance for `api.trace_ancestry`. Sprint 213b's two-terminal observation contract (parent + reviewer sessions across `child_session_name`) waits on the substrate-ui SessionRegistry.turn() wiring.

## halt conditions

- `substrate_primitive_missing` — path 1's SessionRegistry.turn() is the deferred piece; the raise is honest.
- `dual_contract_fail` if provenance breaks in either direction.

## definition of done

Paths 2, 3, 4 + baseline override + both-way provenance wired and tested. Path 1 defers cleanly. Sprint 213b (substrate-ui SessionRegistry.turn + path 1 seam + 2 tests) may dispatch on this landing.
