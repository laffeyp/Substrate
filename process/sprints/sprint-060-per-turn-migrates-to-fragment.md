# Sprint 060 — `per_turn` migrates from string prefix to `PromptFragment(source=per_turn)`

```yaml
---
id: 060
status: open
phase: 8
pass_kind: migration
---
```

## Product-spec conformance

**Fulfills:** the first real migration of an existing composition site onto the Producer graph from sprint 059. `per_turn` today prefixes every UserMessage inside `render_transcript` (`src/substrate/topologies/session/transcript.py`); after this sprint it flows through the composer as a typed fragment. Product spec R-RISK-5 keeps this at the topology layer; the discipline is the substrate-native shape, not a spec addition.

**Consumes:** the composer Producer from sprint 059. The `per_turn` string field on `SessionManifest` stays exactly as it is — client-supplied, PATCH-able, persistent. Only its consumer path changes.

## Motivation

`per_turn` is the safest first real-source migration because it already has a live consumer. `render_transcript(per_turn=…)` (transcript.py:262-268) reads the manifest's `per_turn` value on every model firing and prefixes it to the UserMessage before token accounting. That works. The migration keeps the same field, the same wire, the same PATCH surface — and replaces the consumer with a `per_turn_producer` that yields a typed `PromptFragment(source=per_turn, text=manifest.per_turn, precedence=<early>, provenance={})`.

Why do it: (a) proves the sprint 059 primitive against a real string, not a stub. (b) puts the `per_turn` fragment on the record with its own seq, so `record diff` between two sessions of the same manifest shows a divergent `per_turn` at fragment granularity, not buried inside a bigger `assembled_prompt`. (c) uniform shape across every source, so sprint 061-064 slot in without needing case-by-case handling in `_model_factory`.

## Scope

One new Producer body, one Trigger, one deletion inside `render_transcript`, one update to `_model_factory`.

**`per_turn_producer` Producer.** Fires on `UserMessage` (every turn). Body: reads `manifest.per_turn` (bound at topology-build time from the daemon path; empty string when absent), yields `PromptFragment(source="per_turn", text=<value>, precedence=10, provenance={})`. When the manifest's `per_turn` is empty, yields nothing — the composer's empty-cohort handling from sprint 059 covers the no-fragment case cleanly.

**Precedence value.** `per_turn` is a session-scoped prefix; it should land BEFORE the current UserMessage but AFTER any role prompt (which is session-open-scoped). Precedence 10 leaves room: role at 0, bundle slots at 5, per_turn at 10, tools_suite at 20, parent_context at 30, user_message at 100.

**`render_transcript` deletion.** Remove the `per_turn` parameter from `render_transcript` (signature at `transcript.py:270`) and from the internal `_render` helper (`transcript.py:221`). The prefix injection is at `transcript.py:252-253` — remove. Per_turn tokens also feed the K-window budget calc at `transcript.py:176, 186, 298-299` (`_compute_k(driver_context_tokens, seed_tokens, per_turn_tokens, driver_headroom_frac)`). That dependency is real, not speculative: the budget must still account for per_turn's token cost after the migration. Two choices:
  - (a) The composer tracks per-fragment token estimates on `PromptComposed.total_tokens` and the K-window budget is computed against that value instead of against `per_turn` in isolation. Cleaner; the composer is the authority on prompt cost.
  - (b) `render_transcript` keeps a `session_open_fragment_tokens: int` parameter (renamed from `per_turn_tokens`) that the topology fills in at build time. Preserves the current budget-computation seam.

Prefer (a) — the composer emits total_tokens as an event field precisely so downstream consumers do not need to re-derive it.

**`_model_factory` update.** Pass `manifest.per_turn` into `per_turn_producer` at topology-build time, not into `render_transcript`. Same as the current `driver`, `seed`, `tools` bindings.

## Prerequisites

