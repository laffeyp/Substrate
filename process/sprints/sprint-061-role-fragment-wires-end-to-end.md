# Sprint 061 — `role` wires end-to-end as `PromptFragment(source=role)`

```yaml
---
id: 061
status: closed
phase: 8
pass_kind: wire-a-currently-dead-concept
closed_at: 2026-09-01
closed_by: substrate main HEAD after this card
scope_note: live-model assertion deferred to sprint 064; _model_factory does not yet consume PromptComposed. Role fragment lands on the record with correct precedence + provenance in this sprint.
---
```

## Product-spec conformance

**Fulfills:** first sprint that wires a currently-dead concept. `manifest.role` today is validated at POST `/api/session` (`substrate-ui/server.py:1141`), stored on the manifest, echoed back in JSON at `server.py:1226` and `:1661`, and never touched again. The five prompt files sprint 053 shipped — `reviewer.md`, `planner.md`, `tester.md`, `explainer.md`, `default.md` under `substrate/src/substrate/topologies/session/prompts/` — are read at validation time only. The resolved prompt text has no consumer. Product spec R-RISK-5 keeps this at the topology layer; this sprint makes the topology layer honest.

**Consumes:** the composer + `per_turn_producer` from sprints 059-060. The four-layer resolver `substrate/src/substrate/topologies/session/roles.py::resolve_role_prompt` stays as it is — it already resolves correctly, it just needs a consumer.

## Motivation

The 2026-09-01 audit finding F2 named this directly (KIT_DIARY finding 69 recurrence): a resolver + validator + persisted field with no runtime consumer is dead scaffolding that reads as a working feature. Every session created with `--role reviewer` today looks correct to the client and drives the model with the default (or empty) prompt. That is a silent bug of the first order.

The fix uses the shape sprint 060 built. A `role_producer` fires once at session open, reads the role prompt via `resolve_role_prompt`, yields one `PromptFragment(source=role, text=<resolved>, precedence=0, provenance={"role_name": ..., "resolved_from": <file_path>})`. Because `precedence=0`, the role prompt lands FIRST in every composed prompt. The composer picks it up in every subsequent turn's cohort — or, better, the role fragment rides on a session-open View so it does not need to re-emit per turn; the composer reads the latest `KindBuffer("PromptFragment")` slice that includes it.

## Scope

One new Producer, one new View, one manifest binding, one wire through to the daemon path.

**`role_producer` Producer.** Fires on `substrate.RunStarted` (once per session). Body: `text = resolve_role_prompt(role, repo_root=Path.cwd())`; when non-empty, yield `PromptFragment(source="role", text=text, precedence=0, provenance={"role_name": role, "resolved_from": <path>})`. When empty (default role + no default.md → the resolver raises today, keep that raise as a session-open failure per current shape).

**Session-open fragment carrying.** A role prompt fires once and needs to be visible in every turn's composed prompt. Two shapes to choose from at implementation:
- (A) Fragment cohort per-turn includes every `PromptFragment` since `substrate.RunStarted`, not just since the previous `PromptComposed`. The composer's cohort window widens for session-open sources.
- (B) The composer re-emits session-open fragments on every turn by reading a `KindBuffer("PromptFragment", filter=source in SESSION_OPEN_SOURCES)` View.

Prefer (B) — cleaner boundary; the composer's per-turn cohort stays turn-scoped and the View makes the session-scoped inclusion explicit. Halt-and-articulate on (A) if the View shape needs a filter primitive that does not exist.

**Provenance and resolver info.** The `resolve_role_prompt` return value is text-only today; extend the resolver to return `(text, source_path)` so the fragment's `provenance` carries the file path it resolved from. Backwards-compat: add an overload or a sibling `resolve_role_prompt_with_source` — do not silently change the return type of the existing function (six unit tests read the string).

**Daemon binding.** `_build_session_topology_from_manifest` at `substrate-ui/server.py:439` currently passes `manifest.workspace_path`, `manifest.bundle`, `manifest.driver_params` etc. into `session_topology`. Pass `manifest.role` too. `session_topology` gains a `role: str` parameter that flows into `role_producer`'s factory.

