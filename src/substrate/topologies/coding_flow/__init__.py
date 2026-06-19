"""coding_flow — best-of-N code generation with build-validation and a correction loop.

The precursor (prompt-factory) orchestrated open-source models to write code ONE candidate at a
time, validated by a project build. This topology generalizes that and adds the thing Substrate
makes free that a sequential orchestrator can't: N candidates drafted CONCURRENTLY — typically one
from each of N DIFFERENT models (an ensemble: qwen-coder, deepseek, llama, … each with its own
strengths and failure modes — that heterogeneity, not just sampling temperature, is where best-of-N
gets its diversity) — each build-validated in parallel, the passing one selected; and on a round
where none pass, the gate failures are fed back into a fresh round of N drafters, bounded. The whole
search — every candidate, every gate run, every correction round — is one replayable record.

Heterogeneous by the rule: DRAFTING (initial + correction) is the only model work. SEEDING,
VALIDATION (running the gate), SELECTING, and CORRECTING are deterministic code — the truth is a
test run, never an LLM's opinion of its own code.

    seeder ─N×Draft─▶ drafter (MODEL) ─Candidate─▶ validator (runs the GATE) ─Verdict─┐
                         ▲                                                            │
       Draft(round+1, failures) ◀── judge ◀──[round done, none passed, rounds left]──┤
                          Exhausted ◀── judge ◀──[round done, none passed, out of rounds]
                             Solved ◀── judge ◀──[round done, one passed]─────────────┘

The judge fires ONCE per round, after all N verdicts land — so the full best-of-N comparison is on
the record before it selects, corrects, or gives up.

The flow is NOT replay-deterministic (the gate is a real subprocess — variable timing, so verdict
order varies); it is OUTCOME-deterministic in CI (a known-good candidate passes -> Solved). So it is
a RUN-and-observe demo, not a committed-record replay demo — `deterministic=False` is honest.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ... import api
from ...reference._models import DeterministicResponder, OllamaResponder, Responder, call_responder
from .gate import parse_artifacts, run_gate
from .task import CodingTask, kvstore_task

_Factory = Callable[[], Any]


class Draft(Struct, frozen=True):
    """A request to draft a candidate. `context` is "" for the seed round, or the prior round's gate
    failures for a correction round."""

    round: int
    slot: int
    context: str


class Candidate(Struct, frozen=True):
    """A drafter's output — the raw `# path:`-headed artifact text the validator parses + writes."""

    round: int
    slot: int
    response: str


class Verdict(Struct, frozen=True):
    """The gate's verdict on one candidate. `passed` is exit-code truth; `summary` the normalized log."""

    round: int
    slot: int
    passed: bool
    returncode: int
    summary: str


class Solved(Struct, frozen=True):
    """A passing candidate was selected — the success terminal."""

    round: int
    slot: int


class Exhausted(Struct, frozen=True):
    """Every round's candidates failed the gate and the round budget is spent — the give-up terminal."""

    rounds: int


def _seeder_factory(n: int) -> _Factory:
    async def seed(_inp: Any) -> AsyncIterator[Draft]:
        for i in range(n):
            yield Draft(round=1, slot=i, context="")

    return lambda: seed


def _drafter_factory(task: CodingTask, responders: list[Responder]) -> _Factory:
    async def draft(inp: Any) -> AsyncIterator[Candidate]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        context = str(inp.get("context", "")) if hasattr(inp, "get") else ""
        prompt = task.spec
        if context:
            prompt += (
                "\n\nA PRIOR attempt FAILED the gate. Return a corrected full set of files. "
                f"The gate output was:\n{context}"
            )
        response = await call_responder(responders[slot % len(responders)], prompt)
        yield Candidate(round=rnd, slot=slot, response=response)

    return lambda: draft


def _validator_factory(task: CodingTask, timeout: float) -> _Factory:
    async def validate(inp: Any) -> AsyncIterator[Verdict]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        slot = int(inp.get("slot", 0)) if hasattr(inp, "get") else 0
        response = str(inp.get("response", "")) if hasattr(inp, "get") else ""
        artifacts = {**task.fixtures, **parse_artifacts(response)}
        # the gate is a blocking subprocess; offload it so N candidates validate CONCURRENTLY (the
        # build-validation parallelism the sequential precursor couldn't do).
        result = await asyncio.to_thread(run_gate, artifacts, task.gate, timeout=timeout)
        yield Verdict(
            round=rnd,
            slot=slot,
            passed=result.passed,
            returncode=result.returncode,
            summary=result.summary,
        )

    return lambda: validate


def _judge_factory(n: int, max_rounds: int) -> _Factory:
    """Fires once per round, after all N verdicts are in. The full best-of-N comparison is on the
    record by the time it runs: select the (first) passing candidate -> Solved; else feed every
    candidate's gate failures back into a fresh round -> N Drafts; else, out of rounds -> Exhausted."""

    async def judge(inp: Any) -> AsyncIterator[Any]:
        rnd = int(inp.get("round", 1)) if hasattr(inp, "get") else 1
        verdicts = list(inp.get("verdicts", [])) if hasattr(inp, "get") else []
        passing = [v for v in verdicts if v["passed"]]
        if passing:
            yield Solved(round=rnd, slot=int(passing[0]["slot"]))
        elif rnd < max_rounds:
            failures = "\n\n".join(
                f"[candidate {v['slot']}] gate exit {v['returncode']}\n{v['summary']}"
                for v in verdicts
            )
            for i in range(n):
                yield Draft(round=rnd + 1, slot=i, context=failures)
        else:
            yield Exhausted(rounds=rnd)

    return lambda: judge


