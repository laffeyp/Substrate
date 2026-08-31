# Review — daily-driver piece A, sprints 205 → 208.5 → 209a in flight

Reviewer: Claude. Date: 2026-08-25.
Scope: correctness, SDD adherence, code style, substrate-principle hold, reinvention check.
Read: `src/substrate/topologies/session/__init__.py`, `session/transcript.py`, `session/views.py`, `session/prompts/default.md`, the seven `tests/test_render_*.py` and `tests/test_session_topology_end_to_end.py`, sprint cards 208.5 and 209a, BLACKBOARD head + Decisions.

## The shape of what's landed

Piece A committed through sprint 208.5 (commits `466365e`, `9347c11`, `11a6b07`). Session topology skeleton, ten triggers, `pause_await_input(Park) any_of threshold_count(SessionEnded,1)`, the `all_completed` refusal guard, the rolling-window renderer, the driver-context lookup, the seed-alone-exceeds `SessionWarning` initial — all on disk and green. Sprint 209a's four producer bodies (model / tool / park / session_end) are written into `session/__init__.py` and covered by a three-case end-to-end test. That work is uncommitted; the sprint card writes `status: closed` while the BLACKBOARD Surfaced-for-review head is still 208.5.

`prompts/default.md` ships with sprint 205, so the §1.6.5 fallback my earlier direction review flagged is on disk. The `park-on-interrupt` trigger subscribes to `substrate.ProducerCancelled` where `producer.kind == "model"` (sprint 206), which closes the second gap the direction review named. The vocabulary is ratified in `## Decisions` on 2026-08-25 — the "unratified header" concern from the earlier vocab review is superseded.

## Three real breaches

### The model producer never yields TranscriptCompacted despite declaring it in its schemas

`session/__init__.py:326` declares `schemas=[ToolCall, FinalAnswer, ModelReply, TranscriptCompacted]` on the `model` producer_kind. `_model_factory` at lines 170–204 has three dispatch paths (final, script, driver-parse). None yields a `TranscriptCompacted`. `transcript.py:6-8` states the contract: "one `TranscriptCompacted` rides on `compaction_events`; the model Producer yields those before its first `ToolCall`/`ModelReply` so the compaction is anchored to the firing that drove it." That anchor does not exist in code. The vocabulary lock's cadence rule for `TranscriptCompacted` — "fires only when `turns_dropped > 0`" — is undischargeable at the record; nothing in the topology writes the event.

### The model producer bypasses `render_transcript` entirely and reinvents a raw-events prompt

`_prompt_for_driver` at `session/__init__.py:218-234` assembles the driver prompt by hand. No call to `render_transcript` appears anywhere in `session/__init__.py`; grep confirms it. The whole point of sprint 207 was to feed the model producer the rolling-window rendering. The model factory carries `driver`, `per_turn`, and `script` but not `record_root`, `driver_context_tokens`, or a rendered-transcript reader, so it cannot call the renderer even if it wanted to.

The visible consequence lives at line 233: `f"Tool results so far: {progress}"` — `progress` is a `list[dict]`, so the f-string interpolates Python `repr()`. The driver reads `Tool results so far: [{'tool': 'add', 'ok': True, 'output': 5}]`. Single quotes, Python `True`, no JSON. This is the raw shape the renderer was built to replace.

Two problems compound here. First, the reinvention: two prompt-assembly paths for the same producer, one used by sprint 207's tests, the other used by sprint 209a's body. Second, `render_transcript` reads `record_root` — it needs a wired path from either the daemon-side seed assembler or the model producer's factory signature. Neither exists yet.

### The docstring promises a `TOOL:` parse branch the body does not implement

`_model_factory`'s docstring at `session/__init__.py:158-168` reads: "if the response looks like a `TOOL: <name> args=[...]` line, yield a ToolCall instead." The body at 202–204 emits `ModelReply` then `FinalAnswer` unconditionally, no matching branch. For the scripted path the tests exercise, this never matters. For sprint 210's real-LLM contract, this collapses every driver reply into a single-step `FinalAnswer`; no multi-step tool loop reaches the driver-parse path. Either the design intent was dropped in the write-up or the docstring is lying. Either way the two disagree.

