# Sprint 068 — fragment-source failure surfaces as `SessionWarning`; chain never breaks

```yaml
---
id: 068
status: closed
phase: 8
pass_kind: correctness
closed_at: 2026-09-02
closed_by: substrate main HEAD after this card
scope_note: chain triggers now subscribe to {PRODUCER_COMPLETED, PRODUCER_FAILED} — chain never breaks. warn-on-fragment-error trigger surfaces every fragment-source failure as SessionWarning(kind=fragment_source_failed, source_name=<kind>). Vocabulary bumped to v0.2.1. Session runs to completion despite fragment failures.
---
```

## Product-spec conformance

**Fulfills:** the error-handling audit of sprints 058-067 surfaced two related bugs (F1 + F2). Both close in one sprint because both need the same chain-trigger change and share the vocabulary extension.

**F1:** a session-open fragment-source Producer failure (role file deleted between session-create validation and RunStarted; bundle slot ambiguity trips `BundleShapeError`; parent record torn when `parent_context_producer` fires) currently produces `substrate.ProducerFailed{producer.kind=<source>}` on the record but no session-side trigger handles it. Composer keeps firing on the per-turn chain; `PromptComposed.text` silently drops the failed source; model runs on a truncated prompt. No `SessionWarning` fires. No operator signal. The user sees a model that ignores its role or bundle instructions and cannot tell whether the prompt was assembled wrong or the model just refused.

**F2:** the per-turn chain (`UserMessage → per_turn_fragment → user_message_fragment → composer`) subscribes to `substrate.ProducerCompleted` only. If per_turn or user_message ever raised (their bodies do no I/O today, but a future turn-scoped fragment source might), the chain breaks — no PromptComposed → post-sprint-067 `resume-on-composed` never fires → session hangs. `session_topology`'s termination policy `any_of(pause_await_input(Park), threshold_count(SessionEnded, 1))` requires a Park or a SessionEnded; neither can happen.

## Motivation

Substrate discipline says every failure lands on the record with source provenance; every operator-relevant condition emits a typed signal. Today fragment-source failures are invisible in one direction (F1) and structurally fragile in the other (F2). One trigger extension + one new SessionWarning kind + one new payload field fixes both.

## Scope

Three edits + one vocabulary bump + tests.

**Chain-trigger subscription extension.** `emit-user-message-fragment` and `compose-on-cohort-complete` triggers extend their subscription from `{substrate.ProducerCompleted}` to `{substrate.ProducerCompleted, substrate.ProducerFailed}`. Predicates unchanged (still filter on producer.kind). Chain fires whether the prior link succeeded or failed. Composer's cohort simply lacks the failed fragment; PromptComposed emits with whatever landed.

**`warn-on-fragment-error` trigger (new).** Subscribes to `substrate.ProducerFailed` with predicate `producer.kind in FRAGMENT_SOURCE_KINDS`. Fires a session_warning producer instance with an input dict naming the failed source kind. Cadence: at most once per (session_id, source_name) pair per session — a repeated failure on the same source across turns fires the warning ONCE, not per turn.

**`session_warning` producer body extension.** Today's `_session_warning_factory` closes over `kind="seed_alone_exceeds"` and its fields. Needs to accept an input variant carrying the fragment-source name. Either: extend the factory to take a discriminated union of warning shapes, OR add a second producer_kind `fragment_error_warning` that emits `SessionWarning(kind="fragment_source_failed", source_name=<name>, ...)`. Prefer the second — the factory closures stay simple; each producer_kind has one input shape.

**Vocabulary bump.** `substrate/process/signals/session-vocabulary.md` § I appended with a v0.2.1 section: `SessionWarning.kind` gains value `"fragment_source_failed"`; a new optional payload field `source_name: str?` names the failed fragment producer's kind (e.g., `"role_fragment"`, `"bundle_methodology_fragment"`). Cadence: at most once per (session_id, source_name) pair.

## Prerequisites

- Sprints 058-067 all closed.
- The error-handling audit findings F1 + F2 (this sprint's own motivation).

## Context files

- `src/substrate/topologies/session/__init__.py`:
  - Chain triggers `emit-user-message-fragment` (~L858-869) and `compose-on-cohort-complete` (~L920-928) — extend subscription.
  - New `warn-on-fragment-error` trigger — add after the chain triggers.
  - `_session_warning_factory` (~L440ish) — extend or sibling new factory.
  - New `fragment_error_warning` producer_kind registration.
- `src/substrate/topologies/session/vocabulary.py` — add `FRAGMENT_SOURCE_KINDS` frozenset.
- `substrate/process/signals/session-vocabulary.md` § I — append v0.2.1 section with the new kind value + payload field.
- `tests/test_prompt_fragment_role.py` and siblings — reference for existing fragment-source test shapes.

## Artifact contract → Files modified

- `src/substrate/topologies/session/__init__.py` — chain trigger extensions; new trigger; new producer_kind + factory.
- `src/substrate/topologies/session/vocabulary.py` — `FRAGMENT_SOURCE_KINDS` frozenset naming the seven kinds.
- `substrate/process/signals/session-vocabulary.md` — v0.2.1 section under § I.
- `tests/test_fragment_source_failure_handling.py` (new, ~5 tests):
  - Delete a role .md between topology-build and RunStarted; assert `SessionWarning(kind=fragment_source_failed, source_name=role_fragment)` lands.
  - Chain-robustness: monkey-patch `per_turn_producer_factory` to raise; assert composer still fires and emits PromptComposed with only user_message.
  - Cadence: two turns, same failed source; assert exactly one SessionWarning.
  - Session runs to completion (`SessionEnded` lands) despite fragment failures.
- Live-model test: session with a role that raises at RunStarted; verify model still produces a ModelReply.

## Signal contract → Emits

`substrate.session.SessionWarning@1` with `kind="fragment_source_failed"`, new optional payload field `source_name`. Existing `kind` values (`"seed_alone_exceeds"`, `"bundle_changed"`) unchanged.

## Observation contract

- Force `role_fragment` to fail (delete the file after topology build); assert:
  - `substrate.ProducerFailed{producer.kind=role_fragment}` on the record.
  - `SessionWarning(kind=fragment_source_failed, source_name=role_fragment)` on the record.
  - `PromptFragment(source=role)` absent from the record.
  - `PromptComposed` still fires per turn; its text lacks the role content.
  - `ModelReply` still lands (session runs to completion).
- Chain-robustness: patch `per_turn_producer_factory` to raise; assert composer chain still fires (compose-on-cohort-complete predicate matches on Failed too); assert PromptComposed emits with only user_message + tools_suite.
- Cadence: two turns with the same failed role; assert exactly one SessionWarning (not two).
- Live-model: same shape as above but against a real driver; assert ModelReply exists (proves no hang).

## Halt conditions

- `bridge_mapping_required` if the kernel's `Subscription` shape does not allow OR-ing across `PRODUCER_COMPLETED` and `PRODUCER_FAILED` (should — subscription.kinds is a frozenset). Halt if a per-kind fanout is required instead.
- `spec_ambiguity` if session-vocabulary v0.2 already ratified a distinct meaning for the `source_name` field. Grep the doc first.

## Definition of done

Every fragment-source failure lands on the record as both `substrate.ProducerFailed` (kernel-emitted) AND `SessionWarning(kind=fragment_source_failed, source_name=<kind>)` (topology-emitted, operator-visible). The per-turn composer chain never breaks — subscribes to both terminal states. Session runs to completion despite any fragment-source failure; the model reads a possibly-truncated composed prompt and replies normally. A live-model test proves no hang.
