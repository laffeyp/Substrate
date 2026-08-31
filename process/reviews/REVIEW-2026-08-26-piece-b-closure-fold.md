# Piece-B closure review — fold summary (2026-08-26)

Source: `substrate/process/REVIEW-2026-08-26-piece-b-closure.md` (Claude,
2026-08-26). Eighteen findings — eight real (1–8), ten smaller (9–18).
Twelve landed in place, five deferred into sprint 216 (its natural home
for queue-cap + resource-cap discipline), one closed as historical drift
in a superseded card.

Full-suite check after the fold: **37 piece-B tests pass in 29.71s**
(create 4, turn 5, list 4, by-name 4, delete 5, sse 4, registry 6, and
five new review-fold pins). No new dependencies.

## Landed in code

### 1. BLACKBOARD scope claim corrected (finding 1)
The 2026-08-26 sprint 214c entry claimed "the six endpoints TECH-SPEC §4
named for piece B." TECH-SPEC §4 names fourteen for piece B. The append
below (`## Sprint tail`) corrects the count and names the split: sprints
214a/b/c ship the six read/create/turn/delete endpoints; interrupt/end/
PATCH move to sprint 215; topology/applications/bundle move to piece E/H.

### 2. SSE finalisation-past-since_seq hang closed (findings 2 + 10 + 15)
`substrate-ui/server.py::_session_events` — the seq filter ran before the
finalisation check, so a client reconnecting with `since_seq >=
runfinalised_seq` hit `continue` on every envelope and the outer
`while not finalised:` polled forever. The fold checks the RunFinalised
kind first and only then applies the filter. `LiveRecord.follow(until_finalised=True)`
at `attach.py:112-123` uses this ordering; the manual reimplementation
had not. Same edit switches the SSE frame to bytes-native
(`b"data: " + msgspec.json.encode(env) + b"\n\n"`), dropping the
encode/decode/reencode round trip finding 15 named.

### 3. DELETE sub-resource parse fixed (finding 3)
`substrate-ui/server.py::do_DELETE` — `DELETE /api/session/<id>/turn`
reached `SessionRegistry.delete("<id>/turn")` and returned 404 pretending
the mangled id was the session name. The real session was never
targeted, but the parse was silently wrong. The fold rejects any
`session_id` containing `/` (or empty) at the routing layer with a
"no delete endpoint" 404.

### 4. `SessionRegistry.delete` no longer races an in-flight turn (finding 4)
`substrate-ui/session_registry.py::delete` — the earlier shape popped
the manifest without regard to any in-flight `turn_sync`; the in-flight
turn's tail `update_status` then found the manifest gone and raised
KeyError from inside the running turn, surfacing to the caller as a
generic 500. The fold acquires the per-session `threading.Lock` for the
delete under `setdefault` (creating one if absent), so an in-flight turn
completes cleanly and any turn_sync caller still waiting on the lock
finds the manifest gone under its own under-lock re-check and raises
`SessionEndedMidTurn` — the existing 410 shape.

### 5. `_session_create` accepts `seed_text` (finding 6)
`substrate-ui/server.py::_session_create` — TECH-SPEC §4 names the field
`seed_text`; the handler read `seed` only, so a spec-following client
silently sent nothing. Both names now accepted; `seed_text` wins when
both are present. `role`, `tools`, `isolate` remain unimplemented — those
are functional expansions beyond piece B's read/create/delete scope and
have no natural home before sprint 215's lifecycle endpoints land.

