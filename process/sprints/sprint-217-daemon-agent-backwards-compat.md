# Sprint 217 — /api/agent backwards-compat adapter

```yaml
---
id: 217
status: superseded
phase: daily-driver-piece-B
pass_kind: functional
---
```

## superseded by sprint 223e (2026-08-28)

The `/api/agent` compat bridge shipped as sprint 223e (piece-B gap-fill
batch) with a simpler naming rule than this card proposed. 223e uses
the `?session=<name>` query param as the find-or-create key rather than
`sha256(workspace + client_ip + first-user-agent-header)[:8]` — a bare
name is clearer to callers, matches every other endpoint's session-name
resolution, and drops the client-fingerprint dependency this card
carried the review deferral note about. `?legacy=true` opts into the
pre-bridge shape for one release; unregistered callers get 503 per
sprint 224d.

Test lives at `substrate-ui/tests/test_server_agent_compat.py`, per
TECH-SPEC §7 line 700. The daemon prints no stderr deprecation notice
today; that landed as `deprecated: true` on the legacy-shape response
body instead of stderr — a machine-readable signal is more useful to
the piece-G UI rewrite than a boot-time console line.

Original scope below, kept for the audit trail.

---

## scope (original — not what shipped)

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
