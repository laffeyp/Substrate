# Sprint 203 — daily-driver vocabulary lock (substrate-ui side + dual-contract pairing)

```yaml
---
id: 203
status: closed
phase: daily-driver-piece-0
pass_kind: architecture
---
```

## scope

Bump the substrate-ui grader vocabulary from v0.5 to v0.6. Author `substrate-ui/signals/versions/0.6.json` adding EIGHT new grader tags matching the substrate-side kinds locked in sprint 202 per TECH-SPEC §13.5 pairing table:

- `DRIVER_SESSION_STARTED` — pairs with substrate `SessionStarted`.
- `USER_MESSAGE_INJECTED` — pairs with substrate `UserMessage`.
- `PARK_LANDED` — pairs with substrate `Park`.
- `DRIVER_SESSION_ENDED` — pairs with substrate `SessionEnded`. (Prefix ratified 2026-08-25 option-1 vote: v0.5's `SESSION_ENDED` is browser page unload, a different object; the `DRIVER_` prefix keeps v0.6 a strict superset of v0.5.)
- `TRANSCRIPT_COMPACTED_LANDED` — pairs with substrate `TranscriptCompacted`.
- `DRIVER_SESSION_WARNING_EMITTED` — pairs with substrate `SessionWarning`.
- `DRIVER_SESSION_END_REQUEST_ISSUED` — pairs with substrate `SessionEndRequested`.
- `PANE_SCROLLED` — new pane-category tag; carries `model_reply_ref` (substrate seq of the reply that caused the scroll) under `optional_payload`. This is the structural pairing for substrate `ModelReply` per TECH-SPEC §13.5 (no per-reply 1:1 named event). Sprint 202's "existing PANE_SCROLLED" note is corrected in the same landing to "new in v0.6." `SessionCompositeSpec` had a gap-proposal in §13.5 but is dropped from v0.6 in sprint 202 (daemon-internal, no record presence), so its `SESSION_COMPOSITE_OPENED` proposal drops with it.

The three tags round-5 named at TECH-SPEC §10 for the UI view lifecycle (`SESSION_TURN_INJECTED`, `SESSION_PARKED`, `SESSION_ENDED_BY_USER`) are UI-VIEW cadence tags, not dual-contract pairings for record-side kinds. They land in piece G's ui-side v0.6 bump (substrate-ui/sprints/033-onward), not here. Post-review 2026-08-25.

Extend `checkSessionBookends` grader invariants per TECH-SPEC §10. Author `substrate-ui/signals/versions/0.6-rationale.md` with the dual-contract pairing table (TECH-SPEC §13.5). Extend `checkSessionBookends` grader invariants per TECH-SPEC §10.

## prerequisites

- Sprint 202 closed and Architect-ratified.

## context_files

- Sprint 202's output: `substrate/process/signals/0.6.json`, `substrate/process/signals/0.6-rationale.md`.
- `substrate-ui/signals/versions/current.json` (v0.5, current).
- `substrate-ui/signals/versions/0.5-rationale.md` (for style parity).
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §13.5 (pairing table), §10 (grader invariants), §3 (event Structs).
- `substrate-ui/KIT_DIARY.md` H10 (reader-AND-controller UIs need own vocabulary) — the doctrine this bump follows.
- `substrate-ui/process/BLACKBOARD.md` — `## Decisions` for the vocabulary bump ratification.

## signal contract

### Emits

None (documentation).

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate-ui/signals/versions/0.6.json` — new file.
- `substrate-ui/signals/versions/0.6-rationale.md` — new file.
- `substrate-ui/signals/versions/current.json` — symlink update to `0.6.json`.

### Content assertions

- `0.6.json` parses. `vocabulary_version` equals `"0.6"`. `supersedes` equals `"0.5"`. `tag_count` equals `54 + 8 = 62` (seven `DRIVER_`-prefixed driver-session tags + `PANE_SCROLLED` as a new pane-category tag introduced in v0.6 to carry the `model_reply_ref` structural pairing).
- Each new tag entry declares `stratum`, `pane_id_scope` (which UI panes emit it), and any structural payload fields.
- `checkSessionBookends` grader entries added under `invariants` block naming: (a) every DRIVER_SESSION_STARTED followed by exactly one DRIVER_SESSION_ENDED within record lifetime OR record `status == "paused"` at grader read time; (b) no repeated `substrate.RunStarted` on one `session_id`; (c) every USER_MESSAGE_INJECTED reaches at least one FinalAnswer OR a `ProducerFailed` on the `model` producer; (d) every PARK_LANDED{reason: final_answer} is preceded by exactly one FinalAnswer at the same (session_id, turn_index); (e) DRIVER_SESSION_WARNING_EMITTED fires at most once per (session_id, condition_kind); (f) TRANSCRIPT_COMPACTED_LANDED.dropped_seq_end < TRANSCRIPT_COMPACTED_LANDED.kept_seq_start.
- `0.6-rationale.md` carries the full pairing table from TECH-SPEC §13.5 as a markdown table. Every substrate-side behavior kind from sprint 202 has a row.

### Command exit codes

- `python -m json.tool substrate-ui/signals/versions/0.6.json` exits 0.
- `cd substrate-ui && npm run signals` grades clean against v0.6 (existing fixtures continue to pass; new grader entries do not fire on the v0.5 fixtures because those records carry no session kinds).
- `grep -c "^| " substrate-ui/signals/versions/0.6-rationale.md` returns at least 12 (table rows).

## observation contract

Documentation + config bump. Observation is: run `npm run signals` on the existing console + studio fixtures — the grader must continue to pass without regression, since v0.6 is a strict superset of v0.5. Architect ratifies in `substrate-ui/process/BLACKBOARD.md ## Decisions` with a one-paragraph entry naming v0.6 as the daily-driver UI-side lock and the dual-contract pairing as recorded.

## halt conditions to watch

- `vocabulary_change_required` — if the pairing table shows a substrate-side kind with no viable UI grader tag. Propose a typed gap in the rationale doc; halt until Architect ratifies the gap or renames the substrate-side kind.
- `dual_contract_fail` — if `npm run signals` regresses on existing fixtures. Do not close.
- `awaiting_architect_decision` — the ratification entry.

## definition of done

Both files exist. `npm run signals` green. Pairing table matches TECH-SPEC §13.5 row-for-row. Architect Decision ratifies v0.6 on the UI side. Sprint 204 (canonical-home registry + cross-repo ratification) can dispatch.
