# Sprint 166 — Budget uses a named `Cap` struct (fold external review F6)

---

```yaml
---
id: 166
status: closed
phase: 1
pass_kind: architecture
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Replace the unnamed-tuple types for `Budget.wall_seconds` (was `tuple[float, str]`) and `Budget.event_counts` values (was `tuple[int, str]`) with a named frozen `Cap(limit: int | float, reason: str)` struct. Every enforcement site the follow-on runtime sprint (roadmap v2 S1b) writes will read `cap.limit` and `cap.reason` at named fields instead of positional-tuple indices. Export `Cap` from `substrate.api` alongside `Budget`. Update the seven Sprint 164 tests to construct with `Cap(limit=..., reason=...)`; add two tests: `Cap` frozen, `Cap.limit` accepts int or float. Amends Sprint 164's landing before the enforcement sprint dispatches.

Closes external review F6 at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`. The reviewer's argument: "the kernel is the substrate that enforces vocabulary discipline; it should not itself use unnamed tuples for named concepts."

---

## prerequisites

- Sprint 164 (Budget primitive registration-only landing).
- External review at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F6.

---

## context_files

- `sdd-kit-2/AGENTS.md` (hard rule 6; additive kernel change).
- `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F6.
- `src/substrate/kernel/topology.py` (file modified; `Budget` class at line 29+).
- `src/substrate/api.py` (file modified; re-export block).
- `tests/test_kernel_budget.py` (file modified; construction pattern updated).
- `src/substrate/topologies/swebench_solver/records.py::Reproduction` (precedent for named-struct-in-payload discipline).

---

## signal contract

### Emits

None at runtime — architectural amendment. No new event kinds; the follow-on runtime sprint (roadmap v2 Sprint 1b) adds `substrate.BudgetExceeded`.

### Consumes

Files listed in `context_files`.

### Invariants

- Every `Budget` construction across the codebase uses `Cap(limit=..., reason=...)` — no unnamed tuples remain in production or test code.
- `Cap` is a frozen msgspec Struct — mutation raises `AttributeError`.
- `Cap.limit` typed `int | float`; msgspec preserves the input type on the wire.
- No existing producer_kind call in the codebase uses `Budget` yet (Sprint 164 was registration-only, no consumers), so the type change has no non-test callers to migrate.
- `Cap` re-exported from `substrate.api` and in `api.__all__`.

---

## artifact contract

### Files modified

- `src/substrate/kernel/topology.py` — add `class Cap(Struct, frozen=True)` with `limit: int | float` and `reason: str`; change `Budget.wall_seconds` type to `Cap | None`; change `Budget.event_counts` value type to `Cap`; extend docstring naming the F6 fold.
- `src/substrate/api.py` — add `Cap` to the import from `.kernel.topology`; add `"Cap"` to `__all__` under "topology + execution".
- `tests/test_kernel_budget.py` — update the six existing tests to construct with `api.Cap(...)`; add `test_cap_frozen`; add `test_cap_accepts_int_or_float_limit`; extend the exports test to check both `Budget` and `Cap`; update the module docstring.

### Content assertions

- `src/substrate/kernel/topology.py` contains `class Cap(Struct, frozen=True):`.
- `Budget.wall_seconds` field type is `Cap | None`.
- `Budget.event_counts` field type is `dict[str, Cap] | None`.
- `src/substrate/api.py`'s import from `.kernel.topology` includes `Cap`.
- `api.__all__` contains both `"Budget"` and `"Cap"`.
- `tests/test_kernel_budget.py` contains 9 test functions.
- No `tuple[float, str]` or `tuple[int, str]` type annotation remains on any `Budget` field.

### Command exit codes

- `uv run python -m pytest tests/test_kernel_budget.py -v` returns 0 (9/9 pass).
- `uv run ruff check src/substrate/kernel/topology.py src/substrate/api.py tests/test_kernel_budget.py` returns 0.
- `uv run mypy --strict src/substrate/kernel/topology.py src/substrate/api.py tests/test_kernel_budget.py` returns 0.
- `grep -n "tuple\[float, str\]\|tuple\[int, str\]" src/substrate/kernel/topology.py` returns nothing on `Budget` field lines (both retired at this sprint).

---

## observation contract

Not applicable — architectural amendment; unit tests carry the substance. The additive
contract is: existing producer_kind calls unchanged (no producer used `budget=` before Sprint 166); every new call uses `Cap(...)` at construction; enforcement (Sprint 1b) reads `cap.limit` / `cap.reason` at named fields.

---

## done criteria

`Cap` struct exists on the kernel; `Budget` uses `Cap | None` and `dict[str, Cap] | None`; `substrate.api` re-exports both; nine unit tests pass; ruff + mypy strict clean. The follow-on runtime enforcement sprint (roadmap v2 Sprint 1b) reads the named fields at every enforcement site.

---

## notes

- **F6 finding.** Reviewer at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md:88-111`: "The `str` slot in each tuple is a reason string. Field access at the enforcement site (Sprint 165) reads `budget.wall_seconds[0]` for the cap and `budget.wall_seconds[1]` for the reason. The tuple slot is opaque at the read site." The fix names the fields at the type layer so the enforcement site can't swap indices silently.
- **Additive.** No existing producer_kind call in the codebase uses `Budget`; Sprint 164 was registration-only. The type change lands with no consumer to migrate.
- **`int | float`.** Wall-clock caps use float; event-count caps use int. Union covers both; msgspec preserves input type. Simpler than two separate structs for the two use cases.
- **Ratification path.** Sprint 164 is not yet ratified in `## Decisions`; Sprint 166 amends the Sprint-164 landing before ratification. Architect's ratification of the amended Sprint 164 + Sprint 166 shape is a single decision.
- Roughly 30 minutes; two source files + one test file.

---

## plan-mode review checklist

- [x] `Cap` frozen msgspec Struct.
- [x] `Budget.wall_seconds: Cap | None`; `Budget.event_counts: dict[str, Cap] | None`.
- [x] `Cap` exported from `substrate.api` and in `__all__`.
- [x] Nine unit tests pass; two new tests (frozen, int-or-float).
- [x] Ruff + mypy strict clean.
- [x] Two source files + one test file — within sweet spot.
