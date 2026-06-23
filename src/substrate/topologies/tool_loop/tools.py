"""tool_loop's tool suite — the real tools a tool-using agent has available (Wave 14b).

Designed by reading the SOURCE of three reference agents (not blog summaries) — opencode's
`packages/core/src/tool/`, Cline's `sdk/packages/core/src/extensions/tools/definitions.ts` +
`apps/cli/src/runtime/tool-policies.ts`, and aider's `coders/editblock_coder.py` (findings in
docs/tool-loop-tool-suite.md). The tool SHAPE is adopted from all three: a tool is a typed `name` +
schema + an `execute` that returns a STRUCTURED result OR a typed failure the model reads (errors
are observations, never a crash — the loop catches a tool exception OR a non-encodable return
alike); output is CAPPED to protect the context; surgical `edit_file` (search/replace) is the
primary code tool, `write_file` for new files.

WHERE WE DIVERGE — PERMISSIONS. The three references gate mutation behind human approval by default
(Cline auto-runs only a SAFE read/search/fetch set; opencode decorates each tool with a permission
check; aider suggests shell for the human to run). THIS SUITE DOES NOT. By default it runs with NO
permission gate — full autonomy, equivalent to a coding agent in auto-accept mode, or more
permissive. That is deliberate: the substrate's end state is the LLM running these topologies ITSELF
(the self-reflecting / self-running direction in the backlog), so the default is autonomy, not a
human in the loop. Approval-gating is an OPT-IN capability — gate any tool behind `pause_await_input`
(R-2) when an operator wants one — never the default.

The one partition that IS load-bearing is DETERMINISM, not approval: pure tools keep the committed CI
record byte-reproducible; real-I/O tools are `deterministic=False`.

  - PURE       : add, mul                                  (deterministic — the CI demo)
  - READ-ONLY  : read_file, list_dir, grep, web_fetch      (deterministic=False — real I/O)
  - WRITE/EXEC : edit_file, write_file, bash               (deterministic=False — mutates the host, ungated)

A real agent topology passes `FULL_SUITE`; the committed CI demo uses `CALCULATOR` (pure) so the
record stays replayable. NEXT (docs/tool-loop-tool-suite.md): per-tool msgspec input schemas; an
OPT-IN `pause_await_input` gate for operators who want one; a substrate-native `delegate` tool.

SAFETY: `edit_file`/`write_file`/`bash` mutate the host — by design, ungated by default. An operator
runs FULL_SUITE knowing it is autonomous; sandbox the run if that autonomy is unwanted.
"""

from __future__ import annotations

import subprocess
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple


class Tool(NamedTuple):
    name: str
    describe: str  # one line for the model's prompt — its available tool surface
    deterministic: bool
    run: Callable[[list[Any]], Any]  # run(args) -> a structured result; raise on failure


# ── PURE (deterministic — the CI demo) ────────────────────────────────────────
def _add(a: list[Any]) -> int:
    return int(a[0]) + int(a[1])


def _mul(a: list[Any]) -> int:
    return int(a[0]) * int(a[1])


# ── READ-ONLY (real I/O — deterministic=False) ────────────────────────────────
def _read_file(a: list[Any]) -> str:
    return Path(str(a[0])).read_text(encoding="utf-8")[:8000]


def _list_dir(a: list[Any]) -> list[str]:
    p = Path(str(a[0]) if a else ".")
    return sorted(e.name + ("/" if e.is_dir() else "") for e in p.iterdir())


def _grep(a: list[Any]) -> list[str]:
    pat, root = str(a[0]), Path(str(a[1]) if len(a) > 1 else ".")
    files = [root] if root.is_file() else root.rglob("*")
    hits: list[str] = []
    for f in files:
        if not f.is_file():
            continue
        try:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if pat in line:
                    hits.append(f"{f}:{n}: {line.strip()[:120]}")
                    if len(hits) >= 50:
                        return hits
        except (UnicodeDecodeError, OSError):
            continue
    return hits


def _web_fetch(a: list[Any]) -> str:
    req = urllib.request.Request(str(a[0]), headers={"User-Agent": "substrate-tool-loop"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 — explicit agent tool
        return str(r.read(20000).decode("utf-8", "replace"))


# ── WRITE / EXEC (side effects — deterministic=False) ─────────────────────────
def _edit_file(a: list[Any]) -> str:
    # the primary code tool across all three agents: a surgical search/replace, not a full rewrite
    # (aider EditBlock / Cline edit_file). A missing search string is a typed failure, not a crash.
    path, search, replace = Path(str(a[0])), str(a[1]), str(a[2])
    text = path.read_text(encoding="utf-8")
    if search not in text:
        raise ValueError(f"edit_file: search text not found in {path}")
    path.write_text(text.replace(search, replace, 1), encoding="utf-8")
    return f"edited {path} (1 replacement)"


def _write_file(a: list[Any]) -> str:
    Path(str(a[0])).write_text(str(a[1]), encoding="utf-8")
    return f"wrote {len(str(a[1]))} bytes to {a[0]}"


def _bash(a: list[Any]) -> dict[str, Any]:
    proc = subprocess.run(  # noqa: S602 — explicit agent shell tool (opt-in, not CI)
        str(a[0]), shell=True, capture_output=True, text=True, timeout=60
    )
    return {"exit": proc.returncode, "stdout": proc.stdout[:8000], "stderr": proc.stderr[:2000]}


CALCULATOR: dict[str, Tool] = {
    "add": Tool("add", "add(a, b) -> a+b", True, _add),
    "mul": Tool("mul", "mul(a, b) -> a*b", True, _mul),
}

FULL_SUITE: dict[str, Tool] = {
    **CALCULATOR,
    "read_file": Tool("read_file", "read_file(path) -> the file's text", False, _read_file),
    "list_dir": Tool("list_dir", "list_dir(path) -> directory entries", False, _list_dir),
    "grep": Tool("grep", "grep(pattern, path) -> matching 'file:line: text'", False, _grep),
    "web_fetch": Tool("web_fetch", "web_fetch(url) -> the page text", False, _web_fetch),
    "edit_file": Tool("edit_file", "edit_file(path, search, replace) -> surgical search/replace (SIDE EFFECT)", False, _edit_file),
    "write_file": Tool("write_file", "write_file(path, text) -> create/overwrite a file (SIDE EFFECT)", False, _write_file),
    "bash": Tool("bash", "bash(cmd) -> {exit, stdout, stderr} (SIDE EFFECT)", False, _bash),
}


def suite_describe(suite: dict[str, Tool]) -> str:
    """One line per tool — the available-tool surface to hand a model in its prompt."""
    return "\n".join(f"  {t.describe}" for t in suite.values())
