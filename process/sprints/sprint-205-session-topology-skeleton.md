# Sprint 205 — session topology skeleton + event Structs

```yaml
---
id: 205
status: closed
phase: daily-driver-piece-A
pass_kind: architecture
---
```

## scope

Author `substrate/src/substrate/topologies/session/__init__.py` with `session_topology(*, driver, driver_name, driver_context_tokens, seed, tools, per_turn, max_turns, turn_max_steps, session_id, workspace_path, parent_session_id, parent_seq_at_call)`. Declare the eight frozen msgspec Structs that ride the record: SessionStarted, UserMessage, ModelReply, Park, SessionEnded, SessionEndRequested, TranscriptCompacted, SessionWarning. `SessionCompositeSpec` is NOT declared here — it is a daemon-internal dataclass returned by `pair_coding_application` (sprint 225) and lives in `applications/pair_coding_composite.py`; it never lands on a substrate record and does not belong in the session topology's schemas. Sprint 202's vocab lock is amended in parallel (post-review 2026-08-25) to remove `SessionCompositeSpec` from `0.6.json` — no record ever carries the kind, so locking it as a signal was wrong.

Also author `substrate/src/substrate/topologies/session/prompts/default.md` — the unconditional fallback role prompt required by TECH-SPEC §1.6.5 layer 4. Without it, any session opened without an explicit `--role` (which defaults to `"default"`) raises `RegistrationError` at session open. Sprint 210's observation contract depends on this file existing. `reviewer.md`, `planner.md`, `tester.md`, `explainer.md` land in a follow-on sprint (or here if the Agent has time — they are role-narrowing prompts, one short paragraph each). Post-review 2026-08-25. Register four producer kinds (`model`, `tool`, `park`, `session_end`) with their schemas. Register three Views (`results`, `user_turns`, `model_failures` — the last a small subclass in `session/views.py`). Do NOT wire triggers or termination yet; that is 206. This sprint's `session_topology` builds without triggers — `build()` will fail cleanly, which is how the follow-on sprint knows it inherits a scaffolded surface.

## prerequisites

- Sprint 204 closed and ratified — piece 0 done.

## context_files

- `substrate/process/signals/0.6.json` — kind names to match.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §3 (signature + Producers + Structs), §1.6.5 (seed inputs the topology accepts).
- `substrate/src/substrate/kernel/topology.py` — `TopologyBuilder` + `producer_kind` + `Budget`.
- `substrate/src/substrate/topologies/tool_loop/__init__.py` — reference shape for `model` + `tool` Producers.
- `substrate/src/substrate/kernel/views.py` — `KindBuffer`, `KindCount`, `BufferView` pattern for the `model_failures` custom view.

## signal contract

### Emits

Producer schemas registered (nothing fires yet — no triggers wired):

- `model` kind: `ToolCall`, `FinalAnswer`, `ModelReply`, `TranscriptCompacted`
- `tool` kind: `ToolResult`
- `park` kind: `Park`
- `session_end` kind: `SessionEnded`

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate/src/substrate/topologies/session/__init__.py` — new.
- `substrate/src/substrate/topologies/session/views.py` — new. Custom View subclass for `model_failures` (filters `substrate.ProducerFailed` where `producer.kind == "model"`).

### Content assertions

- Nine msgspec Structs present, all `frozen=True`.
- No Struct name uses `substrate.` prefix (validate via `is_reserved`).
- `session_topology` signature matches TECH-SPEC §3 exactly (12 kwargs).
- Four `b.producer_kind(...)` calls with the correct schemas.
- Three `b.view(...)` calls.
- Import from `substrate.api` only (F-API-6).

### Command exit codes

- `uv run python -c "from substrate.topologies.session import session_topology; print('import OK')"` exits 0.
- `uv run ruff check src/substrate/topologies/session/` exits 0.
- `uv run mypy --strict src/substrate/topologies/session/` exits 0.
- A build-attempt test proves the scaffold state sprint 206 inherits: `TopologyBuilder.build()` completes without error, and the returned `Registration` carries four producer_kinds (`model`, `tool`, `park`, `session_end`), three views (`results`, `user_turns`, `model_failures`), zero triggers, and `termination is None`. (Post-sprint-205 correction 2026-08-25: `build()` does not statically check for a missing termination — that would fire at `Runtime.run` time. The scaffold contract is the registration shape, not a build-time raise.)

## observation contract

Architecture sprint; no runtime behavior yet. Verify: `session_topology` builds far enough to hit the missing-terminal error, not earlier. That proves Producers + Views + Structs are correctly registered.

## halt conditions to watch

- `vocabulary_change_required` if a Struct field turns out to need a shape not covered by v0.6.
- `bridge_mapping_required` if a new external SDK creeps in (no external SDK expected).
- `comprehension_failed` if the twelve kwargs cannot be restated as one bounded paragraph.

## definition of done

Import succeeds. Ruff + mypy strict clean. Nine Structs frozen and non-reserved. Sprint 206 (triggers + termination) can dispatch.
