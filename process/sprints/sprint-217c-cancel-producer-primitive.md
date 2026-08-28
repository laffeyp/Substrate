# Sprint 217c — `Runtime.cancel_producer(instance)` primitive with provenance

```yaml
---
id: 217c
status: closed
phase: substrate-kernel
pass_kind: architecture
---
```

## scope

Substrate/kernel primitive replacement. Commit `08dcaed6` shipped `Runtime.cancel_producers(kind)` without a sprint card. The primitive cancels every producer of a kind at once, writes no provenance envelope, and has one test that does not exercise its cross-thread contract. The 215b halt entry named `cancel_producer(instance)` and a producer-scoped external-event channel as the two candidates. Neither shipped. This card replaces the shipped primitive with the per-instance shape, adds a `cause` annotation to `substrate.ProducerCancelled` so the record carries who cancelled and why, and lands the test suite the shipped primitive shipped without.

**Primitive.**

```python
def cancel_producer(
    self,
    instance: str,
    *,
    cause: str = "external",
    caller: str | None = None,
) -> ProducerRef | None:
    """Cancel one live Producer by instance id. Records the cause on the
    producer's ProducerCancelled envelope. Returns the ProducerRef of the
    cancelled instance, or None if the instance is unknown / already done.

    Thread safety: call from the event-loop thread. From another thread use
    `loop.call_soon_threadsafe(runtime.cancel_producer, instance, ...)`.
    """
```

**Provenance.** `substrate.ProducerCancelled.payload` grows two optional fields — `cause: str` (`"external"` when set by `cancel_producer`; unset on cascade cancels during run teardown; `"policy"` on the `_cancel_others` path) and `caller: str | None`. The envelope's `producer` field is unchanged. The `cause` field is populated by looking up `st.cancel_reasons[instance]` inside `_producer_task`'s `except asyncio.CancelledError` handler; the store is written synchronously by `cancel_producer` and by `_cancel_others` before the task cancel dispatches.

**No new reserved kind.** Kernel v15's twelve-lifecycle-kind boundary stays intact. The change to `ProducerCancelled` is a payload extension, additive. Consumers that read `producer` keep working. Consumers that want causality read `cause` and `caller`. `VOCAB_VERSION` bumps from `"0.2"` to `"0.3"` to record the schema extension; `signals/0.3.json` succeeds `0.2.json` under sdd-kit-2 hard rule 12; `0.3-rationale.md` names the extension.

**Removed.** `Runtime.cancel_producers(kind)`. The kind-scoped batch is a composition on top of `cancel_producer(instance)`; callers that want it iterate `[cancel_producer(inst) for inst, k in st.kind_by_instance.items() if k == kind]`. Neither existing caller (substrate-side test, daemon interrupt) wants the batch shape; both want one instance.

**Rationale for by-instance over by-kind.** A session topology's model producer fires once per resume-on-user; the interrupt case has exactly one running model instance to kill. By-kind cancels every current AND every latent-scheduled model producer of the topology, a broader semantic than any caller today needs. Instance is the primitive; kind is a policy composable on top. The 215b halt entry named the same shape.

**Rationale for a cause annotation, not a new CancelDispatched kind.** Two envelopes for one action (CancelDispatched → ProducerCancelled) doubles the record footprint of every cancel. The causality lives one envelope down; the reader who wants "why cancelled" reads `ProducerCancelled.payload.cause`, one hop. Kernel v15's twelve-kind boundary stays intact.

## prerequisites

- None (retroactive fix to `08dcaed6`).

## context_files

- `substrate/src/substrate/kernel/runtime.py` — `_producer_task` at `:566-618`, `_flush_scheduled` at `:549-565`, `_cancel_others` at `:743-779`, current `cancel_producers` at `:797`, `_new_run_state` at `:301`.
- `substrate/src/substrate/kernel/runstate.py` — `RunState.task_by_instance` at `:70`, `kind_by_instance` at `:72`.
- `substrate/src/substrate/constants.py` — `VOCAB_VERSION` at `:34`, `LIFECYCLE_KINDS` at `:52-65`.
- `substrate/src/substrate/api.py` — public export block.
- `substrate/process/signals/0.2.json` and `0.2-rationale.md` — the current locked vocabulary.
- `substrate/tests/test_cancel_producers.py` — the one existing test.
- `substrate/process/REVIEW-2026-08-26-piece-b-fold-and-215-216-red-team.md` — the review that named the shape gaps.

## signal contract

### Emits (schema-modified)

- `substrate.ProducerCancelled` — payload grows optional `cause: str` and `caller: str | None`. Existing consumers that don't read the new fields are unaffected.

### Consumes

