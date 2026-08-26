# REVIEW — session-vocabulary.md (2026-08-25)

*Reviewer role. Target: `substrate/process/signals/session-vocabulary.md` (163 lines, read in full). Cross-checks: `sprint-202-daily-driver-vocab-substrate.md`, `sprint-203-daily-driver-vocab-ui.md`, `sprint-204-daily-driver-canonical-home-ratification.md`, `sprint-206-session-topology-triggers-termination.md`, `sprint-225-pair-coding-session-composite.md`, `TECH-SPEC-2026-08-25-round6.md` §§ 3, 3a, 6, 10, 13.5, `substrate/process/BLACKBOARD.md` `## Decisions`, `substrate/src/substrate/kernel/runtime.py` for `_Lifecycle`, directory listing of `substrate/process/signals/`.*

---

## Severity

Two serious items — a ratification the BLACKBOARD does not carry, and a Park invariant no trigger fires. Four consistency items where the doc, its own sprint card, and adjacent docs disagree on shape or count. Three smaller precision items.

Nothing on fire. The vocabulary shape reads correct; the case-convention rule at §A closes a prior review finding, the SessionCompositeSpec carve-out is defensible, the §G pairing table lands one previously-open gap-proposal. The issues sit at the boundary between what the vocab locks and what the sprint chain actually implements.

## What checks

- **§A names the two-convention rule explicitly.** PascalCase for msgspec Structs, SCREAMING_SNAKE for wire events emitted via `_Lifecycle`. Closes the prior finding about mixed casing in one lock.
- **§A declares `SessionCompositeSpec` out of scope with reason.** "daemon-internal dataclass ... never lands on a substrate record, and is deliberately not in this lock." Closes the prior finding about a name locked without a shape.
- **§G pairs `SessionEndRequested` with `SESSION_END_REQUEST_ISSUED` — "named tag (ratified 2026-08-25)".** Half of the prior Sprint 203 pairing gap closed.
- **`_Lifecycle` exists at `runtime.py:42` and emits every `substrate.ProducerCancelled` at `runtime.py:577`.** The vocab's citation resolves.
- **§C locks Park.reason as three values including "interrupt".** The vocabulary layer commits to the invariant the direction review flagged; the vocabulary side of the fix is done.
- **§H names the extension discipline.** "Additions follow the swebench-solver-vocabulary pattern: bump the header status to `RATIFIED — v0.X`, add a new lettered section at the bottom, byte-preserve §§ A-H. Never re-flow." Discipline that already worked once on the SWE-bench arc.
- **Every field's stratum is named.** §B, §C, §D, §E all carry a `Stratum: event/ambient` line per BOOTSTRAP.md.

## Serious — two findings

### The doc's `RATIFIED` header cites a Decision the BLACKBOARD does not carry

Line 3: "Status: RATIFIED — v0.1 (2026-08-25). Locked at Sprint 202 close, ratified by Architect Decision entry in `substrate/process/BLACKBOARD.md`." §H line 161: "Sprint 202 close, 2026-08-25 ... Architect ratifies in `substrate/process/BLACKBOARD.md ## Decisions` — the Decision entry unblocks piece A dispatch per sprint 204."

`substrate/process/BLACKBOARD.md ## Decisions` (read in full) has no 2026-08-25 entry. The most recent Decision is 2026-08-11 (holistic review Tier 1 + rate-limit shim). Sprint 202 (`substrate/process/sprints/sprint-202-...`) carries `status: pending` with no Built entry. Sprint 204 (the ratification sprint) is also pending. No 2026-08-25 Decision unblocks piece A anywhere on disk.

The doc claims ratification that has not executed. A reader trusting the header would assume piece A is dispatchable; the actual chain still holds at Sprint 202-not-yet-closed.

### §C locks a Park-follows-Cancelled invariant that no piece-A trigger fires

§C line 92: "Exactly one [Park] after each `FinalAnswer`, `substrate.ProducerFailed{producer.kind:"model"}`, or `substrate.ProducerCancelled{producer.kind:"model"}`."

Tech spec §3 wires nine triggers. `park-on-final` subscribes to `FinalAnswer`. `park-on-model-error` subscribes to `substrate.ProducerFailed` where `producer.kind == "model"`. No trigger subscribes to `substrate.ProducerCancelled`. Sprint 206 wires exactly the nine triggers from §3 (verified by reading the card); no Cancelled-subscribing trigger.

