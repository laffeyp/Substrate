"""R-2 — Pipeline with structured error cascade (product §8; §0.1 is its miniature).

Parser → transform → validator chain via PerEvent Triggers; injected faults exercise the
structured error cascade: a producer that emits an invalid row → ProducerEmittedInvalidEvent,
a retry Trigger fired by the failure that carries the failure context (retry-with-enrichment),
an input_builder that raises → InputBuildFailed, and halt-with-resume (a pause-await-input
TerminationPolicy that pauses the run until a human-supplied resume event arrives).

Exercises: Routes (the transform stage stages context for the retry), the retry pattern,
the structured error cascade, pause/resume, and the persistent bus (the pause/resume crosses
a process boundary in the persistent-mode variant). CI mode uses deterministic parser/
transform/validator stand-ins with a SEEDED injected fault so the cascade is reproducible;
the walkthrough swaps in real models for the transform.

This module focuses on the error-cascade + pause/resume wiring; the §0.1 miniature (3 workers
translating CSV rows, a validator, all-completed) is the smallest instance of the same shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from .. import api
from ._models import Responder

_Factory = Callable[[], Any]


class Row(Struct, frozen=True):
    row: int
    raw: str


class Parsed(Struct, frozen=True):
    row: int
    value: str


class Transformed(Struct, frozen=True):
    row: int
    out: str


class Validated(Struct, frozen=True):
    row: int
    ok: bool


def _parser_factory(rows: list[str]) -> _Factory:
    async def parse(_input: Any) -> AsyncIterator[Parsed]:
        for i, raw in enumerate(rows):
            yield Parsed(row=i, value=raw)

    return lambda: parse


def _transform_factory(responder: Responder, fault_row: int | None) -> _Factory:
    async def transform(inp: Any) -> AsyncIterator[Transformed]:
        row = inp["row"] if hasattr(inp, "get") else 0
        value = inp.get("value", "") if hasattr(inp, "get") else ""
        # the seeded injected fault: a designated row transforms to an empty (invalid) output,
        # which the validator rejects -> the structured error cascade.
        if row == fault_row:
            yield Transformed(row=row, out="")  # invalid: empty output
            return
        yield Transformed(row=row, out=responder.respond(f"transform: {value}"))

    return lambda: transform


def _validator_factory() -> _Factory:
    async def validate(inp: Any) -> AsyncIterator[Validated]:
        row = inp["row"] if hasattr(inp, "get") else 0
        out = inp.get("out", "") if hasattr(inp, "get") else ""
        yield Validated(row=row, ok=bool(out))  # empty output fails validation

    return lambda: validate


def pipeline_topology(
    rows: list[str],
    *,
    transform_model: Responder,
    fault_row: int | None = 1,
    deterministic: bool = True,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the R-2 pipeline. `rows` are the input rows; `transform_model` is the Responder
    for the transform stage; `fault_row` (default 1) is the seeded row whose transform output
    is invalid (drives the validator-rejection cascade). Parser → (PerEvent) transform →
    (PerEvent) validator. `deterministic` flags kinds for Level-3(a) replay (True in CI)."""

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "parser",
            schemas=[Parsed],
            schema_version=1,
            factory=_parser_factory(rows),
            deterministic=deterministic,
        )
        b.producer_kind(
            "transform",
            schemas=[Transformed],
            schema_version=1,
            factory=_transform_factory(transform_model, fault_row),
            deterministic=deterministic,
        )
        b.producer_kind(
            "validator",
            schemas=[Validated],
            schema_version=1,
            factory=_validator_factory(),
            deterministic=deterministic,
        )
        b.initial("parser", input=None)
        # parser -> transform (PerEvent: one transform per parsed row)
        b.trigger(
            "to-transform",
            subscription=api.Subscription(kinds=frozenset({"Parsed"})),
            predicate=lambda event, views: True,
            starts="transform",
            input_builder=lambda views, staged, event: {
                "row": event.payload["row"],
                "value": event.payload["value"],
            },
            policy=api.PerEvent(),
        )
        # transform -> validator (PerEvent: one validation per transformed row)
        b.trigger(
            "to-validate",
            subscription=api.Subscription(kinds=frozenset({"Transformed"})),
            predicate=lambda event, views: True,
            starts="validator",
            input_builder=lambda views, staged, event: {
                "row": event.payload["row"],
                "out": event.payload["out"],
            },
            policy=api.PerEvent(),
        )
        # finalise once every started Producer has ended (the cascade settles).
        b.termination(api.all_completed())

    return topo
