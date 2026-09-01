# Sprint 062 — bundle prose slots wire as `PromptFragment(source=bundle_methodology|bundle_personality)`

```yaml
---
id: 062
status: open
phase: 8
pass_kind: wire-a-currently-dead-concept
---
```

## Product-spec conformance

**Fulfills:** the second real wiring of a currently-dead concept. `substrate/src/substrate/bundles.py` ships a 501-line loader that reads `methodology.md`, `personality.md`, `per_turn.md`, corpus paths, tools enable-list, and extends-chain configuration from `~/.substrate/bundles/<name>/`. The 2026-09-01 audit finding F3 confirmed: `assemble_seed`, `assemble_seed_from_chain`, and `bind_slots` have zero callers outside their own tests. `manifest.bundle` names a bundle for observability (SessionStarted emits it) but the bundle's prose slots never reach the model.

**Consumes:** the composer + fragment-source pattern from sprints 059-061. The `bundles.load_bundle` loader stays as it is — it works correctly; it just needs a consumer.

## Motivation

A bundle is a Producer factory. `bundle_producer(bundle_name)` reads the bundle's methodology and personality slots at session-open and yields one `PromptFragment` per non-empty slot. The `assemble_seed_from_chain` hardcoded order (personality → ancestor methodologies → own methodology → project → task) becomes a `precedence` declaration on the fragments — data, not Python control flow. `bind_slots`'s Mad Lib slot binding is out of scope for this sprint; that machinery either lands in a follow-up (a fragment-source variant that takes slot inputs) or gets deleted in sprint 065. This sprint wires the two prose slots that have a clear runtime role.

`per_turn` at the bundle level is handled: sprint 060 wired `manifest.per_turn`, and a bundle's `per_turn.md` slot's role is to populate that manifest field at bundle-load time (a bundle sets the session's `per_turn` default at create-time). Do not double-emit as a fragment.

## Scope

Two new fragment sources, one Producer factory, one wire.

**`bundle_methodology_producer` Producer.** Fires on `substrate.RunStarted`. Body: reads `manifest.bundle` (if not None), calls `bundles.load_bundle(name)`, walks the extends chain via `bundles.resolve_extends`, yields one `PromptFragment(source=bundle_methodology, text=<methodology>, precedence=5, provenance={"bundle_name": name, "extends_chain": [<names>]})` per non-empty methodology in the chain. Ancestor methodologies fire before the caller's own (precedence orders within source: `5.0` for the deepest ancestor, ascending to `5.9` for the caller). Empty methodology → no fragment.

**`bundle_personality_producer` Producer.** Fires on `substrate.RunStarted`. Body: reads `manifest.bundle`, calls `bundles.load_bundle(name)`, walks extends chain, picks the FIRST non-empty personality in `reversed(chain)` (caller wins, then nearest ancestor). Yields one `PromptFragment(source=bundle_personality, text=<personality>, precedence=3, provenance={"bundle_name": <resolved_from>, "chain_position": <n>})`. Empty personality anywhere in the chain → no fragment.

**Precedence layout so far.** `role=0` (identity), `bundle_personality=3` (voice), `bundle_methodology=5.0-5.9` (approach), `per_turn=10` (per-turn instruction), `tools_suite=20` (suite description), `parent_context=30` (delegate slice), `user_message=100` (the ask).

**Daemon binding.** `_build_session_topology_from_manifest` at `substrate-ui/server.py:439` passes `bundle=manifest.bundle` to `session_topology` today for SessionStarted observability. After this sprint, `session_topology` also uses that value to fire the two bundle producers.

## Prerequisites

- Sprint 058, 059, 060, 061 closed.
- `bundles.load_bundle` + `resolve_extends` unchanged (they already work; this sprint calls them, does not rewrite them).

## Context files

- `src/substrate/bundles.py` — `load_bundle` (~L140), `resolve_extends` (~L310), `Bundle` Struct (~L79). No modifications; consumers only.
- `src/substrate/topologies/session/bundle_producer.py` (new) — the two Producer bodies.
- `src/substrate/topologies/session/__init__.py` — register both producers; wire `manifest.bundle` through.
- `substrate-ui/server.py:439` — `_build_session_topology_from_manifest`. `bundle=manifest.bundle` already passes; the topology consumes it as of this sprint.
- `substrate/src/substrate/topologies/session/bundle/` — the shipped "session" default bundle (see `_shipped_bundle_dir` in bundles.py). Has a `methodology.md` and probably a `personality.md`. Test targets.
- `substrate/src/substrate/topologies/applications/*.bundle/` — the shipped application bundles. Same shape.

## Artifact contract → Files modified

- `src/substrate/topologies/session/bundle_producer.py` (new, ~90 lines) — the two Producer bodies + shared bundle-load helper (memoize per session_id to avoid re-loading on every fragment source).
- `src/substrate/topologies/session/__init__.py` — register both producers on `session_topology` when `bundle is not None`.
- `tests/test_prompt_fragment_bundle_methodology.py` (new, ~6 tests) — deterministic driver, create session with `bundle=session` (shipped default), run one turn, assert `PromptFragment(source=bundle_methodology)` on the record with the shipped `methodology.md` text, provenance carries the chain.
- `tests/test_prompt_fragment_bundle_personality.py` (new, ~4 tests) — same shape for personality.
- `tests/test_prompt_fragment_bundle_extends_chain.py` (new, ~5 tests) — synthetic bundle A extends B extends C, each with a distinct methodology; assert three `PromptFragment(source=bundle_methodology)` events with precedence 5.0/5.1/5.2 and text in resolution order.

## Signal contract → Emits

`substrate.session.PromptFragment@1` with `source=bundle_methodology` and `source=bundle_personality`. Two more emit sites on the schema locked in sprint 058.

## Observation contract

- Deterministic test — session with `bundle=session`, run one turn, assert `PromptFragment(source=bundle_methodology, text=<contents of shipped methodology.md>)` on the record; assert `PromptComposed.text` contains that text after any role fragment but before `per_turn`.
- Deterministic test — session with a bundle that has empty personality; no `PromptFragment(source=bundle_personality)` on the record.
- Deterministic test — extends chain A → B → C, distinct methodologies; assert three methodology fragments in the right precedence order.
- Deterministic test — session with `bundle=None`; zero bundle fragments on the record. Composer sees no bundle-shaped fragments.
- **Live-model test** — `test_realmodel_bundle_methodology.py`. Ship a test bundle at `<test_tmp>/.substrate/bundles/citrus/` with `methodology.md = "When answering, always begin your reply with the word LEMON."`; create session with `bundle=citrus`; run one turn; assert `ModelReply.text` starts with "LEMON" (case-insensitive). Marked `@pytest.mark.realmodel`. Widen assertion if the model paraphrases — check for a citrus token in the first sentence.

## Halt conditions

- `bridge_mapping_required` if the shipped `session` bundle turns out to already conflict with a role prompt (both prescribe conflicting behavior). Halt and record which; do not silently let the higher-precedence source clobber the other in the composed prompt.
- `dual_contract_fail` if the memoization helper in `bundle_producer.py` races across concurrent session-open Producers. Rare — session-open producers fire once per session — but audit.

## Definition of done

`manifest.bundle` becomes a live runtime input. The bundle's methodology and personality slots emit typed fragments on the record with precedence and chain provenance. `PromptComposed.text` reflects those fragments in the right order. A live-model test proves the bundle text reaches the driver.
