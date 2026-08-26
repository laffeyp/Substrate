# Sprint 213 — delegate four dispatch paths + provenance

```yaml
---
id: 213
status: pending
phase: daily-driver-piece-C
pass_kind: functional
---
```

## scope

Implement the four dispatch paths in `Tool.run(a)` per TECH-SPEC §5:

1. `child_session_name` set → resolve `session_id = session_registry.by_name(name)`; call `session_registry.turn(session_id, UserMessage(text=task, ...))` in-process; block on the reviewer session's per-session lock until parked; read last FinalAnswer off the record; return `{answer, child_root, steps: -1, via: "standing_session:<name>"}`. If name unknown → `ToolResult(ok=False, error="unknown session name: <name>")`. If reviewer session ends mid-delegate → `ToolResult(ok=False, error="session_ended_mid_delegate")`.
2. `child_session_name` unset, `model` set → wrap model string into Responder via `_agent_models()` registry pattern at `server.py:118`; instantiate `_default_child_factory` from `delegate.py:130-171`; run via `_run_child_to_answer`.
3. `child_session_name` unset, `model` unset, `context` set → same-driver child with extracted slice from `parent_record_root` via `api.read_record` filtered by `context["parent_seq_range"]` and `context["kinds"]`; cap 8 KiB (§1.6.5); prefix to baseline.
4. Everything unset → existing `_default_child_factory` behavior, fresh child on parent driver.

Provenance both ways: parent's ToolResult carries `child_root`; child's `RunStarted.baseline` carries `parent_session_id` + `parent_seq_at_call` filled from constructor.

## prerequisites

- Sprint 212 closed.

## context_files

- Sprint 211-212 output.
- `substrate-ui/server.py:118` (`_agent_models`) — driver registry for path 2.
- `substrate/src/substrate/topologies/tool_loop/delegate.py:130-171` (`_default_child_factory`, `_run_child_to_answer`).
- `substrate/src/substrate/api.py` — `read_record` for path 3.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §5 four-dispatch-paths block + §1.6.5 explicit context slice cap.

## artifact contract

### Files

- `substrate/src/substrate/topologies/tool_loop/delegate.py` — grow `Tool.run` with the four-way dispatch.

### Assertions

- Path 1: `delegate(task="review this", child_session_name="reviewer")` where `reviewer` is a live registered session → child_root points at the reviewer's record; reviewer's next turn shows the delegated UserMessage.
- Path 1 failure: `child_session_name` unknown → typed ToolResult(ok=False, error contains "unknown session name").
- Path 1 race: reviewer session ends during the delegate call → typed ToolResult(ok=False, error contains "session_ended_mid_delegate").
- Path 2: `delegate(task="hi", model="claude")` spawns a child on Claude while parent stays on Kimi.
- Path 3: extracted slice ≤ 8 KiB. Post-review 2026-08-25 large-event rule: events are dropped at the event boundary, never truncated mid-event, so an event's payload survives whole or is elided whole. Iterate events in seq order; accumulate until the next event would push the running total past 8 KiB; stop; append `"... N events elided; narrow the range (M bytes)"` where N counts dropped events and M is their combined byte size. A single event larger than 8 KiB by itself is included alone (its content is what the caller asked for; truncating it silently would defeat the request) with a trailing note `"... this single event is <bytes> bytes, larger than the 8 KiB slice cap; no other events fit"`.
- Path 4: unchanged from sprint 212's backwards-compat behavior.
- Provenance: every child's `RunStarted.baseline` has `parent_session_id` + `parent_seq_at_call`. Every parent ToolResult carries `child_root`. `api.trace_ancestry` walks either direction.

### Tests

- `tests/test_delegate_per_call_child_session_name.py`
- `tests/test_delegate_per_call_model.py`
- `tests/test_delegate_per_call_context.py`
- `tests/test_delegate_per_call_baseline.py`
- `tests/test_delegate_provenance.py`
- `tests/test_delegate_session_ended_mid_delegate.py`
- `tests/test_delegate_session_queue_serialization.py` — two parents delegate to same standing session; second FIFO-blocks on the per-session lock; both complete.

## observation contract

Two-terminal test (scripted): terminal A registers `--name reviewer`; terminal B runs a session that calls `delegate(task, child_session_name="reviewer")` twice; assert both delegated turns land on the reviewer's record with correct provenance both directions; assert `trace_ancestry` walks from parent to child to parent.

## halt conditions

- `bridge_mapping_required` if a new dependency creeps in.
- `dual_contract_fail` if provenance breaks in either direction.

## definition of done

Four dispatch paths pass tests. Provenance both ways. Piece C closes. Pieces B, D, F unblock (E is independent, H depends on E).
