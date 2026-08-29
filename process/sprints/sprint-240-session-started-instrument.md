# Sprint 240 — wire SessionStarted instrument on RunStarted

```yaml
---
id: 240
status: closed
phase: 6
pass_kind: functional
---
```

## scope

`substrate/src/substrate/topologies/session/__init__.py` declares
`SessionStarted` as one of eight session Structs (`vocabulary.md` v0.1
line 15). Comment at line 579 promises: "SessionStarted fires via an
instrument on `substrate.RunStarted` (sprint 209 wires it)." Grep
`SessionStarted\(` returns exactly one hit — the class definition — as
of 2026-08-28. Sprint 209 never wired the instrument.

Closes REVIEW-2026-08-28-piece-g-full SDD-1 + SUB-1 + SUB-3 (folded).
The vocabulary lock's own promise gets honored, and the substrate-ui
`terminal.ts` moves `DRIVER_SESSION_STARTED` from a daemon-ack seam to
a record-envelope seam (SUB-1 fix: one vocabulary per event).

Two files. One concept (SessionStarted wiring — instrument plus the
two new session_topology params the SessionStarted schema needs).

## prerequisites

- Piece-B sprints 205-208 (session topology exists).

## context_files

- `substrate/src/substrate/topologies/session/__init__.py:70-82` —
  the SessionStarted Struct.
- `substrate/src/substrate/topologies/session/__init__.py:577-583` —
  the comment that names sprint 209.
- `substrate/src/substrate/kernel/topology.py:290-348` — the
  `instrument` primitive.
- `substrate-ui/server.py::_build_session_topology_from_manifest` —
  the daemon-side factory that already carries every field
  `SessionStarted` needs off the manifest.

## artifact contract → Files created/modified

- `substrate/src/substrate/topologies/session/__init__.py` — adds
  `_session_started_factory(session_id, seed, driver_name,
  driver_context_tokens, tool_names, workspace_path, workspace_shape,
  bundle, parent_session_id, parent_seq_at_call)`. Adds
  `workspace_shape: str = "flat"` + `bundle: str | None = None`
  parameters to `session_topology`. Adds one `b.instrument(...)` call
  in `topo(b)` binding on `api.RUN_STARTED` and yielding the built
  SessionStarted.
- `substrate/tests/test_session_started_instrument.py` — new.
  Builds a session_topology + drives one turn against
  DeterministicResponder + reads the record + asserts one
  SessionStarted envelope lands at (or near) seq 2 (RunStarted → the
  synthesized TriggerFired → SessionStarted) with every schema field
  populated.

Companion edit (not owned by this sprint but landed alongside so the
daemon path exercises it):

- `substrate-ui/server.py::_build_session_topology_from_manifest` —
  passes `workspace_shape=manifest.workspace_shape`,
  `bundle=manifest.bundle`, `parent_session_id=manifest.composite_of`
  to `session_topology`. Ships in the same commit because without it,
  the daemon path never exercises the new instrument.

## signal contract → Emits

- `SessionStarted{session_id, seed, driver_model, driver_context_tokens,
  tool_suite, workspace_path, workspace_shape, bundle, baseline,
  parent_session_id, parent_seq_at_call}` — once per run, at seq 2
  (or wherever the instrument's synthesized TriggerFired lands per the
  `instrument` primitive).

## observation contract

- New pytest (details above) — session-topology run yields exactly one
  SessionStarted with matching payload.
- Grep after landing: `grep -rn "SessionStarted(" substrate/src/`
  returns two hits (the class definition + the factory-yield inside
  `_session_started_factory`).
- Substrate-ui `npm run signals` chain PASS — the session fixture's
  first non-lifecycle envelope on the record is `SessionStarted`;
  terminal.ts's new SSE branch (SUB-1 fix, landed alongside) reads
  it and fires `DRIVER_SESSION_STARTED` from the record instead of
  from the POST-ack. `checkDriverSessionBookends` still passes.

## halt conditions

- `dual_contract_fail` if the pytest sees zero SessionStarted or more
  than one per run.

## definition of done

`_session_started_factory` + the instrument on RunStarted land in
`session/__init__.py`. Daemon factory threads the two new
kwargs. New test PASS. Grep confirms the emit site exists.
Substrate-ui side simplifies once terminal.ts moves to record-side
consumption (companion edit in the same review-response commit).
