#!/usr/bin/env python
"""Agency assay — run one task across models and score each run's TRAJECTORY, not its artifact.

This measures the thing SWE-bench structurally can't (RESEARCH R-13): did the model actually run its
code, react to failures, and report honestly — the loop that separates an agent from a code-completer.
Each model drives the real tool loop on the same task; the run RECORD is the trajectory, and
`score_agency` reads it into a 0-100 score + a label (VERIFIED / ATTEMPTED / NO_VERIFY / NO_ENGAGE),
orthogonal to whether the produced artifact is correct. Prints an agency leaderboard.

Usage: `uv run python scripts/agency_assay.py --model kimi-k2.6:cloud --model qwen3-coder:480b-cloud
[--think] [--task ...]`. Ollama must be running with the models available. n=1 per model — these are
behaviour classes, not rates; run repeatedly to turn classes into rates.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from substrate.adapters import OllamaResponder
from substrate.api import Runtime, read_record
from substrate.topologies.tool_loop import tool_loop_topology
from substrate.topologies.tool_loop.agency import (
    AGENCY_SUITE,
    AgencyScore,
    aggregate_agency,
    score_agency,
)
from substrate.topologies.tool_loop.tools import full_suite

_DEFAULT_TASK = (
    "Build a working command-line Hangman game in Python at {workdir}/hangman.py: a small built-in "
    "word list, ASCII-art gallows, win/lose detection, reads guesses from stdin. Then PROVE it works "
    "by running it via bash with guesses piped in. If it errors, read the file, fix it, and re-run "
    "until it completes cleanly."
)


async def _score_one(
    model: str, prompt: str, seed: dict[str, str], args: argparse.Namespace
) -> AgencyScore | str:
    workdir = Path(tempfile.mkdtemp(prefix="agency-"))
    for name, content in seed.items():  # seed files (e.g. a broken program to fix) before the run
        (workdir / name).write_text(content)
    record = workdir / "record"
    task = prompt.replace("{workdir}", str(workdir))
    try:
        await Runtime(record).run(
            tool_loop_topology(
                model=OllamaResponder(
                    model, max_tokens=args.max_tokens, think=args.think, timeout=args.timeout
                ),
                walkthrough=True,
                deterministic=False,
                tools=full_suite(workdir),
                task=task,
                max_steps=args.max_steps,
            )
        )
    except Exception as exc:  # noqa: BLE001 — a model/daemon failure is data, not a crash of the assay
        return f"{type(exc).__name__}: {exc}"
    return score_agency(read_record(record))


def _run_suite(args: argparse.Namespace) -> int:
    """Run the AGENCY_SUITE (a grid of task shapes) across the models; print a per-(model,task) grid of
    labels+scores plus a per-model mean. Measures agency across shapes, not one lucky task."""
    grid: dict[str, dict[str, AgencyScore | str]] = {}
    for m in args.models:
        for t in AGENCY_SUITE:
            grid.setdefault(m, {})[t.name] = asyncio.run(_score_one(m, t.prompt, t.seed, args))
    tasks = [t.name for t in AGENCY_SUITE]
    header = f"{'MODEL':<24} " + " ".join(f"{t[:14]:>14}" for t in tasks) + "   mean"
    print("\nAGENCY SUITE — trajectory score per (model, task):")
    print(header)
    print("-" * len(header))
    for m in args.models:
        oks: list[AgencyScore] = []
        cells: list[str] = []
        for t in tasks:
            r = grid[m][t]
            if isinstance(r, AgencyScore):
                oks.append(r)
                cells.append(f"{r.label[:4]}:{r.score:>3}")
            else:
                cells.append("ERROR")
        mean = aggregate_agency(oks).mean_score
        print(f"{m:<24} " + " ".join(f"{c:>14}" for c in cells) + f"   {mean:>4.0f}")
    print("\n(agency = trajectory across task shapes; n=1 per cell — classes, not rates)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", action="append", dest="models", required=True, help="repeatable")
    ap.add_argument("--task", default=_DEFAULT_TASK, help="{workdir} is substituted")
    ap.add_argument("--max-steps", type=int, default=16)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--think", action="store_true", help="enable thinking mode (reasoning models)")
    ap.add_argument("--repeats", type=int, default=1, help="runs per model; n>1 prints RATES")
    ap.add_argument(
        "--suite", action="store_true", help="run the AGENCY_SUITE (a grid of task shapes)"
    )
    args = ap.parse_args()

    if args.suite:
        return _run_suite(args)

    scored: dict[str, list[AgencyScore]] = {}
    errs: dict[str, list[str]] = {}
    for m in args.models:
        for _ in range(args.repeats):
            r = asyncio.run(_score_one(m, args.task, {}, args))
            (
                scored.setdefault(m, []).append(r)
                if isinstance(r, AgencyScore)
                else errs.setdefault(m, []).append(r)
            )

    if args.repeats == 1:
        rows = [(m, scored[m][0]) for m in args.models if scored.get(m)]
        print(f"\n{'MODEL':<26} {'LABEL':<10} {'SCORE':>5}  ran saw0 resil honest  spin")
        print("-" * 74)
        for m, s in sorted(rows, key=lambda r: -r[1].score):
            b = lambda x: " ✓ " if x else " · "  # noqa: E731
            print(
                f"{m:<26} {s.label:<10} {s.score:>5}  {b(s.ran_code)}{b(s.saw_exit_zero)}"
                f"{b(s.resilient)}  {b(s.honest_final)}  {s.max_same_file_writes:>4}"
            )
    else:  # RATES: aggregate N runs per model into a distribution
        print(f"\n{'MODEL':<26} {'runs':>4} {'VERIFIED':>9} {'mean':>5}   distribution")
        print("-" * 74)
        for m in args.models:
            agg = aggregate_agency(scored.get(m, []))
            dist = "  ".join(f"{k}:{v}" for k, v in sorted(agg.labels.items())) or "(none)"
            vr = f"{agg.verified}/{agg.runs}" if agg.runs else "0/0"
            print(f"{m:<26} {agg.runs:>4} {vr:>9} {agg.mean_score:>5.0f}   {dist}")
    for m, elist in errs.items():
        print(f"{m:<26} ERROR ×{len(elist)}: {elist[0][:50]}")
    tag = f"n={args.repeats}" + (" — RATES" if args.repeats > 1 else " each — classes, not rates")
    print(f"\n(agency = trajectory, NOT artifact correctness; {tag})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
