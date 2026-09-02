# Sprint 069 — `KindBufferWithSeqs` kernel primitive; composer emits real fragment seqs

```yaml
---
id: 069
status: open
phase: 8
pass_kind: primitive
---
```

## Product-spec conformance

**Fulfills:** the error-handling audit's F3 — `PromptComposed.fragment_seqs` provenance lie. `session-vocabulary.md § I` documents the field as "seq of every `PromptFragment` that composed the text, in composition order," implying a reader can trace back to record envelopes. Today `composer.py:100-104` populates it with positional cohort indices (`list(range(len(fragments)))`), not real envelope seqs. The provenance contract is violated on every session.

**Consumes:** `kernel/views.py`. Composer's input builder currently reads the fragment cohort via `KindBuffer.value()` which returns payloads only.

## Motivation

Substrate discipline says every event has a total-order seq; every field on the record that claims to point at an event points at its seq. Fragment provenance is that pointer for prompt composition. A reader inspecting a session's record should be able to grep `PromptComposed.fragment_seqs=[47,52,58,71]` and pull those envelopes by seq to see exactly which fragments composed the text. Today they cannot — the tuple is `[0,1,2,3]` and traces to nothing.

The root cause: `KindBuffer` (`kernel/views.py:47-65`) stores payloads only. `update(event)` appends `event.payload`; `value()` returns `list(self._items)`. The envelope's seq is dropped at the boundary. The composer's input builder reads the payload list and has no way to reconstruct the seq of each entry.

## Scope

One kernel-view addition + one composer input builder change + tests.

**Kernel-side: `KindBufferWithSeqs` view.** New class in `kernel/views.py`, sibling to `KindBuffer`. Same `Subscription(kinds=frozenset({kind}))` shape. `update(event)` appends `(event.payload, event.seq)` as a tuple. `value()` returns `list[tuple[payload, seq]]`. `deterministic = True` per the existing pattern.

Alternative under consideration: extend `KindBuffer` with a `values_with_seqs()` method that keeps a parallel seq list. Kernel surface stays smaller (one class not two). Downside: two `.value()`-shape methods on the same class read as an API accident rather than an API design. Prefer the new class.

**Topology-side: composer's cohort view.** `session_topology` registers `fragment_cohort` as a `KindBuffer(PROMPT_FRAGMENT)`; sprint 069 replaces it with `KindBufferWithSeqs(PROMPT_FRAGMENT)`. Composer's `compose-on-cohort-complete` trigger input builder reads `ctx.views["fragment_cohort"].value()` and gets a list of `(payload, seq)` tuples. Passes both into the composer producer's input as separate keys: `fragments` (payload list) and `fragment_seqs` (real seq list).

**Composer body:** `_compose_prompt(fragments, fragment_seqs)` already accepts a seq list — this sprint just fills it with real seqs. The pure function does not change. Sorting stays `(precedence, seq)` — same behavior; now `seq` is the actual record seq, so the ordering is deterministic against the record's total order.

**Rename compat:** existing callers of `_compose_prompt` in `test_prompt_composer.py` pass positional-index seq lists; those tests continue to work because the pure function does not know or care whether the seqs are real. Only the integration test needs to verify real seqs.

## Prerequisites

- Sprints 058-068 all closed.
- No open work modifying `kernel/views.py` or the composer's trigger.

## Context files

- `src/substrate/kernel/views.py:47-65` — `KindBuffer` definition (the model to copy).
- `src/substrate/kernel/views.py:1-25` — imports and the `Event`/`Subscription` types the new class needs.
- `src/substrate/topologies/session/__init__.py`:
  - `fragment_cohort` view registration (~L750ish) — swap the view class.
  - `compose-on-cohort-complete` trigger input_builder (~L920ish) — extend to unpack the (payload, seq) tuples.
- `src/substrate/topologies/session/composer.py:96-107` — composer body reads `fragments` and `fragment_seqs` from input; pure function `_compose_prompt` already accepts both. No factory change beyond documenting the seq source.
- `tests/test_prompt_composer.py` — existing tests should still pass; add a new integration test that reads the record's PromptComposed and verifies every fragment_seq matches a real envelope seq.

## Artifact contract → Files modified

- `src/substrate/kernel/views.py` — new `KindBufferWithSeqs` class (~20 lines).
- `src/substrate/kernel/__init__.py` (or wherever `KindBuffer` is exported) — export the new class.
- `src/substrate/topologies/session/__init__.py` — swap view class, extend input builder.
- `src/substrate/topologies/session/composer.py` — docstring update naming the seq source; body unchanged (already accepts seqs from input).
- `tests/test_prompt_composer.py` — add `test_prompt_composed_fragment_seqs_trace_to_record_envelopes`: run a session, read the record, for every `PromptComposed.fragment_seqs` verify each seq maps to a `PromptFragment` envelope on the record with matching source.
- `tests/test_kernel_views.py` (or wherever `KindBuffer` is tested) — unit tests for `KindBufferWithSeqs`.

## Signal contract → Emits

None new. `PromptComposed.fragment_seqs` becomes truthful — the field's existing v0.2 contract is now honored.

## Observation contract

- Kernel-level: `KindBufferWithSeqs` unit tests — three events of the subscribed kind land; view value is a list of three `(payload, seq)` tuples with seqs matching the envelopes' seqs.
- Topology-level: run a two-turn CI session with per_turn set and tools bound. Read the record. For every PromptComposed:
  - `fragment_seqs` is a tuple of ints.
  - Each seq is < the PromptComposed envelope's own seq (causality).
  - Each seq maps to a `PromptFragment` envelope on the record.
  - The set of sources named by those PromptFragment envelopes matches the sources represented in `PromptComposed.text` (verified by string containment).
- Regression: every existing sprint 058-068 test still passes.

## Halt conditions

- `bridge_mapping_required` if the kernel event API doesn't expose `.seq` on the object passed to `View.update(event)`. Read `kernel/runtime.py`'s view-update path first; the shape is standard but worth verifying.
- `spec_ambiguity` if `KindBuffer` has hidden callers assuming `value()` returns pure payloads (very likely — `results` view in `session_topology` reads `ctx.views["results"].value()` as `list[dict]`). Keep the old `KindBuffer` untouched; `KindBufferWithSeqs` is a sibling.

## Definition of done

`PromptComposed.fragment_seqs` on every session's record contains real envelope seqs. A reader inspecting the record can trace each seq to its `PromptFragment` envelope. The provenance contract in `session-vocabulary.md § I` now holds. `KindBufferWithSeqs` lives as a first-class kernel view alongside `KindBuffer`.
