# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""role fragment source — sprint 061.

Fires once at `substrate.RunStarted` (session-open scope). Resolves the
role prompt via the four-layer resolver at `roles.py::resolve_role_prompt_
with_source`; yields one `PromptFragment(source="role", text=<resolved>,
precedence=0, provenance={"role_name": role, "resolved_from": <path>})`.
Precedence 0 puts the role first in the composed prompt — identity before
methodology, methodology before per-turn instructions.

Wires a currently-dead concept end-to-end. Pre-sprint 061 `manifest.role`
was validated at POST /api/session and then dropped — the resolved prompt
had no consumer, and the five shipped prompts under
`topologies/session/prompts/` (reviewer.md, planner.md, tester.md,
explainer.md, default.md) were read at validation-time only. Sprint 061
puts each one on the record as a typed fragment for every session that
names it.

Deferred to sprint 064: the composer's cohort-scoping fix (session-open
sources need to appear in every turn's `PromptComposed` — today the
composer reads the entire `KindBuffer("PromptFragment")` so they do
appear, but for the wrong reason; sprint 064 pins the invariant with a
proper session-open filter). Also deferred to sprint 064: the live-model
assertion that a role fragment reaches the driver — `_model_factory` does
not yet consume `PromptComposed.text`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from . import PromptFragment
from .roles import resolve_role_prompt_with_source
from .vocabulary import PROMPT_SOURCE_ROLE


_PRECEDENCE = 0  # reserved band from session-vocabulary.md § I


def role_producer_factory(role: str, *, repo_root: Path | None = None) -> Callable[[], Any]:
    """Return the role fragment-source Producer body factory.

    The topology binds `manifest.role` and the daemon's `repo_root` at
    topology-build time. The producer fires once per session and yields a
    single `PromptFragment` when the resolver returns non-empty text.

    Resolution failure at RunStarted is a hard error — the resolver
    already validates at POST /api/session, so a resolution failure at
    RunStarted means the file was deleted or the layer was moved between
    session create and first turn. Producers that raise surface as
    `substrate.ProducerFailed`; the session's own `park-on-model-error`
    style handling belongs downstream if this pattern needs softening.
    """

    async def _role(_inp: Any) -> AsyncIterator[PromptFragment]:
        text, source_path = resolve_role_prompt_with_source(role, repo_root=repo_root)
        if not text:
            return
        yield PromptFragment(
            source=PROMPT_SOURCE_ROLE,
            text=text,
            precedence=_PRECEDENCE,
            provenance={"role_name": role, "resolved_from": str(source_path)},
        )

    return lambda: _role


__all__ = ["role_producer_factory"]
