# Sprint 224i — sprint 221 slash tests hit a real daemon

```yaml
---
id: 224i
status: closed
phase: testing-discipline
pass_kind: observation
---
```

> **Renamed from sprint 224b to sprint 224i on 2026-08-28** (REVIEW F1 —
> id collision with `sprint-224b-app-bundled-ci-factories.md`, which
> also carried `id: 224b`). The old filename lives in git history; every
> outside reference to "224b (slash router)" now resolves as "224i (slash
> router)". `pass_kind` also corrected from the invented `test-refactor`
> tag to `observation` per REVIEW F2. Body unchanged.

## scope

`substrate/tests/test_cli_slash_221.py` monkeypatches every daemon call
(`patch_session`, `list_sessions`). Tests verify the CLI passes strings
through a boundary; they do NOT verify the daemon updated state. That is
half the dual contract.

Rewrite each router test that has a daemon-side effect to run against a
real `ThreadingHTTPServer` + `SessionRegistry` (the shape sprint 219 SSE
test uses). `/model` fires PATCH, then the test asserts
`manifest.driver` on the registry. `/tools` same. `/list sessions` calls
the real endpoint and asserts against the real payload shape.

Tests with no daemon side effect (`/help`, `/exit`, `/context`, `/run`
deferral, `/list applications` deferral, unknown-slash) stay unit-only.

## artifact contract

### Files

- `substrate/tests/test_cli_slash_221.py` — updated in place; new
  fixture spins a daemon per test module.

### Assertions

- After `/model X`, `_SESSION_REGISTRY.get(sid).driver == "X"`.
- After `/tools a,b`, `_SESSION_REGISTRY.get(sid).tools == ("a", "b")`.
- After `/list sessions`, stderr shows the sid returned by the real
  `GET /api/session`.
- Zero monkeypatches on `_daemon` for the state-mutating slashes.
