#!/usr/bin/env python
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Run the tool-loop agent WILD in a disposable container, to surface crashes and edge cases.

The product is host-native (direct fs, like Claude Code) — this is a TEST harness, not the
product. Each (model, task) pair runs in its own throwaway `substrate-arena` container: the model
(on the HOST via Ollama) drives the real FULL_SUITE against the container's `/arena` filesystem,
free to do anything, and we watch what breaks. Destructive tool use costs nothing here.

The point is edge-case discovery, not a pass/fail grade. A run is flagged CRASH when the loop
did not finalise cleanly — a non-zero exit, or a `PredicateQuarantined` / `ProducerFailed` /
`Traceback` on the record (the `glob **/*.py` wedge was exactly this). CRASH is the interesting
outcome: it is a scenario we can now reproduce-then-kill.

Prereqs: `docker build -f Dockerfile.arena -t substrate-arena .` (once), Ollama running on the
host with the models pulled. Usage: `uv run python scripts/agent_arena.py [--model M ...]
[--image NAME] [--max-steps N]`. Full per-run logs land under `--logdir` for inspection.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Deliberately open-ended / adversarial tasks — the kind a real user throws at it, aimed at the
# tool-loop's soft spots: huge/recursive output, mutation, ambiguity, multi-step builds, the
# read->edit line-prefix hazard, replace_all, empty reads, path escapes, and "just talk to me".
# Paths are relative on purpose (they resolve to the /arena workspace); a couple are absolute to
# exercise the root passthrough. The workspace is disposable, so destructive tasks cost nothing.
WILD_TASKS: dict[str, str] = {
    "glob-storm": "Glob '**/*' under / and tell me how many files there are.",  # the offload wedge
    "build-app": "Build a tiny Python calculator CLI at calc.py with add and mul, then show me the "
    "file and give a one-line final answer.",
    "multi-file": "Create a package: pkg/__init__.py, pkg/math.py with an add(a,b), and a "
    "test_math.py that imports and checks it. Then run the test with bash and report the result.",
    "recursive-grep": "Grep for the word 'import' everywhere under / and summarise what you find.",
    "rename-all": "Write config.py containing 'DEBUG = 1\\nif DEBUG:\\n    print(DEBUG)', then "
    "rename DEBUG to VERBOSE everywhere in that file, then show me the file.",
    "grep-then-edit": "Write greetings.py with a line 'msg = \"hello world\"', grep for 'hello' to "
    "find it, then edit that file so the message says 'goodbye world'. Show the final file.",
    "read-empty": "Create an empty file blank.txt, read it back, and tell me exactly what you saw.",
    "just-a-poem": "Write me a four-line poem about the ocean. Just the poem.",
    "self-destruct": "List everything under the current directory, then delete all of it, then "
    "confirm it's empty.",
    "ambiguous-edit": "Edit the file nope.txt to replace 'x' with 'y'.",  # missing file -> typed error
    "escape-attempt": "Write a file at ../../escaped.txt with the text 'out', then read it back.",
    "big-output": "Run a bash command that prints 50000 lines of the word 'flood', then tell me the "
    "last line.",
}

CRASH_MARKERS = ("PredicateQuarantined", "ProducerFailed", "Traceback (most recent call last)")
# a SOFT failure: the run finalised cleanly but the model emitted a raw TOOL CALL as its final answer
# — a {"name": ..., "arguments": ...} object — so it did NO work, yet OK/CRASH would score it OK. The
# arena surfaced this on qwen (batched multi-tool-calls); flag it so the class can't hide as green.
# Require BOTH keys: a first cut that matched any leading ``` fence FALSE-flagged legit "show me the
# file" answers (a ```python file dump is an answer, not a no-op) — the tool-call shape is the signal.
_SOFTFAIL_ANSWER = re.compile(r'FinalAnswer:.*"name"\s*:.*"arguments"\s*:', re.DOTALL)


def _run_one(image: str, model: str, name: str, task: str, max_steps: int, logdir: Path) -> str:
    """Run one (model, task) in a fresh container; return OK / SOFT / CRASH and save the log."""
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--add-host=host.docker.internal:host-gateway",  # reach host Ollama (Linux; harmless on Mac)
            image,
            "--model",
            model,
            "--workdir",
            "/arena",
            "--max-steps",
            str(max_steps),
            "--task",
            task,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = proc.stdout + "\n" + proc.stderr
    (logdir / f"{model.replace('/', '_').replace(':', '_')}__{name}.log").write_text(out)
    if any(m in out for m in CRASH_MARKERS):
        return "CRASH"
    if _SOFTFAIL_ANSWER.search(out):
        return "SOFT"  # finalised but the "answer" is an unparsed tool call — no work done
    return "OK" if proc.returncode == 0 else "CRASH"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Ollama model to test (repeatable; default: qwen2.5-coder:7b)",
    )
    ap.add_argument("--image", default="substrate-arena", help="arena image tag")
    ap.add_argument("--max-steps", type=int, default=8, help="tool-call budget per run")
    ap.add_argument(
        "--logdir",
        type=Path,
        default=Path("arena-logs"),
        help="where per-run logs land (default: ./arena-logs)",
    )
    args = ap.parse_args()
    models = args.models or ["qwen2.5-coder:7b"]
    args.logdir.mkdir(parents=True, exist_ok=True)

    print(f"{'MODEL':<24} {'TASK':<16} RESULT")
    print("-" * 60)
    to_investigate: list[tuple[str, str, str]] = []  # (result, model, task) for CRASH + SOFT
    for model in models:
        for name, task in WILD_TASKS.items():
            try:
                result = _run_one(args.image, model, name, task, args.max_steps, args.logdir)
            except subprocess.TimeoutExpired:
                result = "CRASH"  # a hang is an edge case too
            print(f"{model:<24} {name:<16} {result}")
            if result in ("CRASH", "SOFT"):
                to_investigate.append((result, model, name))

    print("-" * 60)
    if to_investigate:
        print(
            f"\n{len(to_investigate)} to reproduce-then-kill (CRASH=broke, SOFT=no-op answer) — "
            f"logs in {args.logdir}/:"
        )
        for result, model, name in to_investigate:
            print(f"  [{result}] {model} · {name}")
    else:
        print(f"\nno crashes or soft-fails surfaced this pass (logs in {args.logdir}/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
