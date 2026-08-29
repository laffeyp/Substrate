# Sprint 237 — `run_topology_sync` primitive; collapse four sync-runner sites

```yaml
---
id: 237
status: pending
phase: architecture
pass_kind: architecture
---
```

## scope

REVIEW-2026-08-28 Q10 named the duplicate work:

- `_run_resume_sync(topology, record_root, ...)` in session_registry.py.
- `_run_run_sync(topology, record_root, ...)` in session_registry.py.
- `_run_child_to_answer(topology, record_root, timeout_seconds)` in
  delegate.py.
- The inline `asyncio.run(api.Runtime(root).run(topology_factory))`
  in server.py `_topology_run` (sprint 225a).

Four sync runners, four worker-thread bodies, one substrate primitive
underneath. Each re-implements cross-thread cancel via
`loop.call_soon_threadsafe(task.cancel)` and each re-implements
timeout + cancel-grace.

Ship `substrate.testing.run_topology_sync(topology, record_root, *,
mode="run"|"resume"|"until_answer", resume_event=None,
timeout_seconds=None, handle_out=None)` (or `substrate.api` — venue
decision pending Architect ratification). Four callers collapse to one.

The primitive lives on the substrate side because it is a
substrate-runtime concept (fresh event loop + Runtime.run/resume in
a worker thread with cross-thread cancel), not a daemon concept.

## prerequisites

- REVIEW-2026-08-28 ratified.
- Sprint 235 + 236 closed (their splits shape the call sites the
  primitive would collapse).

## artifact contract

### Files

- `substrate/src/substrate/testing/sync_runner.py` (or
  `substrate/src/substrate/api.py` growth) — one function + tests.

### Assertions

- All four existing sync-runner tests pass against the shared primitive.
- Delegate's timeout + cancel-grace behavior unchanged (52 delegate
  tests).
- SessionRegistry's fresh-vs-populated dispatch behavior unchanged
  (all 217a invariant tests).
- Server's `_topology_run` await_completion=true/false behavior
  unchanged (sprint 225a's 4 tests).

### Tests

- New: `test_run_topology_sync_primitive.py` — all four modes covered.
- Existing tests continue to pass after callers adopt the primitive
  (one follow-up sprint per caller).

## signal contract

Emits: (none — the primitive is a synchronous wrapper over Runtime,
no new runtime emit sites; it just holds the loop + worker thread).

## observation contract

Behavior across the four callers unchanged after adoption. Each
follow-up caller-adoption sprint (delegate, session_registry, server)
verifies via existing tests.

## halt conditions

- `bridge_mapping_required` if the primitive needs a new kernel
  surface (e.g. a Runtime.run_sync convenience method).
- `dual_contract_fail` if any caller's timeout/cancel semantics drift
  after adoption.

## definition of done

One primitive exports; three follow-up caller-adoption sprints queued
(238-240 or similar). Cross-thread cancel logic lives once.
