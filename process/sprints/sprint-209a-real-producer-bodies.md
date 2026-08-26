# Sprint 209a — real producer bodies (model / tool / park / session_end)

```yaml
---
id: 209a
status: closed
phase: daily-driver-piece-A
pass_kind: functional
---
```

## scope

Wire the four core Producer bodies on `substrate/src/substrate/topologies/session/__init__.py`. Sprint 205's scaffolds raised `NotImplementedError`; sprint 209b (bundled + CI record) and sprint 210 (piece-A observation contract) both need real bodies. Split out of sprint 209 during the 2026-08-25 SDD-techniques review: sprint 209 as carded assumed the four bodies existed. This card wires them; sprint 209b bundles + records.

- `park` — yields `Park(awaiting="UserMessage", turn_index=<from input>, reason=<from input>)` and completes. `deterministic=True`.
- `session_end` — yields `SessionEnded(reason=<from input>, total_turns=<from input>)` and completes. `deterministic=True`.
- `tool` — verbatim from `tool_loop._tool_factory` (import + reuse; tech spec §3 says "Verbatim from tool_loop"). `deterministic` = all-tools-deterministic AND-condition.
- `model` — three dispatch paths in order:
  1. `final=True` on the wrap-up input → force `FinalAnswer` synthesized from the last tool result.
  2. `script` given → yield the next scripted `ToolCall`; on exhaustion, `FinalAnswer` citing the last output. Parallels `tool_loop`'s script hook.
  3. Otherwise → call `driver.respond(prompt)`, yield `ModelReply(text, {}, turn_index)` then `FinalAnswer(text, step)`. Minimal driver-parse; sprint 210's real-model contract runs this path.
   Anti-spin: run of `_MAX_CONSECUTIVE_FAILS = 3` tool failures at the tail bails with a truthful `FinalAnswer` naming the last error.

New signature kwarg: `script: list[tuple[str, list[Any]]] | None = None` — CI dispatch hook.

## prerequisites

- Sprint 208.5 closed.

## context_files

- Sprint 205-208.5 output.
- `substrate/src/substrate/topologies/tool_loop/__init__.py:124-332` — reference model + tool factories.
- `substrate/src/substrate/kernel/runtime.py:156-218` — `_bootstrap` vs `_resume_bootstrap` dispatch.
- `substrate/src/substrate/testing.py` — F-API-4 primitives.

## signal contract

### Emits

- `model` → `ToolCall` / `ModelReply` / `FinalAnswer` per input dispatch.
- `tool` → `ToolResult` (via `_tool_factory` from tool_loop).
- `park` → one `Park`.
- `session_end` → one `SessionEnded`.

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate/src/substrate/topologies/session/__init__.py` — replace four `_scaffold_*_factory()` scaffolds with real bodies; add `script` kwarg; import `_tool_factory` from `tool_loop` as `_tool_loop_tool_factory`; add `_model_factory` + `_park_factory` + `_session_end_factory` + `_answer_text_from_results` + `_prompt_for_driver`.
- `substrate/tests/test_session_topology_end_to_end.py` — three tests using `assert_event` / `assert_no_event` primitives (F-API-4).

### Content assertions

- `substrate.topologies.session.session_topology(...)(TopologyBuilder())` succeeds with `producer_kinds` including all five (`model`, `tool`, `park`, `session_end`, `session_warning`) and ten triggers wired.
- Scripted one-turn resume produces a record whose payload-kind sequence includes `UserMessage → ToolCall → ToolResult → ToolCall → ToolResult → FinalAnswer → Park(reason=final_answer)`.
- Second-turn resume appends monotonically on the same record; two `Park` events with `turn_index` 0 and 1.
- `/exit` on a second turn lands `SessionEnded(reason="user_exit")` and the run finalises.
- `assert_replayable` is not called in this sprint's tests. See surfaced finding below.

### Command exit codes

- `uv run python -m pytest tests/test_session_topology_end_to_end.py -q` exits 0 (3 passed).
- `uv run ruff check src/substrate/topologies/session/ tests/test_session_topology_end_to_end.py` exits 0.
- `uv run mypy --strict src/substrate/topologies/session/` exits 0.

## observation contract

Three end-to-end tests fire session_topology against a real record with a scripted `DeterministicResponder`. The payload-kind sequence proves the ten-trigger loop closes correctly: `resume-on-user → model → tool → continue → model → tool → continue → model → FinalAnswer → park-on-final → Park → pause_await_input`.

## halt conditions to watch

- `substrate_primitive_missing` — surfaced. `Runtime(root, persistent=True).resume(topology, resume_event=...)` on a FRESH persistent root does NOT write `substrate.RunStarted`. `_resume_bootstrap` (`runtime.py:409-450`) is documented as "the run is CONTINUING, not opening; seq continues the existing sequence." Level-3(a) replay reads the deterministic-producer manifest off RunStarted, so `assert_replayable(root, "3a")` refuses with "no RunStarted." Sprint 214 (daemon session API core) needs to define the session-open dance — either a fresh `.resume()` writes RunStarted, or the daemon opens with `.run()` for a priming turn. Deferred to sprint 214 with a BLACKBOARD entry.

## definition of done

Four real bodies wired. Ten triggers still register cleanly. Three end-to-end tests pass. Sprint 209b (bundled + CI record) can dispatch on this landing. The substrate open-dance gap is filed for sprint 214.
