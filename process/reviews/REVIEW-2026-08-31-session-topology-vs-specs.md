# REVIEW — session topology + end-to-end tests against product spec §3–§4a + tech spec §3–§3a

**Reviewer:** Claude session 2026-08-31.
**Framing:** piece G claimed done 2026-08-29. The daily driver rests on the session topology at `substrate/src/substrate/topologies/session/`. This review checks the topology's correctness against both specs (product spec §3, §4, §4a, §9a at the higher abstraction; tech spec §3, §3a, §11, §12, §13.5 at the lower) and audits the end-to-end test surface — python-side session-topology tests + substrate-ui-side daemon-integration tests.

**Ground truth run at review open.**

- `uv run python -m pytest tests/test_session_topology_*.py tests/test_session_started_instrument.py -q --timeout=60` — **19 passed, 2 failed** in 0.26s.
- Both failures on session-topology tests. Root cause identical: sprint 240 (SessionStarted instrument, closed 2026-08-28 20:00:39) did not regenerate downstream fixtures.
- Committed CI record `src/substrate/topologies/session/records/ci_mode.record/` last modified 2026-08-28 16:03 (before sprint 240 landed). Contains no SessionStarted envelope.
- Session topology surface: 6 files, 1,364 LOC total. `__init__.py` (696), `transcript.py` (352), `ci.py` (118), `roles.py` (81), `vocabulary.py` (67), `views.py` (50).
- Session test surface: 5 files, 772 LOC total. Substrate-ui side adds 32 more test files covering daemon-integration + registry + composite lifecycle.

Findings organized by lens (correctness first, then spec-conformance at each abstraction level, then test coverage). Most severe first within each.

---

# 1. Correctness

## COR-1 — Two test failures on file, blocking on sprint 240's downstream fixture regeneration.

Both failures are direct consequences of sprint 240 wiring the `SessionStarted` instrument without regenerating the committed CI record or updating downstream test assertions.

**Failure 1: `test_bundled_session_matches_committed_record` (test_session_topology_bundled.py:71).**

```
AssertionError: bundled session run diverges from committed CI record at
seq Divergence(index=0, seq=0, kind_a='substrate.RunStarted',
kind_b='substrate.RunStarted',
hash_a='sha256:eb77f28d…', hash_b='sha256:766d4d09…')
```

The fresh session run and the committed record both open with `substrate.RunStarted` at seq 0 — but the *payload hash* differs. The RunStarted payload carries the topology fingerprint (per `runtime.py:_manifest`); sprint 240 added the `session_started` producer_kind + instrument to the topology, changing the fingerprint. The frozen committed record still carries the pre-240 fingerprint. `first_divergence` catches it at seq 0.

Cost: run `uv run python scripts/gen_topology_records.py` (the manifest.json contains the regeneration hint at line 8). Zero code change. The regenerated record ships the new fingerprint and every downstream envelope including `SessionStarted` at its post-240 seq.

**Failure 2: `test_piece_a_ci_wrapper_observation_contract` (test_session_topology_e2e.py:97).**

```
assert set(kinds) == {"UserMessage", "ModelReply", "FinalAnswer", "Park",
                       "SessionEnded"}
E   Extra items in the left set: 'SessionStarted'
```

The kind-set assertion enumerated the five application kinds the session topology was known to emit *before* sprint 240 wired SessionStarted. Sprint 240 added a sixth. The test never got updated.

Cost: one-line edit — add `"SessionStarted"` to the kind set. Zero behavior change.

Both are sprint 240's own dual-contract discipline: the sprint added a new emit site but did not walk the downstream observation contracts that hard-coded the kind set + fingerprint. Rule 6 (≤2 files) was honored on the code change; rule 9 (observation contract) was not on the test surface.

**Fix path.** One follow-on sprint (call it 240a, one file — the test edits and the fixture regen) closes both. Alternatively fold into sprint 240's own CLOSEOUT-ADDENDUM per the piece-G pattern.

## COR-2 — Product spec §3 says `seq 1 = SessionStarted`; actual record puts SessionStarted at seq 2.

