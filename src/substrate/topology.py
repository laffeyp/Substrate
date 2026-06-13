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
from .triggers import Cooldown, FiringPolicy, Logical, PerEvent, WallClock
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
    exports: dict[str, type] = field(default_factory=dict)
    baseline: dict[str, Any] = field(default_factory=dict)
    has_wall_clock_cooldown: bool = False


class TopologyBuilder:
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
        if is_reserved(kind):
            raise RegistrationError(
                f'producer_kind "{kind}": Producer kinds MUST NOT use the reserved '
                f'"substrate." prefix (F-OBS-5).'
            )
        schema_map: dict[str, tuple[type, int]] = {}
        for s in schemas:
            if not (isinstance(s, type) and issubclass(s, Struct)):
                raise RegistrationError(f'producer_kind "{kind}": schema {s!r} is not a msgspec Struct.')
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
        self._reg.producer_kinds[kind] = ProducerKindReg(
            kind, schema_map, factory, deterministic, author_version
        )

    def view(self, name: str, view: View) -> None:
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
        if subscription.is_empty():
            raise RegistrationError(f'trigger "{id}": subscription is empty; subscribe to a kind/producer.')
        cd = cooldown or Logical(0)
        if isinstance(cd, WallClock):
            self._reg.has_wall_clock_cooldown = True
        self._reg.triggers.append(
            TriggerReg(id, subscription, predicate, starts, input_builder, policy or PerEvent(), cd)
        )

    def route(self, id: str, *, subscription: Subscription, slot: str,
              transform: Callable[[Any], Any]) -> None:
        if subscription.is_empty():
            raise RegistrationError(f'route "{id}": subscription is empty.')
        self._reg.routes.append(RouteReg(id, subscription, slot, transform))

    def initial(self, kind: str, *, input: Any = None) -> None:
        self._reg.initials.append(InitialReg(kind, input))

    def termination(self, policy: TerminationPolicy, *, scope: str = "run") -> None:
        # v0.1 ships run-scoped termination; per-Producer scoping is a documented extension.
        self._reg.termination = policy

    def export(self, inner_kind: str, *, outer_schema: type) -> None:
        self._reg.exports[inner_kind] = outer_schema

    def baseline(self, **metadata: Any) -> None:
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
    _REGISTRY[name] = factory


def get_topology(name: str) -> Callable[[TopologyBuilder], None]:
    if name not in _REGISTRY:
        raise KeyError(f"unknown topology {name!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]
