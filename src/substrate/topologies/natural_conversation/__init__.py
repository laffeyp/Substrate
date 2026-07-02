"""natural_conversation — the emergence ablation (the flagship composition demo).

Two THIN speakers (no character prescription) on one substantive question, over the conversation
engine (`../conversation.py`). The demo is the COMPARISON: with `instruments=True`, common ground
accretes and a repair detector fires as a side-effect of every turn — both Routed back into the
speakers — so adjustment-to-the-other compounds; with `instruments=False`, the same prompts produce
two parallel monologues. The DELTA is the demonstration of composition. The WITH record is in
`records/`; the WITHOUT arm's record is in `../natural_conversation_bare/records/` (same code, the
`instruments=False` config — `bundled.py` registers both so the ablation is a runnable contrast).
"""

from __future__ import annotations

from collections.abc import Callable

from ... import api
from ...adapters import DeterministicResponder, Responder
from ..conversation import Instrument, conversation_topology, speakers
from ..instruments.common_ground import CommonGround, common_ground_factory
from ..instruments.grader import Grade, grader_factory
from ..instruments.repair import REPAIR_OK, Repair, repair_factory

_NC_TOPIC = (
    "Is consciousness substrate-independent — could the same conscious experience arise in "
    "silicon, biological neurons, or a slow paper-and-pencil simulation, or is it tied to the "
    "wetware it evolved in?"
)
_NC_THIN = (
    "You are SPEAKER {n} in a conversation about: {topic} Develop your position incrementally "
    "(one thought per turn); speak directly, no preamble; do not narrate that you are an LLM."
)


def _emergence_instruments(
    *, deterministic: bool, responder: Responder | None = None
) -> list[Instrument]:
    """The three side-Producers whose WITH-vs-WITHOUT delta IS the natural-conversation ablation:
    common-ground accretion + a repair detector (both Routed back into the next speaker via `into`)
    + a grader (observation-only — its Grades are scored off the bus). The demo composes them and
    hands them to the engine; the engine knows nothing about them. CI uses a seeded stand-in."""
    r = responder or DeterministicResponder(seed=999)
    return [
        Instrument(
            "common-ground",
            [CommonGround],
            common_ground_factory(r),
            lambda ctx: {
                "transcript": list(ctx.views["transcript"].value()),
                "round": int(ctx.event.payload["round"]),
            },
            into="cg",
            via=lambda event: list(event.payload["facts"]),
        ),
        Instrument(
            # in CI, alternate the repair status by round so the record shows the detector both
            # firing and staying quiet (it discriminates, not just fires); walkthrough judges for real.
            "repair",
            [Repair],
            repair_factory(r, ci_status=REPAIR_OK, alternate=True),
            lambda ctx: {"round": int(ctx.event.payload["round"])},
            into="repair",
            via=lambda event: {"status": event.payload["status"], "note": event.payload["note"]},
        ),
        Instrument(
            "grader",
            [Grade],
            grader_factory(r),
            lambda ctx: {
                "round": int(ctx.event.payload["round"]),
                "prior_turns": list(ctx.views["transcript"].value()),
            },
        ),
    ]


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
    spk = speakers(systems, walkthrough=walkthrough, model=model)
    insts = _emergence_instruments(deterministic=not walkthrough) if instruments else ()
    return conversation_topology(
        spk, max_rounds=max_rounds, deterministic=not walkthrough, instruments=insts
    )
