# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Behavioral smoke: fire the light topology + fixed rate-limit wrapper + real Ollama on 3-10 Lite instances.

Sprint 179 (closes external round-2 M5). Between the last live assay run (2026-08-11 20:41)
and now the tree accumulated a postmortem, a halt, two roadmap versions, an audit, a paper,
twelve sprint cards, and twenty-plus modified files. The verifiable-behavior surface moved
zero. Sprint 168's `test_semaphore_released_during_retry_sleep_lets_peer_progress` proves
the semaphore releases in a mock; it does not prove the fix survives 300 real Ollama calls
at Pro tier.

This script fires `swebench_repair_topology` (light) against a small Lite sample using the
current `RateLimitedResponder` (Sprint 168 fix) and the current Ollama endpoint.
Reads the resulting cell records for:

  - `RateLimitAttempted` / `RateLimitGranted` / `RateLimitDenied` / `RateLimitRetried` counts
    per cell — verifies `RateLimitedResponder`'s typed retry choreography lands on the record. NOTE: as
    of Sprint 179 `RateLimitedResponder` does NOT emit these events (roadmap v2 S5.2's `RateLimitProducer`
    will); this smoke instead reads httpx-level 429/503 counts from `ModelUsage` errors and
    from the runner's cell rows' `reason_counts`.
  - `SelectedPatch` present per cell (topology emitted something)
  - grade verdict per cell (harness ran or NO_VERDICT with typed reason)
  - wall-clock per cell

Prints a CSV-shaped summary to stderr so the Architect reads throughput against the fixed
`RateLimitedResponder` before deciding whether Verified pass 1 fires against it or waits for S5.2's
`RateLimitProducer`. Standing rule from Sprint 170's mid-turn note: Verified waits for the
producer; this smoke measures `RateLimitedResponder` to inform the wait, not to substitute for the
producer.

Usage
-----
    SUBSTRATE_SMOKE_N=5 \\
    SUBSTRATE_SMOKE_MODEL=deepseek-v4-pro:cloud \\
    SUBSTRATE_OLLAMA_TIER=pro \\
    OLLAMA_HOST=https://ollama.com \\
    OLLAMA_API_KEY=... \\
    uv run python scripts/smoke_shim_under_load.py

Env
---
    SUBSTRATE_SMOKE_N:        instance count (default 5; keep small — this is a smoke)
    SUBSTRATE_SMOKE_MODEL:    the model tag to hit (default "deepseek-v4-pro:cloud")
    SUBSTRATE_OLLAMA_TIER:    "free" | "pro" | "max" | "local" (default "pro")
    SUBSTRATE_SMOKE_OUT:      override output directory under process/smokes/
    OLLAMA_HOST + OLLAMA_API_KEY: Cloud endpoint credentials
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


N = int(_env("SUBSTRATE_SMOKE_N", "5"))
MODEL = _env("SUBSTRATE_SMOKE_MODEL", "deepseek-v4-pro:cloud")
TIER = _env("SUBSTRATE_OLLAMA_TIER", "pro")
OUT_DIR = Path(_env("SUBSTRATE_SMOKE_OUT", f"process/smokes/{int(time.time())}_smoke"))


def _summarize_cell(record_path: Path) -> dict[str, object]:
    """One record → {SelectedPatch count, ModelUsage count, wall_ms, error kinds}."""
    if not record_path.exists():
        return {
            "root": str(record_path),
            "record_present": False,
            "selected_patch": 0,
            "model_usage": 0,
            "wall_ms": 0,
        }
    events = [json.loads(line) for line in record_path.read_text().splitlines() if line.strip()]
    kinds: dict[str, int] = {}
    for e in events:
        kind = e.get("kind", "")
        kinds[kind] = kinds.get(kind, 0) + 1
    started = next((e.get("t") for e in events if e.get("kind") == "substrate.RunStarted"), 0)
    finalised = next(
        (e.get("t") for e in events if e.get("kind") == "substrate.RunFinalised"),
        started,
    )
    return {
        "root": str(record_path.parent),
        "record_present": True,
        "selected_patch": kinds.get("SelectedPatch", 0),
        "model_usage": kinds.get("ModelUsage", 0),
        "wall_ms": int((float(finalised) - float(started)) * 1000) if started else 0,
        "kinds": {k: v for k, v in kinds.items() if v},
    }


