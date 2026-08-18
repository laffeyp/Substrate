# Sprint 164 — Kernel `Budget` primitive (registration only)

---

```yaml
---
id: 164
status: closed
phase: 1
pass_kind: architecture
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Add a `Budget` msgspec.Struct to `src/substrate/kernel/topology.py` and an
optional `budget: Budget | None = None` kwarg to
`TopologyBuilder.producer_kind`. Store the budget on `ProducerKindReg`. Export
`Budget` from `substrate.api`. Additive change: every existing producer without
a budget registration behaves identically. Runtime enforcement is Sprint 165
(roadmap v2 S1b) — Sprint 164 puts the primitive on the shelf, ratifies its
API shape, and lets the S5.x producer sprints declare budgets against a stable
contract.

Roadmap v2 Sprint 1 was originally scoped as one architectural sprint. Sprint
164 is Sprint 1a — the additive type + registration change; Sprint 165 will
be Sprint 1b — the runtime enforcement. Split honors AGENTS.md hard rule 6
(≤2 source files per sprint) and lets ratification proceed against the
smallest possible surface.

---

## prerequisites

- Sprint 161 close (vocabulary v0.2 consolidation).
- Sprint 162 close (boundary bridge mapping in WORKING_AGREEMENT.md).
- Sprint 163 close (vocabulary v0.3 boundary event tags — PROPOSED, ratifies
  before S5.x producer sprints dispatch, but does not gate the kernel change).
- Roadmap v2 ratified verbally 2026-08-12.

---

## context_files

- `sdd-kit-2/AGENTS.md` (hard rule 6 sweet spot; additive-only kernel change discipline).
- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` § "Sprint 1".
- `process/WORKING_AGREEMENT.md` § "SWE-bench external substrates" (Sprint 162 output — every producer declares a Budget).
- `src/substrate/kernel/topology.py` (the file modified; `producer_kind` at line 88; `ProducerKindReg` at line 29).
- `src/substrate/api.py` (the file modified; re-export block for `topology`).
- `src/substrate/protocols.py::Producer` (the protocol producers implement — shape-compatible with the noop test producer).
- `tests/test_api_sugar.py::_ticker` (existing shape reference for an async-gen producer in tests).

---

## signal contract

### Emits

None at runtime. Sprint 164 is a type + registration addition; no
substrate.* event kinds added (the `substrate.BudgetExceeded` kind lands in
Sprint 165 with enforcement).

### Consumes

Files listed in `context_files`.

### Invariants

- Every existing `producer_kind` call in the codebase compiles and runs
  identically — the `budget` kwarg defaults to `None`; storing `None` on
  `ProducerKindReg.budget` matches the pre-Sprint-164 behaviour where the
  field did not exist.
- `Budget` is a frozen `msgspec.Struct` — mutating raises `AttributeError`
  per the kernel-vocabulary discipline.
- `Budget` is exported from `substrate.api` and appears in `api.__all__`.

---

## artifact contract

### Files modified

- `src/substrate/kernel/topology.py` — add `Budget` Struct (with `wall_seconds`
  and `event_counts` optional fields); add `budget: Budget | None = None`
  field to `ProducerKindReg`; add `budget: Budget | None = None` kwarg to
  `producer_kind`; pass through to the Reg construction; extend the
  `producer_kind` docstring.
- `src/substrate/api.py` — import `Budget` from `.kernel.topology`; add
  `"Budget"` to `__all__` in the "topology + execution" group.

### Files created

- `tests/test_kernel_budget.py` — seven unit tests: registration without
  budget stores `None`; registration with wall_seconds-only budget round-trips;
  with event_counts-only round-trips; with full budget round-trips; empty
  `Budget()` legal; Budget frozen (mutation raises `AttributeError`); Budget
  exported from `substrate.api`.

### Content assertions

- `src/substrate/kernel/topology.py` contains a `class Budget(Struct, frozen=True):` definition.
- `ProducerKindReg` dataclass has a `budget: Budget | None = None` field.
- `producer_kind`'s signature contains `budget: Budget | None = None`.
- `src/substrate/api.py`'s import from `.kernel.topology` includes `Budget`.
- `api.__all__` contains `"Budget"`.
- `tests/test_kernel_budget.py` exists with 7 test functions.

### Command exit codes

- `uv run python -m pytest tests/test_kernel_budget.py -v` returns 0 (7/7 pass).
- `uv run ruff check src/substrate/kernel/topology.py src/substrate/api.py tests/test_kernel_budget.py` returns 0.
- `uv run mypy --strict src/substrate/kernel/topology.py src/substrate/api.py tests/test_kernel_budget.py` returns 0.
- `uv run python -m pytest tests/ -k "kernel or api or topology" --timeout 30` returns 0 (broader kernel/api tests still pass — 113 tests green at Sprint 164 close).

---

## observation contract

Not applicable — architectural sprint with unit test coverage. The additive
contract IS the observation: existing producer_kind registrations behave
identically (asserted by the pass of the pre-Sprint-164 test suite: 113
kernel/api/topology tests still green), and the new field round-trips per
the seven unit tests. Runtime enforcement observation lives in Sprint 165's
observation contract (`substrate.BudgetExceeded` events on the record;
producers cancelled at overrun; wall-clock cap honored under load).

---

## done criteria

`Budget` type defined on the kernel; `producer_kind` accepts the optional
kwarg and stores it on the Reg; `substrate.api` re-exports `Budget`; seven
unit tests pass; broader kernel/api test suite still green; mypy strict
clean; ruff clean. Sprint closes with the primitive on the shelf ready for
Sprint 165's runtime enforcement.

---

## notes

- **Additive-only.** No existing producer_kind call in the codebase touches
  the new kwarg. Verified by running the full `-k "kernel or api or topology"`
  test suite pre- and post-change: 113 tests pass identically.
- **Split from roadmap v2 Sprint 1.** The original Sprint 1 folded types +
  registration + runtime enforcement into one sprint touching three files
  (topology.py, runtime.py, tests). Hard rule 6 says ≤2 source files; split
  cleanly at the type/enforcement seam. Sprint 165 (roadmap v2 S1b) picks up
  runtime enforcement.
- **`event_counts` typing.** Uses `dict[str, tuple[int, str]] | None` matching
  `ProducerKindReg.schemas`'s dict pattern. msgspec's frozen Struct does not
  enforce dict-value immutability at runtime, but the pattern matches
  existing kernel dataclasses; the discipline is convention, same as
  everywhere else in the codebase.
- **No `substrate.BudgetExceeded` yet.** The event kind lands with
  enforcement in Sprint 165. Sprint 164 producers that declare a budget do
  not overrun — the runtime does not check yet.
- Roughly two hours of work; two source files + one test file. Tests: 7
  functions, ~110 lines. Verification: 7/7 pass in 0.11s.

---

## plan-mode review checklist

- [x] Additive-only (existing producer_kind calls unchanged).
- [x] Budget is a frozen msgspec Struct.
- [x] Budget exported from substrate.api and in __all__.
- [x] ProducerKindReg.budget defaults to None.
- [x] Seven unit tests pass.
- [x] Broader kernel/api test suite (113 tests) still green.
- [x] Ruff + mypy strict clean.
- [x] Two source files + one test file — within sweet spot.
