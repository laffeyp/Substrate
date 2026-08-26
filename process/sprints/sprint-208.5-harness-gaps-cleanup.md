# Sprint 208.5 — harness gaps cleanup (test primitives + assert_replayable + realmodel gate)

```yaml
---
id: 208.5
status: pending
phase: daily-driver-piece-A
pass_kind: testing
---
```

## scope

Close three findings surfaced by the 2026-08-25 SDD-techniques review of the sprints 205-208 landings.

**Finding 1 (TECHNIQUE #38, medium).** Two record-touching tests do raw envelope-dict inspection where `substrate.testing.assert_event` / `assert_no_event` / `assert_sequence` — the F-API-4 primitives shipped for exactly this purpose — read shorter and match the convention `tool_loop`/`code_review`/`test_realmodel_demos` already follow. Rewrite the record assertions:
- `tests/test_render_transcript_compacted_on_record.py:70` (raw `[e for e in envelopes if e["kind"] == "UserMessage"]`).
- `tests/test_render_seed_alone_exceeds.py:92,95` (raw `warnings = [e for e in envelopes if e["kind"] == "SessionWarning"]`).

**Finding 2 (assert_replayable, medium).** `park`, `session_end`, `session_warning` all declare `deterministic=True`. The two tests that write a real record with a deterministic producer never invoke `substrate.api.assert_replayable(root, "3a")` — the substrate's own Level-3a determinism check. Every deterministic-topology test in the repo (`test_replay.py:170`, `test_conversation_topology.py:10`) does. Add the call after `Runtime(...).run(...)`:
- `tests/test_render_transcript_compacted_on_record.py::test_transcript_compacted_seqs_match_on_real_record`.
- `tests/test_render_seed_alone_exceeds.py::test_session_warning_producer_emits_exactly_one_and_completes`.

**Finding 3 (live realmodel probe not committed, high).** Sprint 208's card named a `SUBSTRATE_REALMODEL=1` gated test. That env var appears only in the sprint card + BLACKBOARD — not a real repo convention. The actual pattern is `pytestmark = pytest.mark.realmodel` + a `_require(*models)` skip helper that SKIPs when Ollama is unreachable or a tag is absent (see `tests/test_realmodel_demos.py:42-59`). The sprint 208 live probe (`resolve_driver_context_tokens('qwen', OllamaResponder('huihui_ai/qwen2.5-coder-abliterate:7b')) == 32768`) never landed in the suite; the "verified live" claim on the `/api/show` bridge row is only re-verifiable by rerunning my one-shot `uv run python -c "..."`. Author `tests/test_render_ollama_context_lookup_realmodel.py`:
- `pytestmark = pytest.mark.realmodel`.
- `_require(*models)` skip helper reading `/v1/models`.
- one test per available local Ollama tag (fast + smart from the demo suite), each asserting `resolve_driver_context_tokens(name, OllamaResponder(tag)) > 0` and matching what `/api/show` returns directly for that tag.

## prerequisites

- Sprints 205-208 closed and pushed.

## context_files

- `substrate/src/substrate/testing.py` (the F-API-4 primitives).
- `substrate/src/substrate/api.py` (`assert_replayable`).
- `substrate/tests/test_realmodel_demos.py:42-59` (the `pytestmark` + `_require(*models)` convention).
- `substrate/tests/test_replay.py:170` (assert_replayable call site reference).
- `substrate/sdd-kit-2/TECHNIQUES.md` §38 (test-fixtures-from-confirmed-good-captures rationale).
- `substrate/process/BLACKBOARD.md` 2026-08-25 review entry.

## signal contract

### Emits

None (test-only sprint).

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate/tests/test_render_transcript_compacted_on_record.py` — swap raw envelope inspection for `assert_event`; add `assert_replayable(root, "3a")` after the deterministic fixture producer runs.
- `substrate/tests/test_render_seed_alone_exceeds.py::test_session_warning_producer_emits_exactly_one_and_completes` — same treatment.
- `substrate/tests/test_render_ollama_context_lookup_realmodel.py` — new file. `pytestmark = pytest.mark.realmodel`; `_require(*models)` skip helper; per-tag assertions.

### Content assertions

- Neither modified test contains `e["kind"] ==` on a real record path.
- Both modified tests call `assert_replayable(...)` after their `Runtime(...).run(...)`.
- The new realmodel test file declares `pytestmark = pytest.mark.realmodel` and defines a `_require(*models)` skip helper matching the shape at `test_realmodel_demos.py:49-59`.
- The new realmodel test asserts, for at least one available local tag, that `resolve_driver_context_tokens(name, OllamaResponder(tag))` equals the daemon's own `/api/show` value for that tag.

### Command exit codes

- `uv run python -m pytest tests/test_render_transcript_compacted_on_record.py tests/test_render_seed_alone_exceeds.py tests/test_render_ollama_context_lookup_realmodel.py -q` exits 0.
- Full-suite regression exits 0 with no net-negative test count.
- Ruff + mypy strict clean.

## observation contract

The realmodel test runs against the box's live Ollama daemon and reports either SKIP (no daemon) or PASS (values match). Every determinism claim on the deterministic producers rides on `assert_replayable`'s decision.

## halt conditions to watch

- `dual_contract_fail` if `assert_replayable` reports mismatch on either of the two tests — that means a producer marked `deterministic=True` is actually non-deterministic; the fix is at the producer, not the test.
- `bridge_mapping_required` if the realmodel test surfaces a new tag with an unrecognized family key — extend the WORKING_AGREEMENT `/api/show` row with the new `<family>.context_length` example.

## definition of done

Two tests rewritten to use the F-API-4 primitives and `assert_replayable`. One realmodel test authored under the `pytest.mark.realmodel` gate. Full-suite regression green. Sprint 209 (bundled registration + CI record) may dispatch on this landing.
