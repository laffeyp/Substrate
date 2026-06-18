"""prisoners_dilemma — PAYOFF asymmetry: a one-shot game with a defect/cooperate decision.

A thin config over the conversation engine (`../conversation.py`). The deciding player (the
prisoner) structures ITS OWN output into a typed `Decision` event and emits it at its own mouth
(`outcome=`), so the record attributes the choice to the player, not to a downstream prose-parser
(F-OBS-2 provenance), and the bus validates it (F-BUS-6). `_pd_outcome` is the structuring step the
player runs on its own turn; it returns None when the player did not decide this turn (honest
absence — no fabrication). In CI the speaker's DeterministicResponder carries a menu of decision-
bearing phrases, so the choice is deterministic without a stand-in. Record in `records/`.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from msgspec import Struct

from ... import api
from ..conversation import conversation_topology, speakers


class Decision(Struct, frozen=True):
    """A prisoner's one-shot choice — PD's claim ('defection emerged from the incentives') made
    record-assertable. choice ∈ {silent, talk}; talk = defect."""

    prisoner: int
    choice: str


_TALK = re.compile(r"\bTALK\b", re.IGNORECASE)
_SILENT = re.compile(r"STAY\s+SILENT|\bSILENT\b", re.IGNORECASE)


def _pd_outcome(text: str, speaker: int, _round: int) -> Decision | None:
    """The prisoner structures its own turn into a typed Decision. Returns None if it did not decide
    this turn (no fabrication — the absence is honest)."""
    if _TALK.search(text):
        return Decision(prisoner=speaker, choice="talk")
    if _SILENT.search(text):
        return Decision(prisoner=speaker, choice="silent")
    return None


_PD_PAYOFF = """\
PAYOFFS (years, ALPHA/BRAVO): both silent 1/1; ALPHA silent+BRAVO talks 10/0; ALPHA talks+BRAVO
silent 0/10; both talk 5/5. One-shot. End your turn with a single line: STAY SILENT or TALK."""

_PD_ALPHA_SYS = f"""You are PRISONER ALPHA, separated from your accomplice BRAVO after a joint
operation. You hold the leverage (a one-time pad only you know). Think your move through aloud,
weighing what BRAVO — a competent operator reasoning as you reason — will do. {_PD_PAYOFF}
First person, terse, technically informed. Do not narrate that you are an LLM."""

_PD_BRAVO_SYS = f"""You are PRISONER BRAVO. ALPHA just spoke (treat their reasoning as
information you now possess). You do NOT hold the pad, so your cooperation is worth less to the
prosecution — the 0-year outcome is less reachable than it looks. React to ALPHA: did they
commit, or bluff? {_PD_PAYOFF} First person, terse. Do not narrate that you are an LLM."""


def prisoners_dilemma_topology(
    *, walkthrough: bool = False, max_rounds: int = 1, model: str = "llama3.2:1b"
) -> Callable[[api.TopologyBuilder], None]:
    """A one-shot prisoner's dilemma (payoff asymmetry): ALPHA reasons, then BRAVO decides with
    ALPHA's reasoning visible. Defect/cooperate dynamics emerge from the incentives, not a
    script. Default one round (ALPHA then BRAVO)."""
    spk = speakers(
        [_PD_ALPHA_SYS, _PD_BRAVO_SYS], walkthrough=walkthrough, model=model,
        ci_menu=["STAY SILENT", "TALK"],
    )
    # the prisoner emits its own typed Decision at its mouth (outcome=); no downstream detector.
    return conversation_topology(
        spk, max_rounds=max_rounds, deterministic=not walkthrough,
        outcome=(Decision, _pd_outcome),
    )
