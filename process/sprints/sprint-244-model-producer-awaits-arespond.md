# Sprint 244 — session model producer awaits arespond (unblocks Ctrl+C interrupt)

```yaml
---
id: 244
status: closed-2026-08-31
phase: 6
pass_kind: correctness
---
```

## Product-spec conformance

**Fulfills:** TECH-SPEC-2026-08-25-round6.md §11 failure mode "Ctrl+C interrupts turn only". PRODUCT-SPEC-2026-08-17-round12.md §2 "Ctrl+C interrupts the current turn without ending the session." Both promises depend on `Runtime.cancel_producer(instance)` having a window to fire during a slow model call. Today the model producer body at `topologies/session/__init__.py:297` calls `driver.respond(prompt)` synchronously, blocking the event loop for the duration of the driver call. Under a real Ollama HTTP call (or any blocking sync driver) the interrupt path cannot fire — sprint 243's `test_park_on_interrupt_then_resume` documents this and is skipped pending this fix.

**Consumes:** Responder protocol's `arespond` method (already implemented on OllamaResponder at `adapters/models.py:302`).

## Scope

Route the session model producer through `driver.arespond(prompt)` so the event loop yields during the model call. Every Responder implements both `respond` and `arespond` today; `arespond` is the cancellable path (`_achat` under the hood).

One file. One concept.

Concretely:

- `topologies/session/__init__.py:297` — replace `reply_text = str(driver.respond(prompt_text))` with `reply_text = str(await driver.arespond(prompt_text))`. The `_model` function is already `async def`; the `await` costs one keyword.
- Grep for other `driver.respond(` sites inside the session package; convert each to `await driver.arespond(...)` unless the site is intentionally synchronous (unlikely).

## prerequisites

- Sprint 217c (Runtime.cancel_producer primitive) closed.
- Sprint 243 (failure-mode tests) closed with the interrupt test skipped and pointing here.

## context_files

- `src/substrate/topologies/session/__init__.py` — model producer body at 248-300.
- `src/substrate/adapters/models.py` — Responder protocol, `respond` sync path at 106, `arespond` async at 302.
- `tests/test_session_topology_failure_modes.py::test_park_on_interrupt_then_resume` — the skipped test to un-skip.

## artifact contract → Files created/modified

- `src/substrate/topologies/session/__init__.py` — `reply_text = str(await driver.arespond(prompt_text))` at the model producer body.
- `tests/test_session_topology_failure_modes.py` — remove the `pytest.skip` from `test_park_on_interrupt_then_resume`; the test's body already covers the interrupt path once arespond yields.

## signal contract → Emits

None (mechanism-level fix; no new tags).

## observation contract

- `uv run python -m pytest tests/test_session_topology_failure_modes.py::test_park_on_interrupt_then_resume -v --timeout=60` → PASS (currently SKIPPED).
- Full session-topology suite still green.
- `test_session_topology_bundled.py::test_bundled_session_matches_committed_record` still PASS after CI record regen (arespond is deterministic under DeterministicResponder — the sync respond path just delegates; ci_mode.record byte-shape unchanged).

## halt conditions

- `dual_contract_fail` if the CI record byte-diverges after the change (means arespond and respond produce different outputs on the deterministic responder — a Responder-contract violation).
- `bridge_mapping_required` if any Responder in `adapters/models.py` lacks arespond.

## definition of done

`driver.arespond` in the model producer; the interrupt test un-skips and passes; every existing test green; CI record unchanged.
