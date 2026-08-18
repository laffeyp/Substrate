"""Summarize a wire-check cells JSONL against the S9 observation contract.

Usage:
    uv run python scripts/summarize_wire_check.py <cells.jsonl>

Reads the cells JSONL a confirmatory-runner sweep wrote and reports the four numeric
checks the roadmap v2 § "Sprint 9" observation contract names:

    1. Total cells present / expected (N=300 for Lite, N=500 for Verified).
    2. Verdict distribution: pass / fail / no_verdict; reason_counts across no_verdict rows.
    3. Source distribution: run / salvage / error.
    4. Per-repo cell count + wall-clock spread (the interleaving check — no repo should
       dominate a batch).
    5. Elapsed statistics: min / p50 / p95 / max per-cell wall (seconds).
    6. Model-call statistics: min / p50 / p95 / max per-cell prompt+completion tokens.

The observation contract's boundary-event checks (`RateLimitDenied` count per cell,
`ContainerKilled` count = 0, sustained rate-limit bound) require reading the per-cell
records, not the cells JSONL alone; a follow-on script `summarize_wire_check_boundaries.py`
will read the records for those. The cells file is the fast summary.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


def _p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    i = int(0.95 * (len(xs) - 1))
    return xs[i]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: summarize_wire_check.py <cells.jsonl>", file=sys.stderr)
        return 64
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 64
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        print("cells.jsonl is empty", file=sys.stderr)
        return 65

    print(f"# {path}\n")
    print(f"cells: {len(rows)}\n")

    verdicts = Counter(str(r.get("verdict", "")) for r in rows)
    print("## verdicts")
    for v, n in sorted(verdicts.items()):
        print(f"  {v:12s}  {n:5d}  ({100 * n / len(rows):5.1f}%)")
    print()

    sources = Counter(str(r.get("source", "")) for r in rows)
    print("## sources")
    for s, n in sorted(sources.items()):
        print(f"  {s:12s}  {n:5d}  ({100 * n / len(rows):5.1f}%)")
    print()

    reasons = Counter(str(r.get("reason", "")) for r in rows if r.get("verdict") == "no_verdict")
    if reasons:
        print("## no_verdict reasons")
        for reason, n in sorted(reasons.items()):
            print(f"  {reason:24s}  {n:5d}")
        print()

    by_repo: dict[str, list[dict[str, object]]] = defaultdict(list)
    for r in rows:
        # case_id shape: "<repo>_1776_<slug>" (safe_case_id encoding).
        cid = str(r.get("case_id", ""))
        repo = cid.split("_1776_", 1)[0] if "_1776_" in cid else "unknown"
        by_repo[repo].append(r)
    print("## per-repo cells")
    for repo in sorted(by_repo):
        cell_count = len(by_repo[repo])
        elapsed_vals = [float(r.get("elapsed_ms", 0) or 0) / 1000 for r in by_repo[repo]]
        print(
            f"  {repo:24s}  cells={cell_count:4d}  "
            f"median_wall={median(elapsed_vals):6.1f}s  "
            f"max_wall={max(elapsed_vals):7.1f}s"
        )
    print()

    elapsed_all = [float(r.get("elapsed_ms", 0) or 0) / 1000 for r in rows]
    print("## elapsed (per-cell wall, seconds)")
    print(
        f"  min={min(elapsed_all):6.1f}  median={median(elapsed_all):6.1f}  "
        f"p95={_p95(elapsed_all):7.1f}  max={max(elapsed_all):7.1f}"
    )
    print()

    calls = [int(r.get("model_calls", 0) or 0) for r in rows if r.get("source") == "run"]
    if calls:
        print("## model_calls (RUN cells only)")
        print(
            f"  min={min(calls)}  median={median(calls):.0f}  "
            f"p95={_p95([float(c) for c in calls]):.0f}  max={max(calls)}"
        )
        print()

    prompt_tokens = [int(r.get("prompt_tokens", 0) or 0) for r in rows if r.get("source") == "run"]
    completion_tokens = [
        int(r.get("completion_tokens", 0) or 0) for r in rows if r.get("source") == "run"
    ]
    if prompt_tokens:
        print("## tokens (RUN cells only)")
        print(f"  prompt   total={sum(prompt_tokens):,}   median={median(prompt_tokens):.0f}")
        print(
            f"  compl.   total={sum(completion_tokens):,}   median={median(completion_tokens):.0f}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
