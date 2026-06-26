"""The firewalled coding A/B — concurrent, RESUMABLE, trial-powered. The legible run, made robust.

CONTROL = a strong single model (the bar to erode; defaults to the 480B cloud coder). Arms ablate
orchestration over weaker/free LOCAL models: single weak / weak ensemble no-correction / full ensemble +
correction. The agent iterates on the DEV tests; the oracle grades on disjoint HELD-OUT tests (the
firewall). Headline = the TOST equivalence verdict on `full` vs the strong control at a MEANINGFUL
margin (±0.10). Output quality only; tokens/time are measurements, never money.

Robustness (the lesson from the all-or-nothing first run):
  - INCREMENTAL: every cell's outcome is appended to BENCH_CELLS (a JSONL) the moment it finishes, so a
    kill/crash/interrupt never loses completed work.
  - RESUMABLE: on start, cells already in the JSONL are skipped — re-running continues, never restarts.
  - SALVAGE: BENCH_SALVAGE=<old scratch dir> re-grades finished records from disk (NO model calls — just
    the held-out gate), so a re-run only spends models on cells never reached.
  - TIMEOUT: each cell is bounded by BENCH_RUN_TIMEOUT (a hung model/gate can't stall the sweep).
  - The report is built from the JSONL, so `… report` rebuilds it from whatever has completed, anytime.

    BENCH_TRIALS=10 uv run python scripts/bench_coding.py            # run/continue the sweep
    uv run python scripts/bench_coding.py report                     # rebuild the report from the JSONL

Env: BENCH_STRONG, BENCH_WEAK (comma-sep), BENCH_TRIALS, BENCH_CONCURRENCY, BENCH_MARGIN, BENCH_LIMIT,
BENCH_CELLS, BENCH_SALVAGE, BENCH_SCRATCH, BENCH_RUN_TIMEOUT.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from substrate import api
from substrate.assay import build_report, run_arm_on_case
from substrate.assay.coding import coding_suite
from substrate.assay.coding_problems import coding_problem_bank
from substrate.assay.oracle import EXTERNAL_GRADER, Result
from substrate.assay.run import CaseResult, UsageTotals
from substrate.assay.suite import Arm, Case, Suite

STRONG_MODEL = os.environ.get("BENCH_STRONG", "qwen3-coder:480b-cloud")
WEAK_MODELS = os.environ.get("BENCH_WEAK", "llama3:8b,qwen2.5:7b-instruct").split(",")
TRIALS = int(os.environ.get("BENCH_TRIALS", "10"))
CONCURRENCY = int(os.environ.get("BENCH_CONCURRENCY", "8"))
MARGIN = float(os.environ.get("BENCH_MARGIN", "0.10"))
RUN_TIMEOUT = float(os.environ.get("BENCH_RUN_TIMEOUT", "240"))
CELLS = Path(os.environ.get("BENCH_CELLS", "process/bench_results/coding_cells.jsonl"))
SALVAGE = os.environ.get("BENCH_SALVAGE", "")


def _suite() -> Suite:
    problems = coding_problem_bank()
    limit = os.environ.get("BENCH_LIMIT")
    if limit:
        problems = problems[: int(limit)]
    return coding_suite(
        problems, strong_model=STRONG_MODEL, weak_models=WEAK_MODELS, equivalence_margin=MARGIN, pass_k=1
    )


def _load_rows() -> dict[tuple[str, str, int], dict[str, object]]:
    rows: dict[tuple[str, str, int], dict[str, object]] = {}
    if CELLS.exists():
        for line in CELLS.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                rows[(r["arm"], r["case_id"], int(r["trial"]))] = r
    return rows


def _row(arm: Arm, case: Case, trial: int, passed: bool, source: str, u: UsageTotals, elapsed: int, root: str) -> dict[str, object]:
    return {
        "arm": arm.name, "role": arm.role, "case_id": case.case_id, "trial": trial,
        "passed": passed, "source": source, "elapsed_ms": elapsed, "root": root,
        "prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens,
        "inference_ms": u.inference_ms, "model_calls": u.model_calls, "estimated": u.estimated,
    }


def _to_caseresult(r: dict[str, object]) -> CaseResult:
    p = bool(r["passed"])
    return CaseResult(
        arm=str(r["arm"]), role=str(r["role"]), case_id=str(r["case_id"]), trial=int(r["trial"]),  # type: ignore[arg-type]
        result=Result(passed=p, score=1.0 if p else 0.0, metric="resolved-held-out",
                      oracle_class=EXTERNAL_GRADER, replayable=False, detail=str(r.get("source", ""))),
        usage=UsageTotals(prompt_tokens=int(r.get("prompt_tokens", 0)), completion_tokens=int(r.get("completion_tokens", 0)),  # type: ignore[arg-type]
                          inference_ms=int(r.get("inference_ms", 0)), model_calls=int(r.get("model_calls", 0)), estimated=bool(r.get("estimated", False))),  # type: ignore[arg-type]
        elapsed_ms=int(r.get("elapsed_ms", 0)), root=str(r.get("root", "")),  # type: ignore[arg-type]
    )


_ZERO = UsageTotals(0, 0, 0, 0, False)


def _print_report(suite: Suite) -> None:
    rows = _load_rows()
    report = build_report(suite, [_to_caseresult(r) for r in rows.values()])
    n_run = sum(1 for r in rows.values() if r.get("source") == "run")
    n_salv = sum(1 for r in rows.values() if r.get("source") == "salvage")
    n_fail = sum(1 for r in rows.values() if r.get("source") == "fail")
    trials = (max((int(r["trial"]) for r in rows.values()), default=0) + 1) if rows else 0
    print(f"\n=== {report.suite}  primary={report.primary_metric}  control={report.control_arm} ===")
    print(f"cells: {len(rows)} ({n_run} run, {n_salv} salvaged, {n_fail} failed/timeout)  "
          f"control-ran: {report.control_check.state}  margin=±{MARGIN}  trials={trials}")
    print(f"  TWO CURRENCIES, never spliced: reliable = pass^{trials} (a problem counts only if ALL "
          f"{trials} trials pass); per-trial = pass@1 (mean attempt). flake = per-trial − reliable.")
    for a in report.arms:
        flake = a.pass_at_1 - a.pass_rate
        line = (f"  {a.arm:22s} reliable {a.passes}/{a.n_cases}={a.pass_rate:.3f}  "
                f"per-trial={a.pass_at_1:.3f}  flake={flake:+.3f}")
        if a.delta_vs_control is not None:  # harsher, same currency as the count
            line += f"  | Δreliable={a.delta_vs_control:+.3f}"
            if a.p_value is not None:
                line += f"(McNemar p={a.p_value:.3f})"
        if a.delta_pass_k is not None:
            line += (f"  | Δpass@1={a.delta_pass_k:+.3f} CI95=[{a.ci_low:+.3f},{a.ci_high:+.3f}]"
                     f" margin-verdict={a.equivalence} fdr={a.fdr_significant}")
        print(line)
    print(f"\nread it honestly: 'reliable' (pass^{trials}) and 'per-trial' (pass@1) are DIFFERENT "
          "statistics — quote ONE. 'margin-verdict' is the TOST at ±margin: 'significantly worse' "
          "(CI excludes 0) is NOT 'inferior' (CI clears -margin). A large `flake` means the arm "
          "solves sometimes but not reliably — the gap pass@1 hides.")


async def main() -> None:
    suite = _suite()
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        _print_report(suite)
        return

    CELLS.parent.mkdir(parents=True, exist_ok=True)
    done = _load_rows()
    todo = [
        (arm, case, t)
        for arm in suite.arms
        for case in suite.cases
        for t in range(TRIALS)
        if (arm.name, case.case_id, t) not in done
    ]
    total = len(suite.arms) * len(suite.cases) * TRIALS
    print(f"firewalled coding A/B: {len(suite.cases)} problems x {len(suite.arms)} arms x {TRIALS} trials "
          f"= {total} cells; {len(done)} already done, {len(todo)} to go (concurrency={CONCURRENCY}, "
          f"margin=±{MARGIN}, salvage={'on' if SALVAGE else 'off'})", flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    base = Path(os.environ.get("BENCH_SCRATCH", "/tmp")) / f"bench_{int(time.time())}"
    base.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    progress = {"n": 0}

    async def cell(arm: Arm, case: Case, trial: int) -> None:
        async with sem:
            salv = Path(SALVAGE) / f"{arm.name}__{case.case_id}__t{trial}" if SALVAGE else None
            if salv is not None and (salv / "manifest.json").exists():
                try:
                    passed = await asyncio.to_thread(
                        lambda: suite.oracle.grade(list(api.read_record(salv)), case.ground_truth).passed
                    )
                    row = _row(arm, case, trial, passed, "salvage", _ZERO, 0, str(salv))
                except Exception:
                    row = _row(arm, case, trial, False, "fail", _ZERO, 0, str(salv))
            else:
                root = base / f"{arm.name}__{case.case_id}__t{trial}"
                try:
                    r = await asyncio.wait_for(
                        run_arm_on_case(arm, case, suite.oracle, root, trial=trial), timeout=RUN_TIMEOUT
                    )
                    row = _row(arm, case, trial, r.result.passed, "run", r.usage, r.elapsed_ms, r.root)
                except Exception:
                    row = _row(arm, case, trial, False, "fail", _ZERO, int(RUN_TIMEOUT * 1000), str(root))
            async with lock:
                with CELLS.open("a") as fh:
                    fh.write(json.dumps(row) + "\n")
                progress["n"] += 1
                if progress["n"] % 25 == 0 or progress["n"] == len(todo):
                    rate = progress["n"] / max(1e-9, time.monotonic() - started)
                    eta = (len(todo) - progress["n"]) / max(1e-9, rate)
                    print(f"  ... {progress['n']}/{len(todo)}  ({rate * 60:.0f}/min, ~{eta / 60:.1f} min left)", flush=True)

    await asyncio.gather(*(cell(a, c, t) for a, c, t in todo))
    _print_report(suite)


if __name__ == "__main__":
    asyncio.run(main())
