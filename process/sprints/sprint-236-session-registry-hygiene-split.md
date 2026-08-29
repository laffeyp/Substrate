# Sprint 236 — session_registry.py hygiene split into a package

```yaml
---
id: 236
status: pending
phase: hygiene
pass_kind: architecture
---
```

## scope

REVIEW-2026-08-28 Q3 flagged `substrate-ui/session_registry.py` at 1,232
lines, one `SessionRegistry` class with 18 public methods, `turn_sync`
at 134 lines. The three-way split the piece-C review proposed for
`delegate.py` (into `dispatch.py`, `context.py`, `model.py`) applies:

- `session_registry/__init__.py` — re-exports the public surface
  (SessionRegistry, SessionManifest, exception classes, STATUS_*
  constants). Every existing `from session_registry import <name>` keeps
  working.
- `session_registry/manifest.py` — SessionManifest Struct, JSON
  serialization (`_manifest_to_dict`, `_manifest_from_dict`,
  `_atomic_write_json`), STATUS_* constants, SessionStatus Literal.
- `session_registry/errors.py` — SessionEndedMidTurn,
  FreshSessionRequiresUserMessage, TornRecordOnResume, NameCollision.
- `session_registry/name.py` — by_name index + fcntl.flock discipline
  (_flocked, _read_by_name_index, _write_by_name_index).
- `session_registry/mutation.py` — set_driver, set_name, set_tools,
  set_per_turn, update_status.
- `session_registry/turn.py` — turn_sync, _run_run_sync, _run_resume_sync,
  try_enqueue_turn, dequeue_turn, next_turn_index, worker-thread
  coordination, cross-thread cancel.
- `session_registry/core.py` — the SessionRegistry class itself; uses
  the modules above.

Contract: dual contract unchanged before and after; every existing
substrate-ui test passes; no behavior change.

## prerequisites

- Sprint 235 closed (server.py handler split establishes the shape).

## artifact contract

### Files

- `substrate-ui/session_registry/` (new package, 7 files).
- `substrate-ui/session_registry.py` — deleted; git history preserves.

### Assertions

- Every existing substrate-ui test passes unchanged.
- Every file in `session_registry/` under 400 lines; `turn.py`'s
  `turn_sync` still one function but its helpers (fresh-record vs
  populated-record branch) split into named sub-functions with
  docstrings.
- `SessionRegistry.turn_sync` under 80 lines after the helper split.

### Tests

- Existing tests re-run.
- New: `test_session_registry_package_reexports.py`.

## signal contract

Emits: (none — hygiene split; no runtime emit sites in the diff).

## observation contract

`test_session_composite_cascade_end_225b.py` and every 217a invariant
test continue to pass (those exercise turn_sync end-to-end through
real HTTP).

## halt conditions

- `dual_contract_fail` if any test drifts.

## definition of done

session_registry.py is gone; session_registry/ is a package; turn_sync
under 80 lines after helper extraction.
