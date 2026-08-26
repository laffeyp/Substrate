# Sprint 216 — session queue cap + 410 Gone on session-ended-mid-delegate

```yaml
---
id: 216
status: pending
phase: daily-driver-piece-B
pass_kind: functional
---
```

## scope

Two safety rails from round-2 red team: per-session queue cap default 4 — fifth caller receives HTTP 429 with body `{"ok": false, "error": "session queue full", "queue_position": 4, "queue_cap": 4}`; 410 Gone from `POST /api/session/<id>/turn` when the session has ended between the caller's registry lookup and the POST arrival. Post-review 2026-08-25: one response shape only (429 with the body above); the round-5 "429 or a body-level flag" ambiguity is gone. Cap is configurable via `[session]` block in `~/.substrate/config.toml` (`turn_queue_cap = 4`).

## prerequisites

- Sprint 215 closed.

## context_files

- Sprint 214-215 output.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §4 (queue cap) + §5 (410 mid-delegate).
- `substrate/src/substrate/topologies/tool_loop/delegate.py:196` — `max_children=4` for parity.

## artifact contract

### Files

- `substrate-ui/server.py` — grow `/api/session/<id>/turn` handler with cap check + 410 branch.
- `~/.substrate/config.toml` (default seeded via a small `topologies/session/default_config.toml` template + first-run copier).

### Assertions

- Fifth concurrent `/turn` returns HTTP 429 with body `{"ok": false, "error": "session queue full", "queue_position": 4, "queue_cap": 4}` — does NOT block.
- `/turn` on a session whose status is `ended`, `failed`, or manifest missing returns 410 with `{ok:false, error:"session_ended_mid_delegate"}`.
- `[session] turn_queue_cap = N` in config overrides the default.

### Tests

- `test_server_session_queue_cap.py` — 5 concurrent turns; fifth returns queue-full immediately.
- `test_server_session_410_after_end.py`.

## observation contract

Fire five concurrent `/turn` POSTs to one session; observe fifth returns immediately with queue-full status. End a session via DELETE; a delegate that resolved the session name a second earlier fires `/turn`; receives 410.

## halt conditions

- `awaiting_architect_decision` if the cap value warrants Architect ratification (default 4 matches delegate's `max_children`).

## definition of done

Cap enforced; 410 returned on race. Sprint 217 (/api/agent backwards-compat) can dispatch.
