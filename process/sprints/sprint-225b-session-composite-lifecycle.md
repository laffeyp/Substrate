# Sprint 225b — session composite lifecycle (composite_of field + cascade)

```yaml
---
id: 225b
status: closed
phase: daily-driver-piece-E
pass_kind: functional
---
```

## split rationale

Second of four sub-cards splitting the original sprint 225. Ships the
composite-lifecycle infrastructure — the parent-child manifest link
and the cascade-on-end/rm behavior — without wiring any specific
composite factory (225c does that).

## scope

- `SessionManifest.composite_of: str | None = None` field. `None` for a
  standalone session; the parent's session_id for a child sub-agent.
- `_manifest_to_dict` / `_manifest_from_dict` round-trip the field.
- `SessionRegistry.create(...)` accepts `composite_of` kwarg.
- `POST /api/session/<id>/end` on a parent (any session whose
  session_id appears as another session's `composite_of`) FIRST ends
  every child, THEN ends the parent. Errors on a child do not stop the
  parent's end (best-effort; per-child failure logged and bucketed).
- `DELETE /api/session/<id>` on a parent cascades the same way: every
  child DELETE fires, then the parent. Rule 12: record dirs stay on
  disk for both.

## artifact contract

### Files

- `substrate-ui/session_registry.py` — manifest field + round-trip +
  `create` kwarg + `list_children(parent_id) -> list[str]` helper.
- `substrate-ui/server.py` — cascade branches in `_session_end` and
  `_session_delete`.

### Assertions

- Two sessions where child.composite_of == parent.session_id: end on
  parent ends both records with SessionEnded envelopes.
- Standalone session (composite_of == None) ends alone; no cascade.
- Rule 12: after DELETE cascade, both record dirs still exist under
  `~/.substrate/sessions/<sid>/record/`.
- boot_scan preserves `composite_of` across daemon restart.

### Tests

- `substrate-ui/tests/test_session_composite_cascade_end_225b.py`
- `substrate-ui/tests/test_session_composite_cascade_delete_225b.py`

## observation contract

Two curl calls: `POST /api/session` twice with the second's create
setting `composite_of`; then `POST /end` on the parent; both records
carry SessionEnded.

## halt conditions

- `dual_contract_fail` if a cascade drops one child silently.
