# Sprint 217d — daemon interrupt rewires onto `cancel_producer(instance)` and reports honestly

```yaml
---
id: 217d
status: pending
phase: daily-driver-piece-B
pass_kind: architecture
---
```

## scope

Commit `ebba453` shipped POST /api/session/<id>/interrupt on top of `Runtime.cancel_producers("model")`. That primitive changes shape in sprint 217c. Two additional problems the endpoint carries independent of the primitive:

1. **The response lies about what happened.** `_session_interrupt` returns `{"interrupted": true}` when `call_soon_threadsafe` was scheduled. The producer may not have stopped. The client is told the interrupt landed; the truth is the interrupt was dispatched. Under the SSE contract the client would eventually see `ProducerCancelled` and `Park`, but a naive client reading the /interrupt response and immediately checking session state gets a race.
2. **The single test papers over the race with `time.sleep(2.0)`.** A test that depends on wall-clock timing to assert a race outcome is not a contract test.

This card rewires the daemon side and rewrites the tests to poll for the record state rather than sleep.

**Wire changes.**

- `TurnHandle` gains `instance: str | None` alongside `loop`, `task`, `runtime`. `turn_sync` reads the current model producer's instance from `runtime._st.kind_by_instance` after `.resume()` starts firing producers, and populates `handle.instance`. The read runs on the worker's event loop; the write to the handle is scheduled back to the daemon's context.
- `SessionRegistry.interrupt` calls `runtime.cancel_producer(handle.instance, cause="external", caller="daemon:interrupt")` via `call_soon_threadsafe`. Returns the `ProducerRef` if dispatched, `None` if no instance is running.
- `_session_interrupt` returns `{"interrupted": <bool>, "producer": <ref>, "landed": <bool>}` where `landed` is set after polling the record for the resulting `ProducerCancelled` envelope. Default poll: 100 ms interval, 3 s cap; both configurable via a request query string (`?wait_ms=100&max_wait_ms=3000`). If the envelope does not land within the cap, `landed=false` and the response body names the seq the caller can watch on `/events`.
- Response 200 semantics: `interrupted=true, landed=true` — cancel dispatched and the ProducerCancelled envelope is on the record. `interrupted=true, landed=false` — dispatched, not yet observed; caller watches `/events`. `interrupted=false` — no live producer to interrupt.
- The endpoint stays synchronous from the HTTP caller's view. The wait is inside the handler, capped by `max_wait_ms`.

**Test changes.**

- Delete the `time.sleep(2.0)` in `test_server_session_interrupt.py::test_interrupt_parks_the_session_with_producer_cancelled`. Replace with a poll against `/api/session/<id>/events` (or `read_record`) for the `substrate.ProducerStarted(producer.kind="model")` envelope. Poll interval 50 ms, cap 3 s. Only fire the interrupt AFTER the model producer's start is on the record.
- Add a new test that reads `ProducerCancelled.payload.cause == "external"` and `.caller == "daemon:interrupt"`. Locks 217c's provenance annotation end-to-end.
- Add a test that fires interrupt against an idle session (no live producer) and asserts `{interrupted: false, landed: false}`.
- Add a test that fires interrupt with `max_wait_ms=0` — the handler dispatches but does not poll; returns `landed=false` immediately.

**Ebba453 red-team fixes retro-carded here.** The commit landed three of my red-team findings under the umbrella "red-team fixes." This card names them so the audit trail has one place to point:

- `_daemon_driver_resolver` grew `_RESPONDER_CACHE` (F13 close).
- `SessionRegistry._next_turn_index: dict[str, int]` populated at boot_scan (F14 close).
- `SessionRegistry.set_name` and `set_driver` acquire the per-session `threading.Lock` (red-team pass-2 finding 4 close).

None of the three needs code changes here; they are named for the audit-trail record only. If any regresses under 217c's primitive replacement, this card owns the fix.

## prerequisites

- Sprint 217c closed.

## context_files

- `substrate-ui/session_registry.py` — `TurnHandle` at the module top, `interrupt` method, `_run_resume_sync` populates the handle.
- `substrate-ui/server.py` — `_session_interrupt` handler, `do_POST` routing.
- `substrate-ui/tests/test_server_session_interrupt.py` — the three existing tests to rewrite.
- Sprint 217c output: `Runtime.cancel_producer` signature + `ProducerCancelled.payload.cause` semantics.

## signal contract

### Emits

- None new. The record grows `ProducerCancelled` with the annotation from 217c.

### Consumes

- `session_registry.py::interrupt` calls `runtime.cancel_producer(instance, cause="external", caller="daemon:interrupt")`.
- The endpoint reads the record via `api.read_record` for the poll.

### Invariants

- The endpoint never returns `{interrupted: true}` when nothing was dispatched.
- The endpoint never returns `{landed: true}` without reading a `ProducerCancelled` envelope from the record.
- The wait is bounded by `max_wait_ms`; the endpoint always returns within `max_wait_ms + 100 ms` of dispatch.
- `TurnHandle.instance` is populated before the interrupt endpoint could plausibly be called (populated after `_run_resume_sync`'s worker thread has fired the first producer's start).

## artifact contract

### Files created

- None.

### Files modified

- `substrate-ui/session_registry.py` — `TurnHandle` grows `instance` field; `interrupt` calls `cancel_producer`, returns `ProducerRef | None`.
- `substrate-ui/server.py` — `_session_interrupt` polls for the ProducerCancelled envelope, returns the four-field body.
- `substrate-ui/tests/test_server_session_interrupt.py` — three tests rewritten (no `time.sleep`), two tests added (cause/caller annotation, idle interrupt, no-wait mode).

### Content assertions

- `grep -n 'time.sleep' substrate-ui/tests/test_server_session_interrupt.py` returns zero hits.
- `grep -n 'cancel_producers' substrate-ui` returns zero hits (updated for 217c).
- `grep -n 'cancel_producer\b' substrate-ui/session_registry.py` returns exactly one hit.
- The `_session_interrupt` handler contains one `api.read_record` call inside the poll loop.

### Command exit codes

- `cd substrate && uv run python -m pytest ../substrate-ui/tests/test_server_session_interrupt.py -q` returns 0.
- `cd substrate && uv run python -m pytest ../substrate-ui/tests -q` returns 0.
- `cd substrate && uv run ruff check ../substrate-ui` returns 0.

## observation contract

Boot the daemon against a temp base dir. `POST /api/session {"driver":"deterministic"}`. `POST /api/session/<id>/turn {"text":"hello"}` (in a background thread; the turn takes a few hundred ms). Wait for the model producer to start (poll `/api/session/<id>/events` for a `substrate.ProducerStarted` with `producer.kind == "model"`). `POST /api/session/<id>/interrupt` — response body has `interrupted=true`, `landed=true`, and a `producer` field naming the cancelled model instance. The turn thread returns with `status="parked"`. `/events` shows `ProducerCancelled(cause="external", caller="daemon:interrupt")` → `TriggerFired(park-on-interrupt)` → `ProducerStarted(park)` → `Park(reason="interrupt")` → `TerminationMatched(pause-await-input)`.

## halt conditions

- `dual_contract_fail` if `landed=true` fires without a matching `ProducerCancelled` on the record.
- `substrate_primitive_missing` if 217c has not landed.

## definition of done

`_session_interrupt` returns an honest four-field body. Tests exercise the endpoint by polling the record, not by sleeping. The endpoint's provenance annotation reaches the record.