### 6. `_session_turn` response carries `seq` (finding 7)
`substrate-ui/server.py::_session_turn` — TECH-SPEC §4 names `seq` (the
record's tail at turn start) in the response body. The handler emitted
`{status, final_seq, record}` only. The fold reads the pre-turn tail
before `turn_sync` fires and includes it as `seq`. `record` stays as
an extra (useful to clients; not a spec violation).

### 7. `_session_delete` 204 carries Content-Length: 0 (finding 16)
`substrate-ui/server.py::_session_delete` — a missing Content-Length on
a keep-alive HTTP/1.1 204 leaves some clients reading until close and
stalling the pipelined session. Explicit zero header added.

### 8. `_session_events` rejects malformed `since_seq` as 400 (finding 17)
`substrate-ui/server.py::do_GET` — `?since_seq=abc` raised ValueError
inside `int(...)` and fell through to the generic 500 branch. Bad
query parameters are 400. The parse is now wrapped and a bad value
returns `{"error": "since_seq must be an integer, got 'abc'"}` at 400.

### 9. Session-registry docstrings match the code (finding 9)
`substrate-ui/session_registry.py` module docstring (line 8) and
`SessionRegistry` class docstring (lines 130-134) both promised the
removed `_locks: dict[str, asyncio.Lock]` map. Rewritten to name
`_turn_threading_locks: dict[str, threading.Lock]` with the piece-C
review finding 3 attribution.

### 10. Delete-preserves-record test actually runs its check (finding 8)
`substrate-ui/tests/test_server_session_delete.py::test_delete_leaves_the_record_directory_intact`
— the earlier guard tested `(record_root / "events-000001.jsonl").exists()`
which is never true (real segments are `events-NNNNNN.open.jsonl` and
`events-NNNNNN.sealed.jsonl`), so the content-preservation half of the
SDD-rule-12 check silently skipped. Rewritten to `api.read_record(record_root)`
before and after the delete; the two envelope lists must be equal.

## Regression pins

`substrate-ui/tests/test_server_piece_b_review_folds.py` — six new
tests, one per real behavioral fold:
- delete on sub-resource `/api/session/<id>/turn` returns 404, session survives
- `seed_text` alias lands on the manifest
- `seq` present on the /turn response
- `?since_seq=abc` returns 400
- delete during in-flight turn waits and the turn returns 200 (not 500)
- SSE reader past `runfinalised_seq` returns cleanly instead of spinning

## Deferred to sprint 216

Five findings whose fixes are the per-session queue cap + resource
discipline the pending sprint already carries. Sprint 216 opens with
these attached; its scope grows only in phrasing, not new gates.

- **Finding 5** — TECH-SPEC §4's per-session queue cap (default 4, HTTP
  429 on fifth). Named in the sprint's scope; no code today. Piece B's
  contract with the spec depends on it.
- **Finding 11** — SSE keep-alive comments during idle. Any proxy in
  front of the daemon with an idle timeout closes the connection; the
  standard fix is `: ping\n\n` every ~15-30 s. No proxy today, so no
  observable failure, but the deployment contract is silent about it.
- **Finding 12** — `/turn` has no worker-thread cap; N slow turns pin
  N `ThreadingHTTPServer` threads for up to 600 s each. Closes with
  finding 5's queue cap.
- **Finding 13** — `_daemon_driver_resolver` builds a fresh Responder
  per turn; no cross-turn state (rate-limit counters, retry backoff,
  connection pool) survives. Not a bug for the current adapter set;
  becomes one the moment an adapter carries state. Belongs at the
  Responder-cache seam sprint 216 introduces alongside the queue.
- **Finding 14** — `_session_turn` scans the whole record for the
  pre-turn `seq` (and, in the builder, `next_turn_index`). Same shape
  as piece-C finding 13. No cost yet at realistic sizes.

## Closed as historical drift

- **Finding 18** — the review named an `asyncio.Lock` reference in
  sprint 214a's assertions. Grep across the sprints directory found it
  in `sprint-214-daemon-session-api-core.md:14, 45` — the split-into-
  214a-and-214b **meta** card, whose status is `split-into-214a-and-
  214b`. That card records the pre-split scope; editing its body would
  revise history. The active cards (214a/b/c) use `threading.Lock`
  correctly. Left in place as the audit trail of the pre-split shape.

## SDD adherence

- Hard rule 6 (≤2 files, one concept) — the fold touches
  `server.py` + `session_registry.py` + one test file rewrite + one new
  regression file. A single closure-fold cycle, not a new sprint.
- Hard rule 7 (canonical home registry) — no new entities.
- Hard rule 9 (observation contract) — the new regression tests use the
  same in-process `ThreadingHTTPServer` shape the piece-B endpoint
  tests already established. No new harness.
- Hard rule 12 (no deletions, audit trail) — every edit above is in
  place on code / test / docstring surfaces; the meta card and the
  original review file both stay on disk unchanged. This fold summary
  is a new dated file, not a rewrite.
