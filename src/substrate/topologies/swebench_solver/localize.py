# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
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

from ...adapters import Responder, call_responder_metered
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
    known_files: set[str],
    *,
    top_k: int = 5,
) -> _Factory:
    """The file-level localizer (one model call). Emits the metered usage, the SuspectFiles (top-k), and
    EditLocations (v1: the suspect files ARE the edit context — element/line localization is a later
    refinement, design §5)."""

    async def localize(_inp: Any) -> AsyncIterator[Any]:
        # 2026-08-09 halt-on-error rewrite: no exception swallow. If the model call fails, the
        # producer dies, the kernel records ProducerFailed, the runner halts. Death-resilience
        # (former KIT_DIARY 16 pattern) turned every systemic Ollama failure into a null result
        # that looked like data. Kernel-level halt is the honest signal.
        response, usage = await call_responder_metered(
            responder, build_localize_prompt(issue, repo_skeleton)
        )
        yield usage
        files = parse_suspect_files(response, known_files)[:top_k]
        yield SuspectFiles(files=tuple(files))
        yield EditLocations(targets=tuple(files))

    return lambda: localize


def full_recall_at_k(suspect_files: tuple[str, ...] | list[str], gold_files: set[str]) -> bool:
    """Did the suspect set contain EVERY gold-patch file (gold subset of suspect)? The strict
    'all-found@k' / full-recall boolean — the hard ceiling on the whole pipeline (you cannot repair a
    file you never localized, design §5). Banked per instance so the embedding-arm cut is a data decision."""
    return gold_files.issubset(set(suspect_files))


def recall_at_k(suspect_files: tuple[str, ...] | list[str], gold_files: set[str]) -> float:
    """The fractional recall@k — |gold ∩ suspect| / |gold|, the consensus IR/localization metric.
    Near-miss vs total-miss localization is more diagnostic than the boolean for attributing a low resolve
    rate to localization vs repair (review #61). Empty gold -> 1.0 (vacuously fully localized)."""
    if not gold_files:
        return 1.0
    return len(gold_files & set(suspect_files)) / len(gold_files)
