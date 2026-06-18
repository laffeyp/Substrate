"""Conversation demos — thin configs over the conversation topology (Wave 13).

Each demo is the conversation substrate (substrate/topologies/conversation.py) plus a set of
speaker system prompts that supply a *structural* driver — the emergence-vs-faking lens from the
recursive_strategy_refinment precursor: the dynamic (debate pressure-test, defect/cooperate,
cross-source corroboration) arises as a best-response to the setup, not from prescribing the
output shape. CI mode uses DeterministicResponder (the prompts are inert but the WIRING runs);
walkthrough mode hands each speaker an OllamaResponder carrying its system prompt.

  - debate            — POSITIONAL asymmetry: same information, opposite stipulated sides.
  - prisoners_dilemma — PAYOFF asymmetry: a one-shot game with a defect/cooperate decision.
  - intel_asymmetry   — INFORMATION asymmetry: each holds private intel, must reach a joint call.
"""

from __future__ import annotations

from collections.abc import Callable

from .. import api
from ..reference._models import DeterministicResponder, OllamaResponder, Responder
from .conversation import conversation_topology

# ── debate (positional asymmetry) ──────────────────────────────────────────────
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


def _speakers(systems: list[str], *, walkthrough: bool, model: str) -> list[Responder]:
    if walkthrough:
        return [OllamaResponder(model, system=s) for s in systems]
    return [DeterministicResponder(seed=i) for i, _ in enumerate(systems)]


def debate_topology(
    *, walkthrough: bool = False, max_rounds: int = 3, model: str = "llama3.2:1b"
) -> Callable[[api.TopologyBuilder], None]:
    """Two advocates argue opposite stipulated sides of one claim (positional asymmetry). The
    conversation pressure-tests the claim from both sides; no judge ships — both transcripts are
    the output. CI: deterministic wiring; walkthrough: real local LLMs carrying the PRO/CON
    system prompts."""
    speakers = _speakers([_DEBATE_PRO_SYS, _DEBATE_CON_SYS], walkthrough=walkthrough, model=model)
    return conversation_topology(speakers, max_rounds=max_rounds, deterministic=not walkthrough)


# ── prisoner's dilemma (payoff asymmetry) ──────────────────────────────────────
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
    speakers = _speakers([_PD_ALPHA_SYS, _PD_BRAVO_SYS], walkthrough=walkthrough, model=model)
    return conversation_topology(speakers, max_rounds=max_rounds, deterministic=not walkthrough)


# ── intel asymmetry (information asymmetry) ─────────────────────────────────────
_INTEL_Q = (
    "Is the activity at the Karaganda-South facility consistent with pre-positioning for an "
    "offensive operation, or with a routine logistics-and-readiness exercise?"
)
_INTEL_RULES = """\
First person, analyst voice, sourcing-aware. You hold a private slice of the picture the other
analyst cannot see; you CANNOT quote raw collection but CAN describe its character, ask what the
other is seeing, and tell them what would tip you. Drive toward a JOINT assessment with a
calibrated CONFIDENCE percentage. Keep turns under ~100 words. Do not narrate that you are an
LLM."""

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
    speakers = _speakers(
        [_INTEL_HUMINT_SYS, _INTEL_SIGINT_SYS], walkthrough=walkthrough, model=model
    )
    return conversation_topology(speakers, max_rounds=max_rounds, deterministic=not walkthrough)


# ── natural conversation (the emergence ablation — the flagship composition demo) ──
_NC_TOPIC = (
    "Is consciousness substrate-independent — could the same conscious experience arise in "
    "silicon, biological neurons, or a slow paper-and-pencil simulation, or is it tied to the "
    "wetware it evolved in?"
)
_NC_THIN = (
    "You are SPEAKER {n} in a conversation about: {topic} Develop your position incrementally "
    "(one thought per turn); speak directly, no preamble; do not narrate that you are an LLM."
)


def natural_conversation_topology(
    *,
    instruments: bool = False,
    walkthrough: bool = False,
    max_rounds: int = 4,
    model: str = "llama3.2:1b",
) -> Callable[[api.TopologyBuilder], None]:
    """Two THIN speakers (no character prescription) on one substantive question. The demo is the
    COMPARISON: with `instruments=True`, common ground accretes and a repair detector fires as a
    side-effect of every turn — both Routed back into the speakers — so adjustment-to-the-other
    compounds; with `instruments=False`, the same prompts produce two parallel monologues. The
    DELTA is the demonstration of composition (the precursor's headline emergence demo)."""
    systems = [_NC_THIN.format(n=i + 1, topic=_NC_TOPIC) for i in range(2)]
    speakers = _speakers(systems, walkthrough=walkthrough, model=model)
    return conversation_topology(
        speakers,
        max_rounds=max_rounds,
        deterministic=not walkthrough,
        common_ground=instruments,
        repair=instruments,
        scoring=instruments,
        # in CI, alternate the repair status by round so the record shows the detector both firing
        # and staying quiet (it discriminates, not just fires); the walkthrough judges for real.
        ci_repair_alternate=instruments,
    )
