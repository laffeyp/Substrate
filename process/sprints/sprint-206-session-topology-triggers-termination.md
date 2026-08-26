# Sprint 206 — session topology triggers + termination

```yaml
---
id: 206
status: closed
phase: daily-driver-piece-A
pass_kind: architecture
---
```

## scope

Wire ten triggers on the sprint-205 session topology per TECH-SPEC §3 plus the post-review addition: `run-tool`, `continue`, `wrap-up`, `park-on-final`, `park-on-model-error`, `park-on-interrupt`, `resume-on-user`, `end-on-exit`, `end-on-cap`, `end-on-user-end`. The `park-on-interrupt` trigger subscribes to `substrate.ProducerCancelled` where `producer.kind == "model"` and starts `park` with `reason="interrupt"`. Without it, `POST /api/session/<id>/interrupt` (sprint 215) writes `ProducerCancelled` and no `Park` follows, so the termination policy never matches and the session hangs. Post-review 2026-08-25. Compose termination as `any_of(pause_await_input(when=lambda ctx: ctx.event.kind == "Park", resume_condition="UserMessage"), threshold_count("SessionEnded", 1))`. Add a build-time assertion that refuses `all_completed` in any composed policy (recursively) — the `kernel/policies.py:97` trap must not silently reach a session record.

## prerequisites

- Sprint 205 closed.

## context_files

- Sprint 205 output: `substrate/src/substrate/topologies/session/__init__.py`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §3 (trigger table + termination + build-time assertion).
- `substrate/src/substrate/kernel/policies.py` — `pause_await_input`, `any_of`, `all_completed` (the one to refuse), `threshold_count`.
- `substrate/src/substrate/topologies/tool_loop/__init__.py:399-437` — reference wiring for `run-tool`, `continue`, `wrap-up`.

## signal contract

### Emits

- Triggers fire the four terminal Producers as declared.
- Termination emits `substrate.TerminationMatched{policy: "any_of(pause_await_input,threshold_count)", decision: "pause-await-input"|"finalise-run", resume_condition: "UserMessage"?}` per `kernel/runtime.py:730-741`.

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate/src/substrate/topologies/session/__init__.py` — grow it with nine triggers + termination + `_flatten_policies` + `_refuse_all_completed` helper.

### Content assertions

- Nine `b.trigger(...)` calls with the ids from TECH-SPEC §3.
- Every trigger's `subscription`, `predicate`, `starts`, `input_builder`, `policy` matches the tech-spec row.
- Termination clause matches verbatim: `api.any_of(api.pause_await_input(when=..., resume_condition="UserMessage"), api.threshold_count("SessionEnded", 1))`.
- Build-time assertion: `session_topology(...)` when handed a policy containing `all_completed` at any nesting depth raises `RegistrationError` with the message naming `kernel/policies.py:97`.

### Command exit codes

- `uv run python -m pytest tests/test_session_topology_refuses_all_completed.py -q` exits 0.
- `uv run ruff check src/substrate/topologies/session/` exits 0.
- `uv run mypy --strict src/substrate/topologies/session/` exits 0.

## observation contract

Build the topology with a `DeterministicResponder`; run one turn end-to-end with a fixture UserMessage; confirm the record ends on `Park{reason: "final_answer"}` with `RunResult.status == "paused"`. Then inject a second UserMessage via `Runtime.resume`; confirm second turn continues seq sequence. Third turn = `/exit`; confirm `SessionEnded{reason: "user_exit"}` lands and status finalises.

Expected event trace: `substrate.RunStarted` → `SessionStarted` → `UserMessage(turn_index=0)` → `substrate.TriggerFired(resume-on-user)` → `substrate.ProducerStarted(model)` → `ModelReply` → `FinalAnswer` → `substrate.TriggerFired(park-on-final)` → `Park(reason: "final_answer", turn_index: 0)` → `substrate.TerminationMatched(decision: pause-await-input)`.

## halt conditions to watch

- `dual_contract_fail` if the build-time `all_completed` assertion regresses (tests must lock it).
- `comprehension_failed` if the nine triggers cannot each be restated in one sentence.

## definition of done

All nine triggers wired. Termination composed. Build-time assertion refuses `all_completed`. Two-turn + `/exit` end-to-end fixture green. Sprint 207 (transcript renderer) can dispatch.
