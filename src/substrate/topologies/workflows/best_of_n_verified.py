"""best_of_n_verified — generate N candidates, verify each, select the survivor (workflow-parity W1.2).

The agent-CLI "best of N with verification" pattern, as a general application on real input. It
COMPOSES the existing `best_of_n_correction` loop: a drafter model fans out N candidates, each is
verified, and the built-in judge selects the first that passes (feeding failures back for another
round, up to the budget). No new loop, no new vocabulary — the Draft/Candidate/Verdict/Solved
records are best_of_n's.

Verification is CALLER-SUPPLIED, exactly as best_of_n intends: pass a deterministic `check(response)
-> (passed, reason)` (substrate's preferred, when the answer is mechanically checkable), or an
INDEPENDENT judge Responder (a different model family than the drafter, per finding #42 — LLM-as-judge
with the judge disjoint from the generator, not a model grading its own work) for prose/design/
negotiation where no mechanical check exists. Either way the loop and the record are identical.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from ... import api
from ...adapters import Responder, call_responder, call_responder_metered
from ..best_of_n import Candidate, Verdict, best_of_n_correction

# A deterministic verify: given the candidate text, return (passed, reason). The substrate-preferred
# verifier when the answer is mechanically checkable — no model in the validator slot.
Check = Callable[[str], tuple[bool, str]]

_PASS = "PASS"


def _drafter_factory(task: str, drafter: Responder) -> Callable[[], Any]:
    async def draft(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        context = str(inp.get("context", "")) if hasattr(inp, "get") else ""
        prompt = task
        if context:
            prompt += f"\n\nA PRIOR attempt was REJECTED. Address the feedback and answer again:\n{context}"
        response, usage = await call_responder_metered(drafter, prompt)
        yield usage  # the only model work on the draft side — metered onto the record (inert)
        yield Candidate(round=rnd, slot=slot, response=response)

    return lambda: draft


def _verify_prompt(task: str, response: str) -> str:
    return (
        f"You are an independent verifier — you did NOT write the answer below. Judge whether it "
        f"correctly and completely satisfies the task. Reply with '{_PASS}' on the first line if it "
        f"does, or 'FAIL' on the first line if it does not, then one sentence of reason.\n\n"
        f"TASK:\n{task}\n\nANSWER:\n{response}"
    )


def _validator_factory(task: str, verify: Check | Responder) -> Callable[[], Any]:
    async def validate(inp: Any) -> AsyncIterator[Verdict]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        response = str(inp.get("response", "")) if hasattr(inp, "get") else ""
        if callable(verify) and not isinstance(verify, Responder):
            passed, reason = verify(response)  # deterministic check
        else:
            # an INDEPENDENT judge model (finding #42: judge-family disjoint from the drafter)
            verdict_text = await call_responder(verify, _verify_prompt(task, response))
            passed = verdict_text.strip().upper().startswith(_PASS)
            reason = verdict_text.strip()
        yield Verdict(round=rnd, slot=slot, passed=passed, returncode=0 if passed else 1, summary=reason)

    return lambda: validate


def best_of_n_verified_topology(
    task: str,
    *,
    drafter: Responder,
    verify: Check | Responder,
    n: int = 3,
    max_rounds: int = 2,
    deterministic: bool = False,
    watchdog_seconds: float = 30.0,
) -> Callable[[api.TopologyBuilder], None]:
    """Best-of-N with verification over `task`. `drafter` generates candidates; `verify` is either a
    deterministic `check(response) -> (passed, reason)` or an independent judge Responder. Composes
    `best_of_n_correction` with the default select-first judge — the loop, correction, and record are
    best_of_n's; this only supplies the drafter + verifier factories (the work)."""

    def topo(b: api.TopologyBuilder) -> None:
        best_of_n_correction(
            b,
            n=n,
            max_rounds=max_rounds,
            draft_factory=_drafter_factory(task, drafter),
            validate_factory=_validator_factory(task, verify),
            deterministic=deterministic,
            watchdog_seconds=watchdog_seconds,
        )

    return topo
