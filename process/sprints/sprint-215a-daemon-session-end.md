# Sprint 215a — POST /api/session/<id>/end

```yaml
---
id: 215a
status: closed
phase: daily-driver-piece-B
pass_kind: functional
---
```

## scope

First of four in the sprint 215 split. Sprint 215 as carded touched
`substrate-ui/server.py` for four concepts (POST /end, PATCH, POST
/interrupt, SIGTERM). Rule 6 said split. Sprint 215a lands POST /end
alone — it rides the existing `turn_sync` seam and needs no new
runtime plumbing.

**What sprint 215a ships.**

  1. **`POST /api/session/<id>/end`** at `substrate-ui/server.py`.
     Empty body (or optional `{"source": "user_end"?}`). Delegates to
     `SessionRegistry.turn_sync` with a `SessionEndRequested(session_id,
     source)` as the resume event. The session topology's `end-on-user-end`
     trigger at `session/__init__.py:499-509` fires on any
     `SessionEndRequested` and routes through the `session_end` producer
     to emit `SessionEnded{reason: "user_end", total_turns: N}`;
     `threshold_count("SessionEnded", 1)` matches; the run finalises;
     `turn_sync` transitions the manifest to `"ended"`.
  2. **Response.** `{seq, status: "ended", final_seq, record}`. `seq`
     is the pre-request record tail (piece-B review finding 7 shape);
     `final_seq` is the post-run tail; `status` is always `"ended"`.
     404 on unknown session_id; 410 on a session already ended (the
     existing `SessionEndedMidTurn` shape).

## prerequisites

- Sprint 214c closed (piece B core endpoints live).
- Piece-B review folded (2026-08-26).

## artifact contract

### Files

- `substrate-ui/server.py` — one new handler method `_session_end`;
  one new POST route branch in `do_POST` after the /turn branch.
- `substrate-ui/tests/test_server_session_end.py` — new; ~4 cases.

### Assertions

- `POST /api/session/<id>/end` on a live session returns 200 with
  `{"status": "ended", ...}`; the record shows `SessionEnded{reason:
  "user_end"}` at the tail.
- The manifest status transitions to `"ended"`; the SessionRegistry
  `get(session_id)` returns a manifest whose `.status == "ended"`.
- `POST /end` on an already-ended session returns 410 with typed
  error `session_ended_mid_delegate` (the existing shape from
  `_session_turn`).
- `POST /end` on an unknown session_id returns 404.

### Command exit codes

- `uv run python -m pytest ../substrate-ui/tests/test_server_session_end.py -q`
  exits 0.
- Substrate-side full-suite regression clean (excluding the pre-existing
  `test_instrument_ablation_delta` real-model transience).
- Ruff clean.

## observation contract

Sprint 215a discharges the record-level contract for POST /end. In-
process: spin the real `ThreadingHTTPServer` in a background thread,
create a session, fire one /turn (so the record has UserMessage +
ModelReply + Park), then POST /end. Assert:
- HTTP 200 with `status: "ended"`.
- `SessionEnded{reason: "user_end"}` on the record.
- The `RunFinalised` envelope is present (the topology's
  `threshold_count` termination fires).
- A subsequent /turn returns 410.

## halt conditions

- `substrate_primitive_missing` if `Runtime.resume(resume_event=
  SessionEndRequested(...))` does not fire the `end-on-user-end`
  trigger for reasons the substrate ships but the daemon does not
  see. Piece-C review finding 16 (fresh-root `.resume()` skips
  RunStarted) is orthogonal — this sprint drives an already-existing
  record and does not depend on the RunStarted-on-resume behavior.

## definition of done

POST /end live. Sprint 215b (POST /interrupt) can dispatch on this
landing. 215c (PATCH) and 215d (SIGTERM) are independent; either may
dispatch in parallel with 215b.
