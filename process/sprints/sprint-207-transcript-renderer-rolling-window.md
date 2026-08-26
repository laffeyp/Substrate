# Sprint 207 — transcript renderer + rolling window

```yaml
---
id: 207
status: closed
phase: daily-driver-piece-A
pass_kind: architecture
---
```

## scope

Author `substrate/src/substrate/topologies/session/transcript.py` with `render_transcript(record_root, seed, per_turn, driver_context_tokens, driver_headroom_frac=0.6, strategy="rolling_window", turn_index_now) -> RenderedTranscript`. Structs `RenderedTranscript(prompt_text, threaded_from_turn, turns_dropped, tokens_estimated, compaction_events)`. Helpers `_compute_k`, `_group_by_turn`, `_est_tokens`, `_est_tokens_events`, `_render`. Rolling-window algorithm per TECH-SPEC §3a. The `model` Producer factory in `session/__init__.py` grows to call `render_transcript` at the start of each firing and yields any pending `TranscriptCompacted` events before its first `ToolCall`/`ModelReply`.

## prerequisites

- Sprint 206 closed.

## context_files

- Sprint 205-206 output: `substrate/src/substrate/topologies/session/__init__.py`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §3a (algorithm + cadence rules for TranscriptCompacted).
- `substrate/process/signals/0.6.json` — `TranscriptCompacted` schema + cadence invariant.
- `substrate/src/substrate/api.py` — `read_record`, `narrate` (for comparison to the prose renderer's shape).
- `substrate/src/substrate/kernel/runtime.py:530` — VOCAB_VERSION reference.

## signal contract

### Emits

- `TranscriptCompacted{strategy: "rolling_window", dropped_seq_range: (int, int), kept_seq_start: int, reason: "driver_window_exceeded" | "K_bound", tokens_before: int, tokens_after: int}` — fires only when `turns_dropped > 0`. Cadence: at most one per model firing; grader invariant per §3a.

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate/src/substrate/topologies/session/transcript.py` — new.
- `substrate/src/substrate/topologies/session/__init__.py` — model factory grows a leading `TranscriptCompacted` yield loop.

### Content assertions

- `RenderedTranscript` frozen msgspec Struct with the five fields above.
- `_compute_k` returns `max(1, budget // avg_turn_tokens)` where `budget = int(driver_context_tokens * 0.6) - seed_tokens - per_turn_tokens`; returns 0 iff `budget <= 0`.
- `render_transcript` never returns a prompt whose estimated tokens exceed `driver_context_tokens * driver_headroom_frac` when `k > 0`.
- `TranscriptCompacted.dropped_seq_range` is always a contiguous range strictly below `kept_seq_start`.
- No `TranscriptCompacted` fires when `k >= len(turns)` — `turns_dropped == 0` short-circuits before append.

### Command exit codes

- `uv run python -m pytest tests/test_render_rolling_window_basic.py tests/test_render_no_compaction.py tests/test_render_transcript_compacted_on_record.py -q` exits 0.
- Ruff + mypy strict clean.

## observation contract

Post-sprint-207 correction 2026-08-25. The card originally asked for a 5-turn end-to-end run under a real `session_topology`. That path depends on real Producer bodies for `model` / `park` / `session_end` that arrive in later sprints, and TECH-SPEC §3 explicitly parks the piece-A end-to-end observation contract at sprint 210 (`test_session_topology_park_on_final`, `test_session_topology_resume_appends`, `test_session_topology_slash_exit`, etc.). Sprint 207 discharges its observation contract through: (a) the two synthetic-events tests (`test_render_rolling_window_basic.py`, `test_render_no_compaction.py`) that lock K math + kept/dropped seq boundaries + cadence rule "no TranscriptCompacted when turns_dropped == 0"; (b) `test_render_transcript_compacted_on_record.py` which writes a REAL persistent record through the runtime (a fixture producer emits UserMessage + ModelReply pairs directly) and calls `render_transcript` against the on-disk root — proving the renderer integrates with the real record IO path (segment sealing, envelope framing, seq contiguity). The 5-turn end-to-end run against a real session_topology is sprint 210's scope.

## halt conditions to watch

- `dual_contract_fail` if the ambient cadence (at most one per firing) regresses under fuzzed inputs.
- `comprehension_failed` if the K formula cannot be restated in one line.

## definition of done

`render_transcript` produces bounded prompts. `TranscriptCompacted` fires only when it must. Cadence rules pass. Sprint 208 (driver context lookup + seed-alone-exceeds warning) can dispatch.
