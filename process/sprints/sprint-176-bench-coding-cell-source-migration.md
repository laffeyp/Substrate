# Sprint 176 — `bench_coding.py` migrates to `CellSource` enum (fold external F14)

---

```yaml
---
id: 176
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Close F14. `scripts/bench_coding.py` wrote cell rows with raw source strings (`"run"`, `"salvage"`, `"fail"`) at lines 275, 284, 288 and read them at lines 162-163. `scripts/assay_swebench_confirmatory.py` had migrated to the `CellSource` enum at commit `1ded31b`; bench_coding never followed. Two writers, two disciplines, one cells-file format. Sprint 176 migrates bench_coding to the enum.

## semantic mapping

- `"run"` → `CellSource.RUN.value` — the topology ran + graded.
- `"salvage"` → `CellSource.SALVAGE.value` — regraded from a prior record.
- `"fail"` → `CellSource.ERROR.value` — cell raised or failed to produce a valid grade. bench_coding's `"fail"` matched `CellSource.ERROR`'s semantic ("the cell raised before/around the grade"). The reviewer's F14 note "migrate to `CellSource.FAIL.value`" mis-remembered — `CellSource` has `RUN | SALVAGE | ERROR`, no `FAIL`. bench_coding used `"fail"` where the SWE-bench runner uses `"error"` for the same class of cell.

## files modified

- `scripts/bench_coding.py` — import `CellSource` from `substrate.assay.cells`; replace three writer literals and update the reader. The reader keeps a compat check for pre-fold rows on disk carrying the legacy `"fail"` string (`source in (CellSource.ERROR.value, "fail")`) so any existing cells.jsonl file still reads correctly under the migrated bench_coding.

## contracts

- 85 targeted tests pass (report + preregistration + cells + kernel_budget + rate_limit + confirmatory).
- Ruff clean; bench_coding parses.
- Backward compat: any cells.jsonl already on disk with `"fail"` rows still reports correctly under the migrated bench_coding.
- Forward: every new bench_coding-produced cells.jsonl uses `"run" | "salvage" | "error"` as the source wire form — same lexicon the SWE-bench runner writes.

## done

One file. The vocabulary drift between the two runners is closed; both use `CellSource` values on cells.jsonl now.
