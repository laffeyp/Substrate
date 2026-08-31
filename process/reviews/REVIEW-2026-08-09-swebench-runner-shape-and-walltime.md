# REVIEW — SWE-bench runner: shape and wall-clock

**Reviewer:** external (Claude Opus 4.7 session)
**Date:** 2026-08-09
**Scope:** `scripts/assay_swebench_confirmatory.py`, `src/substrate/assay/swebench*.py`, `src/substrate/topologies/swebench_solver/*`, Sprint tail through 2026-08-09
**Question posed:** does the runner's shape make sense, and where does the day-and-a-half go?

---

## Verdict

The shape is sound. The dual contract, the adapter-only door, the firewall, the pre-registration gate, and the halt-on-error posture are the load-bearing pieces and they are all landed. The 4-12 day wall-clock of a full Sprint 160-pass2 matrix is not architectural. It is arm64→amd64 emulation multiplied by a fresh `docker run --rm` per patch multiplied by an unbatched official grader multiplied by a semaphore of 4. Two changes — batch the grader, reuse the per-instance container — should roughly halve pass-2 wall without touching the topology.

---

## Where the wall goes

The unit of work is a **cell** = (arm, case, trial). Pass 2 = 300 cases × 5 arms × 3 trials = **4,500 cells**. Per cell, on the Architect's arm64 macOS box:

| Step | Site | Wall |
|---|---|---|
| Localize (1 model call) | `element_localizer_factory` at `topologies/swebench_solver/assemble.py:452` | 15-40s |
| Repro-gen (K model calls) | `repro_generator_factory` at `assemble.py:464` | 15-120s |
| Repro base-validate (1 Docker run) | `repro_base_validate_factory` at `assemble.py:479` | 30-90s |
| Draft (up to n·max_rounds = 6 model calls) | `repair_drafter_factory` at `assemble.py:512` | 60-240s |
| Validate (host `git apply` per candidate) | `repair_validate_factory` at `assemble.py:519` | seconds |
| `select_exec` — 1 Docker run per applied patch per round (up to 6) | `_select_exec_factory` at `assemble.py:97-125`, `DockerTestRunner.run` at `select_docker.py:153-192` | 180-600s |
| Grade — 1 fresh harness call per cell, `max_workers=1` | `SwebenchRecordOracle.grade` → `grade_patch` → `run_swebench(..., max_workers=1)` at `assay/swebench.py:242-288` | 60-180s |

At **5-15 min per cell** and `SWEBENCH_CONCURRENCY=4`:

- Pass 1 (1 arm × 300 × 3 trials = 900 cells): 19-56h. The runner's own header estimates ~20-30h.
- Pass 2 (4,500 cells): 95-280h. **4-12 days.**

"A day and a half" fits pass 1 with concurrency raised to 8, or pass 2 with trials cut to 1.

---

## What the shape gets right

