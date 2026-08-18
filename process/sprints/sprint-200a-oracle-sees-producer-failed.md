# Sprint 200a — Log-projection oracle surfaces essential-producer failure at the row (roadmap v2 S9 close)

Sprint 200's Run B N=6 solve_and_grade smoke surfaced a real observation gap. Two `tool_loop_container` cells hit `docker rc=125` and `docker rc=1` on Apple Silicon; the `solve` producer emitted `substrate.ProducerFailed` on the record and the topology finalized on quiescence. `SwebenchLogProjectionOracle` returned `Verdict.FAIL, reason=""` — indistinguishable at the row level from a Draft-Exhausted "arm produced no patch to grade" outcome. The report reads the row, so mechanism failures counted as arm failures. Sprint 200a closes it.

## design decision (why oracle, not runtime or topology)

- **Runtime-level would be wrong.** A topology legitimately has N producers where some fail (one drafter fails, others succeed). The Runtime cannot know which failures are terminal to the topology's goal — that's the oracle's job.
- **Topology-level would be bigger.** Making the grader emit `GradeResult` on failure paths requires a different trigger (fire on `SolveFailed | SelectedPatch` instead of `SelectedPatch`), which means adding a typed `SolveFailed` event and changing the solve producer's exception handling. Real work but larger scope.
- **Oracle-level is the honest fit.** The oracle already reads the record; extending it to see `substrate.ProducerFailed` on the essential-path producers (`solve`, `grader`) keeps one source of truth. The producer's error string is on the record. Classification lives at the oracle, next to the rest of the SWE-bench grade logic.

## files touched

- `src/substrate/assay/swebench.py` — new `classify_reason_string(msg: str) -> str` next to `_HARNESS_REASONS`. Takes `repr(exc).lower()`-shaped strings and returns a `_HARNESS_REASONS` value (docker/container → `docker_error`; git → `git_error`; rate + limit → `rate_limited`; timeout → `timed_out`; else → `harness_error`). `SwebenchLogProjectionOracle.grade` gained a `_ESSENTIAL_PRODUCER_KINDS = frozenset({"solve", "grader"})` class attribute and a new branch in the no-GradeResult fallback: if any `substrate.ProducerFailed` event exists whose `producer.kind` is essential, return `Verdict.NO_VERDICT` with `reason=classify_reason_string(error)` and `detail` naming the producer + truncated error. Otherwise the pre-Sprint-200a fallback (FAIL, no-GradeResult detail) fires — backward compat for every Draft-Exhausted cell.
- `scripts/assay_swebench_confirmatory.py` — `_classify_cell_error`'s string-repr fallback now routes through `classify_reason_string`. One source of truth for the substring taxonomy. Runner-side we UPGRADE the harness_error fallback to `unclassified_error` (halt) when the message contains none of docker/container/git, so an unfamiliar exception class doesn't get silently absorbed as a flake — the classifier's original "halt on unknown" semantics preserved. `subprocess.CalledProcessError` always classifies via `classify_reason_string(repr(exc))` (docker/git present in argv). Removed unused imports `REASON_DOCKER_ERROR`, `REASON_GIT_ERROR`.
- `tests/test_log_projection_oracle_producer_failed.py` (new, 7 tests) — pins the row-level distinction: ProducerFailed on `solve` with docker error → NO_VERDICT, docker_error; on `grader` with git error → NO_VERDICT, git_error; on non-essential producer (e.g. `localize`) → no trigger, FAIL fallback stays (backward compat); no ProducerFailed AND no GradeResult → FAIL (backward compat); GradeResult wins over ProducerFailed when both present; `classify_reason_string` taxonomy; runner + oracle share the classifier (one substring rule change lands in both).
- `tests/test_container_solve_and_grade_arm_e2e.py` — `_docker_up()` uses `docker version` (client-side, fast) instead of `docker info` (queries daemon, slow under load); timeouts extended from 5s → 15s. Test marked `@pytest.mark.timeout(300)` because the flask-4045 grade takes 60-90s under the default pytest 60s timeout.

## contracts

- 15 new tests pass; 850 across the full suite (847 core + 3 live realmodel/swebench_host); 4 skipped; 0 failures.
- Ruff clean on every touched file; mypy strict clean on `swebench.py`.
- Pre-Sprint-200a behavior preserved for every existing path: GradeResult wins when present; no ProducerFailed on essentials → FAIL fallback with old detail; non-essential producer failures don't trigger the new branch.
- **Observation contract landed on Sprint 200's real records.** Re-ran `swebench_log_projection_oracle` over the two docker-failed records from Sprint 200's N=6 solve_and_grade smoke. Pre-Sprint-200a: `verdict=fail, reason=""`. Post-Sprint-200a: `verdict=no_verdict, reason=docker_error`, `detail="essential producer 'solve' failed for astropy__astropy-12907: CalledProcessError(125, ['docker', 'run', ...])"`. The fix works on the real records that surfaced the gap.

## what this does not fix

- **Topology-level failure signal.** A producer failure that lands as `substrate.ProducerFailed` still lets the topology finalize on quiescence (correct — other producers may succeed). Runtime doesn't return `status="failed"` for essential-producer breakage. Sprint 200a moves the SIGNAL to the row via the oracle; the topology's lifecycle is unchanged. A future sprint could add a typed `SolveFailed` event the topology emits when it observes its own essential producer die, giving richer wire information than the current `substrate.ProducerFailed.error` repr.
- **Boundary-typed producers.** KIT_DIARY 40's transferable rule stands: every external boundary should have its own typed producer + typed events. `container_solve_and_grade_arm` still routes docker failures as a subprocess exception string; a future `ContainerProducer` (roadmap S5.3) would emit `ContainerRequested / ContainerStarted / ContainerFailed(reason)` events the oracle reads directly, no string classification. Sprint 200a is honest interim glue; the boundary-typed producer is the real move.

## roadmap position

S0–S9 landed (Sprint 197, 199, 199a-d, 198, 200). S9 close-out lands here (Sprint 200a). Next: S10 (Verified pass 1) — depends on decisions the user owns (which ensemble to fire).
