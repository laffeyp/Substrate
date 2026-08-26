# Sprint 214a — POST /api/session + POST /api/session/<id>/turn + finding 3 fix

```yaml
---
id: 214a
status: closed
phase: daily-driver-piece-B
pass_kind: architecture
---
```

## scope

First half of the sprint 214 split. Sprint 214 as carded touched substrate-ui/server.py + 7 test files + inherited six review-deferred findings (three real, three hygiene). Rule 6 said split. Sprint 214a lands the core turn-taking path plus the finding-3 lock unification; sprint 214b ships list + by-name + delete; sprint 214c wires SSE events.

**What sprint 214a ships.**

  1. **`POST /api/session`** at `substrate-ui/server.py`. Body: `{"driver": "deterministic", "name"?, "workspace"?, "workspace_shape"?, "seed"?, "bundle"?}`. Delegates to `SessionRegistry.create`. Returns `{"session_id", "name", "record", "workspace_shape"}`. 409 on name collision (carries `existing_session_id`).
  2. **`POST /api/session/<id>/turn`** at `substrate-ui/server.py`. Body: `{"text": "..."}`. Runs one turn via `SessionRegistry.turn_sync` (same seam the delegate wire uses). Returns `{"status", "final_seq", "record"}` — status one of `"parked" | "ended"`.
  3. **Finding 3 fix (piece-C review):** removed `SessionRegistry._locks: dict[str, asyncio.Lock]` and the `lock_for` method. Every caller of `turn_sync` — delegate + POST /turn — acquires the same per-session `threading.Lock`. One primitive, one invariant. `sprint 211` test `test_lock_for_returns_same_lock_on_repeat_call` rewritten as `test_per_session_threading_lock_is_stable_across_turn_sync_calls`; the new test also asserts `_locks` and `lock_for` no longer exist on the registry surface.
  4. **`turn_sync` grows an optional `resume_event_builder`** kwarg — a `Callable[[SessionManifest, Path], Any]` that runs UNDER the per-session lock and returns the effective resume event. The daemon's POST /turn handler uses this to compute `next_turn_index` atomically with the write (two concurrent handlers thus see two distinct pre-turn tail states, not the same pre-lock snapshot). Delegate's existing shape (pass a fully-formed `resume_event`) is preserved as backwards-compat.
  5. **`_daemon_driver_resolver`** in `server.py` maps a manifest's `driver` string to a Responder: `deterministic` → `DeterministicResponder`; `claude` / `gemini` → `CliResponder`; anything else → `OllamaResponder`. Richer than substrate-side `_default_model_resolver` (which knows only deterministic + Ollama).
  6. **`_build_session_topology_from_manifest`** in `server.py` — the closure the daemon injects into `SessionRegistry(session_topology_factory=...)` at boot. Rebuilds a `session_topology` per manifest per turn.
  7. **Module-scope `_SESSION_REGISTRY`** in `server.py`, initialized in `main()`. Every handler reads the same catalog + lock map.

## prerequisites

- Sprint 211 closed (SessionRegistry basic surface).
- Sprint 213b closed (`turn_sync` + `SessionEndedMidTurn`).
- Piece C review folded (2026-08-26).

## artifact contract

### Files

- `substrate-ui/session_registry.py` — remove `_locks` map + `lock_for` method; `turn_sync` grows `resume_event_builder` kwarg (backwards-compat with existing resume_event path); prose comment naming the finding-3 fix.
- `substrate-ui/server.py` — add `_SESSION_REGISTRY` module scope; `_daemon_driver_resolver`; `_build_session_topology_from_manifest`; two new POST routes; two new handler methods `_session_create` + `_session_turn`; `_read_json_body` helper.
- `substrate-ui/tests/test_session_registry_by_name.py` — rewrote the lock_for test.
- `substrate-ui/tests/test_server_session_create.py` — new. 4 cases.
- `substrate-ui/tests/test_server_session_turn.py` — new. 5 cases including two-concurrent-turns serialization.

### Assertions

- `POST /api/session` returns 200 with `session_id`, `name`, `record`, `workspace_shape ∈ {"flat","worktree","isolate"}`.
- A second POST with the same name returns 409 carrying `existing_session_id`.
- `POST /api/session/<id>/turn` runs one turn; reviewer's record grows with a `UserMessage` carrying `slash_source="daemon"` and the correct `turn_index` (0 for first turn, incremented for each subsequent).
- Two concurrent POST /turn calls on the same session BOTH complete under the per-session `threading.Lock`; reviewer's record ends with two `UserMessage`s at `turn_index` 0 and 1 (not 0 and 0 — the finding-3 fix + builder-under-lock pattern.)
- `POST /turn` on an unknown session_id returns 404; missing `text` returns 400.

### Command exit codes

- `uv run python -m pytest ../substrate-ui/tests/test_server_session_create.py ../substrate-ui/tests/test_server_session_turn.py -q` exits 0 (9 passed).
- Substrate-side full-suite regression clean.
- Ruff + mypy strict clean.

## observation contract

Sprint 214a discharges the record-level contract for the create + turn endpoints. Sprint 214 as carded named a subprocess-daemon end-to-end harness ("Spawn the daemon in a subprocess. Create session, send two turns, ... Kill the daemon between turns; restart; second turn still succeeds"); that's queued for sprint 214d once every endpoint ships. In-process, sprint 214a's tests spin the real `ThreadingHTTPServer` in a background thread, hit it with `urllib`, and assert the record's own tail — a full HTTP round-trip against the real handler + real registry + real Runtime.resume.

## halt conditions

- `dual_contract_fail` if the concurrent-turn serialization drops back to same-turn_index races (finding 3 regression).
- `bridge_mapping_required` if `_daemon_driver_resolver` needs a new dependency (none yet — CliResponder is already public via substrate.reference).

## definition of done

Two endpoints live. Finding-3 lock unification landed. Sprint 214b (list + by-name + delete) can dispatch on this landing.