`Runtime` emits ProducerCancelled at `runtime.py:577` on task cancellation. Sprint 215 § scope: `POST /interrupt` calls `loop.call_soon_threadsafe(task.cancel)`; Sprint 220's test asserts `substrate.ProducerCancelled` lands within 200ms. Neither sprint asserts a Park follows. On every Ctrl+C during a turn, ProducerCancelled lands, no trigger fires, no Park emission, no `pause_await_input` decision runs. §C's invariant fails on every interrupted turn.

The vocabulary side of the fix is now stronger than the direction review flagged (the invariant is locked); the trigger side is still missing (no `park-on-cancelled` in §3 or Sprint 206).

## Consistency — four findings

### The doc counts eight kinds; Sprint 202 counts nine; the task-breakdown counts nine

Header line 3: "eight application event kinds." §H line 161: "Locks the eight session-topology kinds ahead of piece A." §A last paragraph: "`SessionCompositeSpec` ... is deliberately not in this lock."

Sprint 202 § scope names nine kinds explicitly including `SessionCompositeSpec`. `TASK-BREAKDOWN-2026-08-25-daily-driver.md` row 202 lists the same nine. `TECH-SPEC-2026-08-25-round6.md` §2.5 Deliverables 1 names nine.

The doc's decision reads correct — `SessionCompositeSpec` is a factory return type, not a record event. But Sprint 202's card, the task-breakdown, and tech spec §2.5 all still say nine. Sprint 202 § content assertions line 66: "`grep -c '^### ' substrate/process/signals/0.6-rationale.md` returns at least 9." Under this doc's shape that assertion fails; there are eight.

### §G pairs eight substrate kinds with eight UI tags; Sprint 203 declares nine UI tags; §10 Piece G declares a different seven

§G lists eight pairings (`SessionStarted`→`SESSION_STARTED`, `UserMessage`→`USER_MESSAGE_INJECTED`, `Assistant`→`PANE_SCROLLED`+structural payload, `Park`→`PARK_LANDED`, `SessionEnded`→`SESSION_ENDED`, `SessionEndRequested`→`SESSION_END_REQUEST_ISSUED`, `TranscriptCompacted`→`TRANSCRIPT_COMPACTED_LANDED`, `SESSION_WARNING`→`SESSION_WARNING_EMITTED`).

Sprint 203 § artifact contract line 141 lists nine UI grader tags: SESSION_STARTED, USER_MESSAGE_INJECTED, PARK_LANDED, SESSION_ENDED, TRANSCRIPT_COMPACTED_LANDED, SESSION_WARNING_EMITTED, SESSION_TURN_INJECTED, SESSION_PARKED, SESSION_ENDED_BY_USER.

Tech spec §10 Piece G lists seven: SESSION_STARTED, USER_MESSAGE_INJECTED, PARK_LANDED, SESSION_ENDED, SESSION_TURN_INJECTED, SESSION_PARKED, SESSION_ENDED_BY_USER.

