# Sprint 215 — daemon /api/session/*/end + PATCH + /interrupt + graceful shutdown

```yaml
---
id: 215
status: pending
phase: daily-driver-piece-B
pass_kind: functional
---
```

## scope

Three endpoints + a signal handler. `POST /api/session/<id>/end` injects `SessionEndRequested{reason: "user_end"}` via `Runtime.resume` (using the external-event injection path per `runtime.py:409`); the session_end producer emits `SessionEnded{reason: "user_end"}`. `PATCH /api/session/<id>` mutates `{driver?, tools?, per_turn?}` on the SessionRegistry entry AND the manifest.json; persists across parks — next `Runtime.resume` builds `session_topology` with the new values. `POST /api/session/<id>/interrupt` cancels the current model Producer's task via `loop.call_soon_threadsafe(task.cancel)` (the delegate.py:105-115 pattern applied to the session's Runtime). Add a SIGTERM handler on the daemon: for each running session, inject `SessionEndRequested{reason: "daemon_shutdown"}`, wait up to 10s per session for graceful pause, then exit.

## prerequisites

- Sprint 214 closed.

## context_files

- Sprint 214 output.
- `substrate/src/substrate/kernel/runtime.py:409-450` — `_resume_bootstrap` external-event injection.
- `substrate/src/substrate/topologies/tool_loop/delegate.py:105-115` — cross-thread cancel pattern.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §4 (endpoint shapes).

## artifact contract

### Files

- `substrate-ui/server.py` — three handler methods + SIGTERM installer.

### Assertions

- `POST /api/session/<id>/end` returns 200; record shows `SessionEnded{reason: "user_end"}`; session status → `ended`.
- `PATCH /api/session/<id> {driver: "claude"}` returns 200; next `Runtime.resume` builds session_topology with `driver=CliResponder(["claude","-p"])`; manifest.json updated.
- `POST /api/session/<id>/interrupt` during a turn → record shows `substrate.ProducerCancelled` on the `model` producer; `park-on-model-error`-adjacent trigger with `reason="interrupt"`; session parks.
- SIGTERM on daemon: every running session ends with `SessionEnded{reason: "daemon_shutdown"}`; daemon exits 0 within 10s per session.

### Tests

- `test_server_session_end_reason.py`, `test_server_session_patch_persists.py`, `test_server_session_interrupt.py`, `test_server_daemon_sigterm.py`.

## observation contract

Start a live session with a slow-yielding Responder (0.5s sleep). Fire `POST /interrupt` mid-turn; assert ProducerCancelled lands on the record within 100ms. Fire SIGTERM on daemon with three parked sessions; assert all three carry SessionEnded{daemon_shutdown} on their records at boot after restart (no interrupted status).

## halt conditions

- `dual_contract_fail` if SessionEnded.reason distinctions leak (all four values must reach distinct paths).

## definition of done

Three endpoints + shutdown handler work. Sprint 216 (queue cap + 410) can dispatch.
