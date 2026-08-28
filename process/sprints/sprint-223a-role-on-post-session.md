# Sprint 223a — `role` field on POST /api/session

```yaml
---
id: 223a
status: closed
phase: piece-B-gap-fill
pass_kind: functional
---
```

## scope

TECH-SPEC §7 line 672 declares `role: "reviewer"` as an optional field on
POST /api/session. §1.6.5 line 162 names its CLI counterpart
`--role <name>`. Current `_session_create` (server.py:748-755) ignores it;
`SessionManifest` has no `role` field. This card wires both.

## prerequisites

- Sprint 223f closed (role-prompt resolver available).

## artifact contract

### Files

- `substrate-ui/session_registry.py` — add `SessionManifest.role: str = "default"`;
  round-trip in `_manifest_to_dict` / `_manifest_from_dict`; `create(...)`
  accepts `role`.
- `substrate-ui/server.py` — `_session_create` reads `body.get("role")`,
  passes to `create(...)`. Response echoes `role`.

### Assertions

- POST /api/session with `{"role": "reviewer", ...}` returns `{"role":
  "reviewer", ...}` and `manifest.json` on disk carries `role: "reviewer"`.
- POST /api/session with no `role` defaults to `"default"`.
- A role name whose prompt resolves at none of the four layers returns 400
  naming the role (the resolver's `RegistrationError` translated).
- `boot_scan` preserves `role` across daemon restart.

### Tests

- `substrate-ui/tests/test_server_session_role.py` — three cases: default,
  custom role that resolves, unknown role → 400.

## observation contract

`curl -X POST http://localhost:8765/api/session -H content-type:application/json
-d '{"driver":"deterministic","role":"default"}'` returns `role` in the body.

## halt conditions

- `dual_contract_fail` if `role` lands on the wire but not on the manifest.
- `vocabulary_change_required` if the manifest schema needs a version bump.
## signal contract

Emits: (none — daemon POST body validation + manifest field — no runtime emit sites).

