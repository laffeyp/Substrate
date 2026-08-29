# Sprint 235 — server.py hygiene split into handler modules

```yaml
---
id: 235
status: pending
phase: hygiene
pass_kind: architecture
---
```

## scope

REVIEW-2026-08-28 Q2 flagged `substrate-ui/server.py` at 2,608 lines,
one HTTP-handler class carrying every endpoint. Six handlers averaging
128 lines each. Nine copies of the `if _SESSION_REGISTRY is None:
self._error(503, …); return` prelude. Twenty-seven `except Exception`
sites. The dispatcher is a chain of nine `if path.startswith(...)
return` branches. Every cross-cutting concern (auth, JSON parse, error
shape, registry-availability guard) copied per handler.

Split into a handler package with a routing table:

- `substrate-ui/handlers/__init__.py` — exports the dispatch table.
- `substrate-ui/handlers/session.py` — create, turn, end, patch, delete,
  interrupt, events, list, by_name. ~500 lines.
- `substrate-ui/handlers/topology.py` — run (both one-shot + composite
  dispatch), status. ~250 lines.
- `substrate-ui/handlers/agent.py` — the legacy compat bridge. ~250 lines.
- `substrate-ui/handlers/system.py` — launch, resume, validate, build,
  clear_runs. ~300 lines.
- `substrate-ui/http.py` — the base `Handler` class + `_json`, `_error`,
  `_read_json_body`, `_poll_record_until`, `_origin_ok`,
  `_require_registry` middleware. ~200 lines.
- `substrate-ui/server.py` — becomes the small entry point: registry +
  application boot, SIGTERM install, ThreadingHTTPServer + UDS bind,
  routing table wiring. ~250 lines.

Contract: dual contract unchanged before and after; every existing
test still passes; no behavior change. `_poll_record_until(record_root,
predicate, *, timeout, poll_ms)` collapses the ten mid-write poll
loops into one call site.

## prerequisites

- REVIEW-2026-08-28 ratified.

## artifact contract

### Files

- `substrate-ui/handlers/` (new package, 4 files above + `__init__.py`).
- `substrate-ui/http.py` (new).
- `substrate-ui/server.py` — reduced to ~250 lines.

### Assertions

- Every existing substrate-ui test passes unchanged (175 tests).
- Every endpoint's response shape byte-identical before and after.
- File sizes: no handler module over 500 lines; http.py under 250; the
  reduced server.py under 300.

### Tests

- Existing 175 tests re-run; all pass.
- New: `test_handler_registry_covers_every_route.py` — walks the
  routing table + asserts every path prefix has a handler and every
  handler is reachable.

## signal contract

Emits: (none — hygiene split; no runtime emit sites in the diff).

## observation contract

`curl` at every existing endpoint returns the same shape as pre-split.
End-to-end substrate CLI + daemon integration test (from
test_cli_slash_221.py's real-daemon fixture) continues to pass.

## halt conditions

- `dual_contract_fail` if any test drifts.

## definition of done

Every existing test passes; server.py is ~250 lines; handlers live in
`handlers/`; ten mid-write poll loops collapse to one helper call.
Piece G's UI work has a clean routing surface to build on.
