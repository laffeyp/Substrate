"""REPAIR — the swebench solver's repair phase (sprint 137).

Nests the shared best-of-N + correction loop (`topologies/best_of_n`) with two swebench-specific factories:

  - the DRAFTER (the ONLY model work): emits SEARCH/REPLACE edits for the issue + its edit locations,
    and on a correction round the prior candidate's apply failures.
  - the VALIDATOR (deterministic): the applier. For each candidate it clones the repo at base_commit
    into a PRISTINE local clone (the applier's precondition, review #59), applies the edits, and emits
    Verdict (applied cleanly?) + AppliedPatch (the git-diff `model_patch`).

The loop's Solved is an internal hand-off: SELECT (a later phase) reranks ALL of the round's AppliedPatches,
so the swebench topology passes its own termination (Solved is not the run terminal here).
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator, Callable
from typing import Any

from ...adapters import Responder, call_responder_metered
from ..best_of_n.contracts import Candidate, Verdict
from .applier import ApplyResult, apply_candidate
from .records import AppliedPatch

_Factory = Callable[[], Any]


def build_repair_prompt(spec: str, edit_context: str, failures: str) -> str:
    """The drafter's prompt: the issue + the localized files/edit targets, asking for SEARCH/REPLACE
    edits in the exact format the applier parses; on a correction round, the prior apply failures."""
    parts = [
        "Fix the issue below by emitting SEARCH/REPLACE edits against the given files.",
        "",
        "## issue",
        spec,
        "",
        "## files and edit locations",
        edit_context,
        "",
        "Emit one or more blocks in EXACTLY this format (each marker on its own line):",
        "# path: <relative/path>",
        "<<<<<<< SEARCH",
        "<exact current lines to find>",
        "=======",
        "<replacement lines>",
        ">>>>>>> REPLACE",
        "The SEARCH text must match the file's CURRENT content exactly, as whole lines.",
    ]
    if failures:
        parts += ["", "## a PRIOR attempt failed to apply — correct it:", failures]
    return "\n".join(parts)


def repair_drafter_factory(
    responders: list[Responder], spec: str, edit_context: str = ""
) -> _Factory:
    """The model drafter — one responder per slot (the best-of-N ensemble). Emits the metered usage then
    the Candidate (the raw SEARCH/REPLACE text). `edit_context` (the localized files' content) is read
    from the trigger INPUT when present (the full topology builds it at runtime from LOCALIZE's targets);
    the constructor arg is the standalone-test fallback. `Draft.context` carries correction failures only."""

    async def draft(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        failures = str(inp.get("context", "")) if hasattr(inp, "get") else ""
        ctx = (str(inp.get("edit_context", "")) if hasattr(inp, "get") else "") or edit_context
        prompt = build_repair_prompt(spec, ctx, failures)
        try:
            response, usage = await call_responder_metered(
                responders[slot % len(responders)], prompt
            )
            yield usage
        except Exception as exc:  # noqa: BLE001 — a model error must not kill the slot's coroutine
            # If the drafter died here, this slot would emit no Candidate -> no Verdict -> the round never
            # reaches n verdicts -> the judge never fires -> the run wedges to the watchdog (review #62).
            # Emit a FAILED candidate instead: the validator rejects it -> failed Verdict -> the round
            # completes and the correction loop proceeds. Errors-as-observations, as everywhere else.
            response = f"(drafter model error: {type(exc).__name__}: {str(exc)[:120]})"
        yield Candidate(round=rnd, slot=slot, response=response)

    return lambda: draft


def repair_validate_factory(base_checkout: str) -> _Factory:
    """The deterministic validator: a PRISTINE local clone at base_commit per candidate (the applier's
    precondition), apply the edits, emit Verdict + (on success) AppliedPatch. The clone is local
    (hardlinked objects) and torn down once the model_patch string is captured."""

    async def validate(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        response = str(inp.get("response", "")) if hasattr(inp, "get") else ""
        clone = tempfile.mkdtemp(prefix=f"swebench-r{rnd}s{slot}-")
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "clone", "--quiet", "--local", base_checkout, clone],
                check=True,
                capture_output=True,
            )
            result = await asyncio.to_thread(apply_candidate, response, clone)
        except Exception as exc:  # noqa: BLE001 — a clone/apply failure is a Verdict, never a crash
            result = ApplyResult(
                applied=False, error=f"clone/apply failed: {type(exc).__name__}: {exc}"
            )
        finally:
            shutil.rmtree(clone, ignore_errors=True)
        yield Verdict(
            round=rnd,
            slot=slot,
            passed=result.applied,
            returncode=0 if result.applied else 1,
            summary=result.error or "applied",
        )
        if result.applied:
            yield AppliedPatch(
                round=rnd,
                slot=slot,
                model_patch=result.model_patch,
                creates_file=result.creates_file,
            )

    return lambda: validate
