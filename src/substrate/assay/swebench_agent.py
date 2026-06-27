"""Container-backend coding AGENT — a read/edit/bash loop that solves inside the live instance container.

The executing arm: unlike the host backend's single blind file pick, the agent can read several files, edit,
and run tests/bash to check its work, iterating up to a step budget — all inside the locked-down container
(`ContainerWorkspace`). The patch is `git diff` in-container at the end. Any model drops in via `Responder`.

Action protocol (one action per step, parsed from the model's reply):
    ACTION: read_file   PATH: <path>
    ACTION: edit_file   PATH: <path>  + a SEARCH/REPLACE block
    ACTION: bash        CMD: <shell>
    ACTION: done
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from .swebench_container import ContainerWorkspace
from .swebench_workspace import graded_test_files

_ACTION = re.compile(r"ACTION:\s*(\w+)", re.IGNORECASE)
_PATH = re.compile(r"PATH:\s*(\S+)", re.IGNORECASE)
_CMD = re.compile(r"CMD:\s*(.+)")
_SR = re.compile(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE", re.DOTALL)


class _Responder(Protocol):
    def respond(self, prompt: str) -> str: ...


def _prompt(issue: str, skeleton: str, history: list[str]) -> str:
    hist = "\n".join(history[-12:]) if history else "(no actions yet)"
    return (
        "You are fixing a bug in a checked-out repository. Work step by step. Each turn, output EXACTLY ONE "
        "action in one of these forms and NOTHING else:\n"
        "ACTION: read_file\nPATH: <repo path>\n\n"
        "ACTION: edit_file\nPATH: <repo path>\n<<<<<<< SEARCH\n<exact current lines>\n=======\n<replacement>\n>>>>>>> REPLACE\n\n"
        "ACTION: bash\nCMD: <shell command, e.g. run a test>\n\n"
        "ACTION: done\n\n"
        f"## issue\n{issue}\n\n## repository files\n{skeleton}\n\n## actions so far\n{hist}\n\nYour next action:"
    )


def _apply_edit(ws: ContainerWorkspace, path: str, search: str, replace: str) -> str:
    """Apply a SEARCH/REPLACE to a file in the container (exact first-occurrence). Returns a status note."""
    content = ws.read_file(path)
    if not content:
        return f"edit_file {path}: file not found or empty"
    if search not in content:
        return f"edit_file {path}: SEARCH text not found (copy the exact current lines)"
    ws.write_file(path, content.replace(search, replace, 1))
    return f"edit_file {path}: applied"


def solve_in_container(instance: dict[str, Any], responder: _Responder, *, max_steps: int = 8) -> str:
    """Run the agent loop in the instance container and return the model_patch (`git diff` in-container,
    graded-test edits dropped). "" if nothing applied. Env-gated (Docker + the eval image + a live model)."""
    with ContainerWorkspace(instance["instance_id"]) as ws:
        _, skeleton = ws.exec("git ls-files | head -400")
        issue = str(instance["problem_statement"])
        history: list[str] = []
        for _ in range(max_steps):
            reply = responder.respond(_prompt(issue, skeleton, history))
            am = _ACTION.search(reply)
            action = am.group(1).lower() if am else ""
            if action == "done":
                break
            if action == "read_file":
                pm = _PATH.search(reply)
                path = pm.group(1) if pm else ""
                content = ws.read_file(path) if path else ""
                history.append(f"read_file {path} ->\n{content[:1500]}")
            elif action == "edit_file":
                pm, sr = _PATH.search(reply), _SR.search(reply)
                if pm and sr:
                    history.append(_apply_edit(ws, pm.group(1), sr.group(1), sr.group(2)))
                else:
                    history.append("edit_file: malformed (need PATH + a SEARCH/REPLACE block)")
            elif action == "bash":
                cm = _CMD.search(reply)
                if cm:
                    rc, out = ws.exec(cm.group(1).strip())
                    history.append(f"bash {cm.group(1).strip()} (rc={rc}) ->\n{out[-1200:]}")
                else:
                    history.append("bash: missing CMD")
            else:
                history.append(f"unparseable action; reply head: {reply[:120]}")
        return ws.diff(drop_files=frozenset(graded_test_files(str(instance.get("test_patch", "")))))


__all__ = ["solve_in_container"]
