# Sprint 217a — daemon composes `Runtime.run` for turn 1 and `Runtime.resume` for turn 2+

```yaml
---
id: 217a
status: closed
phase: daily-driver-piece-B
pass_kind: architecture
---
```

## scope

`SessionRegistry.turn_sync` today drives `Runtime.resume(topology, resume_event=...)` for every turn from turn 1 through turn N. On a fresh session the record does not exist and `_resume_bootstrap` sees `max_seq == -1`; it writes no `substrate.RunStarted`, then injects the resume event as the first envelope. The record's `kinds[0]` is a `UserMessage`, not `substrate.RunStarted`. Every projection that keys on `RunStarted.payload.run_id` — `run_graph`, `explain_producer`, `trace_ancestry` — reads nothing on session records. Piece-C review finding 16 named this in the 2026-08-26 SPRINT 214c LANDED entry and pinned it to sprint 215/216; those sprints closed without addressing it. This card carries the debt.

Fix at the daemon, not the kernel. `Runtime.resume`'s docstring (`substrate/src/substrate/kernel/runtime.py:113-154` and `:423-426`) states one identity: continue an existing run, seq continues the existing sequence, no fresh `RunStarted`. The primitive is correct. `turn_sync` misuses it by handing it an empty record.

**The composition.** `turn_sync` detects the empty-record case and takes one of two paths.

1. **First turn (record does not exist or has zero envelopes).** Build the topology with a first-turn opener kwarg carrying the caller's `UserMessage`. Drive `Runtime.run(topology)`. `.run()` writes `substrate.RunStarted` at seq 0, fires the opener initial, which emits the first-turn `UserMessage` on the bus; `resume-on-user` fires `model`; the turn runs to park; the run pauses at `pause_await_input`. The record opens with `substrate.RunStarted` and carries `UserMessage` at seq 1. The `user_turns` KindCount view increments as it does on every later turn.
2. **Subsequent turns (record exists and has envelopes).** Unchanged. `Runtime.resume(topology, resume_event=UserMessage)` continues the sequence. `_resume_bootstrap` restores `next_seq`, folds views, injects the resume event with `producer=null`.

**Topology change.** `session_topology()` grows one kwarg — `first_turn_user_message: UserMessage | None = None`. When set, the topology declares a `session_open` producer whose body yields exactly that `UserMessage` once, and an `initial("session_open", input={})`. When `None`, no producer, no initial, no change to the resume flow. The kwarg is passed by `_build_session_topology_from_manifest` (`substrate-ui/server.py:153-176`), which grows a matching parameter.

**CI wrapper coexistence.** `ci_session_topology` at `substrate/src/substrate/topologies/session/ci.py` already registers `initial("driver_stepper", ...)` that emits the first turn's `UserMessage` from a scripted sequence. Two initials firing at `.run()` would land two `UserMessage` envelopes at turn 0 and drift every downstream `_turn_index` read by one. The gate closes the collision: `session_open` fires only when `first_turn_user_message is not None`. `ci_session_topology` leaves the kwarg at its default `None` and continues to supply the first `UserMessage` via `driver_stepper`. The base `session_topology`, driven by the daemon, sets the kwarg and fires `session_open`. The two initials never coexist in one build.

**Edge case: fresh session receiving a non-`UserMessage` resume event.** SIGTERM shutdown (`_shutdown_all_sessions`) injects `SessionEndRequested` into every non-ended session, including a fresh one whose record does not exist. On empty record + non-`UserMessage` resume event, `turn_sync` raises the typed `FreshSessionRequiresUserMessage` and writes nothing to the manifest — the raise is atomic; either the resume ran and the manifest transitioned, or nothing was written. The guard lives in the primitive so every future caller (a CLI verb, an admin endpoint, a follow-up daemon shape) inherits the typed refusal without re-implementing it.

The caller (`_shutdown_all_sessions`) catches the raise, transitions the manifest to `"ended"` at its own layer, and buckets the outcome. The result dict grows one bucket to match: `{"ended": N, "skipped_fresh": K, "skipped_ended": M, "failed": P}` — a fresh session that never opened is distinguishable at the SIGTERM exit log from a session whose status was already `"ended"` before the sweep. The old bucket `skipped` splits along the actual reason.

**CI record regeneration.** `substrate/src/substrate/topologies/session/records/ci_session_topology.record` was recorded against the old resume-only shape. Post-fix its first envelope changes from `UserMessage` to `substrate.RunStarted`. `substrate/tests/test_session_topology_bundled.py` and `substrate/tests/test_session_topology_e2e.py` re-record and re-verify. The Cascade/native pattern applies: seeded, deterministic, byte-stable, diff-to-zero on regeneration.

