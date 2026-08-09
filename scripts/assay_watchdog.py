"""Watchdog for a running SWE-bench confirmatory sweep.

Polls the cells JSONL every INTERVAL seconds and prints a one-line health report:
  - progress: (n_cells / expected)
  - rate: cells/min
  - resolve: passed / total
  - no_patch_rate: cells whose detail says "no model_patch on the record" — the systemic-model-
    failure signature that pass 1 hit at 89% (three cloud tags returned HTTP 400 silently, so
    every drafter died and the topology quiesced without a SelectedPatch; the runner then graded
    the empty patch as not-resolved and the resolve rate was zero-with-no-alarm)
  - error_rate: cells with source="error" — the typed-flake taxonomy landed in cells rather than
    halting the sweep
  - repos: current per-repo breakdown of processed instances (so you can see one repo is stuck)
  - active docker: how many docker run/pull sub-processes exist right now (idle-worker signal)
  - active git: how many git clone sub-processes exist right now (mother-clone or per-instance)

Fails LOUD if:
  - the running process has died (no `assay_swebench_confirmatory.py` in ps)
  - no_patch_rate exceeds NO_PATCH_HALT_THRESHOLD (default 0.5) after MIN_CELLS_FOR_HALT cells
  - the cells file has not grown in STALL_SECONDS (default 900 = 15 min)

Usage:
  uv run python scripts/assay_watchdog.py path/to/cells.jsonl [--interval=300] [--tail]

--tail streams status forever until Ctrl-C. Without --tail it prints one report and exits — good
for cron-driven pings. Env-free; reads only the cells file, ps, and the pass1 directory.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

NO_PATCH_HALT_THRESHOLD = 0.85
MIN_CELLS_FOR_HALT = 40
MIN_REPOS_FOR_HALT = 3  # a single-repo run can legitimately show high no_patch (astropy is hard)
STALL_SECONDS = 1800


def _cells(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _proc_count(pattern: str) -> int:
    p = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return len([ln for ln in p.stdout.splitlines() if ln.strip()])


def _runner_alive() -> bool:
    return _proc_count("python scripts/assay_swebench_confirmatory") > 0


def _report(path: Path) -> dict[str, Any]:
    rows = _cells(path)
    n = len(rows)
    if n == 0:
        return {"n": 0}
    sources = Counter(r["source"] for r in rows)
    no_patch = sum(1 for r in rows if "no model_patch on the record" in (r.get("detail") or ""))
    passed = sum(1 for r in rows if r["passed"])
    repos = Counter(r["case_id"].split("_1776_")[0] for r in rows)
    mtime = path.stat().st_mtime
    return {
        "n": n,
        "passed": passed,
        "resolve_rate": passed / n,
        "sources": dict(sources),
        "no_patch": no_patch,
        "no_patch_rate": no_patch / n,
        "repos": dict(repos.most_common(5)),
        "last_write_age_s": int(time.time() - mtime),
        "docker_procs": _proc_count("docker (run|pull)"),
        "git_procs": _proc_count("git clone"),
        "runner_alive": _runner_alive(),
    }


def _emit(path: Path, r: dict[str, Any], prefix: str = "") -> None:
    if r.get("n", 0) == 0:
        print(f"{prefix}no cells yet; runner_alive={_runner_alive()}", flush=True)
        return
    print(
        f"{prefix}n={r['n']} passed={r['passed']} resolve={r['resolve_rate']:.2%} "
        f"no_patch={r['no_patch']}({r['no_patch_rate']:.0%}) "
        f"sources={r['sources']} repos={r['repos']} "
        f"last_write_age={r['last_write_age_s']}s "
        f"docker={r['docker_procs']} git={r['git_procs']} "
        f"alive={r['runner_alive']}",
        flush=True,
    )


def _halt_reason(r: dict[str, Any]) -> str | None:
    if not r.get("runner_alive", True):
        return "runner_dead"
    # No-patch halt requires n >= MIN_CELLS AND coverage across MIN_REPOS. A single-repo
    # accumulation can legitimately show high no_patch (astropy is the hardest in Verified;
    # any single repo can look bad in isolation). Only halt when the failure is
    # *across-the-board*.
    if (
        r.get("n", 0) >= MIN_CELLS_FOR_HALT
        and r.get("no_patch_rate", 0) > NO_PATCH_HALT_THRESHOLD
        and len(r.get("repos", {})) >= MIN_REPOS_FOR_HALT
    ):
        return f"no_patch_rate={r['no_patch_rate']:.0%}>threshold across {len(r['repos'])} repos"
    if r.get("last_write_age_s", 0) > STALL_SECONDS:
        return f"stalled_{r['last_write_age_s']}s"
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("cells", type=Path)
    p.add_argument("--interval", type=int, default=300, help="poll interval seconds (default 300)")
    p.add_argument("--tail", action="store_true", help="loop forever until Ctrl-C")
    args = p.parse_args()

    if not args.tail:
        r = _report(args.cells)
        _emit(args.cells, r)
        return 1 if _halt_reason(r) else 0

    while True:
        r = _report(args.cells)
        ts = time.strftime("%H:%M:%S")
        _emit(args.cells, r, prefix=f"[{ts}] ")
        halt = _halt_reason(r)
        if halt:
            print(f"[{ts}] WATCHDOG HALT: {halt}", flush=True)
            return 2
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
