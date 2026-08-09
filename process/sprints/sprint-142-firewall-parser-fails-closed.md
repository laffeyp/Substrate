# Sprint 142 — firewall parser fails closed

---

```yaml
---
id: 142
status: pending
phase: swebench-close-the-loop
cadence_band: auto-within-phase
pass_kind: functional
---
```

---

## why

`assay/swebench.py`'s `firewall_check` calls a unittest-id parser that returns `True` on any test id it cannot parse (per the solver-code review, swebench.py line ~84). Fail-open on a security check is the wrong default: an unparseable test id passes rather than fails, so a `FAIL_TO_PASS` id that trips the parser silently admits an instance that should have been excluded. Fix by flipping the default.

## scope

Single change to the parser branch: any parse failure → return `False` (excluded), not `True` (admitted). Add a test that exercises malformed ids the current code accepts.

## signal contract

### Emits

No new events. `firewall_check` return-value only.

### Invariants

- No public API change: `firewall_check(instance)` still returns `bool`.
- No behavior change for parseable ids that were already handled correctly.

## artifact contract

### Files modified

- `src/substrate/assay/swebench.py` — fail-closed default in the test-id parse branch.

### Files created

- `tests/test_swebench_firewall_parser.py` — the observation.

### Content assertions

- The parser's default branch on parse failure returns `False`, not `True`.

### Command exit codes

- `uv run python -m pytest tests/test_swebench_firewall_parser.py -q` → 0
- `uv run python -m pytest tests/test_assay_swebench.py -q` → 0 (regression on the existing swebench tests)
- `uv run ruff check src/substrate/assay/swebench.py` → 0
- `uv run mypy src/substrate/assay/swebench.py` → 0

## observation contract

`pass_kind: functional`. Behavior change: an unparseable test id now excludes the instance instead of admitting it.

### Input fixture (deterministic)

Two synthetic instance dicts:
1. `FAIL_TO_PASS = ["::malformed::id::"]` — unparseable id. Before: `firewall_check` returns `True` (admitted). After: `False` (excluded).
2. `FAIL_TO_PASS = ["tests/test_x.py::test_y"]` — well-formed id. Both before and after: unchanged behavior (the file-membership check runs normally).

Assertion: the malformed-id fixture now returns `False`; the well-formed fixture returns whatever it returned before (regression bar).
