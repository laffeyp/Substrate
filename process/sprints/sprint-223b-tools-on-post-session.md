# Sprint 223b — `tools` field on POST /api/session

```yaml
---
id: 223b
status: closed
phase: piece-B-gap-fill
pass_kind: functional
---
```

## scope

TECH-SPEC §7 line 674 declares `tools: ["read_file", "grep"]` on POST
/api/session. Sprint 217e already added `tools` to `SessionManifest` and
made it PATCH-able. This card wires POST to accept it at create time, so
a session opens with the restriction in place rather than needing a
follow-up PATCH.

## prerequisites

- Sprint 217e closed (manifest.tools field + PATCH branch).

## artifact contract

### Files

- `substrate-ui/server.py` — `_session_create` reads `body.get("tools")`,
  validates as list-of-non-empty-strings (mirrors PATCH), passes to
  `SessionRegistry.create(...)` via a new `tools=` kwarg.
- `substrate-ui/session_registry.py` — `create(...)` accepts `tools:
  tuple[str, ...] | None = None`; stores on the manifest.

### Assertions

- POST with `{"tools": ["read_file", "grep"]}` creates a session whose
  manifest.json shows `tools: ["read_file", "grep"]`.
- POST with `tools: []` stores `None` (unrestricted) — same convention as
  PATCH per 217e.
- POST with `tools: [123]` returns 400 naming the offending element.
- Session topology built from the manifest carries only the named tools
  (piece-A `full_suite` filter path, unchanged from 217e).

### Tests

- `substrate-ui/tests/test_server_session_create_tools.py` — four cases:
  named list, empty list → unrestricted, invalid element → 400, missing
  field → unrestricted default.

## observation contract

`curl -X POST /api/session -d '{"driver":"deterministic","tools":["grep"]}'`
returns the session; subsequent `/turn` sees only `grep` in the builder.

## halt conditions

- `dual_contract_fail` if the wire accepts `tools` but the built topology
  does not honor it.
