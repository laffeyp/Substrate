# Sprint 243 — session-topology failure-mode end-to-end tests

```yaml
---
id: 243
status: closed-2026-08-31
phase: 6
pass_kind: observation
---
```

## Product-spec conformance

**Fulfills:** PRODUCT-SPEC-2026-08-17-round12.md §10 failure modes (model timeout, tool fails, standing session busy, daemon dies mid-session) + TECH-SPEC-2026-08-25-round6.md §11 table of failure modes mapped to code paths. The session topology declares three failure-mode triggers (`park-on-model-error`, `park-on-interrupt`, `end-on-cap`); no end-to-end test drives them today. Closes REVIEW-2026-08-31-session-topology-vs-specs.md TS-4.

**Consumes:** session_topology's ten triggers at `__init__.py:558-624`. Runtime.cancel_producer primitive (v0.3, sprint 217c). max_turns parameter on session_topology.

## Scope

Three end-to-end tests in one new file — one per failure-mode trigger. Each test drives the failure through a real `Runtime(root).run(session_topology(...))` and asserts the recorded envelope sequence honors the state machine transition product spec §3 promises.

**Test 1 — `park-on-model-error`.** A Responder that raises during turn 1. Assert `ProducerFailed{producer.kind=="model"}` lands; assert `Park{reason:"model_error"}` follows within the same run; assert next UserMessage resumes on the same record with `resume-on-user` firing.

**Test 2 — `park-on-interrupt`.** A slow Responder mid-turn 1; call `Runtime.cancel_producer(instance, cause="external", caller="test:interrupt")` from a sibling coroutine; assert `ProducerCancelled{producer.kind=="model"}` lands; assert `Park{reason:"interrupt"}` follows; assert next turn resumes cleanly.

**Test 3 — `end-on-cap`.** Build a session_topology with `max_turns=2`; drive three UserMessages via a CI-adjacent stepper; assert the third UserMessage triggers `end-on-cap` per the "(max_turns + 1)th UserMessage" contract at __init__.py:608-612; assert `SessionEnded{reason:"timeout"}` closes; assert `RunFinalised` seals.

Two files. One concept (session failure-mode end-to-end coverage).

## prerequisites

- Sprint 241 (CI record regen) — needed so the session e2e suite is green baseline.
- Sprint 242 (HMAC cursor fix) — unrelated but landed in the same session; keeps the full suite clean.

## context_files

- `src/substrate/topologies/session/__init__.py` — triggers at 558-624.
- `src/substrate/topologies/session/ci.py` — the ci_session_topology wrapper (pattern for driving turns via a stepper).
- `src/substrate/adapters/models.py::DeterministicResponder` — the pattern for a scriptable Responder.
- `src/substrate/api.py` — Runtime.cancel_producer, Runtime.resume, Runtime.run.

## artifact contract → Files created/modified

- `tests/test_session_topology_failure_modes.py` — new. Three async test functions per the shape above.

## signal contract → Emits

None (test-only).

## observation contract

- `test_park_on_model_error_then_resume` — asserts on the record: `ProducerFailed{producer.kind=="model"}` → `Park{reason:"model_error"}` → (after resume) `UserMessage` → `ModelReply` → `FinalAnswer` → `Park{reason:"final_answer"}`.
- `test_park_on_interrupt_then_resume` — asserts on the record: `ProducerCancelled{producer.kind=="model", cause="external", caller="test:interrupt"}` → `Park{reason:"interrupt"}` → (after resume) `UserMessage` → completes.
- `test_end_on_cap_finalises_with_timeout_reason` — asserts on the record: after max_turns=2 completes, the third UserMessage triggers `SessionEnded{reason:"timeout", total_turns:2}` → `RunFinalised`. `RunResult.status == "finalised"`.
- All three pass under `uv run python -m pytest tests/test_session_topology_failure_modes.py -v --timeout=60`.

## halt conditions

- `dual_contract_fail` if any failure-mode trigger's declared shape at __init__.py does not match the recorded envelopes (means the trigger is misconfigured).
- `bridge_mapping_required` if Runtime.cancel_producer's timing semantics prevent reliable interrupt testing (a race the test cannot pin without a flake).

## definition of done

Three failure-mode tests on disk, all passing. Session-topology test suite now covers happy path (existing tests) + three failure paths (this sprint).
