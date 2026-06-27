"""LOCALIZE — the swebench solver's localization phase (sprint 138).

v1: LLM-on-repo-skeleton for file-level localization — the embedding arm is a deliberate cut, GATED on a
measured `recall_at_k` (design §5); without recall measured, a low resolve rate can't be attributed to
localization vs repair. Emits SuspectFiles (the model's suspect set from the issue + repo skeleton) and
EditLocations (the targets the Repairer edits). `recall_at_k(suspect, gold)` is the observable (#24),
computed against the gold-patch files (the ground truth we have at eval time, NOT shown to the solver).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable
from typing import Any

from ...reference._models import Responder, call_responder_metered
from .records import EditLocations, SuspectFiles

_Factory = Callable[[], Any]


def build_localize_prompt(issue: str, repo_skeleton: str) -> str:
    return "\n".join(
        [
            "Identify the files most likely to need changes to fix the issue.",
            "",
            "## issue",
            issue,
            "",
            "## repository files",
            repo_skeleton,
            "",
            "List the suspect file paths, one per line, most-likely first. Paths only, no prose.",
        ]
    )


def parse_suspect_files(response: str, known: set[str] | None = None) -> list[str]:
    """Parse the model's file list: one path per line, kept only if it looks like a file (a slash or a
    dotted extension) and — when `known` is given — is an actual repo path (the model can't invent files).
    Order preserved, deduplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for line in response.splitlines():
        s = line.strip().strip("`-*").strip()
        if not s or " " in s:
            continue
        if "/" in s or re.search(r"\.\w+$", s):
            if known is not None and s not in known:
                continue
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def localizer_factory(
    responder: Responder,
    issue: str,
    repo_skeleton: str,
    *,
    known_files: set[str] | None = None,
    top_k: int = 5,
) -> _Factory:
    """The file-level localizer (one model call). Emits the metered usage, the SuspectFiles (top-k), and
    EditLocations (v1: the suspect files ARE the edit context — element/line localization is a later
    refinement, design §5)."""

    async def localize(_inp: Any) -> AsyncIterator[Any]:
        response, usage = await call_responder_metered(responder, build_localize_prompt(issue, repo_skeleton))
        yield usage
        files = parse_suspect_files(response, known_files)[:top_k]
        yield SuspectFiles(files=tuple(files))
        yield EditLocations(targets=tuple(files))

    return lambda: localize


def recall_at_k(suspect_files: tuple[str, ...] | list[str], gold_files: set[str]) -> bool:
    """The localization observable: did the suspect set CONTAIN every gold-patch file (gold subset of
    suspect)? This is the hard ceiling on the whole pipeline — you cannot repair a file you never
    localized (design §5). Banked per instance so the embedding-arm cut is a data decision."""
    return gold_files.issubset(set(suspect_files))
