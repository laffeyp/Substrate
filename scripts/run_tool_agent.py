"""Run the tool-loop agent: a real local Ollama model driving substrate's tool loop.

The runnable entrypoint for `docs/tool-loop-agent.md`. Give it a task and a model; it runs the
`tool_loop` topology in walkthrough mode with the real tool suite, then prints what the model did
(the ToolCalls / ToolResults / FinalAnswer) and where the full replayable record landed.

Examples:
    cd substrate
    uv run python scripts/run_tool_agent.py \
        --task "Create a file at {workdir}/out.txt containing exactly: substrate works. Then answer."
    uv run python scripts/run_tool_agent.py --model llama3.2:1b --read-only \
        --task "List the .py files under {workdir} and tell me how many there are."

SAFETY: without --read-only the suite includes edit_file / write_file / bash, which mutate the host
and are UNGATED (see docs/tool-loop-agent.md §5). Point --workdir at a scratch directory.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
from pathlib import Path

from substrate.api import Runtime, read_record
from substrate.adapters import OllamaResponder
from substrate.topologies.tool_loop import tool_loop_topology
from substrate.topologies.tool_loop.tools import CALCULATOR, Tool, full_suite


def _read_only_suite(root: Path) -> dict[str, Tool]:
    keep = {"read_file", "list_dir", "glob", "grep", "web_fetch"}
    return {**CALCULATOR, **{k: v for k, v in full_suite(root).items() if k in keep}}


async def _run(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="agent-"))
    workdir.mkdir(parents=True, exist_ok=True)
    record = workdir / "record"
    task = args.task.replace("{workdir}", str(workdir))
    # the suite is ROOTED at the workspace: relative paths and bash resolve inside workdir (the way
    # Claude Code operates in a repo), so the task can say "out.txt", not just an absolute path.
    suite = _read_only_suite(workdir) if args.read_only else full_suite(workdir)

    print(
        f"model={args.model}  workdir={workdir}  tools={'read-only' if args.read_only else 'FULL_SUITE'}"
    )
    print(f"task: {task}\n")

    result = await Runtime(record).run(
        tool_loop_topology(
            model=OllamaResponder(args.model, max_tokens=args.max_tokens, think=args.think),
            walkthrough=True,
            deterministic=False,
            tools=suite,
            task=task,
            max_steps=args.max_steps,
        )
    )

    print(f"status: {result.status}")
    for e in read_record(record):
        k, p = e["kind"], e.get("payload", {})
        if k == "ToolCall":
            print(f"  → ToolCall  {p['tool']}({p['args']})")
        elif k == "ToolResult":
            out = str(p["output"])[:100]
            print(f"  ← ToolResult ok={p['ok']} {out if p['ok'] else p['error']}")
        elif k == "FinalAnswer":
            print(f"  ✓ FinalAnswer: {p['text'][:200]}")
    print(f"\nfull replayable record: {record}")
    print(
        "view it: SUBSTRATE_UI_PORT=8799 uv run python ../substrate-ui/server.py  →  http://127.0.0.1:8799/"
    )
    return 0 if result.status == "finalised" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a local LLM as a tool-using agent on Substrate.")
    ap.add_argument(
        "--task", required=True, help="the plain-English task; {workdir} is substituted"
    )
    ap.add_argument(
        "--model", default="qwen2.5-coder:7b", help="an Ollama model (default: qwen2.5-coder:7b)"
    )
    ap.add_argument(
        "--workdir", default=None, help="scratch dir the agent may use (default: a temp dir)"
    )
    ap.add_argument("--max-steps", type=int, default=6, help="tool-call budget (default: 6)")
    ap.add_argument("--max-tokens", type=int, default=256, help="per model call (default: 256)")
    ap.add_argument(
        "--read-only", action="store_true", help="inspect-only suite (no edit/write/bash)"
    )
    ap.add_argument(
        "--think",
        action="store_true",
        help="enable the model's thinking mode (for reasoning models)",
    )
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
