# Sprint 223c — `isolate` field on POST /api/session (§9c Mode 3)

```yaml
---
id: 223c
status: closed
phase: piece-B-gap-fill
pass_kind: functional
---
```

## scope

TECH-SPEC §7 line 675 declares `isolate: false` on POST /api/session; §9c
Mode 3 defines the isolation semantics. When `isolate=true`, the session
opens with `workspace_shape="isolate"` — its tool file writes stay inside
`~/.substrate/sessions/<session_id>/workspace/` and never touch the
caller-supplied `workspace` path. Mode 1 (`isolate=false`, default) keeps
the current shared-workspace behavior.

## prerequisites

- Sprint 223b closed (POST body fields extension pattern in place).

## artifact contract

### Files

- `substrate-ui/server.py` — `_session_create` reads
  `body.get("isolate")`; when truthy, overrides `workspace_shape` to
  `"isolate"` and rewrites `workspace` to
  `_SESSIONS_BASE / session_id / "workspace"` (creating the dir).
- `substrate-ui/session_registry.py` — no schema change (`workspace_shape`
  is already a manifest string; `"isolate"` is a new valid value).

### Assertions

- POST with `{"isolate": true, "workspace": "/tmp/anywhere"}` returns
  `workspace_shape: "isolate"` and the manifest's workspace path is
  `~/.substrate/sessions/<id>/workspace`, NOT `/tmp/anywhere`.
- POST with `isolate: false` (or absent) preserves the caller's workspace.
- `isolate: true` and `workspace_shape: "worktree"` in the same body →
  400 (mutually exclusive; explicit halt over silent priority).
- The isolated workspace directory exists on disk after create.

### Tests

- `substrate-ui/tests/test_server_session_isolate.py` — four cases:
  isolate=true creates isolated dir, isolate=false preserves caller path,
  isolate+worktree → 400, isolate=true dir exists on disk.

## observation contract

`curl -X POST /api/session -d '{"driver":"deterministic","isolate":true}'`
returns `workspace_shape:"isolate"`; `ls ~/.substrate/sessions/<id>/workspace/`
exists.

## halt conditions

- `dual_contract_fail` if a Mode-3 session's tool writes reach the caller's
  workspace (a live tool-loop test in the observation contract catches this).
## signal contract

Emits: (none — daemon POST body + workspace_shape plumbing — no runtime emit sites).