- `substrate/src/substrate/kernel/runtime.py` — `cancel_producers` removed, `cancel_producer` added; `_producer_task`'s `except asyncio.CancelledError` handler reads `st.cancel_reasons.get(instance)`.
- `substrate/src/substrate/kernel/runstate.py` — new `cancel_reasons: dict[str, dict[str, str]] = field(default_factory=dict)` on `RunState`.
- `substrate/src/substrate/api.py` — `cancel_producers` removed from `__all__`; `cancel_producer` not re-exported (it is a method on `Runtime`, not a module-level function).

### Invariants

- Kernel v15's twelve reserved lifecycle kinds unchanged.
- `Runtime.run`, `Runtime.resume`, `_bootstrap`, `_resume_bootstrap` unchanged.
- `cancel_producer` on an unknown instance returns None; does not raise.
- `cancel_producer` on an already-done instance returns None; does not raise.
- `cancel_producer` called from another thread WITHOUT `call_soon_threadsafe` raises `RuntimeError` (Python's own asyncio task-cancel-from-other-thread refusal, uncaught).
- `st.cancel_reasons[instance]` is written before `task.cancel()` so the annotation is visible when the CancelledError handler runs.
- Every `ProducerCancelled` envelope on the record carries `producer.kind` and `producer.instance` at minimum. `cause` and `caller` are optional.

## artifact contract

### Files created

- `substrate/process/signals/0.3.json` — vocabulary successor to `0.2.json`; the `ProducerCancelled` schema entry gains optional `cause` and `caller` fields.
- `substrate/process/signals/0.3-rationale.md` — one section naming the extension, the reason (bedrock provenance), and the compatibility posture (additive).
- `substrate/tests/test_cancel_producer.py` — nine tests covering the shape:
    1. Cancel a running producer, `ProducerRef` returned, `ProducerCancelled` lands with `cause="external"`.
    2. Cancel from a worker thread via `loop.call_soon_threadsafe`, envelope carries the annotation.
    3. Cancel an unknown instance returns None, no envelope.
    4. Cancel an already-done instance returns None, no envelope.
    5. Cancel a producer wrapped in `asyncio.wait_for` (wall budget), CancelledError propagates cleanly, `ProducerCancelled` carries `cause="external"` not `error="budget_exceeded"`.
    6. `_cancel_others` policy path writes `cause="policy"` on the ProducerCancelled envelopes.
    7. Topology with a `PRODUCER_CANCELLED` subscriber (a park-on-interrupt shape) fires the trigger and emits `Park`, ending at `pause_await_input`.
    8. Topology WITHOUT a `PRODUCER_CANCELLED` subscriber ends at quiescence or a threshold cleanly; `RunFinalised` lands.
    9. Cancel called before `Runtime.run/.resume` raises `RuntimeError`.

### Files modified

- `substrate/src/substrate/constants.py` — `VOCAB_VERSION = "0.3"`.
- `substrate/src/substrate/kernel/runtime.py` — `cancel_producers` removed; `cancel_producer` added with the shape above; `_producer_task`'s CancelledError handler reads `st.cancel_reasons.get(instance)` and threads `cause`/`caller` into the `ProducerCancelled` payload; `_cancel_others` writes `cause="policy"` to `st.cancel_reasons[instance]` before every task.cancel() in its loop.
- `substrate/src/substrate/kernel/runstate.py` — `cancel_reasons: dict[str, dict[str, str]]` field added.
- `substrate/src/substrate/api.py` — `cancel_producers` removed from `__all__`.
- `substrate/tests/test_cancel_producers.py` — deleted; replaced by `test_cancel_producer.py`.

### Content assertions

- `grep 'cancel_producers' substrate/src` returns zero hits.
- `grep 'def cancel_producer' substrate/src/substrate/kernel/runtime.py` returns exactly one hit.
- `signals/0.3.json` parses as JSON; `ProducerCancelled` entry declares `cause` and `caller` optional.
- `VOCAB_VERSION` reads `"0.3"`.

### Command exit codes

- `cd substrate && uv run python -m pytest tests/test_cancel_producer.py -q` returns 0 (nine cases).
- `cd substrate && uv run python -m pytest -q` (full suite) returns 0.
- `cd substrate && uv run ruff check src tests` returns 0.
- `cd substrate && uv run mypy --strict src` returns 0.

## observation contract

Not applicable (kernel primitive change; contracted by tests + record shape).

## halt conditions

- `dual_contract_fail` if any existing test that reads `ProducerCancelled.payload` breaks on the additive field.
- `vocabulary_change_required` if the schema extension surfaces a downstream consumer that treats `cause`/`caller` as required.

## definition of done

`Runtime.cancel_producer(instance, cause=, caller=)` in place. `cancel_producers(kind)` removed. `ProducerCancelled` carries `cause` and `caller` when set. Nine tests green including the cross-thread contract. Vocabulary v0.3 locked. Sprint 217d (daemon interrupt rewire) may dispatch.
