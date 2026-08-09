"""The confirmatory SWE-bench runner — parity with `scripts/bench_coding.py`.

Sprint 144 replaced `scripts/assay_full_run.py` (deleted); Sprint 144a brings this runner to
`bench_coding.py` parity so the confirmatory path is actually usable for the arm matrix + trials
Sprint 159 will drive. Every solve goes through `run_arm_on_case`; every cell lands as one JSONL
row alongside a self-describing `.meta.json` + `.cases.json` sidecar.

Eight parity gaps closed against `bench_coding.py`:

    (1) Async concurrency  — `asyncio.Semaphore(CONCURRENCY)` + `asyncio.gather` across cells.
    (2) Per-cell timeout    — `asyncio.wait_for(..., timeout=RUN_TIMEOUT)`; a wedged Docker cannot
                              stall the sweep.
    (3) Salvage mode        — `SWEBENCH_SALVAGE=<dir>` regrades finished records without model
                              calls; a re-run only spends models on cells never reached.
    (4) Refuse mixed configs — on resume, the JSONL is rejected if any prior row's `config_fp`
                              differs from the current — no silent mixing of configs in one file.
    (5) Flat meta.json shape — `{"config_fp": ..., "run_id": ..., **cfg}` at top level (NOT
                              nested under "config"), so `provenance_status` at cells.py:79-105
                              recomputes the fingerprint from the right dict and returns
                              `verified`, not `tampered`.
    (6) `msgspec.to_builtins(report)` — the report is a frozen `@dataclass`; `.__dict__` does
                              not recurse into the tuple of `ArmReport`. Use the proper serializer.
    (7) `.cases.json` sidecar — an array of `{case_id, instance_id, repo, base_commit, image,
                              regression_files, exclude, passed_at_base}` written next to the cells
                              file, so Sprint 152's `report_from_cells` SWE-bench branch can
                              reconstruct a `swebench_suite` without re-cloning every case. Written
                              BEFORE the sweep so a mid-run abort still leaves it on disk.
    (8) `UsageTotals.estimated` aggregated — `_sum_usage` (run.py:48-58) already sums it; the
                              cell row carries it so the stats layer can distinguish provider-truth
                              from word-count stand-ins.

Env (all optional; defaults are a smoke slice — the real confirmatory run sets non-default
`SWEBENCH_MODELS`, `SWEBENCH_LIMIT=300`, and `SWEBENCH_TRIALS=3` per Sprint 160):

    SWEBENCH_MODELS       comma-sep model ids (default: "llama3.2:1b" — Sprint 160 will require
                          this to be explicitly set; the 1B default reports near-zero on Lite and
                          is misleading as a confirmatory headline)
    SWEBENCH_N            best-of-N drafters per case (default: 3)
    SWEBENCH_LIMIT        cap instance count (default: 3 — smoke slice; use 0 for the full split)
    SWEBENCH_TRIALS       trials per (arm, case) (default: 1 — real trials land in Sprint 159)
    SWEBENCH_CONCURRENCY  concurrent cells (default: 4; SWE-bench cells are Docker-heavy)
    SWEBENCH_ROLE         arm role: baseline | ablation | full (default: "full")
    SWEBENCH_ARM_NAME     arm name written to cells (default: "swebench_solver")
    SWEBENCH_CELLS        cells JSONL path (default: "process/assay_smoke/swebench_cells.jsonl")
    SWEBENCH_SCRATCH      per-cell record roots (default: "process/assay_smoke/records/")
    SWEBENCH_DATASET      HuggingFace dataset (default: "princeton-nlp/SWE-bench_Lite")
    SWEBENCH_SPLIT        dataset split (default: "test")
    SWEBENCH_MARGIN       pre-registered equivalence margin (default: 0.10; frozen in Sprint 160)
    SWEBENCH_CONTROL      control arm name for delta framing (default: same as SWEBENCH_ARM_NAME)
    SWEBENCH_RUN_TIMEOUT  per-cell wall-clock timeout in seconds (default: 1800)
    SWEBENCH_SALVAGE      salvage directory — regrade finished records without model calls
    SWEBENCH_ARMS         which arm set to build (default: "solver" — one arm, pre-160 behaviour;
                          "pass1" — ensemble only, used to observe K for matched compute;
                          "matrix" — all 5 arms of the Sprint 160 confirmatory matrix)
    SWEBENCH_ENSEMBLE     comma-sep model ids for the ensemble arm (default: empty — required by
                          "pass1" and "matrix"; single_draft/no_correction/repair/matched arms
                          use SWEBENCH_MODELS[0] as the single strong model)
    SWEBENCH_K            K value for baseline_matched_compute (default: read from .preg.json
                          under the matrix mode; required for "matrix" without a pre-reg)

Usage:

    uv run python scripts/assay_swebench_confirmatory.py            # run/continue
    uv run python scripts/assay_swebench_confirmatory.py report     # rebuild from cells

Env-gated: needs git + Docker + the swebench eval images pullable; a real Ollama endpoint for the
listed models (or a deterministic responder for smoke).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import msgspec
from datasets import load_dataset

from substrate import api
from substrate.assay import run_arm_on_case
from substrate.assay.cells import report_from_cells
from substrate.assay.preregistration import (
    fingerprint as _fingerprint_shared,
    guard as preregistration_guard,
)
from substrate.assay.run import UsageTotals, project_reproduction_for_selected
from substrate.assay.suite import Arm, Case
from substrate.assay.swebench_matrix import (
    baseline_matched_compute_arm,
    n_drafts_no_correction_arm,
    n_drafts_repair_ensemble_arm,
    repair_arm,
    single_draft_baseline_arm,
)
from substrate.assay.swebench_suite import (
    prepare_swebench_case,
    swebench_solver_arm,
    swebench_suite,
)

MODELS = os.environ.get("SWEBENCH_MODELS", "llama3.2:1b").split(",")
N = int(os.environ.get("SWEBENCH_N", "3"))
LIMIT = int(os.environ.get("SWEBENCH_LIMIT", "3"))
TRIALS = int(os.environ.get("SWEBENCH_TRIALS", "1"))
CONCURRENCY = int(os.environ.get("SWEBENCH_CONCURRENCY", "4"))
ROLE = os.environ.get("SWEBENCH_ROLE", "full")
ARM_NAME = os.environ.get("SWEBENCH_ARM_NAME", "swebench_solver")
CELLS = Path(os.environ.get("SWEBENCH_CELLS", "process/assay_smoke/swebench_cells.jsonl"))
SCRATCH = Path(os.environ.get("SWEBENCH_SCRATCH", "process/assay_smoke/records"))
DATASET = os.environ.get("SWEBENCH_DATASET", "princeton-nlp/SWE-bench_Verified")
SPLIT = os.environ.get("SWEBENCH_SPLIT", "test")
MARGIN = float(os.environ.get("SWEBENCH_MARGIN", "0.10"))
CONTROL = os.environ.get("SWEBENCH_CONTROL", ARM_NAME)
RUN_TIMEOUT = float(os.environ.get("SWEBENCH_RUN_TIMEOUT", "1800"))
SALVAGE = os.environ.get("SWEBENCH_SALVAGE", "")
PREG = os.environ.get("SWEBENCH_PREG", "")  # sprint 151: pre-registration gate (path to .preg.json)
ARMS_MODE = os.environ.get("SWEBENCH_ARMS", "solver")  # sprint 160-plan: solver | pass1 | matrix
ENSEMBLE = [m.strip() for m in os.environ.get("SWEBENCH_ENSEMBLE", "").split(",") if m.strip()]
K_CALLS = int(os.environ.get("SWEBENCH_K", "0"))  # 0 = read from .preg.json when in matrix mode
# F4 fix (review 2026-08-08): K parallel reproduction samples per instance. 1 = pre-F4 behaviour
# (one repro per candidate); >1 = combine K runner scripts into one Docker invocation, majority-
# vote at the marker level. Sprint 160-pass2 should set this to 3.
REPRO_K = int(os.environ.get("SWEBENCH_REPRO_K", "1"))

_ZERO = UsageTotals(0, 0, 0, 0, False)
_RUN_ID = ""  # set in main(); stamped on every cell for provenance
_CONFIG_FP = ""  # config fingerprint; the resume guard refuses to mix configs in one file


def _config() -> dict[str, object]:
    """The full parameterization behind this run so the cells JSONL is self-describing.
    `assay_kind` is the dispatch key Sprint 152's `suite_from_meta` reads."""
    return {
        "models": MODELS,
        "n": N,
        "limit": LIMIT,
        "trials": TRIALS,
        "role": ROLE,
        "arm_name": ARM_NAME,
        "dataset": DATASET,
        "split": SPLIT,
        "margin": MARGIN,
        "control_arm": CONTROL,
        "run_timeout": RUN_TIMEOUT,
        "assay_kind": "swebench",  # Sprint 152 dispatch
    }


