# Sprint 058 — session-vocabulary v0.2: `PromptFragment` and `PromptComposed`

```yaml
---
id: 058
status: open
phase: 8
pass_kind: vocabulary
---
```

## Product-spec conformance

**Fulfills:** the SDD entry gate for the prompt-composition arc. Product spec `draft7.md` R-RISK-5 (line 766) rules prompts, roles, and LLM tooling as topology-layer concerns. Session-vocabulary v0.1 (locked 2026-08-25 at `signals/versions/0.1.json`) names eight Structs — SessionStarted, UserMessage, ModelReply, Park, SessionEnded, SessionEndRequested, SessionWarning, TranscriptCompacted — none of which describe a prompt fragment or a composition event. This card adds the missing vocabulary so every downstream sprint has typed events to emit against.

**Consumes:** the session vocabulary lock file at `substrate/process/signals/session-vocabulary.md` (v0.1). Not the kernel v15 vocabulary — this is a topology-layer extension under the session namespace.

## Motivation

The 2026-09-01 context-composition audit (see [[audit-context-composition-2026-09-01]] on BLACKBOARD ## Surfaced for review) found five distinct prompt-composition concepts in the tree (`seed`, `per_turn`, `bundle`, `role`, delegate `context`), three of them with no runtime consumer, and every composition site building strings with `f"..."` or `"\n\n".join(parts)`. Replay reconstructs no fragment provenance; `record diff` cannot show which fragment changed between two runs; a view cannot count how many fragments a session composed, or how many tokens each source spent.

The substrate-native shape is a typed event per fragment plus a typed event per composition. Everything downstream — the composer Producer (sprint 059), the per-source fragment Producers (sprints 060-064), the dead-code deletion (sprint 065) — depends on this vocabulary being locked first.

## Scope

Two new Structs and one enum, added to session-vocabulary v0.2. All under the session namespace (no `substrate.` prefix per kernel rule).

**`PromptFragment`.** One yielded by each fragment-source Producer. Fields:

- `source: str` — one of the enum values below.
- `text: str` — the fragment's contents, as the model will read them.
- `precedence: int` — the composer's ordering key (lower fires earlier in the composed text).
- `provenance: dict[str, Any]` — the resolver's own audit trail (file path for a role, bundle name + slot for a bundle slot, `(record_root, seq_range, kinds)` for a delegate context slice, empty dict for `per_turn`). Not typed further at this layer — the source's own tests pin its shape.

**`PromptComposed`.** One yielded by the composer per model firing. Fields:

- `text: str` — the assembled prompt the model receives.
- `fragment_seqs: tuple[int, ...]` — the seq of every `PromptFragment` that composed into this text, in order.
- `total_tokens: int` — estimated token cost (chars/4 heuristic per `transcript.py`).
- `strategy: str` — `"precedence_join"` in v0.2; leaves room for a v0.3 template strategy.

**`PromptSource` enum values (v0.2 initial set).** `per_turn`, `role`, `bundle_methodology`, `bundle_personality`, `parent_context`, `tools_suite`, `user_message`. `user_message` is the current turn's UserMessage.text — a fragment source like any other, uniform shape.

## Prerequisites

- No open sprint on session-vocabulary. Sprint 202 locked v0.1; nothing has amended it since.

## Context files

- `substrate/process/signals/session-vocabulary.md` — v0.1 lock file. Read in full; do not overwrite (rule 12). Add a `## v0.2` section below the v0.1 section, dated, with the two new Structs and the enum.
- `signals/versions/0.1.json` (substrate side) and `signals/versions/0.1-rationale.md` — the machine-readable lock. Add `signals/versions/0.2.json` + rationale as new files.
- `src/substrate/topologies/session/vocabulary.py` (69 lines) — the Python home for the kind-name constants. Add `PROMPT_FRAGMENT` and `PROMPT_COMPOSED` string constants.
- `src/substrate/topologies/session/__init__.py` — home of every existing session Struct. Add the two new Structs alongside.

## Artifact contract → Files modified

- `substrate/process/signals/session-vocabulary.md` — append `## v0.2 — 2026-09-XX` section with the two Structs + enum, rationale one paragraph per Struct. v0.1 section stays byte-identical.
- `signals/versions/0.2.json` (new) + `signals/versions/0.2-rationale.md` (new). Match the shape of v0.1's files.
- `src/substrate/topologies/session/vocabulary.py` — two new string constants; add to `__all__`.
- `src/substrate/topologies/session/__init__.py` — two new `msgspec.Struct` classes, frozen, at the same seam as the existing eight; add to `__all__`.

## Signal contract → Emits

`substrate.session.PromptFragment@1` and `substrate.session.PromptComposed@1` — declared in v0.2, no emit sites yet (that lands in sprint 059). Sprint 058 ships the vocabulary; sprint 059 ships the first Producer that emits against it.

## Observation contract

- The two Structs import cleanly from `substrate.topologies.session`.
- The two kind-name constants match between `vocabulary.py` and the Struct qualname.
- `signals/versions/0.2.json` parses and validates against the schema shape v0.1 uses.
- `substrate.process.signals.session-vocabulary.md` v0.1 section is byte-identical pre and post (audit: `git diff --stat` shows only additions in the v0.2 section).
- Unit test: `test_session_prompt_vocabulary_v02.py` — instantiates both Structs, round-trips through `msgspec.to_builtins` + `msgspec.convert`, asserts field shape.

## Halt conditions

- `bridge_mapping_required` if any existing Struct field name collides with a v0.2 field name. Should not (the eight v0.1 Structs use their own field names); grep confirms.
- `spec_ambiguity` if the vocabulary lock file's v0.1 section names an ordering constraint on the enum that v0.2's additions would violate. Read v0.1 in full first.

## Definition of done

Two Structs, one enum, one appended section in the vocabulary lock file, one new json + rationale pair under `signals/versions/`. No emit sites. Sprint 059 opens with the vocabulary already locked and reachable.
