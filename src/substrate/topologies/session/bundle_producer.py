# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""bundle prose-slot fragment sources — sprint 062.

Two Producers, one per prose slot. Both fire once at session open
(`initial` binding). Both read `manifest.bundle` through `bundles.load_
bundle` + `bundles.resolve_extends` and yield one or more `PromptFragment`
events per non-empty slot in the resolved chain.

Methodology semantics: the extends chain lands ancestor-first (per
`resolve_extends`); every non-empty methodology in the chain yields one
fragment. Precedence band 5.0-5.9 orders ancestors before the caller
(deepest ancestor at 5.0, caller at the highest occupied slot). The
composer's `(precedence, seq)` tie-break preserves order within source.

Personality semantics: caller wins, then nearest ancestor. Walks
`reversed(chain)`; picks the first non-empty personality; yields exactly
one fragment. Precedence 3.

`manifest.bundle=None` yields zero fragments from either Producer —
the empty-body path completes cleanly. `load_bundle` failure at session
open (bundle name resolves at POST /api/session but the directory is
gone by RunStarted) surfaces as `substrate.ProducerFailed`. Same shape
as sprint 061's role_producer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from ...bundles import Bundle, BundleNotFoundError, load_bundle, resolve_extends
from . import PromptFragment
from .vocabulary import (
    PromptSource,
)


def _resolve_chain(bundle_name: str) -> list[Bundle]:
    """Resolve a bundle's extends chain, tolerating the shipped-bundle
    fallback that `resolve_extends` alone cannot walk.

    `resolve_extends` walks `_bundles_root(None)` (i.e. `~/.substrate/
    bundles/`) and does not consult the shipped-package fallback that
    `load_bundle` has for the "session" default and the "<app>.bundle"
    application defaults. A shipped bundle with no `extends` therefore
    trips `BundleNotFoundError` in `resolve_extends` even though
    `load_bundle` finds it fine.

    This helper first tries `resolve_extends`; on BundleNotFoundError
    for the top-level name, falls back to `[load_bundle(name)]`. That
    covers every shipped bundle whose extends chain is empty (the v1
    "session" bundle and every current .bundle default), and preserves
    the error for chains where an intermediate ancestor is genuinely
    missing (resolve_extends succeeds at the top level then fails
    walking up).
    """
    try:
        return resolve_extends(bundle_name)
    except BundleNotFoundError:
        return [load_bundle(bundle_name)]


_METHODOLOGY_PRECEDENCE_BASE = 5  # reserved band 5.0-5.9 per session-vocabulary.md § I
_PERSONALITY_PRECEDENCE = 3


def bundle_methodology_producer_factory(bundle: str | None) -> Callable[[], Any]:
    """Return the methodology fragment-source Producer body factory.

    Yields one fragment per non-empty methodology in the resolved extends
    chain. Deepest ancestor at precedence 5.0; each downstream link
    increments by 0.1 (int representation on the wire — bumps to
    integers 50, 51, 52 to survive msgspec's Struct field type of
    `precedence: int` without a float rebinding). Sprint 062 uses
    50, 51, 52... so a chain of five bundles occupies 50-54, still
    under the per_turn band at 100 (10 in the fragment enum, 100 in
    the reserved band naming).
    """

    async def _methodology(_inp: Any) -> AsyncIterator[PromptFragment]:
        if bundle is None:
            return
        chain = _resolve_chain(bundle)
        occupied = 50  # base of the methodology band (int representation)
        for entry in chain:
            if not entry.methodology:
                continue
            yield PromptFragment(
                source=PromptSource.BUNDLE_METHODOLOGY,
                text=entry.methodology,
                precedence=occupied,
                provenance={
                    "bundle_name": entry.name,
                    "chain_position": chain.index(entry),
                },
            )
            occupied += 1

    return lambda: _methodology


def bundle_personality_producer_factory(bundle: str | None) -> Callable[[], Any]:
    """Return the personality fragment-source Producer body factory.

    Caller wins across the extends chain, then nearest ancestor. Walks
    `reversed(chain)` and yields the FIRST non-empty personality it
    finds. Precedence 3 places personality before methodology in the
    composed prompt. Empty personality across the whole chain yields
    zero fragments.
    """

    async def _personality(_inp: Any) -> AsyncIterator[PromptFragment]:
        if bundle is None:
            return
        chain = _resolve_chain(bundle)
        for entry in reversed(chain):
            if entry.personality:
                yield PromptFragment(
                    source=PromptSource.BUNDLE_PERSONALITY,
                    text=entry.personality,
                    precedence=_PERSONALITY_PRECEDENCE,
                    provenance={
                        "bundle_name": entry.name,
                        "chain_position": chain.index(entry),
                    },
                )
                return

    return lambda: _personality


__all__ = [
    "bundle_methodology_producer_factory",
    "bundle_personality_producer_factory",
]
