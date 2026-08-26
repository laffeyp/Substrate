# Sprint 209b — session in BUNDLED + CI record (with sprint 209a review folded)

```yaml
---
id: 209b
status: closed
phase: daily-driver-piece-A
pass_kind: functional
---
```

## scope

Register `"session"` in `substrate/src/substrate/topologies/bundled.py::BUNDLED` with a CI-mode factory that runs a scripted three-turn session to `finalised` in one `.run()`. Generate the committed CI record at `substrate/src/substrate/topologies/session/records/ci_mode.record/`. Author `tests/test_session_topology_bundled.py`.

`session_topology`'s production termination is `pause_await_input(Park)` — the correct shape for a driver conversation that yields between turns. It does not finalise in one `.run()`, so `scripts/gen_topology_records.py` cannot record it directly. The `ci_session_topology` wrapper at `session/ci.py` adds a `driver_stepper` producer that walks a three-turn script ending in `/exit`, an `advance-on-park` trigger that fires the next turn's `UserMessage` on every `Park`, and overwrites the termination to `threshold_count("SessionEnded", 1)`. The `end-on-exit` trigger from `session_topology` fires `session_end` on the `/exit` UserMessage; SessionEnded lands; threshold matches; run finalises.

The sprint 209a review (`process/REVIEW-2026-08-25-piece-a-work-in-progress.md`) landed here as prerequisite fixes. Twelve findings folded (three blocking, five medium, four small). See the commit body for the full ledger. Highlights:

- `_model_factory` now takes `record_root`, `seed`, `driver_context_tokens`, `driver_headroom_frac`; when `record_root` is set it calls `render_transcript` and yields `TranscriptCompacted` from `result.compaction_events` BEFORE any other schema. `_prompt_for_driver` deleted. The Python-`repr` progress-line the reviewer flagged is gone.
- `producer_kind_from_lifecycle_payload` extracted to `session/views.py`; both the trigger predicate and `ModelFailures` view call it.
- `TranscriptCompacted.tokens_before` now uses the same axis as `tokens_after` (`_est_tokens(_render(...))` over the un-compacted turn list); subtracting them gives a meaningful "tokens the window saved."
- `_TURN_EVENT_KINDS` includes `TranscriptCompacted` so a compaction lands in its turn's render bucket.
- `end-on-cap` predicate flipped `>= max_turns` → `> max_turns` with intent-naming comment: "max_turns turns run, then the next attempt ends."

## prerequisites

- Sprint 209a closed and pushed (`e9f82b1`).
- Sprint 209a review committed and analyzed.

## context_files

- Sprint 209a output: `substrate/src/substrate/topologies/session/__init__.py`.
- `substrate/process/REVIEW-2026-08-25-piece-a-work-in-progress.md` — twelve findings folded here.
- `substrate/src/substrate/topologies/bundled.py:65-86` — the BUNDLED dict.
- `substrate/scripts/gen_topology_records.py` — record generator.
- `substrate/src/substrate/topologies/tool_loop/records/ci_mode.record/` — reference committed-record shape.

## artifact contract

### Files created or modified

- `substrate/src/substrate/topologies/bundled.py` — one new row `"session": ci_session_topology` plus the import.
- `substrate/src/substrate/topologies/session/ci.py` — new CI wrapper.
- `substrate/src/substrate/topologies/session/records/ci_mode.record/events-000001.open.jsonl` — committed.
- `substrate/src/substrate/topologies/session/records/ci_mode.record/manifest.json` — committed.
- `substrate/src/substrate/topologies/session/__init__.py` — review folds (see commit).
- `substrate/src/substrate/topologies/session/transcript.py` — review folds.
- `substrate/src/substrate/topologies/session/views.py` — extracted helper.
- `substrate/tests/test_session_topology_bundled.py` — new; four cases.
- `substrate/tests/test_session_topology_refuses_all_completed.py` — refusal error string update.
- `substrate/tests/test_session_topology_end_to_end.py` — slim comment.
- `substrate/tests/test_render_seed_alone_exceeds.py` — direct `SessionWarning` import.

### Content assertions

- `"session"` in `bundled.BUNDLED`.
- Running `bundled.BUNDLED["session"]()` under `Runtime.run` reaches `status="finalised"`.
- `api.first_divergence(fresh_root, committed_record)` is `None` — a fresh run is byte-identical to the committed record on the seq/kind/payload axes replay checks.
- The committed record carries: three `UserMessage`, three `ModelReply`, three `FinalAnswer`, one `SessionEnded`, and 2-3 `Park` events (the last turn's Park may or may not land before the SessionEnded-triggered termination matches; both shapes are legitimate and the assertion is bounded).
- `api.assert_replayable(fresh_root, "3a")` succeeds — the wrapper is fully deterministic (scripted opener + DeterministicResponder + deterministic CALCULATOR tool).

### Command exit codes

- `uv run python -m pytest tests/test_session_topology_bundled.py -q` exits 0 (4 passed).
- `uv run python scripts/gen_topology_records.py` exits 0 for all 14 bundled topologies including session.
- `uv run ruff check src/substrate/topologies/session/ tests/test_session_topology_bundled.py` exits 0.
- `uv run mypy --strict src/substrate/topologies/session/` exits 0.

## observation contract

The bundled entry produces the expected event trace via `.run()`. `first_divergence` against the committed record is `None`. `assert_replayable(root, "3a")` locks Level-3(a) byte-identical replay as a first-class assertion.

## halt conditions to watch

- `dual_contract_fail` if `first_divergence` returns anything non-`None` between a fresh `.run()` and the committed record.
- `substrate_primitive_missing` — the sprint 209a-surfaced `.resume()` open-dance gap remains open. Sprint 214 (daemon session API core) owns it. The CI wrapper here works around it by driving the whole scripted session through one `.run()` instead.

## definition of done

`session` registered in BUNDLED. CI record committed and replay-clean. Twelve review findings folded. Sprint 210 (piece-A observation contract, live-model run) may dispatch on this landing.
