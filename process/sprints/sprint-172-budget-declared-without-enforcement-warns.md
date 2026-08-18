# Sprint 172 — Budget declaration emits UserWarning until enforcement ships (fold external F7)

---

```yaml
---
id: 172
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Close F7. `producer_kind(...)` called with `budget=Budget(...)` now emits a `UserWarning` at build time naming roadmap v2 Sprint 1b as the enforcement sprint. A caller who reads `WORKING_AGREEMENT.md § "Producer-authorship rules"` and declares a cap sees at build time that the promise is not live yet — the primitive is on the shelf, the runtime does not enforce.

Warning (not `RegistrationError`) because the field is legitimately additive; producers can declare budgets ahead of enforcement so the enforcement sprint has consumers ready. When the enforcement sprint lands, the warning is deleted and the runtime gate takes over.

## files modified

- `src/substrate/kernel/topology.py` — add `warnings.warn(...)` at the `producer_kind` boundary when `budget is not None`.
- `tests/test_kernel_budget.py` — `_build` helper suppresses the warning so existing budget tests stay quiet; two new tests exercise the warning path: `test_budget_declaration_warns_until_enforcement_ships` and `test_no_warning_when_no_budget_declared`.

## contracts

- 11/11 tests pass (9 preserved + 2 new). Ruff + mypy strict clean.
- Every existing producer_kind call in the codebase behaves identically (none declares a budget in production yet, so the warning fires zero times outside the test suite).

## done

One source file + one test file. Ratifies discipline before the enforcement sprint ships.
