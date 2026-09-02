# Sprint 063 — delegate context slice rewrites as `PromptFragment(source=parent_context)` in the child topology

```yaml
---
id: 063
status: closed
phase: 8
pass_kind: migration
closed_at: 2026-09-01
closed_by: substrate main HEAD after this card
scope_note: fragment producer + session_topology binding shipped. delegate.py rewrite deferred to a follow-up card — today's delegate drives tool_loop children (not session children), and rewiring the child factory shape is larger than the fragment producer work. _prefix_context_slice stays until that follow-up.
---
```

## Product-spec conformance

**Fulfills:** substrate-native replacement for `delegate.py::_prefix_context_slice` (~L280-301). Today the delegate builds a string in the parent process, prefixes it to the child's task, and hands the child a bare `assembled_prompt`. The child never sees the parent context as a typed fragment on its own record. `record diff` between two delegate calls with different context slices shows one giant string diff, not a fragment-level provenance trace.

**Consumes:** the fragment/composer pattern from sprints 059-062. The parent-record read logic in `_extract_context_slice` (~L203-266) stays — the extraction is correct; the packaging is what changes.

## Motivation

The delegate's context-slice path (path 3 in `delegate.py`) is one of the three real live-model composition sites in the tree, alongside role and per_turn. The 2026-09-01 audit finding F4 named the shape: string concatenation at three fixed anchors, no record trace on the child side.

The substrate-native shape: the delegate hands the child a `ParentContext` producer factory. The child's `session_topology` registers that producer; it fires at `substrate.RunStarted`; it reads the parent record's slice (path is passed in from the delegate); it yields one `PromptFragment(source=parent_context, text=<slice>, precedence=30, provenance={"parent_record_root": …, "parent_seq_range": [lo, hi], "kinds": [...]})`. Composer picks it up in every turn's `PromptComposed` (parent context is session-scoped, not turn-scoped).

The delegate no longer does string concatenation. It passes structured context to the child topology, which builds its own composed prompt through the same composer every other session uses.

## Scope

One new fragment source, one delegate-side rewrite, one wire.

**`parent_context_producer` Producer.** Fires on `substrate.RunStarted`. Body: reads `parent_record_root`, `parent_seq_range`, `kinds` from its bound inputs (passed by the delegate at topology-build time). Calls the existing `_extract_context_slice` (which stays as-is in `delegate.py` — the extraction logic is correct). Yields one `PromptFragment(source=parent_context, text=<slice>, precedence=30, provenance={"parent_record_root": <str>, "parent_seq_range": [lo, hi], "kinds": [...], "elided_count": <n>, "elided_bytes": <n>, "single_oversize": <bool>})`. When the slice is empty (no matching events), yields nothing.

**Delegate rewrite.** `_prefix_context_slice` at `delegate.py:280-301` deletes. Where it was called (`delegate.py:563-566`), the code instead binds `parent_context_producer` into the child topology's build. `assembled_prompt=task` at `delegate.py:491` stays clean — the task is the task; the parent context rides on its own producer.

**Session-open sourcing.** Same shape as sprint 061's role fragment — parent context fires at session-open and needs to appear in every turn's `PromptComposed`. Reuses the session-open fragment-carrying mechanism sprint 061 chose (shape A or B).

## Prerequisites

- Sprint 058, 059, 060, 061, 062 closed.
- Session-open fragment-carrying mechanism from sprint 061 landed.

## Context files

- `src/substrate/topologies/tool_loop/delegate.py`:
  - `_extract_context_slice` (~L203-266) — stays as-is; the producer body calls it.
  - `_format_context_event` (~L269-277) — stays as-is; producer uses it.
  - `_prefix_context_slice` (~L280-301) — deletes; the string-concat shape it embodies is gone.
  - The path-3 branch at ~L551-566 — rewrites to bind the producer instead of string-prefixing the task.
- `src/substrate/topologies/session/parent_context_producer.py` (new) — the Producer body.
- `src/substrate/topologies/session/__init__.py:session_topology` — new optional parameter `parent_context: dict | None = None` that binds the producer when set.
- `tests/test_delegate_per_call_context.py` (9 tests) — every existing test needs a shape update: instead of asserting the child's first UserMessage was prefixed with a `[context from parent record…]` header, assert the child's record carries a `PromptFragment(source=parent_context)` with matching provenance.

## Artifact contract → Files modified

- `src/substrate/topologies/session/parent_context_producer.py` (new, ~60 lines).
- `src/substrate/topologies/session/__init__.py` — `session_topology` gains `parent_context` parameter; registers the producer when non-None.
- `src/substrate/topologies/tool_loop/delegate.py` — delete `_prefix_context_slice`, rewrite path-3 to bind the producer, remove the string-prefix from `assembled_prompt`.
- `tests/test_delegate_per_call_context.py` — 9 tests updated to new shape.
- `tests/test_prompt_fragment_parent_context.py` (new, ~5 tests) — deterministic driver, delegate with `context={parent_seq_range: [0, 100], kinds: ["UserMessage", "ModelReply"]}`, assert `PromptFragment(source=parent_context)` on child record with matching text and provenance.

## Signal contract → Emits

`substrate.session.PromptFragment@1` with `source=parent_context`. One more source on the schema locked in sprint 058.

## Observation contract

- Deterministic test — parent record has UserMessage@seq=1, ModelReply@seq=2, UserMessage@seq=3; delegate with `context={parent_seq_range: [1, 2], kinds: ["UserMessage", "ModelReply"]}`; child record carries one `PromptFragment(source=parent_context)` whose text contains `[seq=1 kind=UserMessage]` and `[seq=2 kind=ModelReply]` and NOT `[seq=3]`.
- Deterministic test — empty slice (no matching events) → zero `PromptFragment` on child.
- Deterministic test — single oversize event → fragment carries the note "this single event is N bytes, larger than the K-byte slice cap", provenance carries `single_oversize=True`.
- Deterministic test — every existing `test_delegate_per_call_context.py` invariant reads at the fragment level, not the string-prefix level. The context reaches the child.
- **Live-model test** — `test_realmodel_delegate_parent_context.py`. Parent session (kimi driver) says "the secret code is HALCYON-9"; parent delegates to a child session (any driver) with `context={parent_seq_range: [<seq of ModelReply>, <seq of ModelReply>], kinds: ["ModelReply"]}` and task="repeat the secret code you were given"; assert child's `ModelReply.text` contains "HALCYON-9". Marked `@pytest.mark.realmodel`.

## Halt conditions

- `bridge_mapping_required` if `parent_context_producer` cannot receive its bound inputs cleanly at topology-build time (the delegate's factory closure has to pass them through). Prefer a factory arg over a Producer-side State read.
- `dual_contract_fail` if the child's `PromptComposed.text` shows the parent context at the wrong precedence relative to `role` or `per_turn`. Fix precedence, do not fix by re-ordering the string in the producer.

## Definition of done

`delegate.py` no longer builds prompt strings. The child's parent context arrives as a typed fragment on the child's own record with provenance. `_prefix_context_slice` is deleted. A live-model test proves the parent's information reaches the child through the composer.
