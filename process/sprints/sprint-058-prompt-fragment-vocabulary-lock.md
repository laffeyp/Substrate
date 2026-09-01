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

**Consumes:** the session vocabulary lock file at `substrate/process/signals/session-vocabulary.md` (v0.1, ratified 2026-08-25 by sprint 202). NOT the master Substrate vocabulary track at `substrate/process/signals/0.1.json` / `0.2.json` / `0.3.json` — that track covers kernel `substrate.*` events (currently at v0.3 after sprint 217c's `ProducerCancelled` provenance additions). Session-topology vocabulary is tracked in the single `session-vocabulary.md` document, not as per-version json files. This card appends a v0.2 section to the md file.

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
- `src/substrate/topologies/session/vocabulary.py` (69 lines) — the Python home for the kind-name constants. Add `PROMPT_FRAGMENT` and `PROMPT_COMPOSED` string constants.
- `src/substrate/topologies/session/__init__.py` — home of every existing session Struct. Add the two new Structs alongside.
- `substrate-ui/signals/versions/` — this DOES have per-version files (0.1-0.7.3). The substrate-ui vocabulary is the paired grader-side lock, not the substrate side. If a paired ui-side tag needs to land alongside PromptFragment/PromptComposed (per the dual-contract audit at `session-vocabulary.md § G`), open a companion sprint on the substrate-ui side; do not touch that tree from this substrate-side card.

## Artifact contract → Files modified

- `substrate/process/signals/session-vocabulary.md` — append `## v0.2 — 2026-09-XX` section with the two Structs + enum, rationale one paragraph per Struct. v0.1 section stays byte-identical. This is the only lock file the session vocabulary track writes to.
- `src/substrate/topologies/session/vocabulary.py` — two new string constants; add to `__all__`.
- `src/substrate/topologies/session/__init__.py` — two new `msgspec.Struct` classes, frozen, at the same seam as the existing eight; add to `__all__`.

## Signal contract → Emits

`substrate.session.PromptFragment@1` and `substrate.session.PromptComposed@1` — declared in v0.2, no emit sites yet (that lands in sprint 059). Sprint 058 ships the vocabulary; sprint 059 ships the first Producer that emits against it.

## Observation contract

- The two Structs import cleanly from `substrate.topologies.session`.
- The two kind-name constants match between `vocabulary.py` and the Struct qualname.
- `substrate/process/signals/session-vocabulary.md` v0.1 section is byte-identical pre and post (audit: `git diff` shows only additions in the new v0.2 section).
- Unit test: `test_session_prompt_vocabulary_v02.py` — instantiates both Structs, round-trips through `msgspec.to_builtins` + `msgspec.convert`, asserts field shape.

## Halt conditions

- `bridge_mapping_required` if any existing Struct field name collides with a v0.2 field name. Should not (the eight v0.1 Structs use their own field names); grep confirms.
- `spec_ambiguity` if the vocabulary lock file's v0.1 section names an ordering constraint on the enum that v0.2's additions would violate. Read v0.1 in full first.

## Definition of done

Two Structs, one enum, one appended v0.2 section in `substrate/process/signals/session-vocabulary.md`. No emit sites. Sprint 059 opens with the vocabulary already locked and reachable.