def _round_verdicts(ctx: api.TriggerContext, rnd: int) -> list[dict[str, Any]]:
    return [v for v in ctx.views["verdicts"].value() if int(v["round"]) == rnd]


def coding_flow_topology(
    task: CodingTask | None = None,
    *,
    responders: list[Responder],
    n: int = 3,
    max_rounds: int = 2,
    timeout: float = 60.0,
    deterministic: bool = False,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the coding-flow topology: a seeder fans out N drafters; each Candidate is gate-validated
    by a validator; when a round's N verdicts are all in, the judge selects the passing candidate
    (-> Solved), or — if none passed — re-drafts N candidates with every failure fed back (round+1),
    or, out of rounds, emits Exhausted. Terminates on Solved or Exhausted. `responders` (one per slot)
    is the model seam — DeterministicResponder stand-ins in CI, OllamaResponder in walkthrough."""
    job = task or kvstore_task()

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "seeder",
            schemas=[Draft],
            schema_version=1,
            factory=_seeder_factory(n),
            deterministic=deterministic,
        )
        b.producer_kind(
            "drafter",
            schemas=[Candidate],
            schema_version=1,
            factory=_drafter_factory(job, responders),
            deterministic=deterministic,
        )
        b.producer_kind(
            "validator",
            schemas=[Verdict],
            schema_version=1,
            factory=_validator_factory(job, timeout),
            deterministic=deterministic,
        )
        b.producer_kind(
            "judge",
            schemas=[Solved, Draft, Exhausted],
            schema_version=1,
            factory=_judge_factory(n, max_rounds),
            deterministic=deterministic,
        )
        b.view("verdicts", api.KindBuffer("Verdict"))
        b.initial("seeder", input=None)
        # one Trigger drafts a candidate per Draft (seed OR correction) — the recursive best-of-N loop.
        b.trigger(
            "draft",
            subscription=api.Subscription(kinds=frozenset({"Draft"})),
            predicate=lambda ctx: True,
            starts="drafter",
            input_builder=lambda ctx: {
                "round": int(ctx.event.payload["round"]),
                "slot": int(ctx.event.payload["slot"]),
                "context": ctx.event.payload["context"],
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "validate",
            subscription=api.Subscription(kinds=frozenset({"Candidate"})),
            predicate=lambda ctx: True,
            starts="validator",
            input_builder=lambda ctx: {
                "round": int(ctx.event.payload["round"]),
                "slot": int(ctx.event.payload["slot"]),
                "response": ctx.event.payload["response"],
            },
            policy=api.PerEvent(),
        )
        # a round is done when all N of its verdicts are in; the judge then selects the passing
        # candidate, or corrects, or gives up. Fires ONCE per round — at that round's Nth verdict.
        b.trigger(
            "judge",
            subscription=api.Subscription(kinds=frozenset({"Verdict"})),
            predicate=lambda ctx: len(_round_verdicts(ctx, int(ctx.event.payload["round"]))) >= n,
            starts="judge",
            input_builder=lambda ctx: {
                "round": int(ctx.event.payload["round"]),
                "verdicts": _round_verdicts(ctx, int(ctx.event.payload["round"])),
            },
            policy=api.PerEvent(),
        )
        b.termination(
            api.any_of(api.threshold_count("Solved", 1), api.threshold_count("Exhausted", 1))
        )

    return topo


def ci_responders(task: CodingTask, n: int = 3) -> list[Responder]:
    """CI stand-ins: a deliberate best-of-N mix — the last slot drafts the known-GOOD candidate, the
    rest draft the known-BAD one. So round 1 shows real candidates failing the gate and one passing,
    the passing one selected. Deterministic in OUTCOME (which is what the CI test asserts)."""
    return [
        DeterministicResponder(seed=i, menu=[task.ci_good if i == n - 1 else task.ci_bad])
        for i in range(n)
    ]


def walkthrough_responders(
    models: list[str] | str, *, temperature: float = 0.6, max_tokens: int = 900
) -> list[Responder]:
    """Best-of-N over an ENSEMBLE — one drafter per model. The real diversity in best-of-N comes from
    N DIFFERENT models (each family has its own strengths + failure modes), not just N samples of one;
    so pass several distinct model names — e.g. ["qwen2.5-coder:7b", "deepseek-r1:8b", "llama3:8b"].
    The topology hands slot i to `models[i]`. A single name (or a name repeated) still works — that is
    degenerate best-of-N, sampling-temperature diversity only — but the point is heterogeneity."""
    names = [models] if isinstance(models, str) else list(models)
    return [OllamaResponder(m, temperature=temperature, max_tokens=max_tokens) for m in names]
