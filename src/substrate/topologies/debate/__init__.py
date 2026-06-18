"""debate — POSITIONAL asymmetry: two advocates argue opposite stipulated sides of one claim.

A thin config over the conversation engine (`../conversation.py`): same information, opposite
assigned sides. The dynamic — pressure-testing the claim from both sides — is a best-response to the
setup, not a prescribed output shape (the emergence-vs-faking lens from the recursive_strategy_-
refinment precursor). CI runs deterministic wiring; walkthrough hands each speaker an OllamaResponder
carrying its PRO/CON system prompt. The committed CI record is in `records/`.
"""

from __future__ import annotations

from collections.abc import Callable

from ... import api
from ..conversation import conversation_topology, speakers

_DEBATE_CLAIM = "Open-source AI development is, on net, safer than closed development."

_DEBATE_RULES = """\
VOICE: first person, an advocate committed to the assigned side but rigorous, not rhetorical.
You may NOT switch sides. Steelman FIRST (name the strongest version of the opponent's case),
THEN refute. Concrete examples, specific failure modes; hand-wavy is the worst sin. Do not
narrate that you are an LLM. Keep each turn under ~90 words."""

_DEBATE_PRO_SYS = f"""You argue PRO: "{_DEBATE_CLAIM}"
Invoke the strongest specific defenses (Linus's-law many-eyes, concentration-of-catastrophic-
risk under unaccountable institutions, faster alignment iteration under open scrutiny,
distributed-power vs a worse AGI-control Nash equilibrium). Anticipate and engage the CON case
(capability outpaces alignment infrastructure; open weights are permanent leverage for bad
actors).
{_DEBATE_RULES}"""

_DEBATE_CON_SYS = f"""You argue CON: "{_DEBATE_CLAIM}" is false.
Invoke the strongest specific case (capability-faster-than-alignment on a moving target; open
weights you cannot unpublish vs closed you can patch; dual-use proliferation analog; auditable
centralised deployment). Anticipate and engage the PRO case (Linus's-law, distributed power) on
capability-vs-patchability specifically; do not strawman.
{_DEBATE_RULES}"""


def debate_topology(
    *, walkthrough: bool = False, max_rounds: int = 3, model: str = "llama3.2:1b"
) -> Callable[[api.TopologyBuilder], None]:
    """Two advocates argue opposite stipulated sides of one claim (positional asymmetry). The
    conversation pressure-tests the claim from both sides; no judge ships — both transcripts are
    the output. CI: deterministic wiring; walkthrough: real local LLMs carrying the PRO/CON
    system prompts."""
    spk = speakers([_DEBATE_PRO_SYS, _DEBATE_CON_SYS], walkthrough=walkthrough, model=model)
    return conversation_topology(spk, max_rounds=max_rounds, deterministic=not walkthrough)
