"""Conversation topology — the general N-speaker turn-based substrate (Wave 13).

The shape every conversation demo lifted from the recursive_strategy_refinment precursor
(debate, prisoner's dilemma, intel asymmetry, natural conversation) instantiates: N speaker
Producers take turns; each reads the transcript-so-far and emits one Turn; a round-robin
Trigger fires the next speaker; the run is bounded by a round budget and ended early when any
speaker emits Converged. The precursor hand-rolled this as a cascade scheduler; here it falls
out of Producers + one Trigger per speaker + a transcript View + a threshold termination.

Demos are thin configs over this: debate = two opposing-stipulated responders; prisoner's
dilemma = two responders with asymmetric payoff prompts; intel asymmetry = two responders with
private-knowledge inputs. The system prompts live with each demo; this module is the substrate.

Determinism note: this is TURN-BASED (speaker k+1 fires when speaker k's Turn lands), the
deterministic core. The precursor's concurrent chunked-cascade (all N stream at once, next
fires at a chunk boundary) is the pair_coding pattern; a conversation can adopt it later, but
turn-based keeps the CI record deterministic for Level-2 replay.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, NamedTuple

from msgspec import Struct

from .. import api
from ..reference._models import DeterministicResponder, Responder
from .instruments.common_ground import CommonGround, common_ground_factory
from .instruments.grader import Grade, grader_factory
from .instruments.repair import REPAIR_OK, Repair, repair_factory

_Factory = Callable[[], Any]


class Turn(Struct, frozen=True):
    speaker: int
    text: str
    round: int


class Converged(Struct, frozen=True):
    by: int  # the speaker who declared convergence (CONVERGED early-stop)


class Detector(NamedTuple):
    """A per-game OUTCOME detector: a side Producer fired on each Turn that emits a typed outcome
    event (the game's claim as a record assertion, not prose). Deterministic — a pure parse of the
    turn, no model. Installed observation-only (no Route), exactly like the grader instrument. The
    game (debate / PD / intel) supplies the kind + the factory that reads a Turn and emits it; the
    CI stub text has no decision token, so a detector emits a deterministic stand-in there (the
    wiring is what CI proves) and parses the real choice in walkthrough mode."""

    name: str
    schemas: list[type]
    factory: _Factory
    input_builder: Callable[[api.TriggerContext], Any]


def _next_round(turn: dict[str, Any], n: int) -> int:
    # the round advances when the round-robin wraps from speaker N back to speaker 1.
    return int(turn["round"]) + 1 if int(turn["speaker"]) >= n else int(turn["round"])


def _after_predicate(k: int, n: int, max_rounds: int) -> Callable[[api.TriggerContext], bool]:
    # fire speaker k+1 after speaker k's Turn, while within the round budget (closure over k/n,
    # so the callback is a clean single-`ctx` lambda — no default-arg trick mypy can't infer).
    return lambda ctx: (
        int(ctx.event.payload["speaker"]) == k
        and _next_round(ctx.event.payload, n) <= max_rounds
    )


def _after_input(nxt: int, n: int) -> Callable[[api.TriggerContext], Any]:
    return lambda ctx: {
        "round": _next_round(ctx.event.payload, n),
        "speaker_id": nxt,
        "prior_turns": list(ctx.views["transcript"].value()),
        "common_ground": ctx.staged.get("cg"),
        "repair": ctx.staged.get("repair"),
    }


def _speaker_factory(
    speaker_id: int, responder: Responder, converge_at: tuple[int, int] | None
) -> _Factory:
    async def speaker(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        prior = inp.get("prior_turns", []) if hasattr(inp, "get") else []
        cg = inp.get("common_ground") if hasattr(inp, "get") else None
        rep = inp.get("repair") if hasattr(inp, "get") else None
        transcript = "\n".join(f"S{t['speaker']}: {t['text']}" for t in prior)
        # the instruments feed the speaker (this is the emergence wiring): the accreted common
        # ground and any requires-repair cue enter the prompt, so a WITH-instruments run produces
        # different turns than the bare run — the natural-conversation ablation's whole point.
        extra = ""
        if cg:
            extra += f"\nCOMMON GROUND SO FAR: {cg}"
        if rep and rep.get("status") != REPAIR_OK:
            extra += f"\nREQUIRES REPAIR: {rep.get('note', '')}"
        # The user message must INSTRUCT the turn, not just dump the transcript: a real model handed
        # a bare transcript "completes" it by echoing the last line (the round-2 echo bug). In CI the
        # deterministic stub hashes the whole prompt, so any wording yields a unique stub — the bug is
        # invisible there and only a real model exposes it. Frame the speaker's task explicitly.
        if prior:
            user_msg = (
                f"You are speaker {speaker_id}. The conversation so far:\n\n{transcript}\n\n"
                f"Write speaker {speaker_id}'s NEXT turn now — advance your own position and respond "
                f"to what was just said. Do not repeat or copy an earlier turn.{extra}"
            )
        else:
            user_msg = f"You are speaker {speaker_id}. Open the conversation.{extra}"
        text = responder.respond(user_msg)
        # strip any leaked transcript label ("S2:", even doubled "S2: S2:") the model copied from the
        # transcript format into its own output — cosmetic, keeps the recorded turn clean.
        text = re.sub(r"^\s*(S\d+:\s*)+", "", text)
        # A deterministic convergence hook for CI (in walkthrough, a speaker converges by the
        # responder emitting the CONVERGED sentinel; that path is a demo concern). converge_at
        # names the (speaker, round) that declares convergence, so tests can exercise early-stop.
        if converge_at is not None and converge_at == (speaker_id, rnd):
            yield Converged(by=speaker_id)
        else:
            # cap the recorded turn — generous enough to retain a trailing decision line (PD's
            # "STAY SILENT / TALK", intel's calibrated %), which a per-game detector parses. CI stub
            # text is ~20 chars, so this cap only bounds verbose real-model turns.
            yield Turn(speaker=speaker_id, text=text[:700], round=rnd)

    return lambda: speaker


def conversation_topology(
    responders: Sequence[Responder],
    *,
    max_rounds: int = 3,
    converge_at: tuple[int, int] | None = None,
    deterministic: bool = True,
    watchdog_seconds: float = 60.0,
    common_ground: bool = False,
    repair: bool = False,
    scoring: bool = False,
    instrument_responder: Responder | None = None,
    ci_repair_status: str = REPAIR_OK,
    ci_repair_alternate: bool = False,
    detectors: Sequence[Detector] = (),
) -> Callable[[api.TopologyBuilder], None]:
    """Build an N-speaker turn-based conversation. `responders` is one Responder per speaker
    (N = len). Speaker 1 opens; a round-robin Trigger fires the next speaker on each Turn until
    `max_rounds` rounds complete; any speaker emitting Converged ends the run early. `converge_at`
    (speaker, round) makes that speaker declare convergence (deterministic early-stop for CI).

    The instrument cues (common_ground / repair) a speaker sees reflect the PREVIOUS turn's
    instrument output — the same stage-then-read lag as pair_coding (a side Producer for turn T
    stages AFTER the next-speaker Trigger for turn T reads the slot). Deterministic, and
    semantically right (you react to what was just said); not same-turn coupling."""

    n = len(responders)
    if n < 2:
        raise api.RegistrationError("a conversation needs at least 2 speakers")

    def topo(b: api.TopologyBuilder) -> None:
        for i, r in enumerate(responders, start=1):
            b.producer_kind(
                f"speaker-{i}",
                schemas=[Turn, Converged],
                schema_version=1,
                factory=_speaker_factory(i, r, converge_at),
                deterministic=deterministic,
            )
        b.initial("speaker-1", input={"round": 1, "prior_turns": []})
        # the transcript every speaker reads (Turn events only — not Converged).
        b.view("transcript", api.KindBuffer("Turn"))
        # optional emergence instruments: side Producers fired on each Turn that emit a typed
        # event Routed into the next speaker's input. Toggling these on/off over the SAME prompts
        # is the natural-conversation ablation (the delta is the demo). Non-load-bearing.
        inst_responder = instrument_responder or DeterministicResponder(seed=999)
        # each instrument is a side Producer fired once per Turn (the identical
        # producer_kind+trigger+route triple) — `b.instrument` collapses it to one call.
        if common_ground:
            b.instrument(
                "common-ground",
                on="Turn",
                schemas=[CommonGround],
                factory=common_ground_factory(inst_responder),
                deterministic=deterministic,
                input_builder=lambda ctx: {
                    "transcript": list(ctx.views["transcript"].value()),
                    "round": int(ctx.event.payload["round"]),
                },
                into="cg",
                via=lambda event: list(event.payload["facts"]),
            )
        if repair:
            b.instrument(
                "repair",
                on="Turn",
                schemas=[Repair],
                factory=repair_factory(
                    inst_responder, ci_status=ci_repair_status, alternate=ci_repair_alternate
                ),
                deterministic=deterministic,
                input_builder=lambda ctx: {"round": int(ctx.event.payload["round"])},
                into="repair",
                via=lambda event: {
                    "status": event.payload["status"],
                    "note": event.payload["note"],
                },
            )
        if scoring:
            # the grader scores the prior speaker's confidence claims against the turn that
            # follows; the Grade events on the bus are scored by a proper rule post-run — an
            # observation-only instrument (no `into=`/Route), the payoff that closes the
            # cheap-talk loop.
            b.instrument(
                "grader",
                on="Turn",
                schemas=[Grade],
                factory=grader_factory(inst_responder),
                deterministic=deterministic,
                input_builder=lambda ctx: {
                    "round": int(ctx.event.payload["round"]),
                    "prior_turns": list(ctx.views["transcript"].value()),
                },
            )
        # per-game OUTCOME detectors: a side Producer fired on each Turn that emits the game's typed
        # outcome (Decision / JointCall) — the claim as a record assertion. Observation-only (no
        # Route), deterministic (a pure parse of the Turn). The natural-conversation `score` grader
        # is the same shape; this generalizes it to the game claims.
        for det in detectors:
            b.instrument(
                det.name,
                on="Turn",
                schemas=det.schemas,
                factory=det.factory,
                deterministic=True,
                input_builder=det.input_builder,
            )
        # one round-robin Trigger per speaker: after speaker k's Turn, fire speaker k+1 (wrapping
        # N→1), carrying the next round and the transcript-so-far, while within the round budget.
        for k in range(1, n + 1):
            nxt = k + 1 if k < n else 1
            b.trigger(
                f"after-{k}",
                subscription=api.Subscription(kinds=frozenset({"Turn"})),
                predicate=_after_predicate(k, n, max_rounds),
                starts=f"speaker-{nxt}",
                input_builder=_after_input(nxt, n),
                policy=api.PerEvent(),
            )
        # end on the first Converged (early-stop), else on quiescence once the round budget stops
        # the cascade (the watchdog also backstops a wedged speaker — see code_review for the
        # honest bound: quiescence, not a hard deadline).
        b.termination(
            api.any_of(
                api.threshold_count("Converged", 1),
                api.quiescence_with_watchdog(seconds=watchdog_seconds),
            )
        )

    return topo
