# Sprint 224a — extract wire-error string constants

```yaml
---
id: 224a
status: closed
phase: testing-discipline
pass_kind: refactor
---
```

## scope

`"session_ended_mid_delegate"` lives as a raw string at 5 sites in
`substrate-ui/server.py` and at 3 test assertion sites. `"record_torn"`
and `"fresh_session_never_opened"` land as raw strings on the wire but
have zero test coverage — a rename passes CI silently. The memory item
"retyped kind/status/verdict strings are the core drift" applies here.

Ship `substrate-ui/session_errors.py` exporting the constants. Server
imports and writes them; tests import and assert against them. A rename
fails at the constant name, not silently in the wire string.

## artifact contract

### Files

- `substrate-ui/session_errors.py` — one module. Exports
  `SESSION_ENDED_MID_DELEGATE`, `RECORD_TORN`, `FRESH_SESSION_NEVER_OPENED`.
- `substrate-ui/server.py` — 5 sites replace the literal with the import.
- `substrate-ui/tests/*.py` — 3 test-site literals replace with import.

### Assertions

- `grep -rn '"session_ended_mid_delegate"' substrate-ui/ | wc -l` returns
  0 outside `session_errors.py` and the docstring on session_registry.py.
- All existing tests continue to pass unchanged.
