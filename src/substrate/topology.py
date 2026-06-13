"""TopologyBuilder + the registration set + the topology registry (design §4.1).

A topology is a factory function receiving a TopologyBuilder; one builder method per
primitive (the builder methods ARE the vocabulary). Registration is frozen when the
factory returns; the runtime reads the Registration to drive the run. Static checks
that the runtime would otherwise raise at start are caught at build time (design §5.5).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from msgspec import Struct

from .constants import is_reserved
from .errors import SubstrateError
from .policies import TerminationPolicy
from .protocols import Producer, View
from .triggers import Cooldown, FiringPolicy, Logical, PerEvent, WallClock, WhileTrue
from .types import Subscription


class RegistrationError(SubstrateError):
    """A topology is malformed (design §6.1). Raised at build time, before any run."""


@dataclass(frozen=True)
class ProducerKindReg:
    kind: str
    schemas: dict[str, tuple[type, int]]  # event-kind name -> (Struct type, schema_version)
    factory: Callable[[], Producer]
    deterministic: bool
    author_version: str | None
    # composition export map {inner_kind -> outer_schema_name}, derived from the embedded
    # substrate's own map (the SINGLE source of truth) — None for a non-embedded kind. The
    # manifest reads this; there is no parallel hand-maintained copy.
    export_map: dict[str, str] | None = None


@dataclass(frozen=True)
class TriggerReg:
    id: str
    subscription: Subscription
    predicate: Callable[..., bool]
    starts: str
    input_builder: Callable[..., Any]
    policy: FiringPolicy
    cooldown: Cooldown


@dataclass(frozen=True)
class RouteReg:
    id: str
    subscription: Subscription
    slot: str
    transform: Callable[[Any], Any]


@dataclass(frozen=True)
class InitialReg:
    kind: str
    input: Any


@dataclass
class Registration:
    producer_kinds: dict[str, ProducerKindReg] = field(default_factory=dict)
    views: dict[str, View] = field(default_factory=dict)
    triggers: list[TriggerReg] = field(default_factory=list)
    routes: list[RouteReg] = field(default_factory=list)
    initials: list[InitialReg] = field(default_factory=list)
    termination: TerminationPolicy | None = None
    baseline: dict[str, Any] = field(default_factory=dict)
    has_wall_clock_cooldown: bool = False


class TopologyBuilder:
    """Declares a topology — the Producers, Triggers, Routes, Views, and TerminationPolicy a run
    is built from. A `topology(b)` function receives one of these and calls its methods; the
    runtime builds + statically validates it (`build`) before the run opens. This is the primary
    authoring surface."""

    def __init__(self) -> None:
        self._reg = Registration()

    def producer_kind(
        self,
        kind: str,
        *,
        schemas: Sequence[type],
        schema_version: int,
        factory: Callable[[], Producer],
        deterministic: bool = False,
        author_version: str | None = None,
    ) -> None:
        """Register a Producer kind: its name, the frozen msgspec Struct event schemas it may
        emit (+ schema_version), and a `factory()` returning the Producer callable. Set
        `deterministic=True` if the same input always yields the same events (it gates Level-3a
        replay). Names using the reserved `substrate.` prefix are rejected."""
        if is_reserved(kind):
            raise RegistrationError(
                f'producer_kind "{kind}": Producer kinds MUST NOT use the reserved '
                f'"substrate." prefix (F-OBS-5).'
            )
        schema_map: dict[str, tuple[type, int]] = {}
        for s in schemas:
            if not (isinstance(s, type) and issubclass(s, Struct)):
                raise RegistrationError(
                    f'producer_kind "{kind}": schema {s!r} is not a msgspec Struct.'
                )
            if not getattr(s, "__struct_config__").frozen:
                raise RegistrationError(
                    f'producer_kind "{kind}".schemas: {s.__name__} is not frozen.\n'
                    f"  Producer event schemas must be declared with frozen=True so the\n"
                    f"  runtime can enforce input immutability by construction (F-PROD-3)."
                )
            if is_reserved(s.__name__):
                raise RegistrationError(
                    f'producer_kind "{kind}": event kind "{s.__name__}" collides with the '
                    f"reserved namespace."
                )
            schema_map[s.__name__] = (s, schema_version)
        # Derive the composition export map from the embedded substrate's OWN map (single
        # source of truth): an embedded_substrate `start` callable carries
        # __substrate_export_map__; build the factory once (cheap — just constructs the
        # closure, runs nothing) to read it. Non-embedded factories carry no such attribute.
        export_map: dict[str, str] | None = None
        try:
            start = factory()
            raw = getattr(start, "__substrate_export_map__", None)
            if isinstance(raw, dict):
                export_map = dict(raw)
        except Exception:
            export_map = None  # a factory that can't be pre-built has no static export map
        self._reg.producer_kinds[kind] = ProducerKindReg(
            kind, schema_map, factory, deterministic, author_version, export_map
        )

    def view(self, name: str, view: View) -> None:
        """Register a named View — a deterministic incremental projection over the bus (e.g.
        KindBuffer, KindCount) that Predicates read. The View declares what it subscribes to; an
        empty subscription is rejected (never an implicit subscribe-to-everything)."""
        if view.subscription.is_empty():
            raise RegistrationError(
                f'view "{name}": subscription is empty; subscribe to a kind/producer '
                f"(both empty is never an implicit subscribe-to-everything)."
            )
        self._reg.views[name] = view

    def trigger(
        self,
        id: str,
        *,
        subscription: Subscription,
        predicate: Callable[..., bool],
        starts: str,
        input_builder: Callable[..., Any],
        policy: FiringPolicy | None = None,
        cooldown: Cooldown | None = None,
    ) -> None:
        """Register a Trigger: when an event matching `subscription` is appended and `predicate`
        (over the Views) holds, start a `starts` Producer with the input from `input_builder`.
        `policy` (default PerEvent) controls how often it fires — Once, PerEvent, PerKey,
        WhileTrue; `cooldown` throttles it. The firing and its resolved input are recorded."""
        if subscription.is_empty():
            raise RegistrationError(
                f'trigger "{id}": subscription is empty; subscribe to a kind/producer.'
            )
        pol = policy or PerEvent()
        # Cooldown is a single trigger-level concept enforced once by the runtime. A
        # WhileTrue policy may carry its cooldown as a constructor arg; lift it to the
        # trigger level when no explicit cooldown= is given, so there is exactly one
        # enforcement point (no double-throttle).
        cd = cooldown
        if cd is None and isinstance(pol, WhileTrue):
            cd = pol.cooldown
        cd = cd or Logical(0)
        if isinstance(cd, WallClock):
            self._reg.has_wall_clock_cooldown = True
        self._reg.triggers.append(
            TriggerReg(id, subscription, predicate, starts, input_builder, pol, cd)
        )

    def route(
        self, id: str, *, subscription: Subscription, slot: str, transform: Callable[[Any], Any]
    ) -> None:
        """Register a Route: on an event matching `subscription`, stage `transform(event)` into
        the named `slot` so a later Trigger's input_builder can read it (carrying context — e.g.
        a failure reason — forward into the Producer it starts). The staging is recorded."""
        if subscription.is_empty():
            raise RegistrationError(f'route "{id}": subscription is empty.')
        self._reg.routes.append(RouteReg(id, subscription, slot, transform))

    def initial(self, kind: str, *, input: Any = None) -> None:
        """Declare an initial Producer started at run open (seq 0), with `input`. A topology
        needs at least one initial Producer (or it has nothing to do)."""
        self._reg.initials.append(InitialReg(kind, input))

    def termination(self, policy: TerminationPolicy, *, scope: str = "run") -> None:
        """Set the TerminationPolicy that decides when the run ends (see the termination recipes:
        quiescence_with_watchdog, threshold_count, all_completed, pause_await_input, ...). v0.1
        ships run-scoped termination; per-Producer scoping is a documented extension."""
        self._reg.termination = policy

    # NOTE: there is deliberately NO `b.export`. The composition export map is declared ONCE,
    # at the embedded Producer kind via `embedded_substrate(exports=...)` (F-COMP-1 / §20: the
    # ExportMap is part of the EmbeddedSubstrate kind's declaration). The RunStarted manifest
    # DERIVES its exports section from that single source (producer_kind reads the embedded
    # substrate's own export map), so the recorded boundary can never drift from the map the
    # translator actually uses. (Earlier there was a parallel `b.export` copy — removed; it was
    # the two-source-of-truth flagged in review.)

    def baseline(self, **metadata: Any) -> None:
        """Attach run metadata (fixtures, seeds, environment identifiers) recorded in the
        RunStarted manifest, so every record is interpretable from a known baseline."""
        self._reg.baseline.update(metadata)

    def build(self) -> Registration:
        """Freeze and statically validate (design §5.5). Raises RegistrationError."""
        for t in self._reg.triggers:
            if t.starts not in self._reg.producer_kinds:
                raise RegistrationError(
                    f'trigger "{t.id}": starts="{t.starts}" — unknown Producer kind.'
                )
        for init in self._reg.initials:
            if init.kind not in self._reg.producer_kinds:
                raise RegistrationError(f'initial "{init.kind}" — unknown Producer kind.')
        return self._reg


# ── registry (CLI looks topologies up by name) ─────────────────────────────────
_REGISTRY: dict[str, Callable[[TopologyBuilder], None]] = {}


def register_topology(name: str, factory: Callable[[TopologyBuilder], None]) -> None:
    """Register a topology factory under a name so the CLI can run it by `--topology <name>`."""
    _REGISTRY[name] = factory


def get_topology(name: str) -> Callable[[TopologyBuilder], None]:
    """Look up a topology factory registered with `register_topology`; raises KeyError if
    unknown (naming the registered topologies)."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown topology {name!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]
