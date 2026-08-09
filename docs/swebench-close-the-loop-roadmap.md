# SWE-bench close-the-loop roadmap (round 3)

*Restarted 2026-08-08 after a full read of the substrate: kernel v15 + product draft7 + the entire kernel/record/projections/conformance implementation + adapters + coding_flow + code_review + the three applications + best_of_n + the SWE-bench solver + SWE-bench assay + substrate-ui + the vocab locks (roughly 22,000 lines of code + spec). Every claim cites a specific file:line. Round-2's plan is superseded and preserved as the audit trail; the file it referenced (`docs/swebench-close-the-loop-roadmap.md`) is this document.*

*Then folded 2026-08-08 after an adversarial subagent review that read the SDD kit + project docs, became a SWE-bench external expert (Agentless, SWE-Bench+, Xia/Chen 2025 on oracle error, Kapoor & Narayanan on unaccounted compute, Miller on error bars, Tango 1998 / Nam 1997 on score-TOST), and spot-checked the roadmap's code citations. Six material findings + four polish items landed in the sprints below; the "Round-3 review folds" section at the tail lists what changed.*

*Scope: move the 108/291 exploratory number from `scripts/assay_full_run.py` (deleted, sprint 144) to a publishable confirmatory result routed through the assay control plane the runtime already ships.*

---

## The 108/291 diagnosis, restated from code

The exploratory result came from a direct `Runtime(root).run(swebench_repair_topology(...))` call. It bypassed the assay control plane, so:

- No `Report` was built (`assay/report.py:144`).
- No `pass_hat_k` computed (`assay/stats.py:33`).
- No confidence interval (`assay/stats.py:95`).
- No `UsageTotals` aggregated (`assay/run.py:48`).
- No `.meta.json` sidecar written (`assay/cells.py:79`).
- No `provenance_status` verified.
- No ablation. Single trial per instance. One model.

Everything the assay layer was designed to do was skipped. The fix is not new machinery — it is routing every subsequent run through `run_arm_on_case` (`assay/run.py:77-98`) and closing the specific gaps that stop that from producing a publishable result today.

## What the substrate already offers

- **Assay control plane.** `run_arm_on_case` (assay/run.py:77-98) runs one Arm on one Case at a minted root, times it with `time.monotonic()`, sums `ModelUsage` off the record into `UsageTotals`, and grades with an `Oracle`. `run_suite` (assay/run.py:101-112) walks the Arm × Case × Trial matrix. `Suite` / `Arm` / `Case` at `assay/suite.py:53-115` with control-arm validation and path-safe token constraints.
- **Oracle taxonomy.** `LogProjectionOracle` (assay/oracle.py:59-91) grades from the record (replayable=True). `ExternalGraderOracle` (assay/oracle.py:94-122) runs an external system (Docker, DB) and stamps `replayable=False`. Both wrap the verdict in a frozen `Result` (assay/oracle.py:35-53) with `oracle_class` and `replayable` fields riding on every grade — so a headline can never mistake a run-and-observe grade for a reproducible one.
- **Statistics.** `pass_hat_k` unbiased subset estimator (assay/stats.py:33-41). `bootstrap_delta_pass_k` paired two-level bootstrap resampling Cases outer + trials inner (assay/stats.py:95-145). `equivalence_verdict` with a power-floor gate that refuses to print "equivalent" underpowered (assay/stats.py:148-178). `benjamini_hochberg` FDR across the arm matrix (assay/stats.py:181-197). The bootstrap CI is a percentile-dual TOST — a documented substitute for the Tango/Nam score-TOST the round-2 doc names as owed.
- **ModelUsage discipline.** `ModelUsage` is a first-class event (adapters/models.py:50-71). `call_responder_metered` (adapters/models.py:381-404) emits provider-truth counts for OllamaResponder or word-count stand-ins (with `estimated=True`) for the deterministic path. `_sum_usage` (assay/run.py:48-58) aggregates them into every `CaseResult`. `wall_ms` is inference-only (`_usage` at models.py:177-197 uses `prompt_eval_duration + eval_duration`, excluding VRAM `load_duration` — a real subtlety, deliberate).
- **Firewall discipline.** `firewall_check` (assay/swebench.py:71-124) enforces two data-level conditions per instance: `files(patch) ∩ files(test_patch) == ∅` and every FAIL_TO_PASS test file is added by test_patch. Called at three arm-building sites: `prepare_swebench_case` (assay/swebench_suite.py:93), `solve_on_host` (assay/swebench_host.py:58), `solve_in_container` (assay/swebench_agent.py:88), plus `repair_arm.build` (assay/swebench_matrix.py:104-106, sprint 148 landing). Grade-time filter `filter_diff` drops edits to graded-test files at `swebench_record_oracle` (assay/swebench.py:353-358). Container contamination lockdown at `ContainerWorkspace.start()` (assay/swebench_container.py:56-87): `--network none`, strip remotes, detach HEAD at base, delete every ref, expire the reflog.
- **Provenance sidecar.** `provenance_status` (assay/cells.py:79-105) recomputes the meta.json config fingerprint against the stored `config_fp` and the per-cell stamps; returns `verified` / `tampered` / `unverified`. The upfront gate that would refuse to *write* cells without a pre-registration is missing (sprint 151 below).

