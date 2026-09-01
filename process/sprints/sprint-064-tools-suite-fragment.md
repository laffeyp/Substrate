# Sprint 064 — tools-suite description wires as `PromptFragment(source=tools_suite)`

```yaml
---
id: 064
status: open
phase: 8
pass_kind: migration
---
```

## Product-spec conformance

**Fulfills:** the final real composition site inside `_model_factory`. Today the model Producer body builds tool descriptions inline: `f"{prompt_text}\n\nTools you MAY use:\n{suite_describe(tools)}\n"` (`src/substrate/topologies/session/__init__.py:349`). Wrap-up and loop paths each concatenate their own variants. This sprint moves all of them behind the composer so the model Producer body reads bare text from `PromptComposed`.

**Consumes:** the composer + fragment shape from sprints 059-063. `suite_describe(tools)` (from `substrate.topologies.tool_loop.tools`) stays as-is — it correctly renders a tool suite as prose.

## Motivation

`_model_factory` is the last place in the session topology where prompt text is built inline. Three sites: the driver-path wrap-up prompt (line ~301), the ollama-tools loop prompt (line ~334), and the text-parse loop prompt (line ~349). Each stitches `prompt_text` (the composed prompt from earlier turns' assembled_prompt) with a tools description or a wrap-up instruction. After this sprint, the tools description is a `PromptFragment(source=tools_suite)` on the record, precedence 20; wrap-up instructions become their own fragment source (`source=wrap_up`, added to the enum in this sprint).

Once this sprint closes, `_model_factory` never concatenates strings. Its body reads `PromptComposed.text`, calls the driver, yields the reply. The composition graph fully replaces the string-building.

## Scope

Two new fragment sources, three deletions inside `_model_factory`, one enum addition.

**`tools_suite_producer` Producer.** Fires when `tools` is non-empty on the session_topology (topology-build-time bound). Body: yields one `PromptFragment(source=tools_suite, text=suite_describe(tools), precedence=20, provenance={"tool_names": list(tools.keys())})` at `substrate.RunStarted`. Session-open scope (fires once, carries across turns).

**`wrap_up_producer` Producer.** Fires ONLY on the wrap-up-trigger firing (turn ends with `final=True`). Body: yields one `PromptFragment(source=wrap_up, text="tools disabled this turn; answer plainly; explain what happened in one or two sentences", precedence=15, provenance={"reason": <turn-terminator reason>})`. This one is turn-scoped — it appears in the wrap-up turn's `PromptComposed` and no other turn.

**Enum extension.** Sprint 058's `PromptSource` enum gains two values: `tools_suite` and `wrap_up`. Vocabulary bump lands in `signals/versions/0.2.1.json` (or a full 0.3 lock — decide at start based on how many other cards want to piggyback).

**`_model_factory` deletions.** The three inline concatenations at ~L301, ~L334, ~L349 delete. The body reads `assembled_prompt` from its input (now the `PromptComposed.text` field the model producer's trigger delivers) and passes it verbatim to `call_responder(driver, prompt_text)`. No f-string composition inside the producer body.

## Prerequisites

- Sprint 058, 059, 060, 061, 062, 063 closed.
- No open card modifying `suite_describe` or the tools registration path.

## Context files

- `src/substrate/topologies/session/__init__.py:_model_factory` (~L215-370) — three inline composition sites at ~L301, ~L334, ~L349. All three delete.
- `src/substrate/topologies/tool_loop/tools.py::suite_describe` — the tool-description renderer. Stays as-is; the producer body calls it.
- `src/substrate/topologies/session/tools_suite_producer.py` (new).
- `src/substrate/topologies/session/wrap_up_producer.py` (new).
- `substrate/process/signals/session-vocabulary.md` v0.2 section (from sprint 058) — extend the `PromptSource` enum with two values under a v0.2.1 or v0.3 lock.

## Artifact contract → Files modified

- `src/substrate/topologies/session/tools_suite_producer.py` (new, ~50 lines).
- `src/substrate/topologies/session/wrap_up_producer.py` (new, ~50 lines).
- `src/substrate/topologies/session/__init__.py` — register both producers; delete the three inline concatenations in `_model_factory`; `_model_factory` body shrinks noticeably.
- `substrate/process/signals/session-vocabulary.md` — append the two new enum values under a dated v0.2.1 (or v0.3) section. Prior versions stay byte-identical.
- `signals/versions/0.2.1.json` (or 0.3) — new file, adds the two enum values.
- `tests/test_prompt_fragment_tools_suite.py` (new, ~4 tests) — deterministic driver, session with two tools (`echo`, `sleep`), assert one `PromptFragment(source=tools_suite)` on the record whose text contains both tool names.
- `tests/test_prompt_fragment_wrap_up.py` (new, ~3 tests) — deterministic driver + scripted tool that always fails; force wrap-up; assert one `PromptFragment(source=wrap_up)` on the wrap-up turn and none on prior turns.

## Signal contract → Emits

`substrate.session.PromptFragment@1` with `source=tools_suite` and `source=wrap_up`. Vocabulary bump to v0.2.1 (or v0.3).

## Observation contract

- Deterministic test — session with `tools={"echo": …, "sleep": …}`; assert `PromptFragment(source=tools_suite)` on record whose text contains "echo" and "sleep"; assert `PromptComposed.text` on every turn contains that fragment (session-scoped).
- Deterministic test — session with `tools={}`; zero `PromptFragment(source=tools_suite)` on record.
- Deterministic test — scripted turn that fires the wrap-up trigger; assert one `PromptFragment(source=wrap_up)` on the wrap-up turn's cohort, and it does NOT appear in earlier turns' `PromptComposed`.
- Deterministic test — `_model_factory` no longer contains any f-string composition of prompt text (grep the file: zero hits for the removed patterns).
- **Live-model test** — `test_realmodel_tools_suite_fragment.py`. Session with a single custom tool (`stamp` that echoes its input); prompt = "call the stamp tool with the exact word GARNET"; assert a ToolCall on the record with args containing "GARNET". Proves the tool description reached the model. Marked `@pytest.mark.realmodel`.

## Halt conditions

- `bridge_mapping_required` if `_model_factory`'s wrap-up path cannot cleanly bind the wrap_up fragment BEFORE the composer fires (timing dependency: the wrap-up trigger and the composer trigger both fire on the same anchor). Choose: composer sees wrap-up on the same turn's cohort, or composer fires a second time on the wrap-up turn. Pick one, land the decision in the sprint close.
- `dual_contract_fail` if the model does not call the stamp tool in the live test. Debug through the record: is the tools_suite fragment on it, does the composed text carry the tool description, is the driver receiving that text.

## Definition of done

`_model_factory` body contains zero prompt-composition string operations. Every session's tool suite and every wrap-up instruction ride as typed fragments on the record. A live-model test proves the tool description reaches the driver.
