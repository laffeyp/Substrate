# Sprint 214c — GET /api/session/<id>/events (SSE stream)

```yaml
---
id: 214c
status: closed
phase: daily-driver-piece-B
pass_kind: architecture
---
```

## scope

Third of three in the sprint 214 split. Sprint 214a shipped create + turn + lock unification; sprint 214b shipped list + by-name + delete. Sprint 214c ships the SSE events endpoint. Piece B closes with this landing (sprint 215 is a distinct piece — SessionEndRequested + PATCH + interrupt + shutdown).

**What sprint 214c ships.**

  1. **`GET /api/session/<id>/events?since_seq=N`** — Server-Sent Events stream of the session's record. Each envelope arrives as `data: <json>\n\n`. Stream stays open across turn pauses (the session record keeps growing as `Runtime.resume` fires). Closes when `substrate.RunFinalised` lands OR the client disconnects (broken-pipe handling on `self.wfile.write`). `since_seq` filters the backlog so a reconnecting client resumes from a known cursor.
  2. **Uses `api.attach(record_root)`** — the substrate's public follower primitive. `read_new()` polls the record's growing tail; per-segment cursor tracking never re-yields frames across a segment roll.
  3. **`Handler.do_GET`** grew one new route branch (`/api/session/<id>/events`) after the by-name branch.

**F-API-4 primitive adoption (TECHNIQUE #38).** Sprint 214c's tests replaced raw envelope-dict inspection with `assert_event` / `assert_no_event` over the parsed SSE frame stream — the primitives operate on any envelope iterable, so the frame list plugs in directly. Sprint 214a's `test_server_session_turn.py` also refactored to use `assert_event` for its record-envelope inspections (four raw reads → four primitive calls). Every record-envelope assertion across the piece-B endpoint tests now goes through F-API-4.

## prerequisites

- Sprint 214a closed.
- Sprint 214b closed.

## artifact contract

### Files

- `substrate-ui/server.py` — new route branch in `do_GET`; new `_session_events(session_id, since_seq)` handler method.
- `substrate-ui/tests/test_server_session_sse.py` — new. 4 cases.
- `substrate-ui/tests/test_server_session_turn.py` — F-API-4 refactor (TECHNIQUE #38 adoption).

### Assertions

- `GET /api/session/<id>/events?since_seq=-1` streams the full backlog: `UserMessage`, `ModelReply`, `FinalAnswer`, `Park` (post-turn record shape).
- `substrate.RunStarted` is NOT asserted — the piece-C review's finding 16 (deferred to sprint 214) named a substrate primitive gap: `Runtime.resume` on a fresh persistent root does not write RunStarted. Sprint 214a-c ship the endpoints without changing that primitive; the SSE stream faithfully replays whatever is on the record.
- `since_seq=N` filters: every returned frame carries `seq > N`; a since_seq at the midpoint of a turn's envelopes still streams the tail.
- New envelopes stream as they land: fire a turn from thread A while thread B reads SSE with `since_seq=<pre-turn tail>`; thread B receives the turn's fresh `UserMessage`.
- `GET /api/session/s_nonexistent/events` returns 404 with typed error.

### Command exit codes

- `uv run python -m pytest ../substrate-ui/tests/test_server_session_sse.py -q` exits 0 (4 passed).
- Substrate-side full-suite regression clean.
- Ruff clean on the changed files.

## observation contract

Sprint 214c discharges the record-level contract for the SSE endpoint. In-process, the tests spin the real `ThreadingHTTPServer` in a background thread and hit `/events` through `urllib`. `_read_sse_frames` uses `resp.read1(N)` (returns available bytes without waiting for the full N) with an idle timeout so the reader breaks cleanly when the backlog stops flowing. The socket close on the client side surfaces as `BrokenPipeError` in the server's `wfile.write`, caught cleanly.

## halt conditions

- `substrate_primitive_missing` — piece-C review finding 16 (fresh-root `.resume()` skips RunStarted) is still open; the SSE test acknowledges the gap in prose. Sprint 215 or 216 owns the primitive-side fix.

## definition of done

SSE endpoint live. F-API-4 primitives adopted across the piece-B endpoint tests. **Piece B of the daily-driver arc closes** — sprints 214a + 214b + 214c ship the six endpoints TECH-SPEC §4 named for piece B. Sprint 215 (SessionEndRequested + PATCH + interrupt + shutdown) is a separate concern.
