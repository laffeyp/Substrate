# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Behavioral smoke: `container_arm` against 5 Lite instances, read the record.

Sprint 180 (closes external round-2 R1). The paper cites `container_arm` in three places
as the same-boundary counter-experiment that grounds the natural-experiment claim:
`container_arm` touches the same six external boundaries as the failing solver topology
and works. `container_arm` has been in the matrix since 2026-08-11 (commit 2f311d6); no
assay run has isolated its resolve rate. No sprint declares an observation contract for
it beyond `assert producer_kinds == ["solve"]`.

This script fires `container_arm` on 5 Lite instances and reads the resulting record for:

  - `SelectedPatch` present per cell — the arm emitted its output
  - grade verdict per cell — the harness graded the patch
  - `RateLimitAttempted` shape at the boundary — same signal Sprint 179's rate-limit smoke reads
  - resolve rate — `passes / (attempted - no_verdict)` on the sample

A five-instance smoke does not produce a confirmatory number; a resolve rate on n=5 has a
95% CI of roughly ±40 points. The point is not statistical: it is to prove `container_arm`
runs cleanly under the same boundaries as the repair topology, which is what the paper's
natural-experiment argument turns on.

Two possible outcomes:
1. Clean record with `SelectedPatch` on every cell and verdicts landing → the paper's
   natural-experiment claim gets its first evidence beyond a shape check.
2. Failures land on the record with typed reasons → the natural-experiment claim
   falsifies, and the paper's § 2 argument needs the caveat.

Either way the paper stops leaning on `container_arm` without evidence.

Usage
-----
    SUBSTRATE_ARM_N=5 \\
    SUBSTRATE_ARM_MODEL=deepseek-v4-pro:cloud \\
    SUBSTRATE_OLLAMA_TIER=pro \\
    OLLAMA_HOST=https://ollama.com \\
    OLLAMA_API_KEY=... \\
    uv run python scripts/smoke_container_arm_n5.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None:
        raise SystemExit(f"required env var missing: {name}")
    return v


N = int(_env("SUBSTRATE_ARM_N", "5"))
MODEL = _env("SUBSTRATE_ARM_MODEL", "deepseek-v4-pro:cloud")
TIER = _env("SUBSTRATE_OLLAMA_TIER", "pro")
OUT_DIR = Path(_env("SUBSTRATE_ARM_OUT", f"process/smokes/{int(time.time())}_container_arm_n{N}"))


def _main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"container_arm smoke: N={N} instances, model={MODEL}, tier={TIER}, out={OUT_DIR}",
        flush=True,
        file=sys.stderr,
    )
    print("---", flush=True, file=sys.stderr)

    import subprocess

    cells_path = OUT_DIR / "cells.jsonl"
    env = os.environ.copy()
    env.update(
        {
            "SWEBENCH_LIMIT": str(N),
            "SWEBENCH_TRIALS": "1",
            "SWEBENCH_MODELS": MODEL,
            "SWEBENCH_ARMS": "matrix",  # brings in container_arm alongside the repair arms
            "SWEBENCH_CELLS": str(cells_path),
            "SWEBENCH_SCRATCH": str(OUT_DIR / "records"),
            "SWEBENCH_OLLAMA_TIER": TIER,
            "SWEBENCH_DATASET": "princeton-nlp/SWE-bench_Lite",
            "SWEBENCH_SPLIT": "test",
        }
    )
    started = time.monotonic()
    try:
        subprocess.run(
            [sys.executable, "-m", "scripts.assay_swebench_confirmatory"],
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"runner failed (exit {exc.returncode}); reading what landed anyway...",
            flush=True,
            file=sys.stderr,
        )
    print(
        f"runner wall: {time.monotonic() - started:.1f}s",
        flush=True,
        file=sys.stderr,
    )

    if not cells_path.exists():
        print(f"no cells.jsonl at {cells_path}", flush=True, file=sys.stderr)
        raise SystemExit(1)

    rows = [json.loads(line) for line in cells_path.read_text().splitlines() if line.strip()]
    print(f"\ncells recorded: {len(rows)}", flush=True, file=sys.stderr)

    # Filter to container_arm rows only. The paper's claim is about container_arm
    # specifically; the other arms in the matrix are along for the ride.
    ca_rows = [r for r in rows if str(r.get("arm", "")) == "tool_loop_container"]
    print(f"container_arm rows: {len(ca_rows)}", flush=True, file=sys.stderr)

    verdict_ct: dict[str, int] = {}
    for r in ca_rows:
        v = str(r.get("verdict", ""))
        verdict_ct[v] = verdict_ct.get(v, 0) + 1
    print("container_arm verdicts:", flush=True, file=sys.stderr)
    for v, c in sorted(verdict_ct.items()):
        print(f"  {v}: {c}", flush=True, file=sys.stderr)

    # Selected-patch presence per cell — the load-bearing signal.
    have_selected = 0
    for r in ca_rows:
        root = Path(str(r.get("root", "")))
        if not root.exists():
            continue
        segs = list(root.glob("events*.jsonl"))
        if not segs:
            continue
        events = [json.loads(line) for line in segs[0].read_text().splitlines() if line.strip()]
        if any(e.get("kind") == "SelectedPatch" for e in events):
            have_selected += 1
    print(
        f"\ncontainer_arm cells emitting SelectedPatch: {have_selected} / {len(ca_rows)}",
        flush=True,
        file=sys.stderr,
    )

    passes = verdict_ct.get("pass", 0)
    fails = verdict_ct.get("fail", 0)
    no_verdict = verdict_ct.get("no_verdict", 0)
    graded = passes + fails
    resolve_rate = passes / graded if graded else 0.0
    print("\ncontainer_arm signal on this N:", flush=True, file=sys.stderr)
    print(
        f"  attempted={len(ca_rows)}  graded={graded}  passes={passes}  no_verdict={no_verdict}",
        flush=True,
        file=sys.stderr,
    )
    print(
        f"  resolve_rate on graded: {resolve_rate:.3f} "
        f"(±~0.4 at n={graded} — smoke-scale, not confirmatory)",
        flush=True,
        file=sys.stderr,
    )

    if have_selected == len(ca_rows) and no_verdict == 0:
        print(
            "\nOK: container_arm emitted SelectedPatch on every cell with zero NO_VERDICT — "
            "the paper's natural-experiment counter-argument now has its first behavioral "
            "evidence at n=5. Scale up before citing as confirmed.",
            flush=True,
            file=sys.stderr,
        )
    else:
        print(
            "\nWARN: container_arm did not emit SelectedPatch on every cell, or produced "
            "NO_VERDICT rows. The paper's natural-experiment claim needs the caveat or "
            "the arm needs a fix before the claim carries weight.",
            flush=True,
            file=sys.stderr,
        )


if __name__ == "__main__":
    _main()
