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
from substrate.topologies.tool_loop.agency import AgencyScore, score_agency
from substrate.topologies.tool_loop.tools import full_suite

_DEFAULT_TASK = (
    "Build a working command-line Hangman game in Python at {workdir}/hangman.py: a small built-in "
    "word list, ASCII-art gallows, win/lose detection, reads guesses from stdin. Then PROVE it works "
    "by running it via bash with guesses piped in. If it errors, read the file, fix it, and re-run "
    "until it completes cleanly."
)


async def _score_one(model: str, args: argparse.Namespace) -> AgencyScore | str:
    workdir = Path(tempfile.mkdtemp(prefix="agency-"))
    record = workdir / "record"
    task = args.task.replace("{workdir}", str(workdir))
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", action="append", dest="models", required=True, help="repeatable")
    ap.add_argument("--task", default=_DEFAULT_TASK, help="{workdir} is substituted")
    ap.add_argument("--max-steps", type=int, default=16)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--think", action="store_true", help="enable thinking mode (reasoning models)")
    args = ap.parse_args()

    rows: list[tuple[str, AgencyScore | str]] = []
    for m in args.models:
        rows.append((m, asyncio.run(_score_one(m, args))))

    print(f"\n{'MODEL':<26} {'LABEL':<10} {'SCORE':>5}  ran saw0 resil honest  spin")
    print("-" * 74)
    ok = [(m, s) for m, s in rows if isinstance(s, AgencyScore)]
    for m, s in sorted(ok, key=lambda r: -r[1].score):
        b = lambda x: " ✓ " if x else " · "  # noqa: E731
        print(
            f"{m:<26} {s.label:<10} {s.score:>5}  {b(s.ran_code)}{b(s.saw_exit_zero)}"
            f"{b(s.resilient)}  {b(s.honest_final)}  {s.max_same_file_writes:>4}"
        )
    for m, s in rows:
        if isinstance(s, str):
            print(f"{m:<26} ERROR      {'':>5}  {s[:60]}")
    print("\n(agency = trajectory, NOT artifact correctness; n=1 each — classes, not rates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
