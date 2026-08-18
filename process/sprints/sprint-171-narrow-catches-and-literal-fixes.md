# Sprint 171 — F4 + F10 + F11: three narrow-catches and one literal fix

---

```yaml
---
id: 171
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Close three cleanup findings from external review REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md. All three are one-line fixes in `assay/`. Grouped as one sprint because they touch two files and share one concept (narrow catches, use named constants).

- **F4.** `assay/report.py:414` used the raw literal `"harness_error"` where `REASON_HARNESS_ERROR` from `_HARNESS_REASONS` should live. Fixed: import + substitute.
- **F10.** `assay/swebench.py:307` caught `Exception` around the swebench-package import; narrowed to `ImportError` so real dependency errors surface.
- **F11.** `assay/swebench.py:886` caught `Exception` around `read_record(cell_dir)` and silently skipped the cell; narrowed to `(RecordIncompleteError, RecordGapError)` and added a stderr log line so unclassified read errors surface instead of silently under-counting.

## files modified

- `src/substrate/assay/report.py` — import `REASON_HARNESS_ERROR`; replace literal at line ~476.
- `src/substrate/assay/swebench.py` — narrow `except Exception` → `except ImportError` in `verify_constants`; narrow `except Exception` → `except (RecordIncompleteError, RecordGapError)` in `batch_grade_from_records`; import the typed errors from `..api`; log skipped cells to stderr with typed reason.

## contracts

- Every existing test in `tests/test_assay_report.py` (52) + `tests/test_assay_swebench.py` passes: 46/46 in the intersection, ruff clean, mypy strict clean.
- No behavior change on the success path.
- Real errors (a real dependency issue in swebench, a disk-full during batch grade) now surface instead of being silently swallowed.

## done

Two source files. Three fixes. All green. Sources: external review findings F4/F10/F11.