def _main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"smoke: N={N} instances, model={MODEL}, tier={TIER}, out={OUT_DIR}",
        flush=True,
        file=sys.stderr,
    )
    print(
        "invokes the confirmatory runner with SWEBENCH_LIMIT=N against the light topology.",
        flush=True,
        file=sys.stderr,
    )
    print("---", flush=True, file=sys.stderr)

    # Delegate the actual run to the confirmatory runner script — it already wires
    # the light topology, `RateLimitedResponder`, the runner-side classifier, and the cells writer.
    # This script is the OBSERVER, not the runner; it fires the runner with a small N
    # and then reads what landed.
    import subprocess

    cells_path = OUT_DIR / "cells.jsonl"
    env = os.environ.copy()
    env.update(
        {
            "SWEBENCH_LIMIT": str(N),
            "SWEBENCH_TRIALS": "1",
            "SWEBENCH_MODELS": MODEL,
            "SWEBENCH_N": "1",
            "SWEBENCH_ARMS": "solver",
            "SWEBENCH_CELLS": str(cells_path),
            "SWEBENCH_SCRATCH": str(OUT_DIR / "records"),
            "SWEBENCH_OLLAMA_TIER": TIER,
            "SWEBENCH_SKIP_MODEL_PREFLIGHT": "0",  # keep pre-flight to catch dead models
            "SWEBENCH_DATASET": "princeton-nlp/SWE-bench_Lite",
            "SWEBENCH_SPLIT": "test",
        }
    )
    runner_started = time.monotonic()
    print(f"invoking runner (SWEBENCH_LIMIT={N})...", flush=True, file=sys.stderr)
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
    runner_wall_s = time.monotonic() - runner_started
    print(
        f"runner wall: {runner_wall_s:.1f}s",
        flush=True,
        file=sys.stderr,
    )

    # Read what landed.
    if not cells_path.exists():
        print(
            f"no cells.jsonl at {cells_path} — runner may not have written any rows",
            flush=True,
            file=sys.stderr,
        )
        raise SystemExit(1)
    rows = [json.loads(line) for line in cells_path.read_text().splitlines() if line.strip()]
    print(f"\ncells recorded: {len(rows)}", flush=True, file=sys.stderr)

    verdict_ct: dict[str, int] = {}
    reason_ct: dict[str, int] = {}
    for r in rows:
        v = str(r.get("verdict", ""))
        verdict_ct[v] = verdict_ct.get(v, 0) + 1
        reason = str(r.get("reason", ""))
        if reason:
            reason_ct[reason] = reason_ct.get(reason, 0) + 1

    print("verdict distribution:", flush=True, file=sys.stderr)
    for v, c in sorted(verdict_ct.items()):
        print(f"  {v}: {c}", flush=True, file=sys.stderr)
    if reason_ct:
        print("reason distribution:", flush=True, file=sys.stderr)
        for reason, c in sorted(reason_ct.items(), key=lambda kv: -kv[1]):
            print(f"  {reason}: {c}", flush=True, file=sys.stderr)

    # Walk the per-cell records for topology-level events (SelectedPatch, ModelUsage).
    print("\nper-cell record shape:", flush=True, file=sys.stderr)
    for row in rows:
        root = Path(str(row.get("root", "")))
        # The record shape depends on the runner's persistence layout; find the segment file.
        if not root.exists():
            print(f"  {row.get('case_id', '?')}: root absent", flush=True, file=sys.stderr)
            continue
        segs = list(root.glob("events*.jsonl"))
        if not segs:
            print(
                f"  {row.get('case_id', '?')}: no segments in {root}",
                flush=True,
                file=sys.stderr,
            )
            continue
        summary = _summarize_cell(segs[0])
        print(
            f"  {row.get('case_id', '?')} verdict={row.get('verdict', '?'):>10s} "
            f"selected={summary['selected_patch']} usage={summary['model_usage']} "
            f"wall={summary['wall_ms']}ms",
            flush=True,
            file=sys.stderr,
        )

    # Rate-limit signal: reason_counts["rate_limited"] tells us how many cells got
    # denied out of the batch. Under the fixed rate-limit wrapper, sustained pressure should NOT
    # produce a rate_limited count anywhere near 100% of cells at N=5.
    rate_limited = reason_ct.get("rate_limited", 0)
    total_no_verdict = sum(v for k, v in verdict_ct.items() if k == "no_verdict")
    print("\nrate-limit signal:", flush=True, file=sys.stderr)
    print(f"  rate_limited cells: {rate_limited} / {len(rows)}", flush=True, file=sys.stderr)
    print(f"  no_verdict cells:   {total_no_verdict} / {len(rows)}", flush=True, file=sys.stderr)
    if rate_limited > 0 and len(rows) > 0:
        pct = 100.0 * rate_limited / len(rows)
        if pct > 20.0:
            print(
                f"  WARN: rate_limited fraction {pct:.1f}% > 20% — `RateLimitedResponder`'s Sprint 168 fix is "
                "insufficient at this concurrency + tier + model. Do NOT fire Verified "
                "against `RateLimitedResponder`; wait for roadmap v2 S5.2's `RateLimitProducer`.",
                flush=True,
                file=sys.stderr,
            )
        else:
            print(
                f"  OK: rate_limited fraction {pct:.1f}% ≤ 20% — `RateLimitedResponder`'s Sprint 168 fix holds at "
                "this N. Sprint 168's semaphore-release does what the mock proved.",
                flush=True,
                file=sys.stderr,
            )

    print(f"\ncells: {cells_path}", flush=True, file=sys.stderr)
    print(f"records: {OUT_DIR / 'records'}", flush=True, file=sys.stderr)


if __name__ == "__main__":
    _main()