- Sprint 058 closed (vocabulary).
- Sprint 059 closed (composer + `_model_factory` reads `PromptComposed.text`).

## Context files

- `src/substrate/topologies/session/transcript.py` — `render_transcript` signature at ~L200, `per_turn` prefixing at ~L262-268. Remove the parameter; audit callers.
- `src/substrate/topologies/session/__init__.py:_model_factory` — passes `per_turn` to `render_transcript`; will pass to `per_turn_producer` instead at topology-build time.
- `src/substrate/topologies/session/composer.py` (new in sprint 059) — the composer subscribes to `PromptFragment`; no change here, `per_turn_producer` just adds another emitter.
- `substrate-ui/server.py:2500-2515` — the PATCH `/api/session/<id>` handler that mutates `per_turn`. No change; the wire stays identical.
- `tests/test_render_no_compaction.py`, `tests/test_render_rolling_window_basic.py`, `tests/test_render_transcript_compacted_on_record.py`, and any other `test_render_*` — update to reflect the removed `per_turn` parameter.

## Artifact contract → Files modified

- `src/substrate/topologies/session/__init__.py` — register `per_turn_producer`; pass `manifest.per_turn` into its factory; remove `per_turn` from the `render_transcript` call at line 265.
- `src/substrate/topologies/session/transcript.py` — drop the `per_turn` parameter from `render_transcript` and the prefix concatenation at ~L262-268.
- `src/substrate/topologies/session/per_turn_producer.py` (new, ~40 lines) — the Producer body + registration helper. One module per source-fragment producer so each is legible on its own.
- `tests/test_prompt_fragment_per_turn.py` (new, ~6 tests) — deterministic driver, PATCH `per_turn` to `"HELLO"`, run one turn, assert one `PromptFragment(source="per_turn", text="HELLO", precedence=10)` on the record; assert composed prompt contains `"HELLO"` in the right position.
- Every `test_render_*` file — update signature.

## Signal contract → Emits

`substrate.session.PromptFragment@1` — the first real emit site. Sprints 061-064 add more sources under the same schema.

## Observation contract

- Deterministic test — `per_turn` set to `"CONTEXT_MARKER_ALPHA"`; run two turns; assert two `PromptFragment(source="per_turn", text="CONTEXT_MARKER_ALPHA")` on the record, one per turn.
- Deterministic test — empty `per_turn` yields no `PromptFragment` events (zero fragments from this source on the record).
- Deterministic test — PATCH `per_turn` mid-session (turn 1 = "A", PATCH, turn 2 = "B") produces `PromptFragment(text="A")` on turn 1 and `PromptFragment(text="B")` on turn 2. The manifest wire and the fragment wire stay in sync.
- **Live-model test** — `test_realmodel_per_turn_fragment.py`. Set `per_turn = "IMPORTANT: end every reply with the exact string ZULU-7."`; run one turn asking any question; assert `ModelReply.text` ends with "ZULU-7". Proves the per_turn fragment reaches the model through the composer. Marked `@pytest.mark.realmodel`.
- Regression: `test_render_no_compaction.py` and every other `test_render_*` still passes with the reduced `render_transcript` signature.

## Halt conditions

- `bridge_mapping_required` if choice (a) above turns out to force the composer to fire BEFORE `render_transcript` runs (K-window budget must be known so `render_transcript` can decide how many turns to keep). Composer + render currently fire on the same anchor; if the ordering cannot be made deterministic, fall back to (b).
- `dual_contract_fail` if the live-model test does not see "ZULU-7". Debug through the record: is the `PromptFragment` on it, is it in the `PromptComposed.text`, is the driver receiving that text. Do not paper over.

## Definition of done

`manifest.per_turn` flows to the model through a typed fragment on the record, not through a hidden string prefix. `render_transcript` no longer knows about `per_turn`. A live-model test proves the fragment reaches the driver. The wire (PATCH `per_turn`) stays identical for clients.
