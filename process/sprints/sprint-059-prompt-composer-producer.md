# Sprint 059 — composer Producer: subscribe to `PromptFragment`, emit `PromptComposed`

```yaml
---
id: 059
status: open
phase: 8
pass_kind: primitive
---
```

## Product-spec conformance

**Fulfills:** the substrate-native shape for prompt composition. Product spec §4 principle 6 ("topologies are computations, not templates") is what this sprint honors — a composer is a Producer that subscribes to typed fragment events and emits a typed composed event, not a Python function that concatenates strings.

**Consumes:** the vocabulary from sprint 058 (`PromptFragment`, `PromptComposed`, the `PromptSource` enum).

## Motivation

Today the session topology's `_model_factory` (`src/substrate/topologies/session/__init__.py:215-370`) receives a bare `assembled_prompt: str` on its input event and does string composition inline: `f"{prompt_text}\n\nTools you MAY use:\n{suite_describe(tools)}\n"` (line 349) and similar. The composition happens on the hot path, leaves zero record trace, and cannot be replayed at fragment granularity.

The substrate-native replacement is a `prompt_composer` Producer that fires on every fragment cohort and emits one `PromptComposed`. The model Producer subscribes to `PromptComposed`, not to `UserMessage` directly. Fragments come from other Producers (sprints 060-064 wire the five real sources); the composer's only job is precedence-ordered join.

## Scope

One Producer body, one Trigger, one View, one composition function.

**`prompt_composer` Producer.** Subscribes to `PromptFragment`. Body: collect every fragment in the current cohort (all fragments that fired between the previous `PromptComposed` and now), order by `precedence` ascending, join `text` with `"\n\n"`, emit one `PromptComposed` with `fragment_seqs = tuple(env.seq for env in ordered)`, `total_tokens = sum(_est_tokens(f.text) for f in ordered)`, `strategy = "precedence_join"`.

**`fragment_cohort` View.** `KindBuffer("PromptFragment")` sliced to the tail since the last `PromptComposed`. Same shape as the anti-spin counter's per-turn slice from sprint 047 (`_step_of(ctx) + 1`); the last-composed cursor is a `KindCount("PromptComposed")` value.

**Composer Trigger.** Fires when the fragment cohort matures. Maturity in v0.2 is simple: a `session_ready` Trigger fires the composer once the current turn's fragments have all landed. In v0.2 that means: the composer fires on the same anchor the model Producer used to fire on — the `UserMessage` for the current turn — but AFTER every fragment source has yielded for this turn.

The ordering wrinkle (fragment sources must complete before the composer fires) is real. Handle by giving each fragment source a deterministic input trigger (fires on `UserMessage`) and giving the composer a `all_completed` Trigger over the fragment-source Producer instances. If `all_completed` is too heavy for the per-turn cadence, fall back to a `KindCount("PromptFragment") >= <expected_count>` Predicate where `expected_count` is passed at topology-build time.

## Prerequisites

- Sprint 058 closed (vocabulary locked, Structs importable).
- No open card modifying `_model_factory` or the session Trigger set.

## Context files

- `src/substrate/topologies/session/__init__.py` — `_model_factory` (~L215-370) is the current composition site. The composer replaces its string-building responsibility; `_model_factory` after this sprint reads `PromptComposed.text` off its input.
- `src/substrate/kernel/triggers.py` — `all_completed` and threshold-based Predicates.
- `src/substrate/kernel/views.py` — `KindBuffer`, `KindCount`.
- `substrate/process/signals/session-vocabulary.md` v0.2 section — the vocabulary from sprint 058.

## Artifact contract → Files modified

- `src/substrate/topologies/session/composer.py` (new file, ~120 lines) — the `prompt_composer` Producer body + the fragment-cohort View + the composer Trigger. One module so the seam is legible.
- `src/substrate/topologies/session/__init__.py` — register the composer Producer + Trigger + View in `session_topology`. `_model_factory` changes: its input Predicate becomes `PromptComposed` instead of the current UserMessage-anchored input; it reads `input.text` verbatim, no in-body concatenation.
- `tests/test_prompt_composer.py` (new file, ~10 tests) — deterministic-driver only. Seed the record with N synthetic `PromptFragment` events at varying precedence, fire the composer, assert the emitted `PromptComposed.text` matches the expected join, `fragment_seqs` reflects order, `total_tokens` is the sum.

## Signal contract → Emits

`substrate.session.PromptComposed@1` — one per model firing. Fragment provenance rides on `fragment_seqs`; a record reader trace-back from the composed event to every source fragment is one `read_record` scan.

## Observation contract

- Deterministic test — seed record with three `PromptFragment(source=A, precedence=1, text="alpha")`, `(source=B, precedence=2, text="bravo")`, `(source=C, precedence=0, text="charlie")`; fire composer; assert `text == "charlie\n\nalpha\n\nbravo"`, `fragment_seqs` in the right order, `total_tokens == expected`.
- Deterministic test — no fragments (empty cohort) emits a `PromptComposed(text="", fragment_seqs=(), total_tokens=0)` rather than skipping. Downstream model Producer decides how to handle empty; the composer is honest about the cohort it saw.
- Deterministic test — the composer fires exactly once per turn (not per fragment). A cohort of five fragments produces one `PromptComposed`, not five. Assert via `KindCount("PromptComposed")` on the record.
- **Live-model test** — `test_realmodel_prompt_composer.py`. One deterministic fragment source (a stub that yields `PromptFragment(source=per_turn, text="RESPOND WITH THE WORD BANANA")`); run one turn against a real driver (kimi-k2.7-code:cloud); assert the driver's `ModelReply.text` contains "banana" (case-insensitive). Proves the composed prompt actually reaches the model. Marked `@pytest.mark.realmodel`.

## Halt conditions

- `bridge_mapping_required` if the composer's Trigger anchor cannot be built from the existing kernel primitives (unlikely — `all_completed` over Producer instances is F-LIFE-2; threshold Predicates are standard). Halt and name the missing primitive rather than inventing one on the topology side.
- `dual_contract_fail` if the live-model test flakes for reasons other than the substance-under-test (Ollama timeout, model chose a synonym). Widen the assertion to a family of expected tokens rather than a single string; keep the test in the tree.

## Definition of done

`session_topology` composes prompts through a Producer that emits `PromptComposed`. `_model_factory` reads its input's `text` field and calls the driver — no f-string composition inside the model Producer body. The record carries one `PromptComposed` per model firing and one `PromptFragment` per source that contributed. A live-model test asserts the composed prompt reaches the driver by observing the reply.