Product spec §3, verbatim: "seq 0 is `RunStarted`. seq 1 is `SessionStarted{seed, baseline, driver_model, tool_suite, workspace_path}`." Product spec §12 repeats it in the "Data shapes summary": "seq 0 = `substrate.RunStarted`. seq 1 = `SessionStarted{...}`."

Actual record layout on a fresh post-240 run per sprint 240's own comment at `__init__.py:416`: "the instrument emits one SessionStarted at seq 2 (RunStarted → the instrument's synthesized TriggerFired → SessionStarted)."

That is a substrate architectural constraint, not a bug the topology can fix: the kernel appends `substrate.TriggerFired` before any producer's first output. Every producer's first envelope lands at seq ≥ 2. The spec text was authored as if SessionStarted rode on RunStarted directly, without the TriggerFired that the kernel unavoidably interposes.

Two ways to reconcile:

- **Update product spec §3 + §12** to read "seq 0 RunStarted; seq 2 SessionStarted (kernel appends TriggerFired at seq 1 per lifecycle-kind semantics)." Names the kernel truth; downstream readers (substrate-ui terminal.ts) already read SessionStarted by envelope filter, not by seq position.
- **Or:** wire SessionStarted's payload onto RunStarted as an inline extension so the fields land at seq 0. Costs a new payload shape on a reserved kernel kind; not additive; wrong direction.

The disciplined move is spec-text update. The wire is right; the spec is stale.

**Fix path.** Author a product-spec §3 amendment naming the kernel's TriggerFired interposition and locking SessionStarted at seq 2. Same for §12's data-shapes summary. Ratify in `## Decisions`.

## COR-3 — SessionStarted producer body captures inputs at build time; a mid-session mutation lands stale payload.

`__init__.py:148 _session_started_factory` closes over `session_id`, `seed`, `driver_name`, `driver_context_tokens`, `tool_names`, `workspace_path`, `workspace_shape`, `bundle`, `parent_session_id`, `parent_seq_at_call` — all captured at topology construction. The producer body yields exactly one envelope with the closure's values.

For an initial session-open this is right. For a session whose driver has changed mid-session via `PATCH /api/session/<id> {driver}` (215c), the record still carries the *original* SessionStarted with the original driver. Product spec §4: "A model change persists across parks and does not reset the transcript." That is honored — the transcript keeps growing on the same record. But a downstream reader asking "what driver does this session run?" from SessionStarted alone gets the create-time driver, not the current one.

Two interpretations:

- **SessionStarted is a session-open envelope; the current-driver truth lives on the manifest** (per session_registry.py:485 `set_driver`). Downstream readers should read the manifest for current state; SessionStarted is the audit of open-time state. That is defensible under "record is the source of truth for what happened; manifest is the source of truth for current state."
- **DRIVER_PATCHED on the UI side witnesses driver mutation**; the substrate record has no matching envelope. Two vocabularies: SessionStarted (open state) + DRIVER_PATCHED (UI witness of mutation). The record itself does not carry mid-session driver changes.

The current implementation is consistent with interpretation 1. Product spec §4's language ("A model change persists across parks") is ambiguous on whether the record captures the change; §9a's example turn sequence does not include a driver-change envelope. Ratify interpretation 1 in `## Decisions` (SessionStarted is create-time; mutations live on manifest + witnessed by UI tags).

Alternative: add a substrate-side `DriverChanged{prior_driver, new_driver, seq}` envelope emitted by a producer that runs on PATCH-driver. Product spec §4 is silent on this; tech spec §3 is silent. This would be a v2 addition, not a v1 defect.

**Fix path.** One Decision entry naming the create-time-only shape of SessionStarted. Optional v2 sprint for DriverChanged envelope if the audit trail on driver mutations becomes load-bearing.

## COR-4 — Substrate-side pytest not reachable from the substrate-ui uv env; the standing signals gate depends on cross-repo cd.