- **Adapter is the only door.** `prepare_swebench_case` (`swebench_suite.py:85-128`) is the single admission path. `PreparedPayload` (`swebench_suite.py:44-63`) is a `TypedDict` so `solver_topology_from_payload` refuses a raw dict at check time. The Aug-08 F1 fix rewired every matrix arm through this door.
- **Firewall is structural and disclosed.** `firewall_check` (`assay/swebench.py:76-164`) matches file equality post the F7 substring fix; `exclude` carries only test-file paths, never the graded ids.
- **Pre-registration gate runs before any disk write.** `_run` in `assay_swebench_confirmatory.py:346-399` calls `preregistration_guard` first; `mkdir`, `meta.json`, `.cases.json` follow. A failed guard leaks no artefacts. `arms_fingerprint` hashes per-arm `{models, n, max_rounds}` so a same-name reroll trips it (F151-#1).
- **Salvage mode exists.** `SWEBENCH_SALVAGE` regrades an existing record without model calls (`confirmatory.py:475-501`).
- **Halt-on-error is deliberate.** The Aug-09 flip stops silent inflation of the resolve rate.

---

## Where the fat is — optimisations in impact order

### 1. Batch the grader

`SwebenchRecordOracle` grades one patch at a time through `grade_patch`, which calls `run_swebench([one_pred], max_workers=1)`. That is 4,500 harness starts for pass 2 and 4,500 fresh `run_evaluation` processes. The swebench harness accepts a predictions file with many instances and parallelises via `max_workers`. Collect all patches from a completed sweep, call `run_evaluation` once (or once per arm), and set `max_workers=CONCURRENCY`. **Expected saving: 5-10× on the grade path.**

### 2. Reuse a long-lived container per instance

`DockerTestRunner.run` (`select_docker.py:153-192`) fires `docker run --rm` for every regression run and every repro run. Setup and teardown cost 2-5s × ~8 Docker calls per cell × 4,500 cells = **10-25h of pure container-start overhead**. `ContainerWorkspace` from KIT_DIARY 23 already knows how to hold an instance container open. Route `select_exec` and `repro_base_validate` through the persistent container with `docker exec` per patch and `git reset --hard` between patches. **Expected saving: 40-60% of Docker wall.**

### 3. Cache localise + repro-gen across arms and trials

Both are pure functions of `(issue, repo_skeleton, strong_model)`. They do not move between trials or between the four arms that share `MODELS[0]`. Every cell pays them anyway. Memoise per `(case_id, model_id, "localize" | "repro_gen")` on disk under `SCRATCH`. **Expected saving: about 8,400 model calls across pass 2, plus the paired `repro_base_validate` Docker calls.**

### 4. Pre-pull instance images concurrently in prep

The prep loop already runs `prepare_swebench_case` under a semaphore. Add `docker pull` warmup inside `_prep_one` at `confirmatory.py:424-431` so the first cell on each of the ~30 unique images does not pay the pull cost inside the graded sweep. **Expected saving: 1-2h across 300 instances.**

### 5. Raise `SWEBENCH_CONCURRENCY`

Default 4 was picked when Docker was the shared bottleneck. About half of cell wall is Ollama Cloud network I/O. On a 10-core Apple Silicon with 32GB+ RAM, 8-12 concurrent cells is safe. Test at 12. **Expected saving: 2-3× throughput ceiling.**

### 6. Halt-on-error over 4,500 cells is a footgun

`asyncio.gather` cancels every sibling on a single raise (`confirmatory.py:509-541`). A flake at hour 90 throws away 90h. The Sprint tail justification is "honest signal, better than a bogus resolve rate," and that is correct. The middle ground is a typed per-cell exception taxonomy — `docker_unavailable`, `image_missing`, `model_timeout`, `container_oom`, `git_apply_error` — written to the cell row with `source="error", detail=<typed>`. The report layer already distinguishes `grade_unavailable` from `error` (Drift watchlist 2026-06-27). Halt on typed-critical (a firewall violation on Verified is a benchmark bug); continue on typed-flake.

### 7. Drop `RUN_TIMEOUT` for baseline arms

30 min is the ceiling for `n_drafts_repair` at `max_rounds=2`. `single_draft_baseline` and `n_drafts_no_correction` have no round fan-out; they should return under 10 min. A 30-min ceiling delays surfacing a wedged cell.

### 8. Reconsider `REPRO_K=3` in pass 2

F4's amortisation collapses K variants into one Docker script, but the K parallel model calls for repro-gen still cost. K=3 across 4,500 cells = 9,000 extra model calls. The Sprint 158 κ signal from K=1 already tells the tiebreak story. Stage K=1 first; escalate to K=3 only on cells the κ marks as low-agreement.

### 9. The 5-arm matrix is over-specified for a first confirmatory

`single_draft_baseline` + `n_drafts_repair` is the minimum honest ablation for the mechanism-versus-samples question. Add `baseline_matched_compute` third. `n_drafts_no_correction` and `n_drafts_repair_ensemble` are the second run. Cutting two arms cuts wall by 40% and gets a defensible Δ faster.

### 10. Trials=3 wants a pilot to fix the between-trial variance

Per `project-benchmarking-power-reality`, 300 × 3 gives the paired two-level bootstrap real power, but trials=1 on the full 300 plus trials=3 on a stratified 60-instance subset earns the same variance estimate for a third of the wall.

---

## Substrate-side notes surfaced by the read

- **Stringly-typed cell dispositions.** `source == "run"` / `"salvage"` / implicit `"error"` at `confirmatory.py:186` are literals in the cell row. F10 in the Sprint 158 pass hunted the same pattern in `assemble.py`'s view names — six literals became six constants. The cell rows want a `CellSource` enum in `assay/run.py` so the report layer can set-difference cleanly.
- **`grade_patch`'s `run_id`.** `f"assay-{instance_id}-{sha1(model_name:patch)[:10]}"` at `assay/swebench.py:337` does double duty — cache-collision avoidance and per-cell isolation. If batching lands (item 1), the batch caller supplies one `run_id` for the batch and the harness's per-instance directory disambiguates.
- **Firewall unittest parser is now file-equality (F7).** Good. Docstring-form ids fall back to a substring content search over `test_patch`; the 12-char floor at `swebench.py:141-144` bounds the false-positive shape.

---

## Bottom line

The Aug-08 fold pass and its pass-2 (F1-F12) closed the load-bearing correctness gaps and put the runner into an honest shape. The wall-clock reads long because every cell holds its own harness process open and every patch pays a fresh container. Fix the grader batching and the container reuse first; those two changes alone should halve pass-2 wall. Everything else is second-order.
