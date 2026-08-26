# Sprint 214b — GET /api/session + GET /api/session/by-name/<name> + DELETE /api/session/<id>

```yaml
---
id: 214b
status: closed
phase: daily-driver-piece-B
pass_kind: architecture
---
```

## scope

Second of three in the sprint 214 split. Sprint 214a shipped POST /api/session + POST /api/session/<id>/turn + the finding-3 lock unification. Sprint 214b ships the three remaining non-streaming endpoints: list, by-name, delete. Sprint 214c queues the SSE events endpoint.

**What sprint 214b ships.**

  1. **`GET /api/session`** — returns `{"live": [...], "parked": [...], "ended": [...], "interrupted": [...]}` bucketing every manifest by status. Each entry carries `session_id`, `name`, `driver`, `workspace`, `workspace_shape`, `record`, `created_at`, `bundle`. Reads the in-memory catalog directly; the boot scan (sprint 211) has already reclassified each manifest against the record's own tail.
  2. **`GET /api/session/by-name/<name>`** — resolves a name to `{"session_id", "name"}` on hit; 404 with `{"error": "unknown session name: '<name>'"}` on miss. Names case-sensitive; URL-encoded names (spaces, punctuation) decode correctly.
  3. **`DELETE /api/session/<id>`** — 204 on success; 404 on unknown id. Removes the manifest.json, the by-name entry (under flock), the per-session threading lock. **The record directory stays** — SDD hard rule 12 says the audit trail is the work. A subsequent `POST /turn` on a deleted session returns 404. A deleted name can be reused by a new session.
  4. **`SessionRegistry.delete(session_id) -> SessionManifest`** on the registry side. Removes manifest + by-name entry + lock; leaves the record dir; idempotent (`FileNotFoundError` on the manifest unlink is caught).
  5. **`Handler.do_DELETE`** — new method on the server handler; origin check same as do_POST.

## prerequisites

- Sprint 214a closed.

## artifact contract

### Files

- `substrate-ui/session_registry.py` — add `SessionRegistry.delete` method with SDD-rule-12 record-preservation semantics.
- `substrate-ui/server.py` — add `do_DELETE`; route `/api/session`, `/api/session/by-name/*`, `/api/session/<id>` (DELETE); three new handler methods `_session_list`, `_session_by_name`, `_session_delete`.
- `substrate-ui/tests/test_server_session_list.py` — new. 4 cases.
- `substrate-ui/tests/test_server_session_by_name.py` — new. 4 cases.
- `substrate-ui/tests/test_server_session_delete.py` — new. 5 cases.

### Assertions

- `GET /api/session` on an empty registry returns four empty buckets.
- A running session lands in the `live` bucket; a status update moves it to the right bucket.
- `GET /api/session/by-name/reviewer` returns `{"session_id": "s_...", "name": "reviewer"}`.
- `GET /api/session/by-name/nonexistent` returns 404 with a typed error.
- Case-sensitive name lookup: `Reviewer` and `reviewer` are distinct.
- URL-encoded names decode: `team%20review` resolves to a session named `"team review"`.
- `DELETE /api/session/<id>` returns 204; manifest.json is unlinked; by-name entry removed; `SessionRegistry.get` returns None.
- A deleted session's record directory survives on disk unchanged.
- `DELETE` on an unknown id returns 404 with a typed error.
- `POST /turn` after `DELETE` returns 404.
- A deleted name can be reused by a new session without collision.

### Command exit codes

- `uv run python -m pytest ../substrate-ui/tests/test_server_session_list.py ../substrate-ui/tests/test_server_session_by_name.py ../substrate-ui/tests/test_server_session_delete.py -q` exits 0 (13 passed).
- Substrate-side full-suite regression clean.
- Ruff clean on the changed files.

## observation contract

Sprint 214b discharges the record-level contract for the three endpoints. In-process, sprint 214b's tests spin the real `ThreadingHTTPServer` in a background thread and hit each endpoint through `urllib` — full HTTP round-trip against the real handler + real registry. The SIGKILL/restart harness through the shipped CLI waits on sprint 222.

## halt conditions

- `dual_contract_fail` if the record dir is removed alongside the manifest — SDD hard rule 12 would be violated.

## definition of done

Three endpoints live. Delete honors the audit-trail rule. Sprint 214c (SSE events) can dispatch on this landing.