# sprint 151 review fold (finding 151-#2): consolidated onto substrate.assay.preregistration.fingerprint
# so this script's config fingerprint and the pre-reg gate hash the same bytes. Prior local
# implementation was byte-identical but two copies is where the divergence risk lived.
_fingerprint = _fingerprint_shared


def _load_rows() -> dict[tuple[str, str, int], dict[str, object]]:
    rows: dict[tuple[str, str, int], dict[str, object]] = {}
    if CELLS.exists():
        for line in CELLS.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                rows[(str(r["arm"]), str(r["case_id"]), int(r["trial"]))] = r
    return rows


def _row(
    arm: Arm,
    case: Case,
    trial: int,
    passed: bool,
    source: str,
    u: UsageTotals,
    elapsed: int,
    root: str,
    detail: str = "",
    reproduction: str = "",
    recall_at_k: float | None = None,
    full_recall_at_k: bool | None = None,
) -> dict[str, object]:
    # measured=source=="run" gates null vs measured fields (bench_coding.py:101-131 shape):
    # a salvage/fail cell made NO calls this run, so its compute fields are null (not measured 0).
    # Only freshly-run, metered cells carry real tokens/calls/ms/estimated.
    measured = source == "run"
    return {
        "arm": arm.name,
        "role": arm.role,
        "case_id": case.case_id,
        "trial": trial,
        "passed": passed,
        "source": source,
        "detail": detail,
        "elapsed_ms": elapsed if measured else None,
        "root": root,
        "config_fp": _CONFIG_FP,
        "run_id": _RUN_ID,
        "prompt_tokens": u.prompt_tokens if measured else None,
        "completion_tokens": u.completion_tokens if measured else None,
        "inference_ms": u.inference_ms if measured else None,
        "model_calls": u.model_calls if measured else None,
        "estimated": u.estimated,  # Gap 8: provider-truth vs word-count stand-in
        # Sprint 158: reproduction verdict for the winning slot, projected off the record by
        # run_arm_on_case via project_reproduction_for_selected. Enables report.py's 2x2 + κ
        # aggregation to read the per-cell repro state from cells.jsonl without re-parsing the
        # record. Empty for salvage/fail cells (no CaseResult was produced this run).
        "reproduction": reproduction,
        # F2 fix (review 2026-08-08): localization recall from the oracle. Persists to cells.jsonl
        # so `report_from_cells` reconstructs the ArmReport's mean_recall_at_k / full_recall_at_k_rate
        # without re-reading the record. Null when the oracle didn't emit them (coding assays,
        # SWE-bench runs without SuspectFiles).
        "recall_at_k": recall_at_k,
        "full_recall_at_k": full_recall_at_k,
    }


