# Sprint 067 — `_model_factory` consumes `PromptComposed.text`

```yaml
---
id: 067
status: closed
phase: 8
pass_kind: migration
closed_at: 2026-09-01
closed_by: substrate main HEAD after this card
scope_note: model producer now consumes PromptComposed.text as the primary prompt. render_transcript no longer injects per_turn. Live-model assertion verified per_turn fragment reaches the driver (kimi-k2.6:cloud reply carried "ZULU-7"). The prompt-composition arc (sprints 058-067) is compute-path complete.
---
```

## Product-spec conformance

**Fulfills:** the load-bearing compute-path switch sprint 064 deferred. Sprints 058-064 shipped the vocabulary, composer, and every fragment source; the composed prompt lands on the record with fragment-level provenance. Sprint 065 deleted the pre-arc scaffolding. Sprint 066 cleaned the fabricated spec citations. Sprint 067 flips the model producer to READ the fragment-composed prompt as its input — the arc's telos.

**Consumes:** everything sprints 058-064 shipped. No new primitives.

## Motivation

Post-sprint-064, the composer emits `PromptComposed` with the deterministic full-turn cohort. The record carries `role`, `bundle_*`, `tools_suite`, `per_turn`, `parent_context`, and `user_message` fragments per turn, each with source-specific provenance. But the model producer still reads through `render_transcript` — the fragments are observational only. Live-model assertions for role / per_turn / bundle wait for the switch.

The migration proves the arc: a session with `role=reviewer` produces a model reply that reads as reviewer output; a session with `per_turn="END WITH ZULU-7"` produces a reply ending with ZULU-7. Neither is provable while `_model_factory` reads from `render_transcript`.

## Scope

Three edits + one live-model test file.

**Model producer's trigger.** `resume-on-user` (fires on `UserMessage`) becomes `resume-on-composed` (fires on `PromptComposed`). Composer's chain (`UserMessage → per_turn_fragment → user_message_fragment → composer`) guarantees `PromptComposed` lands per turn; the model waits for it. Input builder reads `PromptComposed.text` from the anchor event's payload and passes it as `composed_prompt`.

**`_continue_input` / wrap-up input builders.** Add `composed_prompt` field from a `latest_composed = PerKindLatest("PromptComposed")` view. Tool-loop continuations within a turn keep the same composed prompt (the user's turn hasn't ended).

**`_model_factory` body.** Reads `composed_prompt` from input; prepends it to the transcript-rendered prompt when non-empty. The transcript rendering retains multi-turn history from prior turns.

**`render_transcript`'s current-turn `per_turn` injection.** Remove. `_render` no longer prepends `per_turn` to the current turn's USER: line. The K-window budget calc keeps `per_turn` as a parameter (still needs the token estimate).

**Live-model test file.** `tests/test_realmodel_prompt_composition.py`. Marked `@pytest.mark.realmodel`; deselected in the default CI run. Verifies per_turn (ZULU-7 pattern) reaches the driver via the fragment path.

## Prerequisites

- Sprint 058 through 066 all closed.
- Composer's `PromptComposed` emission verified on the record via sprint-064 tests.

## Context files

- `src/substrate/topologies/session/__init__.py`:
  - `_model_factory` at ~L237-380 — body reads new `composed_prompt` field from input.
  - `resume-on-user` trigger at ~L720ish — renamed and re-anchored.
  - `_continue_input` helper — gains `composed_prompt` field.
  - `latest_composed` view — new registration.
- `src/substrate/topologies/session/transcript.py`:
  - `_render` at ~L219 — remove the per_turn prefix at ~L252-253.
  - `render_transcript` signature keeps `per_turn` (K-window budget still uses it).
- `tests/test_realmodel_prompt_composition.py` — new file with live-model assertions.

## Artifact contract → Files modified

- `src/substrate/topologies/session/__init__.py` — trigger rename, `_continue_input` extension, `_model_factory` body update, `latest_composed` view registration.
- `src/substrate/topologies/session/transcript.py` — one deletion inside `_render`; docstring update.
- `tests/test_session_topology_e2e.py` — race-tolerant band for ModelReply/FinalAnswer counts (turn 2's /exit may lose the model race post-migration); `resume-on-user` → `resume-on-composed` rename in the trigger-id assertion.
- `tests/test_session_topology_bundled.py` — same race-tolerant band on ModelReply/FinalAnswer.
- `tests/test_realmodel_prompt_composition.py` (new, 2 live-model tests + 1 on-record verification).
- 18 bundled CI records regenerated.

## Signal contract → Emits

No new vocabulary. Existing `PromptComposed` becomes a load-bearing event consumed by the model producer.

## Observation contract

- All existing sprint-058-066 tests stay green.
- Deterministic-driver session end-to-end: model reply reflects fragment-composed prompt (verified by CI records regenerating cleanly).
- Race-tolerant tests: 2 or 3 ModelReply / FinalAnswer / Park across three turns (turn-2 /exit races end-on-exit).
- Live-model: per_turn="ZULU-7" instruction shows up in ModelReply.text.
- Live-model: PromptFragment(source=per_turn) with the right text on the record + PromptComposed containing that text.

## Halt conditions

- `bridge_mapping_required` if `PerKindLatest("PromptComposed")` returns None on the first firing (composer hasn't fired yet). Fall back to `assembled_prompt` from UserMessage payload; document the fallback.
- `dual_contract_fail` if the live-model test fails. Debug via the record: is PromptFragment on it, is PromptComposed containing per_turn text, is _model_factory receiving `composed_prompt`. Do not paper over.

## Definition of done

`_model_factory` reads the model's prompt from `PromptComposed.text` (fragment-composed). `render_transcript` no longer injects `per_turn`. A live-model test asserts a fragment instruction reaches the driver. The prompt-composition arc (sprints 058-067) is compute-path complete.