## What the substrate actually lacks — code-grounded, ranked

1. **`swebench_repair_topology` and `swebench_solver_topology` will build from anything.** Neither self-guards. `swebench_solver_arm` at swebench_suite.py:154-179 routes through `prepare_swebench_case`; `repair_arm` at swebench_matrix.py:92-119 reads `case.ground_truth` directly. Sprint 148 added the guard at the arm level; sprint 149 added an optional `firewall_instance` kwarg on both topologies for hand-stitched callers. Both landed.
2. **`cells.py:suite_from_meta` is coding-only.** Line 65-76 hardcodes `coding_problem_bank()` + `coding_suite()`. Docstring at cells.py:1-8 admits it: "Coding-assay-specific for now (it knows the coding bank); other assay types reconstruct their own suite when they exist." `report_from_cells` on any SWE-bench cells file crashes or produces nonsense. Sprint 152 dispatches by `assay_kind`.
3. **`stats.py`'s TOST is the percentile-CI variant.** Docstring at stats.py:12-14: "NOT the Tango/Nam score-TOST the power analysis prefers; that score test is the upgrade owed before any equivalence claim actually runs." `scripts/power_sim.py` uses the existing `bootstrap_delta_pass_k` — it does *not* contain the score-TOST implementation. Sprint 150 ports Tango 1998 / Nam 1997 from primary references.
4. **No pre-registration gate.** `provenance_status` verifies after cells exist; nothing refuses to run without a `.preg.json`. Template exists at `docs/benchmarking-preregistration-template.md` (18 sections). Sprint 151 lands the runner-side gate.
5. **Reproduction test is model-authored, never validated on base.** `reproduction.py:51-65` writes the repro; `select_exec.py:113-146 run_one` runs it against every applied patch — never against `base_commit`. A trivially-passing repro is not caught. Sprint 155 adds the base-fails-first check.
6. **`SuspectElements` defined, never emitted.** `records.py:51-55` defines it; `swebench_solver/__init__.py:37` exports it. `localize.py:57-85` only emits `SuspectFiles` + `EditLocations` at file granularity. Sprint 157 ships the element-level path as an ablation arm, not a replacement.
7. **`responders[slot % len(responders)]`** in the drafter (repair.py:74). Callers pass one Responder in practice → best-of-N reduces to temperature-diversity from one model. Sprint 157 adds a heterogeneous ensemble Responder.
8. **My Sprint 144 confirmatory script has six real gaps against `bench_coding.py`.** Six-column table below. The most consequential — nested `.meta.json` shape — silently breaks `provenance_status` (always reports "tampered" because the recompute doesn't match the stored hash). Sprint 144a closes them.
9. **Substrate-ui's assay pane hardcodes coding-specific meta keys** at `substrate-ui/server.py:390-392` and `substrate-ui/web/app.js:168-170`. SWE-bench cells won't render right. Sprints U-0/U-1/U-2 close it.
10. **The `swebench_smoke.py` gold-differential harness-binding check** (sprint 146 deletion) had no pytest coverage equivalent. Sprint 146a restores it as a marked test.

## What has landed (verified against the code as it stands)

| # | Concept | Landing citation |
|---|---|---|
| 142 | firewall_check parser fails closed | `assay/swebench.py:98-105` returns `False` on unparseable id |
| 143 | `FirewallViolation` typed exception + `PreparedPayload` TypedDict | `assay/swebench.py:47-59`; `assay/swebench_suite.py:44-62`, `85-126`, `169-179` |
| 144 | Confirmatory entrypoint through `run_arm_on_case`; old runner deleted | `scripts/assay_swebench_confirmatory.py` (new); `pyproject.toml` datasets ignore |
| 145 | `deterministic=True` on 7 pure producers | `topologies/swebench_solver/assemble.py` lines 254, 275, 282, 289 (repair topology); 450, 471, 487 (solver topology) |
| 146 | Dead-runner sweep | `git grep` returns zero for `swebench_smoke`, `assay_swebench_smoke`, `assay_agent_debug` |
| 147 | `FirewallViolation` + `firewall_check` in `__all__` | `assay/swebench.py:367-384` |
| 148 | Firewall gate on `repair_arm` | `assay/swebench_matrix.py:104-106` |
| 149 | `firewall_instance` guard on both topology builders | `topologies/swebench_solver/assemble.py:213, 380` (kwarg); `219-224, 391-396` (check + raise) |
| 153 | `Result.grader_error_band: float \| None = None` | `assay/oracle.py:35`, field at line 58 |
| 154 | `ArmReport.model_ensemble_id`, `ArmReport.split_id` + `build_report` propagates | `assay/report.py:44-89` (Struct), `152-160` (build_report signature), `283-284` (propagation) |

Every landing verified under the full suite (618 passed / 1 skipped baseline, confirmed twice).

## What remains — eleven sprints, dependency-ordered

### Group A — Correctness parity (blocks any real run)

| # | Sprint | Files | Concept |
|---|---|---|---|
| 144a | Confirmatory runner parity with `bench_coding.py` | `scripts/assay_swebench_confirmatory.py` | **Eight gaps.** (1) Async concurrency: `asyncio.Semaphore` + `gather`, cf. bench_coding.py:251-299. (2) Per-cell timeout: `asyncio.wait_for`, cf. bench_coding.py:276-286. (3) Salvage mode: `SWEBENCH_SALVAGE=<dir>` regrade without model calls, cf. bench_coding.py:260-272. (4) Refuse-mixed-configs on resume, cf. bench_coding.py:226-231. (5) Flat meta.json shape: `{"config_fp": ..., "run_id": ..., **cfg}` — my nested `{"config": cfg, "config_fp": ...}` silently breaks `provenance_status` because its recompute at cells.py:94-98 hashes the wrong dict. (6) `msgspec.to_builtins(report)` in place of `report.__dict__` for proper Report serialization. (7) **Write `.cases.json` sidecar** alongside `.meta.json` — an array of `{case_id, instance_id, image, spec, regression_files, exclude, passed_at_base}` sufficient for Sprint 152 to reconstruct a `swebench_suite` from cells without re-cloning. Without this Sprint 152 has no data source and depends on a producer nobody schedules. (8) Set `UsageTotals.estimated` from the record (`sum estimated over ModelUsage events`) so the stats layer distinguishes provider-truth from word-count stand-ins — bench_coding.py:129 writes this; my confirmatory doesn't. |
| 146a | Restore harness-binding validation as a pytest gate | `tests/test_assay_swebench_harness_binding.py` (new), `pyproject.toml` (register marker) | Port `swebench_smoke.py`'s gold-differential logic (predictions=`"gold"` → resolved=True; empty patch → resolved=False) as `@pytest.mark.swebench_harness`, skipped when Docker + swebench aren't available. Same coverage the deleted script had, in the suite. |

### Group B — SWE-bench-aware report_from_cells

| # | Sprint | Files | Concept |
|---|---|---|---|
| 152 | Dispatch by `assay_kind` | `assay/cells.py`, `tests/test_assay_cells.py` | `suite_from_meta(meta)` reads `meta.get("assay_kind", "coding")`. The `"coding"` branch is unchanged. The `"swebench"` branch reconstructs a `swebench_suite` from the `.cases.json` sidecar (written by 144a gap #7). No confirmatory-script edits — 144a owns the writer. Substrate-ui's assay pane then works for SWE-bench cells (currently crashes). |

### Group C — Statistical apparatus

| # | Sprint | Files | Concept |
|---|---|---|---|
| 150 | Tango 1998 / Nam 1997 score-TOST | `assay/stats.py`, `tests/test_assay_stats.py` | Implement the score-TOST for matched-pair proportion difference from the primary references. `equivalence_verdict_score_tost(...)` alongside the existing `equivalence_verdict` (which becomes `method="percentile-ci"` fallback for the trivial cases where they agree). `build_report` gains a `method` parameter defaulting to `"score-tost"`. Existing coding tests still pass by explicitly passing `method="percentile-ci"`. **Degenerate case:** zero discordant pairs (arm perfectly matches control on every case — the "good" outcome) makes the restricted MLE divide by zero. Fall back to `INCONCLUSIVE` with a `zero_discordant` note, mirroring the current bootstrap's zero-width-CI fallback at stats.py:172-177. Test that specific case. |
| 151 | Pre-registration gate | `assay/preregistration.py` (new), `scripts/assay_swebench_confirmatory.py`, `tests/test_assay_preregistration.py` | Runner reads a committed `.preg.json` (schema follows `docs/benchmarking-preregistration-template.md` — primary_metric, δ, k, arms_hash, bank_hash, comparator, timestamp). Hashes it. Refuses to write cells unless the sidecar's `arms_hash` matches the arms the current run builds AND the committed timestamp is before the first cell's write. `provenance_status` at cells.py:79-105 stays as the post-hoc verification. **`arms_hash` canonical form:** `sha256_hex(canonical_bytes(sorted list of {name, role, models, n, max_rounds} for each arm))[:12]` — the same JCS pipeline `_fingerprint(cfg)` already uses. Consolidate the two into one helper (`arms_fingerprint(arms)`) invoked by both the runtime construction and the pre-reg validator; do not carry a second parallel hash. **`comparator` block:** the schema REQUIRES a `comparator: {source, split, model, resolve_rate}` object (e.g. `{"source": "Agentless + GPT-4o (Xia et al. 2024)", "split": "SWE-bench Lite", "model": "gpt-4o-2024-08-06", "resolve_rate": 0.278}`). No comparator, no run — a confirmatory number without a public anchor is unreadable. |

### Group D — Repro fix

| # | Sprint | Files | Concept |
|---|---|---|---|
| 155 | Base-fails-first repro check | `topologies/swebench_solver/repro_base_validate.py` (new producer), `topologies/swebench_solver/assemble.py` (wiring), `tests/test_swebench_repro_base_validate.py` | Add a new producer `repro_base_validate` triggered on `ReproductionTest`. It runs the repro ONCE on unmodified `base_checkout` via the `runner` already in `solver_topology_from_payload` scope; if the repro says RESOLVED on base (or otherwise trivially passes), it emits a `ReproductionTest(code="")` overwrite — the existing "empty code" convention (records.py:82-88 already documents `""` as "generation failed → SELECT falls back to regression-only") absorbs the "dropped" state with no vocab change. `select_exec._select_exec_factory` at assemble.py:80-83 already reads the latest `ReproductionTest.code` from the `reproduction` view — the empty-string overwrite propagates naturally. **NOT a ≤2-file sprint:** three files (new producer + assemble wiring + tests). Original round-2 scoping was wrong; not proposing a vocab change (empty-string reuse means no `vocabulary_change_required` halt). Same discipline as the `passed_at_base` filter already applies at select_exec.py:79-100. |

C.2 (`resolved_in_fallback` flag) stays dropped: `select.py:57-61` already stamps `regression=none-passed-fallback` in `SelectedPatch.reason` when `reg_ok` was empty. Readers can already see when repro was the deciding signal in the fallback case.

### Group E — Ablation-ready mechanisms

| # | Sprint | Files | Concept |
|---|---|---|---|
| 157 | Element-level localizer + heterogeneous ensemble Responder | `topologies/swebench_solver/localize_elements.py` (new), `adapters/ensemble.py` (new), tests for each | Two independent additions bundled because both are additive and enable Sprint 159. **Element-level**: emit `SuspectElements` from Python AST on `base_checkout` for the localized files, so `edit_context` can be trimmed to class/function granularity (Agentless-style). **Ensemble**: `EnsembleResponder(models: list[str])` routes each slot's `arespond`/`arespond_metered` to a distinct model id, replacing round-robin diversity. R-19-verified thinking trio (kimi-k2.6, glm-5.1, nemotron-3-super) is the named default. |
| 158 | Repro 2×2 agreement in the report | `assay/report.py`, `scripts/assay_swebench_confirmatory.py`, `tests/test_assay_report.py` | Uses existing `TestResults.reproduction` (`records.py:99-107`) + `CaseResult.result.passed` (`run.py:71`) — no vocab change. Confirmatory entrypoint projects `TestResults.reproduction` for the selected slot into each cell row. `build_report` aggregates the **full 2×2** as `ArmReport.repro_2x2: dict[str, int]` with keys `resolved_and_passed`, `resolved_and_failed`, `reproduced_and_passed`, `reproduced_and_failed` (`other` outcomes excluded — they carry no repro signal). Derived on the report: `ArmReport.repro_kappa: float \| None` (Cohen's κ over the 2×2 with the `other` cases excluded), plus `ArmReport.repro_agreement_rate: float \| None` for continuity but computed as the sum of the diagonal over the sum of all four cells. **Why 2×2, not one-sided:** a repro that unconditionally says RESOLVED trivially maximizes a positive-agreement-only rate. κ (or the full 2×2) is the number that can actually justify "repro as tiebreak" (per swebench-solver-design.md §5). |
| 159 | Arm matrix + matched compute | `assay/swebench_matrix.py`, `assay/report.py`, `scripts/assay_swebench_confirmatory.py` | **Five arms** — the four below plus a compute-matched baseline: `single_draft_baseline` (n=1, one model, no correction), `n_drafts_no_correction` (N=3, one model, `max_rounds=1`), `n_drafts_repair` (N=3, one model, present today), `n_drafts_repair_ensemble` (N=3, three thinking models, correction on), and `baseline_matched_compute` (single strong model at K attempts where K is the median `model_calls` per case of `n_drafts_repair_ensemble`, oracle-picked best-of-K over the SELECT logic). **Efficiency frontier:** `build_report` gains `ArmReport.resolve_per_call: float \| None = passes / model_calls` (secondary endpoint, per Kapoor & Narayanan 2024's "unaccounted compute" critique). Sprint 160's writeup plots per-arm resolve vs per-arm model_calls — the frontier tells you whether the ensemble is winning by mechanism or by compute. Confirmatory entrypoint runs 5 arms × 300 instances × 3 trials. |

### Group F — The confirmatory run

Sprint 160 is the point of everything above: land a publishable confirmatory number on SWE-bench Lite that
replaces the 108/291 exploratory result. All the runtime-side prerequisites (146a/150/151/152/155/157/158/159)
have landed; execution needs the Architect's box (Docker + Ollama + swebench eval images) and a decision on
models. Split into four sub-sprints because the matched-compute arm's `K` is data-driven — the confirmatory
run is genuinely two passes, and pretending otherwise (fixing K a priori) forfeits the whole point of the
compute-matched baseline (Kapoor & Narayanan 2024).

| # | Sprint | Files | Concept |
|---|---|---|---|
| 160-plan | Wire matrix mode + draft pre-reg + stage the run | `scripts/assay_swebench_confirmatory.py` (matrix mode), `docs/preregistrations/2026-08-swebench-lite.preg.json` (new), this file (Sprint 160 execution plan) | Runner grows `SWEBENCH_ARMS` env var accepting `solver` (default, one arm — pre-160 behaviour), `pass1` (ensemble arm only — used to observe K), or `matrix` (all 5 arms). Pre-reg template drafted with placeholders the Architect fills before Pass 1 (comparator, models, margin, k_calls=`<TBD Pass-1>`). Compute estimates + arm-cost table in this doc. |
| 160-pass1 | Determine K from the ensemble median | invocation on Architect's box | **Prerequisite** (once per box): `uv sync --extra swebench` installs `datasets` + `swebench`. Neither is a runtime dep of the kernel; both are hard-imported by the confirmatory + host scripts. Before the extra existed (pre-2026-08-08) this was tribal knowledge that stranded the script on any fresh checkout. Then: `SWEBENCH_ARMS=pass1` + `SWEBENCH_ENSEMBLE=<a>,<b>,<c>` + `SWEBENCH_TRIALS=3` + `SWEBENCH_LIMIT=0`. Run. Compute `K = median(model_calls per case)` from the resulting cells JSONL. Fill the pre-reg's `k_calls` with K. Estimated wall: ~20-30 hours at CONCURRENCY=8. |
| 160-pass2 | Confirmatory 5-arm matrix run | invocation | Freeze the pre-reg (commit hash timestamps strictly before invocation). Set `SWEBENCH_ARMS=matrix` + `SWEBENCH_PREG=docs/preregistrations/2026-08-swebench-lite.preg.json`. Runner reads K from the pre-reg. Runs 5 arms × 300 instances × 3 trials = 4,500 cells. Estimated wall: ~60-120 hours at CONCURRENCY=8, dominated by the two ensemble/matched-compute arms; the single-draft baselines are ~1h each; salvage-mode resume tolerates crashes/reboots. |
| 160-writeup | Report + BLACKBOARD close | `process/BLACKBOARD.md`, `process/assay_confirmatory_swebench_lite_2026-08/README.md` (new) | Writeup obligations, ordered: (1) name the comparator resolve rate FIRST — "vs Agentless + GPT-4o = 27.8% on SWE-bench Lite (Xia et al. 2024)"; (2) per-arm resolve rate with bootstrap CI + score-TOST verdict + BH-FDR flag; (3) per-arm `model_calls` and `resolve_per_call`, plus the efficiency-frontier plot (arm-vs-arm on the passes-vs-calls axes); (4) `grader_error_band` on every headline resolve number (`108 ± 0.078·108 ≈ 108 ± 8` for Lite); (5) `repro_kappa` + the full 2×2 counts (not just an agreement rate). Every number labelled with `(model_ensemble_id, split_id)`. |

**Arm-cost table (per-case, order-of-magnitude for planning):**

| Arm | Model calls/case | Docker/case | Wall/case (concurrent) |
|---|---|---|---|
| `single_draft_baseline` | 1 (localize) + 1 (draft) = 2 | 1 apply + 1 grade | ~3-5 min |
| `n_drafts_no_correction` | 1 + 3 = 4 | 3 apply + 3 select_exec + 1 grade | ~5-10 min |
| `n_drafts_repair` | 1 + ≤6 = ≤7 | ≤6 apply + ≤3 select_exec + 1 grade | ~8-15 min |
| `n_drafts_repair_ensemble` | 1 + ≤6 = ≤7 | same as n_drafts_repair | ~8-15 min |
| `baseline_matched_compute` (K=6) | 1 + K = ~7 | K apply + K select_exec + 1 grade | ~10-15 min |

At 300 instances × 3 trials × 5 arms = 4,500 cells averaging ~10 min each at CONCURRENCY=8, wall
≈ 4,500 × 10 / 8 / 60 ≈ 94 hours. Salvage-mode + checkpointing lets this run in overnight chunks
over ~5 nights, resumable across reboots.

**Architect decisions before Pass 1:**

- **`SWEBENCH_MODELS` for the ensemble arm** — three heterogeneous thinking models per KIT_DIARY R-19
  (kimi-k2.6, glm-5.1, nemotron-3-super named as the R-19-verified trio; adjust to what's available).
- **Single-strong model for the baselines** — one model used across `single_draft_baseline`,
  `n_drafts_no_correction`, `n_drafts_repair`, `baseline_matched_compute` (typically the strongest of
  the ensemble triplet).
- **Comparator** — Agentless + GPT-4o at 27.8% on Lite (Xia et al. 2024) is the roadmap default; an
  Architect who has a more current SoTA can substitute.
- **Trials per cell** — 3 (roadmap default). Lower would degrade the bootstrap CI; higher raises wall
  linearly with limited variance-reduction return.
- **CONCURRENCY** — default 8; raise if the Architect's box handles it, but note Docker + Ollama
  contention past ~12 tends to increase variance more than throughput.

### Group G — Substrate-ui companions

| # | Sprint | Files | Concept |
|---|---|---|---|
| U-0 | SWE-bench cells fixture | `substrate-ui/gen_swebench_fixture.py` (new) or append to `substrate-ui/gen_demo_records.py` | Mirror the coding-side fixtures at `gen_demo_records.py:124-200`: emit a minimal `swebench_smoke.jsonl` + `swebench_smoke.meta.json` + `swebench_smoke.cases.json` so U-1's tests have something to render against. |
| U-1 | SWE-bench-shaped assays render correctly | `substrate-ui/server.py`, `substrate-ui/web/app.js`, `substrate-ui/tests/test_server.py` | `_assays_index` (server.py:374-398) reads `meta.get("assay_kind")` and includes it in the rail card. `renderAssayFrom` (app.js:159-212) renders coding-specific keys only when `assay_kind == "coding"`; renders SWE-bench-specific keys (`arms`, `dataset`) when `assay_kind == "swebench"`. Prov panel's "comparing ways to write code" becomes assay-kind-aware. Depends on Sprint 152 + U-0. |
| U-2 | New headline fields | `substrate-ui/web/app.js`, `substrate-ui/tests/test_server.py` | Render `ArmReport.repro_agreement_rate` (from Sprint 158), `Result.grader_error_band` on the headline resolve number (from Sprint 153), `(model_ensemble_id, split_id)` qualifiers on the delta (from Sprint 154). Fields render only when present; coding assays render nothing. |

## Dependency graph

```
147 148 149 153 154  ─── LANDED
                     │
                     ├── 144a ─┐
                     ├── 146a  │
                     │         │
                     │         ├── 152 ──┬── U-0 ── U-1
                     │         ├── 151   │
                     │         ├── 150 ──┤
                     │         ├── 155   │
                     │         ├── 157 ──┤
                     │         │         │
                     │         │         ├── 158 ── U-2
                     │         │         └── 159 ── 160
```

Correctness gates (144a, 146a) first — nothing runs on the confirmatory path safely until they land. Then 150 + 151 + 152 in parallel. Then 155 + 157. Then 158 + 159. Then 160. Substrate-ui sprints alongside their dependencies.

## What round 3 changes from round 2

- **Ten sprints in the remaining plan, not fifteen.** Round-2 double-counted a "repro queue-jump" removal (`select.py` doesn't have a queue-jump — verified against `test_swebench_select.py:27-32`). Round-3 also verified my sprint 144 has real parity gaps with `bench_coding.py` that a code read caught immediately, so Sprint 144a is added.
- **Sprint 156 stays dropped.** `select.py:57-61` already stamps `regression=none-passed-fallback` in the reason string when the fallback fired; the concern C.2 targeted is already legible from the record.
- **Sprint B-1 (`RepairSummary.repro_agreed_with_grade`) stays dropped.** Sprint 158 uses existing `TestResults.reproduction` + `CaseResult.result.passed` — no vocab change needed. The vocab-halt ceremony round-2 proposed was unnecessary work.
- **Substrate-ui sprints are pinned to specific server.py + app.js line ranges** rather than described abstractly.
- **Sprint 150 clarified.** `scripts/power_sim.py` uses the existing bootstrap; it does NOT contain the score-TOST. The "Monte-Carlo validated to 1e-9" round-2 doc mentioned is external. Sprint 150 implements Tango/Nam from primary references.

## Round-3 review folds (2026-08-08, adversarial subagent)

Six material findings + four polish items landed:

- **Sprint 144a gained gaps #7 (`.cases.json` writer) and #8 (`estimated` field aggregation).** Sprint 152 was depending on a sidecar nobody wrote and the stats layer was blind to whether `ModelUsage` counts were provider-truth or stand-ins.
- **Sprint 151 names the canonical `arms_hash` form** (`sha256_hex(canonical_bytes(sorted list of {name, role, models, n, max_rounds}))[:12]` — consolidated with `_fingerprint(cfg)` as `arms_fingerprint(arms)`) and now requires a `comparator: {source, split, model, resolve_rate}` block in the pre-reg schema. No comparator, no run.
- **Sprint 155 rescoped to three files** (new `repro_base_validate` producer + `assemble.py` wiring + tests) after the ≤2-file scoping was found impossible: `reproduction.py` has no `TestRunner`, and doing the check in `select_exec.run_one` pays Docker cost N times per instance for a once-per-instance question. Uses the existing empty-`code` convention to signal "dropped" — no vocab halt.
- **Sprint 158 changed from one-sided rate to full 2×2 + κ.** A repro that unconditionally says RESOLVED trivially maximizes a positive-agreement-only rate.
- **Sprint 159 grew a fifth arm** (`baseline_matched_compute` — the strong single model at K attempts where K matches the ensemble's median `model_calls`) and adds `ArmReport.resolve_per_call` as a secondary endpoint. Sprint 160's writeup plots the efficiency frontier so "ensemble beats baseline" can't be published as an uncontrolled-for-compute finding (per Kapoor & Narayanan 2024).
- **Sprint 160 requires a SoTA anchor** as the first line of the writeup — no more publishing a number with no comparator. `SWEBENCH_MODELS` default `llama3.2:1b` will be replaced with a no-default requirement so a run against a 1B model can't accidentally be the headline.
- **Sprint 150 specifies the zero-discordant fallback** (INCONCLUSIVE with `zero_discordant` note, mirroring the current bootstrap's zero-width-CI fallback).
- **LANDED-table line numbers corrected** — 7 producer-flip lines and Result/ArmReport lines verified against HEAD.
- **`oracle.py:44-51` docstring citation fixed** — 7.8% attributes to Xia & Chen 2025 (arxiv 2503.15223), NOT SWE-Bench+ (Aleithan et al. 2024, which reports ~30% on a different axis).

## Deletion policy for this chain

Superseded runners get deleted; run artifacts stay. Every deletion carries a KIT_DIARY entry naming the last-live sha and the sprint that superseded it. This is the corrected reading of hard rule 12 for tooling-vs-evidence: the audit trail is the run's evidence and the KIT_DIARY entry, not the tool that produced the evidence.

---

*Roadmap round-3 authored 2026-08-08 after a full code read (kernel + record + projections + conformance + adapters + coding_flow + code_review + applications + best_of_n + SWE-bench solver + SWE-bench assay + substrate-ui + vocab locks + kernel v15 + product draft7). Groups 1 and 3 landed. Owner: whichever agent picks up the next `## Surfaced for review` entry from the Architect.*
