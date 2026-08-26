# Sprint 214 — daemon /api/session/* core (create, turn, events, list)

```yaml
---
id: 214
status: split-into-214a-and-214b
phase: daily-driver-piece-B
pass_kind: architecture
---
```

## scope

Add core `/api/session/*` handlers to `substrate-ui/server.py`. Endpoints: `POST /api/session` (create — reads body per TECH-SPEC §4 shape; delegates to `SessionRegistry.create` from sprint 211; returns `{session_id, name?, record, workspace_shape}`), `POST /api/session/<id>/turn` (calls `Runtime.resume` inside the session's `asyncio.Lock`; blocks until pause; returns `{seq, status, final_seq?}`), `GET /api/session/<id>/events?since_seq=N` (SSE via `api.attach(record_root).follow(until_finalised=True)`), `GET /api/session` (lists live + parked from registry), `GET /api/session/by-name/<name>` (resolves name), `DELETE /api/session/<id>` (tears down: cancels running turn, seals record, removes manifest, unregisters name).

## prerequisites

- Sprint 211 closed (registry lives).
- Sprint 210 closed (session topology lands).

## context_files

- Sprint 211 output: `substrate-ui/session_registry.py`.
- Sprint 205-210 output: session topology.
- `substrate-ui/server.py:472-491` — existing endpoint routing pattern (`/api/launch`, `/api/agent`, `/api/resume`, `/api/build`).
- `substrate-ui/server.py:_agent_models`, `_launches`, threading patterns for reference.
- `substrate/src/substrate/api.py` — `Runtime`, `attach`, `LiveRecord`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §4 (endpoint list, request/response shapes).

## artifact contract

### Files

- `substrate-ui/server.py` — six new handler methods routed under `/api/session/*`.
- `substrate-ui/tests/test_server_session_*.py` — one test file per endpoint.

### Assertions

- `POST /api/session {driver: "deterministic"}` returns 200 with `session_id`, `record`, `workspace_shape ∈ {"flat","worktree","isolate"}`.
- `POST /api/session/<id>/turn {text: "hi"}` returns 200 with `status ∈ {"paused","running","finalised","failed"}` after Runtime.resume completes.
- `GET /api/session/<id>/events` streams SSE frames as new events land; disconnects gracefully on client close.
- `GET /api/session` returns `{live: [...], parked: [...]}`.
- `GET /api/session/by-name/reviewer` returns `{session_id: "s_..."}` or 404.
- `DELETE /api/session/<id>` returns 204; subsequent `/turn` returns 410.
- Two concurrent POST /turn on the same session serialize on the per-session `asyncio.Lock`.

### Tests

- `test_server_session_create.py`, `test_server_session_turn.py`, `test_server_session_sse.py`, `test_server_session_list.py`, `test_server_session_by_name.py`, `test_server_session_delete.py`, `test_server_session_lock_serialises.py`.

## observation contract

Spawn the daemon in a subprocess. Create session, send two turns, verify SSE streams the new events during each `Runtime.resume` call. Kill the daemon between turns; restart; second turn still succeeds.

## halt conditions

- `bridge_mapping_required` if SSE support requires a new dependency (should be doable with stdlib `http.server`).

## definition of done

Six endpoints live. Concurrency contract honored. Sprint 215 (SessionEndRequested + PATCH + interrupt + shutdown) can dispatch.
