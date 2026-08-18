# Sprint 168 — RateLimitedResponder releases semaphore during 429 sleep (fold external review F1)

---

```yaml
---
id: 168
status: closed
phase: 1
pass_kind: functional
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Move the `async with sem:` boundary in `RateLimitedResponder.arespond` at `src/substrate/adapters/rate_limit.py:153-190` from around the entire retry loop to around each in-flight inner call. The retry sleep (`await asyncio.sleep(delay)`) now happens outside the semaphore scope. Under sustained 429 pressure, a sleeping worker no longer pins a slot — a healthier peer can take the slot and progress. Add one regression test at `tests/test_rate_limit.py::test_semaphore_released_during_retry_sleep_lets_peer_progress` that proves the fix by observing a healthy peer entering its inner call during the sleeping worker's retry-sleep.

Closes external review F1 (BLOCKER) at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`. Unblocks Verified pass 1 without waiting for the roadmap v2 S5.2 `RateLimitProducer` sprint — the shim is what every arm's Responder currently wraps, and the shim's slot-holding bug produced the 82% throttle collapse the 2026-08-12 halt named.

---

## prerequisites

- 2026-08-12 halt at `## Surfaced for review` naming the slot-holding bug (reason 3).
- External review at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F1.
- `docs/DESIGN-2026-08-11-responder-rate-limit-shim.md` (design context for the shim).

---

## context_files

- `sdd-kit-2/AGENTS.md` (hard rule 6; correctness fixes take precedence over refactors).
- `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F1.
- `process/BLACKBOARD.md ## Surfaced for review` 2026-08-12 halt (reason 3).
- `src/substrate/adapters/rate_limit.py:153-190` (file modified; `RateLimitedResponder.arespond`).
- `tests/test_rate_limit.py` (file modified; new regression test added).
- Existing tests as regression baseline: `test_wrapper_honours_retry_after_header`, `test_wrapper_raises_typed_after_exhaustion`, `test_semaphore_key_isolation`, `test_two_wrappers_share_semaphore_for_same_key`.

---

## signal contract

### Emits

None at runtime — the shim raises `ProviderRateLimited` at retry exhaustion (unchanged) and returns a `str` on success (unchanged). No new event kinds. Producer-shaped emit lands with roadmap v2 S5.2.

### Consumes

Files listed in `context_files`.

### Invariants

- Every previously-passing test in `tests/test_rate_limit.py` continues to pass (5 pre-existing tests, all green).
- The retry budget count (`max_retries`) is unchanged; the semaphore contract per-`(provider, model)` is unchanged; the `Retry-After` honour is unchanged; the typed `ProviderRateLimited` raise on exhaustion is unchanged.
- Only the semaphore scope changes: from wrapping the whole retry loop to wrapping each in-flight call individually.
- No API-surface change; every consumer of `RateLimitedResponder` behaves identically on the success path.

---

## artifact contract

### Files modified

- `src/substrate/adapters/rate_limit.py` — merge `arespond` and `_arespond_with_retry` into a single `arespond` method. `async with sem:` scope narrowed to the inner call; `await asyncio.sleep(delay)` moved outside the semaphore scope. Docstring extended with the F1 fix note.
- `tests/test_rate_limit.py` — add `test_semaphore_released_during_retry_sleep_lets_peer_progress` regression pin. Uses a monkey-patched `asyncio.sleep` that yields to the event loop so peer tasks can run during the fake sleep window.

### Content assertions

- `RateLimitedResponder._arespond_with_retry` no longer exists (merged into `arespond`).
- The `arespond` method's docstring contains the F1 fix note.
- `await asyncio.sleep(delay)` appears exactly once in `rate_limit.py`, outside any `async with sem:` scope.
- `tests/test_rate_limit.py` contains a function `test_semaphore_released_during_retry_sleep_lets_peer_progress`.

### Command exit codes

- `uv run python -m pytest tests/test_rate_limit.py -v --timeout 15` returns 0 (6/6 pass).
- `uv run ruff check src/substrate/adapters/rate_limit.py tests/test_rate_limit.py` returns 0.
- `uv run mypy --strict src/substrate/adapters/rate_limit.py` returns 0.

---

## observation contract

Regression pin `test_semaphore_released_during_retry_sleep_lets_peer_progress`
observes the fix mechanically:

- **Setup.** Per-key cap = 1; one worker (`failing`) wraps a Responder that raises 429 with `Retry-After: 1`; a second worker (`healthy`) wraps a Responder that immediately succeeds.
- **Fake sleep instrument.** `asyncio.sleep` is monkey-patched to advance a fake clock and `await real_sleep(0.01)` — yielding to the event loop so peer tasks can run during the fake sleep window.
- **Assertion.** The healthy peer enters its inner call at a fake-clock time strictly less than when the failing worker exits (raises `ProviderRateLimited`). A pre-Sprint-168 implementation would have the healthy peer wait until the failing worker exhausted, because the sleeping worker would pin the only slot.
- **Failure mode.** A regression that puts the sleep back inside the semaphore scope trips this test. The assertion message names the slot-holding bug explicitly.

---

## done criteria

`arespond`'s semaphore scope wraps only the in-flight call; retry sleep happens outside; 6/6 tests pass (5 preserved + 1 new regression pin); ruff clean; mypy strict clean. The rate-limit shim now honors the tier-capacity health contract under sustained 429.

---

## notes

- **F1 finding.** Reviewer at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md:34-44`: "The slot is pinned for the length of the sleep while nothing is in flight. Under sustained 429 pressure the three workers on Pro pin all three slots; five queue; throughput collapses to `capacity / sleep_multiplier` exactly as the 2026-08-12 halt described." The Halt's reason 3 (BLACKBOARD ## Surfaced for review 2026-08-12) named the same bug.
- **Interim fix.** Roadmap v2 S5.2 recasts the shim as `RateLimitProducer` and moves the retry logic outside the semaphore scope via typed producer events. That is one to two sprints out. Sprint 168 unblocks Verified pass 1 today without waiting for producer authoring.
- **Retirement note.** When roadmap v2 S5.2 lands, `RateLimitedResponder` retires per the same discipline `swebench_solver_topology_with_test_selection` followed at KIT_DIARY finding 38 — deprecation notice at module top, body preserved for audit trail. This sprint does not retire; F1 is the fix-in-place required for the interim.
- **No behavior change on success path.** Every existing consumer that gets a non-429 response experiences identical behavior: the wrapper still acquires the semaphore, still calls the inner responder, still returns the string.
- Roughly 40 minutes; one source file + one test file.

---

## plan-mode review checklist

- [x] Semaphore scope narrowed to in-flight call only.
- [x] Retry sleep moved outside semaphore scope.
- [x] Regression pin proves the fix under a controlled peer-scheduling test.
- [x] Every pre-existing test still passes.
- [x] Ruff + mypy strict clean.
- [x] Two files — within sweet spot.