def _write_cases_sidecar(cases: list[tuple[Case, dict[str, object]]]) -> None:
    """Gap 7 — write `.cases.json` next to the cells JSONL, so Sprint 152's SWE-bench branch of
    `report_from_cells` can reconstruct a `swebench_suite` without re-cloning every case.

    Written BEFORE the sweep so an aborted mid-run still leaves the sidecar on disk. The subset
    below is what Sprint 152 needs: `case_id` + `instance_id` to reconstruct Case objects for the
    Suite, plus the `PreparedPayload` fields that let a re-run reconstruct the runner + planner
    without re-doing the base clone.
    """
    path = CELLS.parent / f"{CELLS.stem}.cases.json"
    payload = [
        {
            "case_id": case.case_id,
            "instance_id": str(inst["instance_id"]),
            "repo": inst.get("repo"),
            "base_commit": inst.get("base_commit"),
            "version": inst.get("version"),
            # PreparedPayload subset — spec is coming from swebench.MAP_REPO_VERSION_TO_SPECS at
            # arm-build time (so a re-run doesn't need it inline); regression_files + exclude +
            # passed_at_base + image are the load-bearing pieces the planner reconstructs from.
            "image": case.payload["image"],
            "regression_files": case.payload["regression_files"],
            "exclude": case.payload["exclude"],
            "passed_at_base": case.payload["passed_at_base"],
        }
        for case, inst in cases
    ]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _print_report() -> int:
    """Rebuild a Report from the cells JSONL — no model calls, just the aggregator.

    NOTE: today `report_from_cells` at `assay/cells.py:65-76` is coding-only (hardcodes
    `coding_problem_bank()` + `coding_suite()`). It WILL crash on a SWE-bench cells file until
    Sprint 152's `assay_kind` dispatch lands. This function is here so it's ready when 152 does.
    """
    if not CELLS.exists():
        print(f"no cells at {CELLS}", flush=True)
        return 64
    report, meta = report_from_cells(CELLS)
    # Gap 6: proper serialization for a frozen @dataclass Report with nested ArmReport tuples;
    # `.__dict__` does NOT recurse. msgspec.to_builtins handles the whole tree.
    print(
        json.dumps(
            {"report": msgspec.to_builtins(report), "meta": meta},
            indent=2,
            default=str,
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _build_arms_for_mode() -> tuple[list[Arm], dict[str, dict[str, object]], str]:
    """Sprint 160-plan: dispatch on SWEBENCH_ARMS to build the arm set + the per-arm params dict
    the pre-reg gate compares against. Returns (arms, params_by_arm, control_arm_name).

    - "solver" (default, pre-160): one arm via `swebench_solver_arm` — backward compat for any
      caller that used the runner before the matrix wiring.
    - "pass1" (Sprint 160-pass1): the ensemble arm only. Used to observe K = median model_calls
      per case before the confirmatory matrix run.
    - "matrix" (Sprint 160-pass2): all five arms. Requires SWEBENCH_ENSEMBLE for the ensemble
      arm and either SWEBENCH_K or a .preg.json carrying `k_calls` for the matched-compute arm.
    """
    strong = MODELS[0]  # single strong model for the non-ensemble arms
    if ARMS_MODE == "solver":
        arm = swebench_solver_arm(name=ARM_NAME, role=ROLE, models=MODELS, n=N)
        return [arm], {ARM_NAME: {"models": MODELS, "n": N, "max_rounds": 2}}, CONTROL

    if ARMS_MODE == "pass1":
        if not ENSEMBLE:
            raise SystemExit(
                "SWEBENCH_ARMS=pass1 requires SWEBENCH_ENSEMBLE=<comma-sep models> — the arm "
                "under measurement is the ensemble, and observing K needs its real model_calls."
            )
        ens = n_drafts_repair_ensemble_arm("n_drafts_repair_ensemble", models=ENSEMBLE)
        return (
            [ens],
            {"n_drafts_repair_ensemble": {"models": ENSEMBLE, "n": len(ENSEMBLE), "max_rounds": 2}},
            "n_drafts_repair_ensemble",
        )

    if ARMS_MODE == "matrix":
        if not ENSEMBLE:
            raise SystemExit("SWEBENCH_ARMS=matrix requires SWEBENCH_ENSEMBLE=<comma-sep models>.")
        if K_CALLS <= 0:
            raise SystemExit(
                "SWEBENCH_ARMS=matrix requires SWEBENCH_K=<int from pass1 median> (or a "
                "pre-reg carrying k_calls in its arm params; the runner reads K from env first)."
            )
        arms = [
            single_draft_baseline_arm("single_draft_baseline", model=strong, repro_k=REPRO_K),
            n_drafts_no_correction_arm(
                "n_drafts_no_correction", model=strong, n=N, repro_k=REPRO_K
            ),
            repair_arm(
                "n_drafts_repair", role="full", model=strong, n=N, max_rounds=2, repro_k=REPRO_K
            ),
            n_drafts_repair_ensemble_arm(
                "n_drafts_repair_ensemble", models=ENSEMBLE, repro_k=REPRO_K
            ),
            baseline_matched_compute_arm(
                "baseline_matched_compute", model=strong, k_calls=K_CALLS, repro_k=REPRO_K
            ),
        ]
        params: dict[str, dict[str, object]] = {
            "single_draft_baseline": {"models": [strong], "n": 1, "max_rounds": 1},
            "n_drafts_no_correction": {"models": [strong], "n": N, "max_rounds": 1},
            "n_drafts_repair": {"models": [strong], "n": N, "max_rounds": 2},
            "n_drafts_repair_ensemble": {
                "models": ENSEMBLE,
                "n": len(ENSEMBLE),
                "max_rounds": 2,
            },
            "baseline_matched_compute": {"models": [strong], "n": K_CALLS, "max_rounds": 1},
        }
        # The pre-registered control for the matrix is single_draft_baseline (the floor) —
        # every other arm's delta reads as "beats the floor by X." Overridable via SWEBENCH_CONTROL.
        control = CONTROL if CONTROL != ARM_NAME else "single_draft_baseline"
        return arms, params, control

    raise SystemExit(
        f"SWEBENCH_ARMS={ARMS_MODE!r} unknown — must be one of solver | pass1 | matrix"
    )


async def _run() -> int:
    global _CONFIG_FP, _RUN_ID
    _RUN_ID = f"run-{int(time.time())}"
    # Sprint 155 review-fold nit A3: mkdir AFTER the pre-reg gate so a PREG failure genuinely
    # leaves zero disk artifacts (originally the mkdirs fired first — the gate exited cleanly
    # but left empty directories behind).

    # Sprint 151 (review-fold finding 151-#3): the pre-registration gate runs FIRST, before any
    # disk writes — the fingerprint, the meta.json, the sidecar, the sweep. On failure nothing
    # leaks to disk; on success cfg carries the comparator and the fingerprint reflects the full
    # committed shape (no post-gate re-fingerprint that would leave rows loaded under the OLD fp
    # and mismatch Gap 4's mixed-config guard). params_by_arm threads (models, n, max_rounds) into
    # the arms_hash so a same-name reroll trips the gate (finding 151-#1).
    arms, params_by_arm, control = _build_arms_for_mode()
    cfg = _config()
    cfg["arms_mode"] = ARMS_MODE
    cfg["ensemble"] = ENSEMBLE
    cfg["k_calls"] = K_CALLS
    cfg["control_arm"] = control
    if PREG:
        pre = preregistration_guard(PREG, arms, params_by_arm=params_by_arm)
        cfg["preregistration"] = {"path": pre.path, "arms_hash": pre.arms_hash}
        cfg["comparator"] = dict(pre.comparator)
        print(
            f"pre-registration verified: {pre.path} arms_hash={pre.arms_hash} "
            f"comparator={pre.comparator['source']}={pre.comparator['resolve_rate']}",
            flush=True,
        )
    print(
        f"arms_mode={ARMS_MODE} arms=[{', '.join(a.name for a in arms)}] control={control}",
        flush=True,
    )

    _CONFIG_FP = _fingerprint(cfg)
    CELLS.parent.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    done = _load_rows()

    # Gap 4: refuse to splice cells from a DIFFERENT config into one results file. Rows without
    # a fingerprint (a pre-parity run) are tolerated as legacy data. Runs AFTER the pre-reg gate
    # so the fingerprint compared is the final one (comparator merged), never the intermediate.
    foreign = {str(r.get("config_fp")) for r in done.values() if r.get("config_fp")} - {_CONFIG_FP}
    if foreign:
        raise SystemExit(
            f"{CELLS} holds cells from config(s) {foreign}, current is {_CONFIG_FP}. "
            "Use a fresh SWEBENCH_CELLS (or delete it) — refusing to mix configs in one file."
        )

    # Gap 5: FLAT meta shape — matches bench_coding.py:232-235 so `provenance_status` at
    # cells.py:94-98 recomputes the fingerprint over the same dict shape (config keys top-level,
    # not nested under a "config" wrapper). Written ONCE, after the gate.
    (CELLS.parent / f"{CELLS.stem}.meta.json").write_text(
        json.dumps({"config_fp": _CONFIG_FP, "run_id": _RUN_ID, **cfg}, indent=2, sort_keys=True)
    )

    ds = list(load_dataset(DATASET, split=SPLIT))
    if LIMIT:
        ds = ds[:LIMIT]
    print(f"loaded {len(ds)} instances from {DATASET}:{SPLIT}", flush=True)

    # The Adapter door — every instance goes through prepare_swebench_case; a firewall failure is
    # excluded and logged, never silently admitted. `prepare_swebench_case` runs one Docker call
    # per instance to compute passed_at_base + a git clone. Both are IO-bound (Docker image pull
    # bandwidth + git clone bandwidth), so a serial for-loop leaves the machine idle. Parallelise
    # across CONCURRENCY workers via asyncio.to_thread; the Docker daemon and git handle
    # concurrent pulls fine. 300 instances at CONCURRENCY=8 finishes in ~15-30 min instead of
    # ~5-10 hours (KIT_DIARY-worthy: the pre-fix serial loop was the projection-blower on this
    # confirmatory).
    # 2026-08-09 halt-on-error rewrite: prep failures propagate. Any prep exception (a Docker
    # pull error, a git-clone error, a firewall violation) kills the whole prep with the
    # instance_id in the traceback. Verified is human-audited clean, so the firewall check is
    # not the pre-filter it was on Lite — a real firewall violation on Verified is a data bug
    # in the benchmark and deserves to halt.
    print(f"preparing {len(ds)} cases at CONCURRENCY={CONCURRENCY}...", flush=True)
    prep_sem = asyncio.Semaphore(CONCURRENCY)
    prep_progress = {"done": 0}
    prep_lock = asyncio.Lock()

    async def _prep_one(inst: dict[str, Any]) -> tuple[Case, dict[str, object]]:
        async with prep_sem:
            case = await asyncio.to_thread(prepare_swebench_case, inst)
            async with prep_lock:
                prep_progress["done"] += 1
                if prep_progress["done"] % 20 == 0 or prep_progress["done"] == len(ds):
                    print(f"[{prep_progress['done']}/{len(ds)}] prepared", flush=True)
            return case, inst

    prepped = await asyncio.gather(*(_prep_one(inst) for inst in ds))
    cases: list[tuple[Case, dict[str, object]]] = list(prepped)
    print(f"prepared {len(cases)} cases", flush=True)

    # Gap 7: write the sidecar BEFORE the sweep so a mid-run abort still leaves the .cases.json
    # on disk for Sprint 152's report path.
    _write_cases_sidecar(cases)

    suite = swebench_suite(
        cases=[c for c, _ in cases],
        arms=arms,
        report_root=str(SCRATCH / "grade"),
        dataset_name=DATASET,
        control_arm=control,
        equivalence_margin=MARGIN,
        pass_k=1,
    )

    # Sprint 160-plan: the sweep fans over ARMS × cases × trials. Pre-160 (solver mode) this was
    # over one arm; matrix mode now grows the fanout by the arm count without any other structural
    # change (the same salvage / timeout / row-write shape applies per cell).
    todo = [
        (a, case, t)
        for a in arms
        for case, _ in cases
        for t in range(TRIALS)
        if (a.name, case.case_id, t) not in done
    ]
    total = len(arms) * len(cases) * TRIALS
    print(
        f"todo: {len(todo)} of {total} total cells across {len(arms)} arm(s) "
        f"(already done: {len(done)}; concurrency={CONCURRENCY}, timeout={RUN_TIMEOUT}s, "
        f"salvage={'on' if SALVAGE else 'off'})",
        flush=True,
    )

    sem = asyncio.Semaphore(CONCURRENCY)  # Gap 1
    lock = asyncio.Lock()
    started = time.monotonic()
    progress = {"n": 0}

    async def cell(arm: Arm, case: Case, trial: int) -> None:
        async with sem:
            # Gap 3: salvage — regrade an existing record without new model calls. The record
            # already carries every SelectedPatch/RepairSummary the oracle needs; we just re-run
            # the grade side.
            salv: Path | None = (
                Path(SALVAGE) / f"{arm.name}__{case.case_id}__t{trial}" if SALVAGE else None
            )
            if salv is not None and salv.exists():
                # 2026-08-09 halt-on-error rewrite: salvage failure propagates. A record that
                # can't be re-read + re-graded is a real bug in the record layer or the oracle,
                # not something to silently row-as-fail.
                events: list[Any] = list(api.read_record(salv))
                grade = suite.oracle.grade(events, case.ground_truth)
                row = _row(
                    arm,
                    case,
                    trial,
                    grade.passed,
                    "salvage",
                    _ZERO,
                    0,
                    str(salv),
                    grade.detail,
                    project_reproduction_for_selected(events),
                    grade.recall_at_k,
                    grade.full_recall_at_k,
                )
            else:
                root = SCRATCH / f"{arm.name}__{case.case_id}__t{trial}"
                # 2026-08-09 halt-on-error rewrite: no cell-level exception swallow. A run
                # exception (model failure, Docker failure, timeout) propagates through
                # asyncio.gather, cancels the other in-flight cells, and halts the sweep with
                # the traceback. That is the honest signal — better than a "fail" cell that
                # aggregates into a bogus resolve rate. Timeout also propagates as TimeoutError.
                cr = await asyncio.wait_for(
                    run_arm_on_case(arm, case, suite.oracle, root, trial=trial),
                    timeout=RUN_TIMEOUT,
                )
                row = _row(
                    arm,
                    case,
                    trial,
                    cr.result.passed,
                    "run",
                    cr.usage,
                    cr.elapsed_ms,
                    cr.root,
                    cr.result.detail,
                    cr.reproduction,
                    cr.result.recall_at_k,
                    cr.result.full_recall_at_k,
                )
            async with lock:
                with CELLS.open("a") as fh:
                    fh.write(json.dumps(row) + "\n")
                progress["n"] += 1
                if progress["n"] % 5 == 0 or progress["n"] == len(todo):
                    rate = progress["n"] / max(1e-9, time.monotonic() - started)
                    eta = (len(todo) - progress["n"]) / max(1e-9, rate)
                    print(
                        f"  {progress['n']}/{len(todo)}  ({rate * 60:.1f}/min, "
                        f"~{eta / 60:.1f} min left)",
                        flush=True,
                    )

    if todo:
        await asyncio.gather(*(cell(a, c, t) for a, c, t in todo))

    elapsed = int(time.monotonic() - started)
    print(
        f"\ndone: {progress['n']} new cells, {elapsed}s this session, config_fp={_CONFIG_FP}",
        flush=True,
    )
    print(f"cells: {CELLS}", flush=True)
    print(
        "run `uv run python scripts/assay_swebench_confirmatory.py report` for the aggregated Report",
        flush=True,
    )
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        return _print_report()
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