## Prerequisites

- Sprint 058, 059, 060 closed.
- No open card modifying `session/roles.py` or the role-prompt file set.

## Context files

- `src/substrate/topologies/session/roles.py` (83 lines) — the four-layer resolver. Extend to return source path.
- `src/substrate/topologies/session/prompts/` — the five shipped `.md` files. No change; they stay.
- `substrate-ui/server.py:1141` — the validator call site. After this sprint, `manifest.role` is a live parameter, not a decorative one. The validator stays (fail-fast at create) but its return value drives the runtime path.
- `substrate-ui/server.py:439` — `_build_session_topology_from_manifest`. Add `role=manifest.role` to the `session_topology(...)` call.
- `src/substrate/topologies/session/__init__.py:session_topology` — add `role: str = "default"` parameter.
- `tests/test_role_prompt_resolver.py` — six existing tests; add coverage for the new `(text, source_path)` return.

## Artifact contract → Files modified

- `src/substrate/topologies/session/roles.py` — new `resolve_role_prompt_with_source(role, *, repo_root)` returning `(text, source_path)`. Existing `resolve_role_prompt` stays as a thin wrapper.
- `src/substrate/topologies/session/role_producer.py` (new, ~50 lines) — the Producer body + the session-open View filter helper.
- `src/substrate/topologies/session/__init__.py` — `session_topology` gains `role: str = "default"`; register the role producer + View; wire the fragment cohort widening in the composer or the new session-scoped filter.
- `src/substrate/topologies/session/composer.py` — if shape (B), widen the fragment-cohort View to include session-open sources every turn.
- `substrate-ui/server.py` — pass `role=manifest.role` at `_build_session_topology_from_manifest`.
- `tests/test_prompt_fragment_role.py` (new, ~5 tests) — deterministic driver, create session with `role=reviewer`, run one turn, assert one `PromptFragment(source=role, text=<contents of reviewer.md>)` on the record; assert composed prompt starts with the role text (precedence 0).
- `tests/test_role_prompt_resolver.py` — extend to cover `resolve_role_prompt_with_source`.

## Signal contract → Emits

`substrate.session.PromptFragment@1` with `source=role`. Adds one new emit site to the schema declared in sprint 058.

## Observation contract

- Deterministic test — session with `role=reviewer`; assert exactly one `PromptFragment(source=role)` on the record, `text` equals the contents of `reviewer.md`, `provenance.role_name == "reviewer"`, `provenance.resolved_from` is a real file path.
- Deterministic test — session with `role=default`; role fragment carries the contents of `default.md`.
- Deterministic test — session with `role=reviewer`, run two turns; assert the `PromptComposed.text` on turn 2 STILL contains the role text (session-open sources carry across turns).
- Deterministic test — session with `role=nonexistent`; POST `/api/session` returns 400 (existing behavior, keep pin).
- **Live-model test** — `test_realmodel_role_reviewer.py`. Session with `role=reviewer` against a real driver; prompt = "identify yourself and your job in one sentence"; assert `ModelReply.text` contains "review" (case-insensitive) OR one of a small set of reviewer-cognate tokens. Proves the role prompt reaches the model. Marked `@pytest.mark.realmodel`. Widen the assertion family rather than pinning one exact string — probabilistic test per KIT_DIARY discipline.

## Halt conditions

- `bridge_mapping_required` if the composer's per-turn cohort cannot cleanly include session-open sources without a new View primitive. Halt, name the missing primitive, decide (A) vs (B).
- `dual_contract_fail` if the live-model test fails because the model doesn't self-identify — try a different role that has an even sharper prompt (e.g., write a `test_role.md` under `<repo>/.substrate/prompts/` that instructs "reply with the single word REVIEWER-42-CONFIRMED"). Do not soften the assertion below what a real role prompt would produce.

## Definition of done

Every session with a `role` field emits one `PromptFragment(source=role)` at open and that fragment appears in every turn's `PromptComposed.text` with precedence 0. `manifest.role` is a live runtime input, not a decorative one. A live-model test proves the role reaches the driver.
