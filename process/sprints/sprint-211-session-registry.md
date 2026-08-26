# Sprint 211 — SessionRegistry module + manifest + boot scan

```yaml
---
id: 211
status: closed
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

**Scope amendment folded 2026-08-26.** The original observation contract calls for `substrate session ls` — the CLI verb that lands with sprint 222 and does not exist yet. Rescoped in place: sprint 211 discharges an in-process restart simulation. `test_boot_scan_restores_multiple_sessions_across_restart` creates two sessions with a first `SessionRegistry`, finalises one via `ci_session_topology`, then constructs a SECOND `SessionRegistry` against the same base directory. The fresh registry's `boot_scan()` reads by-name.json + every manifest.json and reclassifies status per the record's own last envelope: `substrate.RunFinalised` → `ended`, `substrate.TerminationMatched(decision="pause-await-input")` → `parked`, torn tail or gap → `interrupted`, everything else → `interrupted`. Sprint 222 adds the SIGKILL/restart harness driven through the shipped CLI.

**Two real bugs surfaced during the sprint 211 tests and fixed at the root.**

  1. `_scan_record_status` initially used `api.recover_open_segment(record_root)` to detect a torn tail. That function is a WRITE operation — it truncates a torn tail and returns the frames-kept count (not None — see `record/record.py:304-324`). Rewritten to read the record's last envelope: RunFinalised → ended, TerminationMatched-pause-await-input → parked, anything else → interrupted.
  2. `_FlockedIndex` initially took the flock on `by-name.json` itself. `_atomic_write_json` writes via tempfile + `os.replace`, which swaps the inode. The next caller's `open()` gets the NEW inode and its flock is on a different lock object — no mutual exclusion. Rewritten to take the flock on a stable sibling `.by-name.lock` file that atomic-rename never touches. The 100-concurrent-create test surfaced this; the fix ships all 100 entries to disk in a single run.

## halt conditions

- `bridge_mapping_required` if `fcntl.flock` needs a WORKING_AGREEMENT mapping (stdlib, likely not needed).

## definition of done

Registry + manifest + boot scan all pass tests. Sprint 212 (delegate per-call args) can dispatch.