## The discipline slip

### Sprint 209a marks `status: closed` while nothing is committed or surfaced

The card's frontmatter at `process/sprints/sprint-209a-real-producer-bodies.md:5` writes `status: closed`. `git status` shows `src/substrate/topologies/session/__init__.py` modified, `tests/test_session_topology_end_to_end.py` untracked, the sprint card itself untracked. `git log --oneline` runs 208.5 → 208 → 207 → 206 → 205 → …; no 209a landing. The BLACKBOARD Surfaced-for-review head is the 208.5 landing entry. AGENTS.md hard rule 12 puts closure after surfacing; writing `closed` in the frontmatter ahead of the surface is closing on paper, not in the ledger.

## Medium — real, not blocking

### `_producer_kind_from_ref` is written twice with the same body

`session/__init__.py:306-309` and `session/views.py:32-37` both read `payload["producer"]["kind"]` through the same defensive `isinstance` ladder. Same guard, same shape, two spellings. A change to the lifecycle payload has to land in both places or the trigger and the view drift.

### `TranscriptCompacted.tokens_before` and `tokens_after` sit on different scales

`transcript.py:330` sets `tokens_after = _est_tokens(prompt_text)` — chars/4 of the rendered string. Line 343 sets `tokens_before = _est_tokens_events(events)` — chars/4 of the text-carrying payload fields plus a fixed +8 per envelope. The two numbers describe different quantities. A reader interpreting the delta as "how much the rolling window saved" gets a number distorted by the per-envelope overhead. The fields will be read; the axis needs to match, or the names need to say what each measures.

### `_group_by_turn` silently drops `TranscriptCompacted` and `SessionWarning` from the render

`transcript.py:203-227` keeps only kinds in `_TURN_EVENT_KINDS = {UserMessage, ModelReply, ToolCall, ToolResult, FinalAnswer, Park}`. The docstring at line 210 names only `substrate.*` lifecycle events as dropped. Every other application kind — including `TranscriptCompacted` (the event the module says the model producer will emit) and `SessionWarning` — falls out of the turn body without notice. If finding 1 above ever ships and TranscriptCompacted rides the record, `render_transcript` will not see it on the next read.

### The `all_completed` refusal error string pins a `kernel/policies.py:90-97` line range

`session/__init__.py:53` — "See `kernel/policies.py:90-97`." The refusal is the right call; the line pointer rots on the next edit to `policies.py`. The docstring at 40-48 already names the symbol (`all_completed` from `policies.py:90`) once; the raise-site message would carry the same load with the symbol alone.

### `test_render_seed_alone_exceeds.py:83` reaches into the substrate's internal `.schemas` tuple shape

The solo-topo fixture iterates `warning_reg.schemas.values()` and destructures each entry as `(cls, _)`. If the substrate ever grows the tuple, the destructure raises and the test fails in a way that reads like an internal-API bug rather than a fixture issue. Either the substrate exposes "the classes this producer emits" as a public read, or this test lives inside `substrate/tests/` and inherits the risk knowingly.

## Smaller

### `_step_of` defaults to `turn_max_steps` when `step` is absent from the payload

`session/__init__.py:296-298`. Every trigger that fires with a missing `step` payload key routes to `wrap-up` (the predicate `_step_of(ctx) + 1 >= turn_max_steps` matches). Payloads on the happy path always carry `step`, so the default never fires. The failsafe reads as a coincidence, not a decision.

### `end-on-cap` counts the just-landed `UserMessage` before the turn runs

`session/__init__.py:466-476`: `int(ctx.views["user_turns"].value()) >= max_turns`. With `max_turns=200`, the 200th `UserMessage` triggers the end and the 200th turn never runs. The intent — cap at the 200th arrival, or let 200 turns finish and end after — is not stated at the trigger.

### The `substrate_primitive_missing` halt explanation lives inside a test-body comment