Three docs, three sets. This doc's §G doesn't mention SESSION_TURN_INJECTED, SESSION_PARKED, SESSION_ENDED_BY_USER at all. Sprint 203's list doesn't include SESSION_END_REQUEST_ISSUED (the "ratified 2026-08-25" tag this doc's §G names). §10 Piece G's list doesn't include either the TRANSCRIPT_COMPACTED_LANDED / SESSION_WARNING_EMITTED pairings or SESSION_END_REQUEST_ISSUED.

### §E.1 emits SESSION_WARNING via `_Lifecycle`, which is a kernel-private primitive

§E.1 line 115: "Emitted directly by the daemon via `_Lifecycle` at session-open condition checks — not a topology producer emission. Kept in this vocab because the daemon writes it onto the same record."

`_Lifecycle` sits at `substrate/src/substrate/kernel/runtime.py:42` (`from .sequencer import AppendCycle, _Emission, _Lifecycle`). The runtime uses it for `substrate.*` events at lines 367, 384, 395, 553, 575, 577, 590, 598. The leading underscore marks it as private per Python convention; the F-API-6 gate (`import-linter` at `cli.py:2-8`) enforces the public-only-import discipline for CLI code and, per tech spec §1.5, extends the same discipline to the daemon.

Application code (the daemon at `substrate-ui/server.py`) emitting a non-`substrate.*` kind via `_Lifecycle` reaches into a kernel-private path from outside the kernel. Either `_Lifecycle` needs promotion to a public seam (rename to `Lifecycle`, expose via `substrate.api`), or SESSION_WARNING needs its own `producer_kind` with a factory that runs inside a `Runtime`. The vocab locks a path the discipline forbids.

### §F #5 grades one Park-precedes case; §C locks three

§F invariant #5: "Every `Park{reason:"final_answer"}` is preceded by exactly one `FinalAnswer` at the same `turn_index`." Only covers `reason == "final_answer"`.

§C last line: "Exactly one [Park] after each `FinalAnswer`, `substrate.ProducerFailed{producer.kind:"model"}`, or `substrate.ProducerCancelled{producer.kind:"model"}`." Covers three terminals.

The doc's own grader is weaker than its own invariant. §F #4 checks the terminal reaches the record; it does not check Park emission follows. Under §F, a session can end a turn with ProducerFailed and no Park, and the grader passes. Under §C, that would be a violation. The doc contradicts itself.

## Smaller — three findings

### `SessionCompositeSpec`'s home file is named as if it exists

§A: "it lives at `substrate/src/substrate/topologies/applications/pair_coding_composite.py`, never lands on a substrate record, and is deliberately not in this lock."

That file is Sprint 225's output (piece E). Sprint 225 is pending. `substrate/src/substrate/topologies/applications/` currently holds `__init__.py`, `best_of_n_verified.py`, `fanout_review.py`, `research_sweep.py` (per tech spec §1 line 56). No `pair_coding_composite.py`. The doc names a future file's location as if it exists.

### Sprint 202's declared artifacts don't exist; `session-vocabulary.md` does

Sprint 202 § artifact contract lists three files: `signals/0.6.json`, `signals/0.6-rationale.md`, `signals/current.json` (symlink). Sprint 202 § content assertions checks properties of `0.6.json` (parses; `vocabulary_version` field; `tag_count`) and `0.6-rationale.md` (`### <kind_name>` headings).

`ls substrate/process/signals/` returns `session-vocabulary.md` (new), the older swebench and applications vocab docs, and the v0.1/v0.2 kernel-vocab files. No `0.6.json`. No `0.6-rationale.md`. No `current.json`. The vocab landed under a different filename that follows the SWE-bench pattern (`swebench-solver-vocabulary.md`) — a defensible choice, but Sprint 202's own assertions can't be evaluated against a file that doesn't exist.

Either Sprint 202 gets amended to match the actual artifact (rename `0.6.json` claims to `session-vocabulary.md`, drop `python -m json.tool` since the doc is markdown, drop `vocabulary_version` field check since markdown has no fields), or the vocab needs a companion `0.6.json` for the runtime code to import.

### §F invariant #4 grades wall time from a record whose `t` is supplementary

§F #4: "Every `UserMessage{turn_index=N}` reaches at least one `FinalAnswer` OR is followed by `substrate.ProducerFailed{producer.kind:"model"}` OR `substrate.ProducerCancelled{producer.kind:"model"}` within `turn_max_steps × model_timeout` wall time."

Substrate's own convention per tech-spec §1 line 40: "`t` is supplementary (excluded from D-8 equivalence, never used for ordering)." A grader reading a completed record cannot distinguish "the model producer took wall time under the budget" from "the daemon delayed the append." The invariant is intent-shaped, not grader-shaped. §F is the checkSessionBookends contract; every rule in it should be mechanically checkable from the record.

Either §F #4 restates as "the FinalAnswer / ProducerFailed / ProducerCancelled event lands at a seq greater than the UserMessage's seq" (grader-checkable, no wall-time), or the invariant moves out of §F into a separate "runtime-side contracts" section that the grader doesn't try to enforce.

## One-sentence summary

The vocab doc reads correct in shape and closes prior review findings (case convention explicit, SessionCompositeSpec carve-out named, SESSION_END_REQUEST_ISSUED pairing ratified), but its `RATIFIED` header cites a BLACKBOARD Decision entry that does not exist, its §C Park invariant covers three terminals the tech spec's trigger table only handles for two, its own §F grader is weaker than its §C invariants, its §E.1 SESSION_WARNING emission path reaches into a kernel-private `_Lifecycle` from application code, and its filename departs from Sprint 202's declared artifact contract without amendment.

---

*Reviewer: Claude, this session. New dated file per no-in-place-edits. Alongside `session-vocabulary.md` and the earlier vocab docs in `substrate/process/signals/`.*
