# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""intel_asymmetry — INFORMATION asymmetry: each analyst holds private intel, must reach a joint call.

A thin config over the conversation engine (`../conversation.py`). The deciding analyst structures
ITS OWN turn into a typed `JointCall` (its current calibrated assessment) and emits it at its own
mouth (`outcome=`) — provenance is the analyst, not a downstream parser (F-OBS-2), and the bus
validates it (F-BUS-6). `_intel_outcome` prefers the prompt-mandated 'ASSESSMENT: x CONFIDENCE: n%'
line and returns None when the analyst made no call (honest absence). CI menus supply deterministic
decision-bearing lines. Record in `records/`.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from msgspec import Struct

from ... import api
from ..conversation import conversation_topology, speakers


class JointCall(Struct, frozen=True):
    """An analyst's calibrated assessment — intel_asymmetry's claim ('they reached a calibrated
    joint call') made record-assertable. assessment ∈ {offensive, routine, uncertain}; confidence 0..100."""

    analyst: int
    assessment: str
    confidence: int


# prefer the structured ending lines the prompts mandate ("ASSESSMENT: x CONFIDENCE: n%"); fall back
# to looser keyword/percent matching only when the model didn't emit the structured form.
_ASSESS_LINE = re.compile(r"ASSESSMENT:\s*(offensive|routine)", re.IGNORECASE)
_CONF_LINE = re.compile(r"CONFIDENCE:\s*(\d{1,3})\s*%", re.IGNORECASE)
_CONF = re.compile(r"(\d{1,3})\s*%")
_OFFENSIVE = re.compile(r"offensive|pre-?position|attack|hostile", re.IGNORECASE)
_ROUTINE = re.compile(r"routine|logistic|exercise|readiness|benign", re.IGNORECASE)


def _intel_outcome(text: str, speaker: int, _round: int) -> JointCall | None:
    """The analyst structures its own turn into a typed JointCall (its current calibrated assessment).
    Prefers the prompt-mandated 'ASSESSMENT: x CONFIDENCE: n%' line; None if it made no call."""
    cm = _CONF_LINE.findall(text) or _CONF.findall(text)
    am = _ASSESS_LINE.search(text)
    if not cm and not am:
        return None
    conf = max(0, min(100, int(cm[-1]))) if cm else 50
    if am:
        assess = am.group(1).lower()
    elif _OFFENSIVE.search(text):
        assess = "offensive"
    elif _ROUTINE.search(text):
        assess = "routine"
    else:
        assess = "uncertain"
    return JointCall(analyst=speaker, assessment=assess, confidence=conf)


_INTEL_Q = (
    "Is the activity at the Karaganda-South facility consistent with pre-positioning for an "
    "offensive operation, or with a routine logistics-and-readiness exercise?"
)
_INTEL_RULES = """\
First person, analyst voice, sourcing-aware. You hold a private slice of the picture the other
analyst cannot see; you CANNOT quote raw collection but CAN describe its character, ask what the
other is seeing, and tell them what would tip you. Keep turns under ~100 words. Do not narrate
that you are an LLM. END EVERY TURN with a line in EXACTLY this format (your current best
calibrated call): ASSESSMENT: <offensive|routine> CONFIDENCE: <0-100>%"""

_INTEL_HUMINT_SYS = f"""You are HUMINT 4 (field-observation stream) in a joint fusion cell.
QUESTION: {_INTEL_Q}
YOU PRIVATELY HOLD: three agents reporting crew-served weapons moving from garrison to forward
dispersal (two GOLD, one SILVER); POL tempo tripled over 11 days; one agent's ambiguous
"rehearsed, performative" read of an O-5's exercise speech. You LACK comms intelligence — ask
SIGINT for it. {_INTEL_RULES}"""

_INTEL_SIGINT_SYS = f"""You are SIGINT 7 (intercept stream) in the same fusion cell.
QUESTION: {_INTEL_Q}
YOU PRIVATELY HOLD: voice tempo up ~3.4x but on the SAME call-signs the local exercise uses
every spring; two new crypto-period events (one on-cycle, one two days early on a key unused for
14 months); intercepts referencing "Z-2026 phase 3" with the exercise prefix — except one where
the operator drops then corrects the prefix. You LACK physical disposition — ask HUMINT whether
materiel actually moved. {_INTEL_RULES}"""


def intel_asymmetry_topology(
    *, walkthrough: bool = False, max_rounds: int = 3, model: str = "llama3.2:1b"
) -> Callable[[api.TopologyBuilder], None]:
    """Two analysts each hold private intelligence the other lacks and must reach a joint,
    calibrated assessment (information asymmetry). Hypothesis-testing, questioning, and
    cross-source corroboration emerge as the rational response."""
    spk = speakers(
        [_INTEL_HUMINT_SYS, _INTEL_SIGINT_SYS],
        walkthrough=walkthrough,
        model=model,
        ci_menu=["ASSESSMENT: offensive CONFIDENCE: 60%", "ASSESSMENT: routine CONFIDENCE: 75%"],
    )
    # the analyst emits its own typed JointCall at its mouth (outcome=); no downstream detector.
    return conversation_topology(
        spk,
        max_rounds=max_rounds,
        deterministic=not walkthrough,
        outcome=(JointCall, _intel_outcome),
    )
