# Sprint 228 — substrate toolkit: list_records / list_topologies / list_applications / list_sessions

```yaml
---
id: 228
status: pending
phase: daily-driver-piece-F
pass_kind: functional
---
```

## scope

Four small read-only tool wrappers in `substrate_tools.py`:

- `make_list_records(records_root) -> Tool` — walks `~/.substrate/sessions/*/manifest.json` + `runs/`; filters by `{status?, since_ts?, topology?, session_name?, limit=20}`; returns newest-first list; one line per record.
- `make_list_topologies() -> Tool` — enumerates `topologies.bundled.names()` + any `api.register_topology`-added at runtime.
- `make_list_applications(app_registry) -> Tool` — returns `_APPLICATIONS` dict from piece E's registry.
- `make_list_sessions(session_registry) -> Tool` — returns live + parked from piece C's registry.

All four carry `Tool.schema` and are folded into `session_topology`'s tool suite alongside `full_suite` and `delegate` (§8 composition).

## prerequisites

- Sprint 227 closed.
- Sprint 223 closed (application registry).
- Sprint 211 closed (session registry).

## context_files

- Sprint 226-227 output.
- Sprint 211 output (SessionRegistry).
- Sprint 223 output (`load_manifests`).
- `substrate/src/substrate/topologies/bundled.py:names` — for `list_topologies`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §8 (four list-tools rows).

## artifact contract

### Files

- `substrate/src/substrate/topologies/tool_loop/substrate_tools.py` — four `make_list_*` functions.
- `substrate/src/substrate/topologies/session/__init__.py` — grow `session_topology`'s tool composition to include the eight substrate tools + `full_suite(workspace)` + `delegate`.

### Assertions

- `list_records()` returns at most 20 records by default, newest first.
- `list_topologies()` returns the BUNDLED names + any runtime registrations.
- `list_applications()` returns the four+ shipped app names from piece E.
- `list_sessions()` returns `{live: [...], parked: [...]}`.
- Session-topology tool suite composition includes all seven substrate tools (`delegate`, `run_topology`, `run_topology_poll`, `inspect_record`, `list_records`, `list_topologies`, `list_applications`, `list_sessions`) alongside `full_suite`.

### Tests

- `test_list_records_shape.py`
- `test_list_topologies_from_bundled.py`
- `test_list_applications_from_registry.py`
- `test_list_sessions_live_and_parked.py`
- `test_session_tool_suite_composition.py` — full session opens with all 16 tools registered (8 substrate + 8 file/shell).

## observation contract

Session with the full tool suite; model calls each list tool once; asserts each ToolResult carries the expected shape.

## halt conditions

- `dual_contract_fail` if any tool schema drifts from the actual return shape.

## definition of done

Four list tools work. Session topology composes the full toolkit. Piece F closes.
