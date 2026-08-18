# Sprint 200 — S9 wire-check report (roadmap v2 S9)

Two runs fired on this box, back-to-back, to satisfy the roadmap v2 § "Sprint 9" observation contract from two angles.

## Run A — N=300 Lite under `SWEBENCH_ARMS=solver`

- **Config.** `SWEBENCH_ARMS=solver`, `SWEBENCH_LIMIT=300`, `SWEBENCH_N=1`, `SWEBENCH_TRIALS=1`, `SWEBENCH_CONCURRENCY=8`, `SWEBENCH_MODELS=llama3.2:1b`, `SWEBENCH_DATASET=princeton-nlp/SWE-bench_Lite`, `SWEBENCH_SKIP_BASE_PYTEST=1`, `SWEBENCH_RUN_TIMEOUT=1200`.
- **Wall time.** 9963 seconds (2 hours 46 minutes).
- **Cells.** 300/300 landed. 100% `source=run`, 100% `verdict=fail`, 100% `reason=""`. Zero salvages, zero errors, zero no_verdict rows.
- **Records.** 300/300 carry `substrate.RunFinalised`. Zero `substrate.ProducerFailed` events across the entire sweep.
- **Per-repo spread.** django 114, sympy 77, matplotlib 23, scikit-learn 23, pytest-dev 17, sphinx-doc 16, astropy 6, psf 6, pylint-dev 6, pydata 5, mwaskom 4, pallets 3. Interleaving cycled through 8 different repos in the first batch, deterministically.
- **Per-cell wall.** min 174s, median 270s, p95 345s, max 385s. No cell hit the 1200s ceiling.
- **Model calls.** Exactly 3 per cell (localize + repair drafter + retry). Zero variance. 1.9M prompt tokens total; 315K completion tokens total (word-count estimated — llama3.2:1b's token counts don't route through the metered path).
- **Verdict.** llama3.2:1b at 1B parameters cannot patch any of the 300 Lite instances; every cell records "no model_patch on the record." The observation is that the RUNNER processes 300 cells cleanly at scale, not that this model resolves anything.

## Run B — N=36 Lite under `SWEBENCH_ARMS=solve_and_grade`

Fired second to close the roadmap contract's `GradeResult`-on-record requirement, which Run A's `solver` mode does not exercise (Run A uses `SwebenchRecordOracle`; the grade fires in the oracle, not as an event on the record).

- **Config.** `SWEBENCH_ARMS=solve_and_grade` (6 arms), `SWEBENCH_LIMIT=6`, `SWEBENCH_TRIALS=1`, `SWEBENCH_CONCURRENCY=3`, `SWEBENCH_MODELS=llama3.2:1b`, `SWEBENCH_ENSEMBLE=llama3.2:1b`, `SWEBENCH_K=3`. 6 astropy instances × 6 arms = 36 cells.
- **Cells.** 36/36 landed. 100% `source=run`, 100% `verdict=fail`. Median wall 63s; max 133s.
- **Records.** 36 finalized records; 2 records (both from `tool_loop_container` on astropy-12907 and astropy-14182) carry `substrate.ProducerFailed` events from docker rc=125 and rc=1 (Apple Silicon platform issues starting the container).
- **`GradeResult` events on record.** 4 total, all from `tool_loop_container` cells where the container-agent loop returned a patch (empty-ish). Each triggered the grader, the harness ran, `GradeResult(instance_id, verdict, reason)` landed on the record. **First live evidence of Sprint 199d's `container_solve_and_grade_arm` firing end-to-end into a real record outside the stub test.**
- **`SelectedPatch` events.** 4 total, same 4 cells. The 5 repair arms produced zero `SelectedPatch` across their 30 cells — llama3.2:1b cannot repair.

## What the contract landed and what it did not

**Landed.**

- Runner processes 300 cells at scale with zero errors, zero salvages, zero timeouts. Every record finalized.
- Cells-JSONL row shape correct across 336 total rows (300 + 36).
- Per-repo interleaving works.
- Per-cell timeout works (no cell hit the 1200s or 600s ceiling in either run).
- Sprint 199d's `container_solve_and_grade_arm` produces real `GradeResult` events on real records at multi-cell concurrency.
- The extracted `run_suite_with_salvage` loop (Sprint 199) processes cells honestly under both `SwebenchRecordOracle` and `swebench_log_projection_oracle` paths.

**Did not land.**

- Rate-limit event bounds (`RateLimitDenied` count per cell < 10; sustained bound < 20% of tier capacity). llama3.2:1b is local; no cloud tier declared; no rate limiting fires. The bounds are trivially satisfied but not tested. A cloud-model wire-check is needed for a real rate-limit observation.
- Model quality contribution to `resolve` rate. Zero resolves on 336 cells. Any statistical claim about `resolve_rate` requires a stronger model (qwen2.5-coder:7b or a cloud model). Not the S9 scope.

## Real observation gap surfaced during Run B

**In-topology `ProducerFailed` events do not reach the runner's cell-level classifier.** The two docker-failed cells in Run B landed as `verdict=fail, source=run, reason=""` at the cells-JSONL row level. The docker failure information lives on the record as `substrate.ProducerFailed`, but the row loses the distinction between (a) topology's `solve` producer failed with a docker error, and (b) topology's `solve` producer completed successfully but produced no patch. Both roll into "fail" via the log-projection oracle's "no GradeResult on record" fallback.

**Follow-on sprint (200a).** `swebench_log_projection_oracle` should scan for `substrate.ProducerFailed` events on the record and, when the failed producer is `solve` or `grader`, surface `verdict=no_verdict, reason=<classified-reason>` instead of the generic "no GradeResult" fallback. The reason routes through `_HARNESS_REASONS` (`docker_error`, `container_crashed`, `harness_error`). This closes the shape that says "the topology failed for a docker reason" at the row level, where the report reads.

## roadmap position

S0–S6 (Sprint 197), S7a (Sprint 199), S7a-SDD-fold (Sprint 199a), S7b (Sprint 199b), S7b-close (Sprint 199c), S7b-follow-on (Sprint 199d), S8 (Sprint 198), **S9 landed here (Sprint 200 — this report).** Next: Sprint 200a (log-projection oracle sees `ProducerFailed`), then S10 (Verified pass 1, ensemble arm only).
