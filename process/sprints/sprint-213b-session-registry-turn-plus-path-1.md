# Sprint 213b — SessionRegistry.turn_sync + delegate path 1 wiring

```yaml
---
id: 213b
status: closed
phase: daily-driver-piece-C
pass_kind: functional
---
```

## scope

Second half of the sprint-213 split. Sprint 213a wired delegate paths 2/3/4 substrate-side. Sprint 213b adds:

  1. `SessionRegistry.turn_sync(session_id, resume_event, *, timeout_seconds)` in `substrate-ui/session_registry.py`. Runs one turn against a standing session synchronously from tool_loop's worker thread — NOT from the daemon's asyncio loop. Serializes on a per-session `threading.Lock`. Rebuilds the session's topology via an injected `session_topology_factory: Callable[[SessionManifest], Callable[[api.TopologyBuilder], None]]`. Returns `(final_manifest, record_root)`.
  2. `SessionEndedMidTurn` typed exception + `_run_resume_sync` worker-thread helper (mirrors delegate's `_run_child_to_answer`).
  3. Delegate path 1 wiring in `substrate/src/substrate/topologies/tool_loop/delegate.py`. `child_session_name` set → resolve via `session_registry.by_name`; call `session_registry.turn_sync(sid, UserMessage(text=task, ...))`; read the tail `FinalAnswer` off the reviewer's record; return `{answer, child_root, steps: -1, via: "standing_session:<name>"}`.
  4. Typed failure paths: unknown name → `ValueError("unknown session name: <name>")`; session ended mid-delegate → `ValueError("session_ended_mid_delegate")`.
  5. `SessionRegistry.__init__` gains a `session_topology_factory` kwarg (defaults None; tests without turn_sync pass None; the daemon injects one at boot in sprint 214).

## prerequisites

- Sprint 213a closed (`1714a56`).
- Sprint 211 closed (SessionRegistry basic surface).

## artifact contract

### Files

- `substrate-ui/session_registry.py` — add `SessionEndedMidTurn`, `SessionTopologyFactory`, `turn_sync`, `_run_resume_sync`; grow `__init__` with `session_topology_factory` kwarg; add per-session `threading.Lock` map.
- `substrate/src/substrate/topologies/tool_loop/delegate.py` — replace the sprint-213a path 1 stub with the real dispatch: `by_name` → `turn_sync` → tail-FinalAnswer read; typed error mapping.
- `substrate-ui/tests/test_delegate_via_standing_session.py` — end-to-end delegate → reviewer → tail-FinalAnswer + concurrent FIFO.
- `substrate-ui/tests/test_delegate_session_ended_mid_delegate.py` — ended session, unknown name, registry-without-factory typed failures.
- `substrate/tests/test_delegate_per_call_child_session_name.py` — updated: error string now names `session_registry`, not sprint 213b's "deferred" text.

### Assertions

- **Path 1 end-to-end.** `delegate(task, child_session_name="reviewer")` where a reviewer session is registered + first-turn-opened runs a second turn on the reviewer's record. UserMessage lands with `slash_source="delegate"`. Parent's ToolResult carries `via="standing_session:reviewer"`, `steps=-1`, `child_root` pointing at the reviewer's record, `answer` matching the reviewer's tail FinalAnswer text.
- **Concurrent FIFO.** Two parent threads delegating to the same reviewer both complete; the reviewer's record ends with all UserMessages in seq order; no exception.
- **Ended session.** Reviewer with `status="ended"` → `turn_sync` raises `SessionEndedMidTurn`; delegate wraps as `ValueError("session_ended_mid_delegate: ...")`.
- **Unknown name.** `by_name` returns None → `ValueError("unknown session name: <name>")`.
- **No factory.** Registry constructed without `session_topology_factory` → `turn_sync` raises `RuntimeError` naming the omitted seam.

### Command exit codes

- `uv run python -m pytest ../substrate-ui/tests/test_delegate_via_standing_session.py ../substrate-ui/tests/test_delegate_session_ended_mid_delegate.py tests/test_delegate_per_call_child_session_name.py -q` exits 0 (8 passed).
- Substrate-side full-suite regression clean.
- Ruff + mypy strict clean.

## observation contract

Sprint 213 as carded named a two-terminal test (parent + reviewer terminals across the shipped CLI). The CLI arrives with pieces D (sprints 218-222); the deferred piece of the observation contract lives there. Sprint 213b discharges the record-level contract in-process: end-to-end path-1 test drives a real reviewer session via `Runtime.resume`, delegate calls into it through `turn_sync`, reviewer's record grows, parent reads the tail — the whole chain.

## halt conditions

- `substrate_primitive_missing` — none. This closes the sprint 213a-surfaced gap.
- `dual_contract_fail` if the reviewer's record does not carry the delegated UserMessage with `slash_source="delegate"`.

## definition of done

Path 1 wired end-to-end. Typed failures for ended / unknown / no-factory. Concurrent FIFO test passes. Piece C closes on this landing (registry + manifest + boot scan + delegate four paths + provenance + turn_sync all shipped). Sprint 214 (daemon session API core) may dispatch on this landing.
