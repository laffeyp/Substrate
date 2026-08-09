"""EnsembleResponder — sprint 157b.

One Responder object that internally routes each successive call to a distinct backend
Responder, so a best-of-N loop that today writes

    responders = [OllamaResponder(m, ...) for m in models]
    ... responders[slot % len(responders)] ...

can instead write

    ensemble = EnsembleResponder([OllamaResponder(m, ...) for m in models])
    ... ensemble ...  # one object, cycles per call

and get the same heterogeneous-ensemble behaviour without the caller managing per-slot indexing.
The roadmap card scopes this alongside `n_drafts_repair_ensemble_arm` (already shipped in Sprint
159): that arm still uses the per-slot list today, but new topologies (delegate flows, tool-loop
agents) can drop the modulo bookkeeping and hold one Responder.

Cycling is deterministic (round-robin from index 0), not random — a caller who wants
random-sample-per-call ensembles composes a different Responder. Round-robin makes the ensemble's
model contribution auditable on the record (call K used model at index K mod N) without any
seeded RNG state.

Concurrency: the counter is a plain int, not lock-protected. The substrate runtime is
single-threaded async; concurrent `arespond` calls on the SAME EnsembleResponder from different
producers would race on the counter (still legal, just non-deterministic distribution). In
practice the per-slot best-of-N pattern awaits each call inside the slot's coroutine, so no
concurrent calls to the same ensemble land. A caller that needs strict ordering under
concurrency wraps the counter externally.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import ModelUsage, Responder


class EnsembleResponder:
    """A Responder that cycles through a list of backend Responders on each successive call.
    Each `respond` / `arespond` / `arespond_metered` / `respond_metered` invocation routes to
    the next backend in round-robin order (index 0, 1, ..., N-1, 0, 1, ...). Sprint 157b.

    The wrapped Responders MUST each implement `respond`; the async / metered paths are
    forwarded when the underlying Responder implements them (falls back to the sync `respond`
    when it doesn't, mirroring `call_responder`'s duck-typing at models.py:373-378). The
    metered path yields a `ModelUsage` with the wrapped Responder's `estimated` flag preserved —
    a caller reading the record can still tell provider-truth from word-count stand-ins.
    """

    def __init__(self, responders: Sequence[Responder]) -> None:
        if not responders:
            raise ValueError("EnsembleResponder needs at least one backing Responder")
        self._responders: tuple[Responder, ...] = tuple(responders)
        self._counter = 0

    def __len__(self) -> int:
        return len(self._responders)

    def _next(self) -> Responder:
        r = self._responders[self._counter % len(self._responders)]
        self._counter += 1
        return r

    def respond(self, prompt: str) -> str:
        return str(self._next().respond(prompt))

    def respond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        r = self._next()
        # Prefer the metered path when available; fall back to synthesising a zero-usage
        # ModelUsage from the sync response otherwise (mirrors call_responder_metered's stand-in
        # posture at models.py:391-404). The stand-in stays `estimated=True` so the aggregator
        # can distinguish provider-truth from a synthesised count.
        metered = getattr(r, "respond_metered", None)
        if callable(metered):
            text, usage = metered(prompt)
            return str(text), usage
        text = str(r.respond(prompt))
        return text, ModelUsage(
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
            wall_ms=0,
            model="ensemble-standin",
            estimated=True,
        )

    async def arespond(self, prompt: str) -> str:
        r = self._next()
        arespond = getattr(r, "arespond", None)
        if callable(arespond):
            return str(await arespond(prompt))
        return str(r.respond(prompt))

    async def arespond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        r = self._next()
        ametered = getattr(r, "arespond_metered", None)
        if callable(ametered):
            text, usage = await ametered(prompt)
            return str(text), usage
        arespond = getattr(r, "arespond", None)
        if callable(arespond):
            text = str(await arespond(prompt))
        else:
            text = str(r.respond(prompt))
        return text, ModelUsage(
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(text.split()),
            wall_ms=0,
            model="ensemble-standin",
            estimated=True,
        )


__all__ = ["EnsembleResponder"]
