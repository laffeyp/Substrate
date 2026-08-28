# Sprint 223e — `/api/agent` compat bridge routes through `/api/session`

```yaml
---
id: 223e
status: closed
phase: piece-B-gap-fill
pass_kind: functional
---
```

## scope

TECH-SPEC §7 line 690: "`/api/agent` at `server.py:554-687` stays for one
release; internally creates a session on first request and routes
subsequent requests to `/api/session/<id>/turn`." Line 700 names the test:
`test_server_agent_compat.py`.

Current `_agent` at server.py:1322 runs its own topology loop and does
NOT touch the session registry. This card rewires it: on first call for
a given `session` query param, POST /api/session internally; store the
session_id in a `dict[legacy_session_name, session_id]`; every request
routes through `SessionRegistry.turn_sync`. The response shape stays
identical (the legacy console reads the record path from it).

## prerequisites

- Sprints 223a-d closed. `role` / `tools` / `isolate` / `per_turn` fields
  reachable from the create call the bridge issues.

## artifact contract

### Files

- `substrate-ui/server.py` — `_agent` replaced. Legacy behavior stays for
  callers that pass `?legacy=true` (kept one release; will delete when
  the last consumer moves). The new default path creates-or-finds a
  session, routes the `task` string as a UserMessage through
  `turn_sync`, returns `{record, session_id}`.

### Assertions

- Two calls to `/api/agent?session=abc&task=hello` (then `&task=again`)
  produce ONE session with two UserMessages on its record.
- The response's `record` path matches the created session's
  `manifest.record_root`.
- A concurrent second call on the same session queues (per-session
  threading lock owned by SessionRegistry).
- `?model=ollama` maps to `driver="ollama"` on the create call.
- The legacy launch-thread path (`?legacy=true`) still works for one
  release; the response includes a `deprecated: true` field.

### Tests

- `substrate-ui/tests/test_server_agent_compat.py` — five cases: first
  call creates session, second call reuses it, model param maps to
  driver, concurrent calls serialize, legacy=true still works.

## observation contract

`curl "http://localhost:8765/api/agent?session=demo&task=hi"` returns
`{record, session_id}`; a second call with the same `session` returns
the same `session_id`; the record shows two UserMessages.

## halt conditions

- `dual_contract_fail` if the bridge writes to a record path not owned
  by the session registry.
- `vocabulary_change_required` if the legacy console needs a response
  field the new shape does not carry.


## signal contract

Emits: (none — daemon compat bridge over existing endpoints — no new emit sites).

## definition of done

All five piece-B gaps (223a-e) closed. Piece B rings the bell: every
endpoint in TECH-SPEC §7 for POST /api/session, PATCH /api/session/<id>,
and the /api/agent compat row lands on the wire, on the manifest, and on
the record.
