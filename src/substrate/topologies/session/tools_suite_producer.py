# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""tools_suite fragment source — sprint 064.

Fires once at session open (`initial` binding). Yields one
`PromptFragment(source=tools_suite, text=<suite_describe(tools)>,
precedence=20, provenance={"tool_names": [...]})` when the session's
tool suite is non-empty, nothing when empty. Session-open scope: the
same tools ride every turn's composed prompt (tools cannot change
mid-session in v1).

Sprint 064 makes the tools list a first-class fragment on the record.
Pre-064 the tools were described inline inside `_model_factory`'s
loop and fallback paths via `f"{prompt_text}\\n\\nTools you MAY use:\\n
{suite_describe(tools)}\\n"`; that string composition is scheduled
for deletion once the compute-path migration lands. This sprint puts
the tools description on the record as a typed fragment for
observability; the compute-path deletion is a follow-up.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from ..tool_loop.tools import Tool, suite_describe
from . import PromptFragment
from .vocabulary import PROMPT_SOURCE_TOOLS_SUITE


_PRECEDENCE = 20  # reserved band from session-vocabulary.md § I


def tools_suite_producer_factory(tools: dict[str, Tool]) -> Callable[[], Any]:
    """Return the tools_suite fragment-source Producer body factory.

    Closes over the `tools` dict from topology-build time. Empty tools
    yields no fragment (empty-body generator completes cleanly). Tool
    names are captured deterministically (sorted) so the fragment
    provenance is byte-stable across builds of the same session.
    """
    tool_names_frozen: tuple[str, ...] = tuple(sorted(tools.keys()))
    described = suite_describe(tools) if tools else ""

    async def _tools_suite(_inp: Any) -> AsyncIterator[PromptFragment]:
        if not tools:
            return
        yield PromptFragment(
            source=PROMPT_SOURCE_TOOLS_SUITE,
            text=described,
            precedence=_PRECEDENCE,
            provenance={"tool_names": list(tool_names_frozen)},
        )

    return lambda: _tools_suite


__all__ = ["tools_suite_producer_factory"]
