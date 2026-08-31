# Review — sprint 210, piece-A observation contract discharge

Reviewer: Claude. Date: 2026-08-26.
Scope: correctness of the discharge, SDD hard-rule-9 hold, coverage of the tech-spec §3 observation contract, code style, substrate primitives use.
Read: `src/substrate/topologies/session/ci.py`, `tests/test_session_topology_e2e.py`, `tests/fixtures/two_turns.json`, `process/sprints/sprint-210-piece-a-observation-contract.md`, BLACKBOARD Surfaced-for-review head, `src/substrate/testing.py:33-40`, commit `cc85ecd`.

## What sprint 210 does

The sprint runs the tech-spec §3 piece-A observation contract in-process against `ci_session_topology(turns=<from tests/fixtures/two_turns.json>)`. Five tests land in `tests/test_session_topology_e2e.py`. The stderr-substring and terminal-screenshot pieces of the tech spec's observation contract defer to sprint 221 (once `substrate chat` exists). The fixture on disk carries three entries: `[{"text": "say hi"}, {"text": "count to five"}, {"text": "/exit"}]`.

The scope amendment is folded honestly on the sprint card at line 16, in the test docstring at lines 3-13, in the commit message, and in the 2026-08-26 BLACKBOARD entry. Piece A closes on the record. Pieces B, C, D, F, H unblock.

## Three real gaps

### The pause-await-input path never fires in sprint 210's discharge

Tech spec §3 lists `substrate.TerminationMatched(decision="pause-await-input")` twice in the expected sequence — after Park in turns 0 and 1 — plus one `finalise-run` after SessionEnded. The sprint card at line 50 reproduces that sequence verbatim as the content assertion.

`ci_session_topology` at `src/substrate/topologies/session/ci.py:113-115` overwrites `session_topology`'s `pause_await_input(Park)` termination with `threshold_count("SessionEnded", 1)`. The test at line 148-150 asserts exactly one TerminationMatched with decision `finalise-run`. The pause-await-input path never runs in sprint 210's tests.

Sprint 209a's `test_one_turn_scripted_pauses_on_park` (turn 0 pauses on Park) and `test_second_turn_appends_to_the_same_record` (turn 1 resumes and appends) do exercise the production termination shape end-to-end, one turn each. The three-turn cycle the production daemon will drive — pause on turn 0, resume, pause on turn 1, resume, `/exit`, finalise — has no single-test pin at either sprint. Piece A closes with the production termination's end-to-end coverage split across two sprints and no sprint-210-level assertion on the shape the sprint was written to verify.

### The third-turn Park loss pins to a substrate scheduling race the topology does not document

The payload-kind list at `test_session_topology_e2e.py:71-84` asserts twelve entries with exactly two Park events. The tech-spec sequence at sprint-card line 50 has one Park per turn.

`/exit` on turn 2 fires two triggers from the same UserMessage: `end-on-exit` starts `session_end`, and `resume-on-user` → `park-on-final` starts `park`. `session_end` emits SessionEnded first, `threshold_count("SessionEnded", 1)` matches, the run finalises before `park` completes and emits its Park(turn_index=2). The commit message calls this "honest reality of the append cycle."

`assert_replayable(root, "3a")` at line 163 proves the race resolves the same way twice on this substrate build. The invariant that decides which producer wins — "session_end wins over park in the /exit chain" — lives nowhere in `session/__init__.py` or `session/ci.py`. A future change to how the substrate interleaves the two concurrent producers flips the resolution and breaks the twelve-entry list-equality pin without any signal at the edit site. The test comment at lines 124-128 names the race; it does not name what the pin depends on.

### The per-payload predicates check one FinalAnswer and one ModelReply out of three

`assert_event` in `src/substrate/testing.py:33-40` returns on the first match: "Assert at least one event of `kind` with the given partial payload exists; return the first match."

`assert_event(record_root, "FinalAnswer", steps=0)` at test line 93 runs once against three FinalAnswer events. A regression that set turn-2's FinalAnswer to `steps=99` passes this assertion. The two ModelReply assertions at lines 90-92 have the same shape — one call per turn index, each returning on the first match for that turn_index.

The sequence pin at 71-84 catches count and order; the per-payload predicates check depth on one instance per kind, not three. The ten assert-lines read like broader coverage than they carry.

## Two small

### `assert callable(assert_sequence)` exists to silence a ruff warning

Test line 176 asserts callability of `assert_sequence` with the comment "silences 'unused import'." The primitive is imported at line 41, not called by any assertion in the file. Asserting the callability of a function to satisfy the linter is ritual, not verification.

### `two_turns.json` holds three entries

The filename reads "two_turns"; the file contains two conversational turns plus `/exit`. The topology counts three UserMessage events with `turn_index` 0, 1, 2 — the test's own payload-kind list at 71-84 shows three UserMessage entries. Sprint 221 will read the file by name.

## What holds

- The scope amendment is folded on the sprint card, in the test docstring, in the commit message, and in BLACKBOARD.
- The fixture is on disk. Sprint 221 consumes an artifact, not a promise.
- The payload-kind sequence pin at test line 71-84 is strict list-equality, twelve entries, exact order.
- `api.assert_replayable(root, "3a")` runs green in `test_piece_a_is_replayable_end_to_end`.
- `ci_session_topology` rejects a `turns` list whose last entry is not `/exit` at build time (`ci.py:74-78`), raising `api.RegistrationError`.
- Every producer (`driver_stepper`, `model`, `park`, `session_end`) fires ProducerStarted; the three that terminate cleanly emit ProducerCompleted; the `session_end`-vs-TerminationMatched race is called out and the assertion relaxed with a prose note (test lines 124-128).
- Four key triggers verified via `TriggerFired`: `resume-on-user`, `park-on-final`, `end-on-exit`, `advance-on-park`.
- Exactly one `substrate.TerminationMatched` event, decision `finalise-run`, and the record's last envelope is `substrate.RunFinalised` (test lines 148-152).
- No `substrate.*` reserved name invented; no kernel-private reach; F-API-4 primitives (`assert_event`, `assert_no_event`, `read_record`) used throughout.
- BLACKBOARD Surfaced-for-review head at 2026-08-26 reads `SPRINT 210 LANDED. PIECE A CLOSED.` The sprint card writes `status: closed` after the surface, not before.
- Full-suite regression 888 passed / 4 skipped / 0 failures. Ruff + mypy strict clean.
- Five tests exist, five green in 0.17s, matching the sprint's claim of five.

## SDD hard-rule-9 hold

The rescope narrows the observation contract's scope, not its discipline. The record-level pin is what a scripted three-turn session commits to on the substrate today. The stderr and screenshot pieces sit in a downstream sprint with a real fixture that unblocks them. The one place the discipline stretches is finding 1 above: the sprint's discharged sequence is not the tech-spec §3 sequence — it is a sibling sequence produced by the CI-mode wrapper. The sprint card is transparent about which sequence its content-assertion block names (tech-spec) versus which sequence the tests actually verify (ci-wrapper). Piece A closes on the tests, not on the card's original assertion.
