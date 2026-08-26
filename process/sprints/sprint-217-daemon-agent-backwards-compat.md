# Sprint 217 — /api/agent backwards-compat adapter

```yaml
---
id: 217
status: pending
phase: daily-driver-piece-B
pass_kind: functional
---
```

## scope

Rewrite the existing `/api/agent` handler at `substrate-ui/server.py:554-687` as a thin adapter over `/api/session/*`. Naming rule (post-review 2026-08-25 — "client-fingerprint" was undefined): first request under a given `?workspace=<name>` creates a session named `agent-<sha256(workspace + client_ip + first-user-agent-header)[:8]>`. `client_ip` is `self.client_address[0]` from BaseHTTPRequestHandler; `first-user-agent-header` is the request's `User-Agent` at first-request time (subsequent requests may differ; only the first sets the name). Two browsers from the same host + workspace with the same User-Agent collide by design (that IS the same client for adapter purposes). Every subsequent request under the same workspace resolves the same session name → same session, and routes to `POST /api/session/<id>/turn`. Print a one-line stderr deprecation notice at daemon start: `"[deprecated] /api/agent is a compatibility adapter over /api/session; slated for removal after v1.1"`. Piece G's UI eventually retires `/api/agent`; this bridge lets the substrate-ui web app keep working during the piece-G rewrite.

## prerequisites

- Sprint 216 closed.

## context_files

- Sprint 214-216 output.
- `substrate-ui/server.py:554-687` — the existing `_agent` handler (must not break existing web app).
- `substrate-ui/web/app.ts` (whichever module hits `/api/agent`) — for compatibility contract.

## artifact contract

### Files

- `substrate-ui/server.py` — rewrite `_agent` as an adapter. Keep the URL. Keep the response shape.

### Assertions

- Existing `substrate-ui` web app (v0.5 shape) still functions against the adapter — every `/api/agent` POST that used to work still works.
- Every `/api/agent` call now creates or reuses a session; running `substrate session ls` after a web-app session shows the `agent-*` name.
- Existing tests around `/api/agent` (whatever exists today) still pass.

### Tests

- `test_server_agent_compat_creates_session.py`
- `test_server_agent_compat_routes_second_turn.py`
- Existing `/api/agent` tests continue passing.

## observation contract

Open the substrate-ui web app; drive a two-turn agent conversation as today; verify (a) the console works, (b) `substrate session ls` shows the generated `agent-*` name, (c) daemon stderr carries the deprecation line once.

## halt conditions

- `dual_contract_fail` if the existing web app breaks — halt and preserve the compatibility contract.

## definition of done

`/api/agent` routes through the session API. Web app unaffected. Piece B closes.