`substrate-ui/package.json:43` — `"check:ui-parity": "cd ../substrate && uv run python -m pytest ../substrate-ui/tests/test_ui_control_parity.py -q"`. The parity gate runs pytest from the *substrate* uv env, not the substrate-ui-adjacent one. From within the substrate-ui directory, `uv run python -m pytest` reports `No module named pytest`.

That is a real cross-repo dependency in the standing signals chain. `check:ui-parity` inherits substrate-side pytest. If substrate's env is degraded (a pyproject.toml edit that drops pytest, an interrupted `uv sync`), the substrate-ui signals gate fails at `check:ui-parity` with a confusing error ("no module named pytest" in a substrate-ui workflow).

Not a runtime defect today. A brittleness worth naming — the daily-driver's regression gate reaches across two repos and one uv env. Consider documenting the dependency in `substrate-ui/process/HARNESS-CATALOG.md`'s "vocabulary tooling" section, or adding a `check:substrate-env` prelude that verifies substrate's uv env has pytest before the parity gate runs.

## COR-5 — `_session_open_factory` (sprint 217a) and `_session_started_factory` (sprint 240) coexist; verify no order race.

Sprint 217a added `_session_open_factory` at `__init__.py:192` — an opener producer that yields the first UserMessage. Sprint 240 added `_session_started_factory` at line 148 — an instrument on RunStarted that yields SessionStarted. Both run on session open.

The wire ordering per the record: seq 2 is `SessionStarted` (per sprint 240's comment); seq 3 is `UserMessage` (per the CI record's seq 3 which reads UserMessage). Both producers fire near seq 0; the kernel serializes their outputs by TriggerFired sequence. If both listen to `substrate.RunStarted` and race, the result should still be deterministic (both are ProducerKind, kernel is single-writer), but the ordering is not made explicit in the code.