`test_session_topology_end_to_end.py:78-86` pastes a 9-line explanation of the `_resume_bootstrap` no-`RunStarted` problem into the first test. The sprint card's `## halt conditions to watch` names the same halt and defers to sprint 214. Two locations for the same explanation; the test-body copy will rot as the sprint moves.

### `assert_event(root, "SessionWarning", kind=...)` collides with the reserved positional `kind`

Sprint 208.5 finding 1 and `test_render_seed_alone_exceeds.py:98-108` work around it by asserting `payload["kind"]` on the returned envelope directly. This is real substrate-testing-API friction — `SessionWarning.kind` is the payload discriminator, `kind` is the envelope discriminator. Not blocking; a substrate-side ergonomics issue worth its own surface.

## What holds

- Ten triggers registered. Termination composes `pause_await_input(Park) any_of threshold_count(SessionEnded, 1)`; the `_refuse_all_completed` guard rejects direct and nested `all_completed` at build time. The end-to-end test observes the first two live: turn-0 pauses on `Park{reason:"final_answer"}`, turn-1 resumes and appends monotonically, turn-2 `/exit` lands `SessionEnded{reason:"user_exit"}` and finalises.
- Sprint 208.5 replaced raw envelope inspection with the F-API-4 primitives (`assert_event`, `assert_no_event`, `read_record`) and added `assert_replayable(root, "3a")` after every deterministic-producer test. The realmodel gate (`pytestmark = pytest.mark.realmodel`, `_require(*models)` skip helper) matches `test_realmodel_demos.py:42-59` — the actual repo pattern, not the sprint-208 card's invented `SUBSTRATE_REALMODEL=1` env var.
- No `substrate.*` reserved names invented in application code; no `_Lifecycle` or `_Emission` access from the topology (F-API-6 held); adapters imported at the module boundary. The `session_warning` producer emits `SessionWarning` through the public path, not through a kernel-private lifecycle route.
- The `park-on-interrupt` trigger closes the interrupt path (subscribes to `substrate.ProducerCancelled` where `producer.kind == "model"`, fires `park` with `reason="interrupt"`). My earlier direction review's real-gap #3 is discharged.
- `prompts/default.md` exists on disk; the §1.6.5 layer-4 fallback is not a phantom. My earlier direction review's real-gap #2 is discharged at the file level (the daemon-side loader is a later sprint's concern).
- Deterministic-topology tests call `assert_replayable(root, "3a")`; the fixture-writer path in `test_render_transcript_compacted_on_record.py` and the `session_warning` solo topology in `test_render_seed_alone_exceeds.py` both prove byte-identical replay.
- `_tool_factory` reused verbatim from `tool_loop`; `_MAX_CONSECUTIVE_FAILS = 3` matches the anti-spin guard already in tool_loop. No re-implementation of the tool seam.
- Session vocabulary ratified 2026-08-25 in `## Decisions`. The eight PascalCase Structs match the lock; the `session/__init__.py` docstring's ratification claim is now backed.

## Reinvention audit

Six candidates checked; none is a live invention.
- `_refuse_all_completed` regex — no equivalent in `kernel/policies.py`. The guard is topology-specific (only pausable topologies need to reject `all_completed`); a local guard is right.
- `ModelFailures` view — patterned on `kernel/views.py::StartedCompletedCounts`, which reads the same `producer.kind` off the same reserved lifecycle events. Same pattern, different filter target. Reasonable.
- `resolve_driver_context_tokens` dispatch on class name (`DeterministicResponder` / `context_tokens()` protocol / CLI-config fallback) — no equivalent in adapters or api. The dispatch belongs at the session-topology boundary; the adapter side exposes `context_tokens()` and the two typed errors. Correct location.
- `_est_tokens` chars/4 heuristic — no substrate-side token counter. Coarse conservative estimator; real spend rides `ModelUsage` on `ModelReply`. Right split.
- `_tool_factory` reused verbatim from `tool_loop`. Not reinvented.
- `_prompt_for_driver` — this IS a reinvention (see finding 2). The renderer at `render_transcript` already does the job.
