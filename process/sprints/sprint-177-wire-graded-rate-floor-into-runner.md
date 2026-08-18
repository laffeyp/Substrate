# Sprint 177 — Wire `graded_rate_floor` from pre-reg → meta → `build_report` (closes external round-2 M3)

---

```yaml
---
id: 177
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Round-2 review M3: Sprint 170 landed `RunUnpublishable` + `graded_rate_floor` in `assay/report.py` and `Preregistration.graded_rate_floor` in `assay/preregistration.py`, then reported F3 closed. `grep "graded_rate_floor\|RunUnpublishable" scripts/assay_swebench_confirmatory.py` returned zero — the primitive was on the shelf and no runner path pulled it down. Any Verified attempt at high NO_VERDICT rate would publish an unbounded headline as if it graded to completion.

Sprint 177 closes the mirage: two edits thread the floor from the pre-registration file through the recorded meta into the report. When the runner uses `SWEBENCH_PREG`, the pre-reg's floor lands on the meta sidecar; `report_from_cells` reads it and passes to `build_report`. Backward compatible — a run without a pre-reg (or with a pre-Sprint-170 pre-reg that lacks the field) sees the floor default to `None` and the existing arm-completeness gate applies.

## files modified

- `scripts/assay_swebench_confirmatory.py` — in the `if PREG:` branch, add `cfg["graded_rate_floor"] = pre.graded_rate_floor` so the value writes to the meta sidecar alongside the arms_hash. Print statement gains the floor value so the runner's startup log shows what discipline the run is bound to.
- `src/substrate/assay/cells.py` — `report_from_cells` reads `meta.get("graded_rate_floor")` and passes to `build_report(..., graded_rate_floor=...)`. `None` on runs without a pre-reg — same behavior as pre-Sprint-170.

## why store on meta, not read live from pre-reg

Storing on meta binds the report to the value the RUN was gated on. Reading live from the pre-reg at report time would let a later pre-reg edit silently move the threshold under an already-recorded run. The provenance guard at `cells.py::provenance_status` also verifies the config fingerprint against the stored meta — so any mutation of `graded_rate_floor` post-run trips the tamper detection Sprint 143 wired.

## contracts

- 65 tests pass across cells + report + preregistration.
- Ruff + mypy strict clean on both files.
- A pre-Sprint-177 run's cells.jsonl (no `graded_rate_floor` on meta) reports identically.
- A Sprint-177+ run with a pre-reg carrying `graded_rate_floor=0.8`: meta records `0.8`; `report_from_cells` reads it; any arm below `0.8 graded_rate` lands `RunUnpublishable` and delta collapses.

## done

Two files, real closure of F3, real closure of round-2 M3. The publish-refusal branch fires on the next Verified attempt whose pre-reg pins a floor.