**What this closes.** Piece-C review finding 16, deferred at 2026-08-26. Every session record from this landing forward carries `substrate.RunStarted` at seq 0. Projections that read `run_id` from the payload return the session's run identity. The `_launch`-style pattern of "background the run, return after `RUN_STARTED` lands" works against session records.

**What this does not close.** Records already on disk from sprints 214a-216 remain in the old shape (`UserMessage` at seq 0). Reading those old records via `run_graph`, `explain_producer`, or `trace_ancestry` still returns nothing. That is a data artefact of the debt window. SDD hard rule 12 forbids rewriting the records in place; the audit trail is the work. The follow-up card that owns the legacy shape has three options and does not start from scratch:

- **Fork.** Synthesize a new record with `substrate.RunStarted` at seq 0, then replay the legacy record's envelopes with `seq` shifted by one. Repoint the manifest's `record_root` to the new record. Leave the original record on disk under a `_pre_217a/` sibling as the archive.
- **Projection shim.** A read-time layer that synthesizes a `RunStarted`-shaped payload from the manifest when a consumer keys on it against a legacy record. The record stays as it is; the shim answers on its behalf. No back-fill; every consumer that reads a projection gets a consistent shape.
- **Accept the drift.** Legacy session records stay non-conformant. Every consumer written between now and forever tolerates both shapes explicitly.

**Cross-piece invariant while the debt window is open.** Any consumer added between 217a and the follow-up must tolerate both record shapes. Piece D at sprint 218+ ships CLI verbs (`substrate session ls`, `substrate chat --resume`, slash commands) that read session records via the same `run_graph` and `explain_producer` seams that read nothing on legacy records. The CLI cannot assume the post-217a shape unless the migration ran. Piece D's cards MUST name this invariant explicitly and take one of the three options above — or 217a's follow-up must land before Piece D opens.

## prerequisites

- Sprint 216 closed.

## context_files

- `substrate/src/substrate/kernel/runtime.py` — `_resume_bootstrap` at `:423-467`, `.run()` and `.resume()` docstrings at `:113-154`, `.run()` writes `RunStarted` at `:381`.
- `substrate-ui/session_registry.py` — `turn_sync` at `:382-471`, `_run_resume_sync` (invoke shape and per-call event loop).
- `substrate-ui/server.py` — `_build_session_topology_from_manifest` at `:153-176`, `_shutdown_all_sessions` at `:114-150`.
- `substrate/src/substrate/topologies/session/__init__.py` — `session_topology` signature at `:266`, existing initials, `resume-on-user` trigger reads `assembled_prompt` from the injected `UserMessage`.
- `substrate/src/substrate/topologies/session/ci.py` and `records/ci_session_topology.record` — CI seed + record to regenerate.
- BLACKBOARD entry SPRINT 214c LANDED (2026-08-26), the paragraph beginning "Substrate-primitive gap surfaced".

## signal contract

### Emits (new)

- `substrate.RunStarted` — on turn 1, at seq 0, before any session vocabulary. Standard `.run()` envelope; nothing new authored.
- `UserMessage` — on turn 1, at seq 1, emitted by the `session_open` producer with `producer=<session_open>` (not `producer=null` as on the resume path). Payload shape identical to the resume-path injection: `text`, `turn_index=0`, `assembled_prompt`, `slash_source`.

### Consumes

- `substrate-ui/session_registry.py::turn_sync` grows the two-path branch.
- `substrate-ui/server.py::_build_session_topology_from_manifest` grows the `first_turn_user_message` kwarg.

### Invariants

- `Runtime.resume` semantics unchanged. Docstring at `runtime.py:113-154` and `:423-426` untouched.
- `Runtime.run` semantics unchanged. `_run_bootstrap` at `runtime.py:381` untouched.
- Turn 2+ path unchanged. Only the branch that hits an empty record diverges.
- `_turn_index` still reads `user_turns.value() - 1`; increments by 1 on both paths.
- Every session record from this landing carries `substrate.RunStarted` at seq 0.

## artifact contract

### Files created

- `substrate-ui/tests/test_session_registry_first_turn_uses_run.py` — three tests: empty record + UserMessage → `.run()` fires, record opens with `substrate.RunStarted` at seq 0 and `UserMessage` at seq 1; non-empty record + UserMessage → `.resume()` fires, `RunStarted` count unchanged; empty record + `SessionEndRequested` → `FreshSessionRequiresUserMessage` raised.
- `substrate-ui/tests/test_server_shutdown_skips_fresh_sessions.py` — three tests: SIGTERM shutdown against a fresh session buckets it under `skipped_fresh` and the manifest transitions to `"ended"`; the fresh session's record directory stays empty on disk (`Runtime.run` never ran); an already-`"ended"` session buckets under `skipped_ended`, and the two buckets stay distinct in the return dict across a mixed sweep.

