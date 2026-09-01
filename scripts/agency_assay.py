#!/usr/bin/env python
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
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
import json
import tempfile
import time
from pathlib import Path

import msgspec

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


class _Sink:
    """Persist every scored cell as a JSONL row, so the board is an ARTIFACT, not just stdout.

    The R-20 board originally existed only as a printed table (the trajectories died with their
    tempdirs) — unreproducible from disk, which contradicts the project's own record-is-the-evidence
    discipline. One row per (model, task, trial): the full AgencyScore (or the error string) plus the
    run-record root when `--keep-records` retained it. First line is a meta row (args + timestamp)."""

    def __init__(self, out_dir: Path, args: argparse.Namespace) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        self.path = out_dir / f"agency-{stamp}.jsonl"
        meta = {
            "meta": True,
            "utc": stamp,
            "models": args.models,
            "repeats": args.repeats,
            "suite": bool(args.suite),
            "max_steps": args.max_steps,
            "max_tokens": args.max_tokens,
            "think": bool(args.think),
        }
        self.path.write_text(json.dumps(meta) + "\n")

    def row(
        self, model: str, task: str, trial: int, result: AgencyScore | str, record: str | None
    ) -> None:
        payload: dict[str, object] = {"model": model, "task": task, "trial": trial}
        if isinstance(result, AgencyScore):
            payload["score"] = msgspec.to_builtins(result)
        else:
            payload["error"] = result
        if record is not None:
            payload["record"] = record
        with self.path.open("a") as f:
            f.write(json.dumps(payload) + "\n")


async def _score_one(
    model: str,
    prompt: str,
    seed: dict[str, str],
    args: argparse.Namespace,
    *,
    record_root: Path | None = None,
) -> tuple[AgencyScore | str, str | None]:
    workdir = Path(tempfile.mkdtemp(prefix="agency-"))
    for name, content in seed.items():  # seed files (e.g. a broken program to fix) before the run
        (workdir / name).write_text(content)
    # --keep-records puts the run record (the trajectory, the actual evidence) at a durable root;
    # without it the record lives in the tempdir workspace and dies with it (scores still persist).
    record = record_root if record_root is not None else workdir / "record"
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
        return f"{type(exc).__name__}: {exc}", None
    kept = str(record) if record_root is not None else None
    return score_agency(read_record(record)), kept


def _record_root(args: argparse.Namespace, model: str, task: str, trial: int) -> Path | None:
    if not args.keep_records:
        return None
    safe = lambda s: "".join(c if c.isalnum() or c in "._-" else "-" for c in s)  # noqa: E731
    return Path(args.keep_records) / f"{safe(model)}__{safe(task)[:40]}__t{trial}.record"


def _run_suite(args: argparse.Namespace) -> int:
    """Run the AGENCY_SUITE (a grid of task shapes) across the models, `--repeats` runs per cell; print
    a per-(model,task) grid + a per-model mean. n=1 cells show label:score; n>1 cells show the
    VERIFIED-rate + mean (the defensible board). Agency measured across shapes, not one lucky task."""
    n = args.repeats
    sink = _Sink(Path(args.out), args)
    grid: dict[str, dict[str, list[AgencyScore]]] = {}
    for m in args.models:
        for t in AGENCY_SUITE:
            scores: list[AgencyScore] = []
            for i in range(n):
                r, kept = asyncio.run(
                    _score_one(
                        m, t.prompt, t.seed, args, record_root=_record_root(args, m, t.name, i)
                    )
                )
                sink.row(m, t.name, i, r, kept)
                if isinstance(r, AgencyScore):
                    scores.append(r)
            grid.setdefault(m, {})[t.name] = scores
    tasks = [t.name for t in AGENCY_SUITE]
    header = f"{'MODEL':<24} " + " ".join(f"{t[:14]:>14}" for t in tasks) + "   mean"
    print(
        f"\nAGENCY SUITE ({'VERIFIED-rate + mean' if n > 1 else 'label:score'}) per (model, task), n={n}:"
    )
    print(header)
    print("-" * len(header))
    for m in args.models:
        cells: list[str] = []
        means: list[float] = []
        for t in tasks:
            agg = aggregate_agency(grid[m][t])
            if agg.runs == 0:
                cells.append("ERROR")
            elif n > 1:
                cells.append(f"{agg.verified}/{agg.runs} {agg.mean_score:>3.0f}")
                means.append(agg.mean_score)
            else:
                s = grid[m][t][0]
                cells.append(f"{s.label[:4]}:{s.score:>3}")
                means.append(float(s.score))
        mean = sum(means) / len(means) if means else 0.0
        print(f"{m:<24} " + " ".join(f"{c:>14}" for c in cells) + f"   {mean:>4.0f}")
    tail = "" if n > 1 else " — classes, not rates"
    print(f"\n(agency = trajectory across task shapes; n={n} per cell{tail})")
    print(f"(rows persisted to {sink.path})")
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
    ap.add_argument(
        "--out",
        default="process/runs/benches/agency",
        help="dir for the per-cell JSONL rows (the persisted board; always written)",
    )
    ap.add_argument(
        "--keep-records",
        default="",
        help="dir to retain each cell's full run record (the trajectory evidence); off by default",
    )
    args = ap.parse_args()

    if args.suite:
        return _run_suite(args)

    sink = _Sink(Path(args.out), args)
    scored: dict[str, list[AgencyScore]] = {}
    errs: dict[str, list[str]] = {}
    for m in args.models:
        for i in range(args.repeats):
            r, kept = asyncio.run(
                _score_one(m, args.task, {}, args, record_root=_record_root(args, m, "default", i))
            )
            sink.row(m, "default", i, r, kept)
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
    print(f"(rows persisted to {sink.path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
