# Sprint 226 — substrate toolkit: run_topology + run_topology_poll

```yaml
---
id: 226
status: pending
phase: daily-driver-piece-F
pass_kind: architecture
---
```

## scope

Author `substrate/src/substrate/topologies/tool_loop/substrate_tools.py`. Two tools:

- `make_run_topology(daemon_client) -> Tool` — the tool's `run(a)` reads `{name, inputs, bundle?, baseline?, context?, await_completion=true, timeout_seconds?}` from `a[0]` dict; calls `daemon_client.run_topology(...)` which POSTs `/api/topology/<name>/run` OR — same-daemon in-process — dispatches directly. `baseline=` merges into the child topology's `TopologyBuilder.baseline` (`topology.py:376`). `await_completion=false` returns `{run_id, record_root, status: "running"}` immediately. Returns `{output, child_root, run_id}` on completion.
- `make_run_topology_poll(daemon_client) -> Tool` — the tool's `run(a)` reads `{run_id}`; calls `daemon_client.topology_status(run_id)`; returns `{status, record_root, output?, elapsed_seconds}`.

Both tools carry their JSON schema on `Tool.schema` (per `tools.py:64`), visible to `ollama_tools`.

## prerequisites

- Sprint 210 closed (piece A).
- Sprint 214 closed (daemon has `/api/topology/*/run`).

## context_files

- `substrate/src/substrate/topologies/tool_loop/delegate.py` — reference for tool-that-spawns-a-run.
- `substrate/src/substrate/kernel/runtime.py:707-726` — `finalisation_payload` shape for `output`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §8 (tool table + progressive-disclosure gradient).

## artifact contract

### Files

- `substrate/src/substrate/topologies/tool_loop/substrate_tools.py` — new.

### Assertions

- `run_topology("code_review", inputs={repo: "/tmp/x"})` from inside a session spawns a child record; ToolResult carries `output` (Verdict) + `child_root` + `run_id`.
- `run_topology("code_review", inputs={...}, await_completion=false)` returns `{run_id, record_root, status:"running"}` in under 100ms.
- `run_topology_poll(run_id)` returns the current status; `status` transitions running → finalised.
- `baseline=` merges into the child topology's `TopologyBuilder.baseline` call.

### Tests

- `test_run_topology_tool.py`
- `test_run_topology_baseline_merges.py`
- `test_run_topology_await_false.py`
- `test_run_topology_poll.py`

## observation contract

Session model calls `run_topology("code_review", inputs={repo: "."}, await_completion=true)`; the child record's Verdict flows back into the session's ToolResult. `run_topology_poll(...)` on a still-running child returns `status:"running"`.

## halt conditions

- `bridge_mapping_required` if a new HTTP-client dep is needed (should be existing patterns).

## definition of done

Two tools work + schema declared. Sprint 227 (inspect_record) can dispatch.