### Files modified

- `substrate/src/substrate/topologies/session/__init__.py` — `session_topology()` grows `first_turn_user_message` kwarg; when set, declares `session_open` producer + `initial("session_open", input={})`.
- `substrate-ui/session_registry.py` — `turn_sync` detects empty record, branches to `.run()` with the topology factory called with `first_turn_user_message=`; new `FreshSessionRequiresUserMessage` typed exception in the module `__all__`; `_run_run_sync` helper added alongside `_run_resume_sync`.
- `substrate-ui/server.py` — `_build_session_topology_from_manifest` accepts `first_turn_user_message` and forwards; `_shutdown_all_sessions` catches `FreshSessionRequiresUserMessage`, transitions the manifest to `"ended"` via `_SESSION_REGISTRY.update_status(sid, "ended")`, and buckets under `skipped_fresh`; the return dict grows from `{ended, skipped, failed}` to `{ended, skipped_fresh, skipped_ended, failed}`; the SIGTERM handler's exit log prints all four counts.
- `substrate/src/substrate/topologies/session/records/ci_session_topology.record` — regenerated. Diff-to-zero verified on second regeneration from the same seed.
- `substrate/tests/test_session_topology_bundled.py` and `substrate/tests/test_session_topology_e2e.py` — assertions on first-envelope kind update from `"UserMessage"` to `"substrate.RunStarted"`; add explicit checks that `UserMessage` lands at seq 1 with `producer=<session_open>` on first turn and at seq N with `producer=null` on later turns.
- `substrate-ui/tests/test_server_session_turn.py` and every piece-B test that inspects a first-turn record — first-envelope assertion updated.

### Content assertions

- Grep on `substrate/src/substrate/kernel/runtime.py` shows zero changes.
- `session_topology` signature carries `first_turn_user_message: UserMessage | None = None`.
- `SessionRegistry.turn_sync` contains one `read_record` call before the topology factory call.
- `FreshSessionRequiresUserMessage` appears in `substrate-ui/session_registry.py` module `__all__`.

### Command exit codes

- `cd substrate && uv run python -m pytest substrate/tests/test_session_topology_bundled.py substrate/tests/test_session_topology_e2e.py -q` returns 0.
- `cd substrate && uv run python -m pytest ../substrate-ui/tests -q` returns 0.
- `cd substrate && uv run python -m pytest -q` (full suite) returns 0.
- `cd substrate && uv run ruff check ../substrate-ui substrate/src substrate/tests` returns 0.
- `cd substrate && uv run mypy --strict substrate/src ../substrate-ui/server.py ../substrate-ui/session_registry.py` returns 0.

## observation contract

Boot the daemon against a temp base dir. `POST /api/session {"driver":"deterministic"}`. `POST /api/session/<id>/turn {"text":"hello"}`. `curl /api/records/<record-path>` (the record_root from the create response) — the returned events open with `substrate.RunStarted` at seq 0, followed by `UserMessage` at seq 1 with `slash_source="daemon"` and `turn_index=0`, followed by the tool-loop cycle, `Park`, `TerminationMatched`. `GET /api/session/<id>/events` streams the same sequence to an SSE client. `POST /api/session/<id>/turn {"text":"again"}` — the record continues; the second `UserMessage` lands with `producer=null` via `_resume_bootstrap`; `RunStarted` count stays at 1.

## halt conditions

- `dual_contract_fail` if any session projection (`run_graph`, `explain_producer`, `trace_ancestry`) reads inconsistent state on a first-turn record after the compose.
- `vocabulary_change_required` if the CI regen surfaces a schema shift on `session_open`'s `UserMessage` envelope that the vocab has not ratified.
- `awaiting_architect_decision` on the retroactive-migration question: whether records already on disk from sprints 214a-216 get a one-time back-fill or stay in the old shape. This card ships the forward fix; the migration question is separate.

## definition of done

Every new session record opens with `substrate.RunStarted` at seq 0. `Runtime.resume`'s docstring is unchanged. `SessionRegistry.turn_sync` composes the two primitives at the daemon layer. The CI record regenerates and diffs to zero on a second regeneration. Every piece-B test that inspects a first-turn record passes against the new shape. Piece-C review finding 16 closes. Sprint 217 (the `/api/agent` compat adapter) inherits status `blocked-on-217a` in its card header and opens after 217a lands.