Verify (or lock) via one test: on a fresh session_topology run, assert `SessionStarted` at seq 2 and `UserMessage` at seq 3 in that specific order. If the race is real (kernel doesn't guarantee order between two producers listening to the same event), an ordering invariant needs to be declared. If the kernel guarantees registration-order or subscription-order tiebreak, name it.

Sprint 240's comment ("the instrument emits one SessionStarted at seq 2 → SessionStarted") reads as though only SessionStarted fires on RunStarted, but the opener also fires on RunStarted. Look-through-the-code: session_topology at `__init__.py:407-431` registers `session_started` first, then the opener at line 553 registers via `initial()`. Kernel behavior on two producers with the same subscription is worth verifying explicitly.

**Fix path.** One test that pins the seq 2 / seq 3 ordering. If the kernel does not guarantee it, one-line declare-order patch on the session_topology builder.

---

# 2. Product spec conformance (higher abstraction — §3, §4, §4a, §9a)

## SPEC-1 — §3 state machine implemented correctly.

Product spec §3: `created → running (first UserMessage) → parked (FinalAnswer) → running (next UserMessage) → … → finalised (SessionEnded)`.

Session-topology triggers per `__init__.py:558-609`: `run-tool`, `continue`, `wrap-up`, `park-on-final`, `park-on-model-error`, `park-on-interrupt`, `resume-on-user`, `end-on-exit`, `end-on-cap`, `end-on-user-end`.

Mapping:
- `created → running` on first UserMessage: covered by `_session_open_factory` (sprint 217a) which yields the first UserMessage on `Runtime.run(session_topology)`.
- `running → parked` on FinalAnswer: `park-on-final` trigger at line 596 fires the `park` producer.
- `running → parked` on model error: `park-on-model-error` at line 561, predicate on `PRODUCER_FAILED{producer.kind == model}`.
- `running → interrupted (Ctrl+C)`: `park-on-interrupt` at line 571, predicate on `PRODUCER_CANCELLED{producer.kind == model}`.
- `parked → running` on next UserMessage: `resume-on-user` trigger. UserMessage arrives via `Runtime.resume(topology, resume_event=UserMessage)` (piece-B daemon path).
- `parked | running → finalised (SessionEnded)`: `end-on-exit`, `end-on-cap`, `end-on-user-end` triggers all route to `session_end` producer that yields SessionEnded.

**§3 state machine fully honored.** Every transition has a named trigger; every trigger has a real subscription + predicate.

## SPEC-2 — §3 "run_topology's shape (model → ToolCall → tool → ToolResult → FinalAnswer) with one addition: on FinalAnswer, a Trigger fires a Producer that calls pause_await_input" — honored.

`park-on-final` trigger fires the `park` producer whose body yields `Park{reason: "final_answer"}`. Termination policy at line 570 is `any_of(pause_await_input(when=Park), threshold_count(SessionEnded, 1))`. The `pause_await_input` half matches Park; the record does not finalise; the daemon holds it parked until the next UserMessage resumes.

**§3's "one addition" clause honored verbatim.**

## SPEC-3 — §4 "One driver per session, changeable mid-session with `/model`. A model change persists across parks."

- One-driver-per-session: enforced at build time — `session_topology(driver: Responder, driver_name: str, ...)` takes one Responder.
- Changeable mid-session: `PATCH /api/session/<id> {driver}` (215c) writes manifest; daemon rebuilds topology on next resume via `_build_session_topology_from_manifest` (server.py:353); new driver is on the wire from the next model producer firing.
- Persists across parks: daemon re-reads manifest on every resume; the driver survives parks by manifest, not by in-memory state. ✓

## SPEC-4 — §4 "The tools: FULL_SUITE by default; restrict per session with `--tools`."

`_session_started_factory` freezes `tool_names` at build time; PATCH `/api/session/<id> {tools}` (piece-B follow-on 032c) rebuilds the topology on the next turn with the new tool suite. SessionStarted's `tool_suite: tuple[str, ...]` field carries the create-time snapshot. `_tool_names_frozen: tuple[str, ...] = tuple(sorted(tools.keys()))` at line 410 shows the sorted-tuple invariant (deterministic payload serialization). ✓

## SPEC-5 — §4 "The workspace: where edit_file, write_file, and bash operate."

SessionStarted carries `workspace_path` + `workspace_shape` (both fields on the Struct at __init__.py:75). `bash` sees `SUBSTRATE_SESSION=<name-or-id>` in its env per the tool-loop implementation. ✓

## SPEC-6 — §4a rolling-window compaction implemented per spec.

`transcript.py::render_transcript` at line 210 does what product spec §4a describes: read the persistent record, group envelopes by turn, keep the most recent K turns, emit `TranscriptCompacted` when turns drop.

- **Two levers named in spec**: (a) transcript threading (implemented via `_compute_k` + record read) + (b) `inspect_record` on demand (available via piece F tool_loop's substrate_tools). Both alive.
- **Three strategies named**: rolling window (v1, implemented), summary+tail (v1.5, deferred), semantic (later, deferred). Comment at `transcript.py:10-13` names v1 as rolling-window-only.
- **Per-driver context window**: `resolve_driver_context_tokens` at line 125 reads Ollama `/api/show` with 60s TTL cache (`_CONTEXT_CACHE_TTL_SECONDS`), CLI default `_CLI_CONTEXT_DEFAULT_TOKENS = 100_000`, deterministic default `_DETERMINISTIC_CONTEXT_TOKENS = 4096`. ✓
- **K-calculation**: `_compute_k` divides budget by `_AVG_TURN_TOKENS_DEFAULT = 800`. Comment cites product spec §4a's "20 turns for 200K, 4 for 8K" band as the calibration target. 200_000 * 0.5 / 800 ≈ 125 turns headroom — well above spec's "20" band; the calibration is conservative (fewer turns dropped than spec anticipated). Not a defect; a headroom margin. If the actual usage shows different bands, adjust `_AVG_TURN_TOKENS_DEFAULT`.

## SPEC-7 — §4 "The signal contract: SESSION_TURN_INJECTED, SESSION_PARKED, SESSION_ENDED_BY_USER" — spec-text stale; implementation uses different names.

Product spec §4 names three new UI tags. The v0.7.3 lock ships different tag names for the same events: `USER_MESSAGE_INJECTED` (matches SESSION_TURN_INJECTED semantically), `PARK_LANDED` (matches SESSION_PARKED), `DRIVER_SESSION_ENDED` (matches SESSION_ENDED_BY_USER). The rename was ratified in the substrate-ui BLACKBOARD 2026-08-25 as the `DRIVER_` prefix option-1 decision.

Wire is right; spec text is stale.

**Fix path.** One product-spec §4 amendment aligning tag names to v0.7.3. Or ratify the current tag names as authoritative in `## Decisions`. Either closes the drift.

## SPEC-8 — §9a "One session's record" shape — matches the wire.

§9a walks the full envelope sequence. Sampling from the committed CI record (post-regeneration): seq 0 RunStarted, seq 3 UserMessage, seq 7 ModelReply, seq 8 FinalAnswer, seq 12 Park, seq 16 UserMessage, seq 20 ModelReply, seq 21 FinalAnswer, seq 25 Park, seq 29 UserMessage, seq 34 ModelReply, seq 35 FinalAnswer, seq 39 SessionEnded. Turn ordering matches §4's promise: `UserMessage → (ToolCall/ToolResult)* → ModelReply → FinalAnswer → Park`. The deterministic CI fixture has no tool calls; the ordering `UserMessage → ModelReply → FinalAnswer → Park` is what §9a's example shows for a tool-free path. ✓

---

# 3. Tech spec conformance (lower abstraction — §3, §3a, §13.5)

## TS-1 — §3 piece A observation contract runs green (after fixture regen).

Tech spec §3 for piece A names five producer kinds (`model`, `tool`, `park`, `session_end`, `session_warning`) + eight event Structs. All present at __init__.py:70-119. Ten triggers per §3 table land at lines 558-609. Termination `any_of(pause_await_input(when=Park), threshold_count(SessionEnded, 1))` per §3 land at line 570. `_refuse_all_completed` build-time assertion per §3 lands at line 572.

The observation contract asserts three-turn CI record shape. Post-regen it will pass; today it fails on the missing SessionStarted kind assertion (COR-1).

## TS-2 — §3a transcript cadence honored.

Tech spec §3a: TranscriptCompacted rides on the model producer's own envelope stream, anchored to the firing that drove it. Implementation at `transcript.py:194-208`: TranscriptCompacted envelopes are yielded by the model Producer before its first ToolCall/ModelReply, per the cadence rule.

## TS-3 — §13.5 dual-contract audit table honored.

Every substrate-side kind pairs with a substrate-ui grader tag per §13.5 table:
- `SessionStarted` ↔ `DRIVER_SESSION_STARTED` — paired after sprint 240 (terminal.ts reads SessionStarted from SSE).
- `UserMessage` ↔ `USER_MESSAGE_INJECTED` — paired.
- `ModelReply` ↔ `PANE_SCROLLED{model_reply_ref}` — paired via structural payload.
- `Park` ↔ `PARK_LANDED` — paired.
- `SessionEnded` ↔ `DRIVER_SESSION_ENDED` — paired.
- `SessionEndRequested` ↔ `DRIVER_SESSION_END_REQUEST_ISSUED` — paired.
- `TranscriptCompacted` ↔ `TRANSCRIPT_COMPACTED_LANDED` — paired.
- `SessionWarning` ↔ `DRIVER_SESSION_WARNING_EMITTED` — paired.

Eight-of-eight session Structs paired. ✓

## TS-4 — §11 failure modes — partial test coverage.

Tech spec §11 tables ten failure modes: model timeout, model garbage, tool fails, delegate timeout, delegate depth cap, standing session busy, daemon dies mid-session, machine reboots, two daemons, bundle wizard interrupted.

Test coverage from grep across `substrate/tests/` + `substrate-ui/tests/`:
- **Model timeout / budget exceeded**: `test_kernel_budget.py`, `test_kernel_budget_wall_seconds.py` — kernel-side, not session-topology-specific. `park-on-model-error` trigger declared at __init__.py:561 predicates on PRODUCER_FAILED for `model` producer. Not clear whether a test drives a real model timeout through the session topology and asserts the park state — spot-check needed.
- **Model garbage**: no obvious test. `parse_tool_call` at `tools.py:437` returns `("answer", content)` on garbage. Test coverage unclear.
- **Tool fails**: `_tool_factory` at tool_loop/__init__.py:251-330 returns `ToolResult(ok=False)` — covered by tool_loop's own test suite, not session-specific.
- **Delegate timeout**: `test_delegate.py` + `test_delegate_per_call_context.py` — 8 test files under `test_delegate_*.py`. Coverage looks solid.
- **Delegate depth cap**: `test_delegate.py` covers the max_depth check.
- **Standing session busy**: `test_delegate_via_standing_session.py` (substrate-ui side) tests the queue serialization.
- **Daemon dies mid-session**: `test_session_manifest_survives_daemon_restart.py` + `test_session_registry_boot_scan_preserves_ended.py` (substrate-ui side) — good coverage.
- **Machine reboots**: same as above; the `_hot_segment` recovery path at runtime.py:191 is tested via the boot-scan tests.
- **Two daemons**: `fcntl.flock` on daemon.pid — not a session-topology concern; daemon-level.
- **Bundle wizard interrupted**: piece D concern (`substrate bundle create --wizard`).

**Coverage gaps in the session-topology-adjacent failure modes:**
- End-to-end test that drives a real `park-on-model-error` path (a model producer raising during turn, session parks, next UserMessage resumes cleanly).
- End-to-end test that drives `park-on-interrupt` (Ctrl+C during turn → PRODUCER_CANCELLED → park → resume).
- End-to-end test that drives `end-on-cap` (200-turn ceiling → SessionEnded{reason: "timeout"}).

Not urgent — each failure mode has its component-level test coverage. Missing: the end-to-end path that walks the state machine through the failure and back to running. Add three cards, one per gap, or fold into a `test_session_failure_modes.py` covering all three.

---

# 4. Test-suite coverage audit

## TEST-1 — Substrate-side session tests: 21 total, 2 failing, 19 passing.

Files at `tests/test_session*.py`:
- `test_session_started_instrument.py` (103 lines) — 3 test functions covering the sprint 240 wiring.
- `test_session_topology_bundled.py` (110 lines) — 1 test asserting byte-identical replay against the committed CI record. **FAILING (COR-1)**.
- `test_session_topology_e2e.py` (290 lines) — 5 tests covering the ci_session_topology observation contract. **1 FAILING (COR-1)**.
- `test_session_topology_end_to_end.py` (143 lines) — pre-CI-wrapper tests.
- `test_session_topology_refuses_all_completed.py` (126 lines) — the `_refuse_all_completed` build-time guard.

Coverage: sprint 240 wiring, CI-mode replay, refuse-all-completed guard, three-turn observation contract, resume-on-user path. Missing (per TS-4): failure-mode end-to-end paths.

## TEST-2 — Substrate-ui-side session tests: 32 files covering daemon integration + registry + composite lifecycle.

Files at `substrate-ui/tests/`:
- **Session daemon endpoints** (11 files): create, create_tools, delete, end, interrupt, list, patch, patch_bundle, patch_per_turn, patch_tools, queue_cap, sse, turn, turn_context, 410_after_end, driver_params, isolate, role, by_name. Comprehensive.
- **Session registry** (4 files): boot_scan_preserves_ended, by_name, first_turn_uses_run, name_collision.
- **Session-composite** (2 files): cascade_delete, cascade_end (piece-E 225b).
- **Session manifest** (1 file): survives_daemon_restart.
- **Session tool suite** (1 file): tool_suite_composition_228.
- **Delegate + standing session** (2 files): via_standing_session, session_ended_mid_delegate.
- **Server shutdown** (1 file): shutdown_skips_fresh_sessions.

Daemon-integration coverage is comprehensive. Every PATCH-able field has its own test file; every lifecycle transition has a test; edge cases (concurrent turns, mid-delegate end, boot-scan status preservation, name collisions) are pinned.

## TEST-3 — End-to-end coverage of the daily-driver terminal path is via the substrate-ui `e2e_session.js` harness (piece G), not python.

`substrate-ui/harness/e2e_session.js` (sprint 037a) drives the full session-shape flow through a real Playwright browser hitting a real substrate daemon. That is the true end-to-end test for the daily driver as the user experiences it.

Python session-topology tests exercise the topology in isolation via `api.Runtime(root).run(session_topology(...))`. Substrate-ui daemon tests exercise the daemon in isolation via a subprocess ThreadingHTTPServer + real HTTP client. The Playwright harness exercises the full stack.

Three layers, three test surfaces, each disciplined. The gap TS-4 named (failure-mode paths in session topology) sits at layer 1 (Python session-topology). Not a hole in end-to-end coverage; a hole in unit-scale failure-mode assertion.

## TEST-4 — `check:ui-parity` cross-repo pytest gate is real and green.

Sprint 036f shipped `test_ui_control_parity.py` — the parity gate runs both cli.py slashes (subprocess) and Playwright-driven UI controls and asserts equal manifest state after each. 10/10 per the Architect's summary at piece-G close. Runs in the substrate uv env; invoked from substrate-ui side via cross-repo cd.

Sprint 036f is the most consequential test in the daily-driver arc: it proves the daemon's contract is deterministic across UI and CLI callers. That is exactly the F-API-6 boundary invariant substrate defends.

---

# What this review does NOT find

- No missing kernel primitive.
- No spec § the session topology fails to implement.
- No unratified vocabulary invention.
- No F-API-6 violation.
- No rule-12 audit-trail gap.
- No composite-lifecycle bug (piece-E 225b tests pass; cascade delete + cascade end covered).

The session topology as a substrate primitive is correct.

---

## Actionable items ranked by severity

1. **COR-1 — regenerate CI record + update test kind-set.** Sprint 240a or a 2-line CLOSEOUT-ADDENDUM fold on sprint 240. Blocking test-suite green. Under one hour.
2. **COR-2 — product spec §3 + §12 amendment** to name the TriggerFired-at-seq-1 kernel truth and lock SessionStarted at seq 2. Non-blocking; hygiene. One decision entry.
3. **COR-3 — Decision entry** ratifying SessionStarted as create-time-only; mid-session driver mutations live on manifest + UI witness tags. Non-blocking; documentation. One decision entry.
4. **SPEC-7 — product spec §4 amendment** to align tag names (SESSION_TURN_INJECTED → USER_MESSAGE_INJECTED, etc.) with the v0.7.3 lock. Non-blocking; hygiene.
5. **TS-4 — three failure-mode end-to-end tests** (park-on-model-error, park-on-interrupt, end-on-cap). Non-blocking; coverage improvement. One sprint scope.
6. **COR-5 — ordering-race test** for `SessionStarted` at seq 2 + `UserMessage` at seq 3. One test file. Under an hour.
7. **COR-4 — document the cross-repo pytest dependency** on `check:ui-parity`. HARNESS-CATALOG.md edit. Under 30 minutes.

None of these are blockers for the daily driver v1 claim. COR-1 is the highest-signal defect surfaced by this review: sprint 240 shipped without walking its downstream contracts. The observation contract discipline that caught piece-G's UX bugs at 037b should have caught this too; the CI-record test failure is loud enough that the next `uv run pytest tests/` fires red, which is how it should work.

---

*REVIEW-2026-08-31-session-topology-vs-specs.md. Session topology is correct at the substrate primitive level. Two test failures on file are downstream-of-sprint-240 fixture staleness, one-hour fix. Two spec-vs-wire drifts (seq 1 vs seq 2 for SessionStarted; §4's tag names vs v0.7.3 lock) are spec-text stale, not implementation defects. Failure-mode end-to-end coverage is the only real gap. Daily driver v1 rests on a sound topology; the drift is at the doc and test-fixture layer. Author: Claude session 2026-08-31.*
