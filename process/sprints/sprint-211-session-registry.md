# Sprint 211 — SessionRegistry module + manifest + boot scan

```yaml
---
id: 211
status: pending
phase: daily-driver-piece-C
pass_kind: architecture
---
```

## scope

Author `substrate-ui/session_registry.py` (a substrate-ui module, since the daemon lives there): in-memory `SessionRegistry` class with atomic-create by name, name → session_id lookup, per-session `asyncio.Lock` dict. Read/write the name index at `~/.substrate/sessions/by-name.json` under `fcntl.flock`. Write manifests at `~/.substrate/sessions/<session_id>/manifest.json` on session open (schema per TECH-SPEC §5). Boot-scan every `~/.substrate/sessions/*/` at daemon start: check `api.recover_open_segment` — non-None → `status="interrupted"`; sealed record with RunFinalised → `status="ended"`; otherwise `status="parked"`. Rebuild in-memory registry from manifests + name index.

## prerequisites

- Sprint 210 closed (piece A done).

## context_files

- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §5 (manifest shape + name index + concurrency contract).
- `substrate-ui/server.py` — reference for existing threading model + storage patterns.
- `substrate/src/substrate/kernel/runtime.py:191` (`_hot_segment`), `:236-267` (finally sealing), `:409-450` (`_resume_bootstrap`).

## artifact contract

### Files

- `substrate-ui/session_registry.py` — new.
- `substrate-ui/server.py` — add boot-scan hook at startup.

### Assertions

- `SessionRegistry.create(name, ...)` returns 409-shaped `{"error": "name already taken", "existing_session_id": "..."}` on collision; atomic via `fcntl.flock` on `by-name.json`.
- `SessionRegistry.by_name("reviewer")` returns the session_id.
- Boot scan of a directory with a hot segment sets manifest `status="interrupted"`; sealed → `"ended"`; neither → `"parked"`.
- Two-parallel-create test: 100 concurrent `create(name=f"s{i}")` calls all succeed; no id collision; no by-name.json corruption.

### Tests

- `substrate-ui/tests/test_session_registry_by_name.py`
- `substrate-ui/tests/test_session_registry_name_collision.py`
- `substrate-ui/tests/test_session_manifest_survives_daemon_restart.py`

## observation contract

Create three named sessions; kill the daemon (SIGKILL); restart; assert all three show up in `substrate session ls` with correct status (running → interrupted; parked → parked; ended → ended).

## halt conditions

- `bridge_mapping_required` if `fcntl.flock` needs a WORKING_AGREEMENT mapping (stdlib, likely not needed).

## definition of done

Registry + manifest + boot scan all pass tests. Sprint 212 (delegate per-call args) can dispatch.
