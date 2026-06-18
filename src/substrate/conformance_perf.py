"""The N-PERF-1 reference-shape append-rate probe (product N-PERF-1; technical §18).

The reference shape (N-PERF-1): 50 registered Predicates and 10 Views, where subscription
filtering reduces SUBSTANTIVE evaluations to <=5 Predicates per append. We build exactly
that: 10 Views and 50 Triggers, but each Trigger subscribes to a NARROW kind so only a
handful match any given append (the subscription index is what makes the floor achievable —
F-PRED-1). A single Producer emits a large burst of events; we measure wall-clock append
throughput (events appended / elapsed) with NoFsync so the disk does not dominate the
kernel-cycle measurement the floor is about.

This is the LIGHTWEIGHT probe the conformance harness (check 15) calls for a quick honest
floor read. The dedicated pytest-benchmark gate (test_perf.py) is the regression-vs-previous-
release-tag mechanism; both measure the same shape. Numbers are REAL — never fudged; if the
floor is not met on the host, the caller reports the measured rate and FAILS honestly.

SPEC-CONFIRM (review #5): the probe measures at the SUBSCRIPTION-FILTERED shape — <=5
substantive Predicate evaluations per append, not all 50. That is EXACTLY N-PERF-1's defined
shape: the requirement explicitly states that subscription filtering (F-PRED-1) reduces
substantive evaluations to <=5 per append, and that filtering "is what makes N-PERF-1's
stated shape achievable" (product §6). So the 100K floor is defined AGAINST the filtered
shape — not "100K with all 50 predicates evaluating every append." The probe is at the right
shape; do not read the floor as the unfiltered worst case.
"""

from __future__ import annotations

import time
from pathlib import Path

from msgspec import Struct

from . import api
from .record import NoFsync

# the burst size: enough events to amortize startup, bounded so the probe stays well under
# the test timeout even on slow hardware.
_BURST = 20_000


# 10 distinct event kinds (Beat0..Beat9). N-PERF-1's shape is 50 registered Predicates but
# subscription filtering (F-PRED-1) reduces SUBSTANTIVE evaluations to <=5 per append — so we
# register 50 Triggers spread 5-per-kind across 10 kinds, and the Producer round-robins the
# kinds. Each append is of ONE kind, so the subscription index consults exactly the 5 Triggers
# (and the 1 View) for that kind — NOT all 50. Measuring all-50-per-append would be a harsher
# shape than the floor is defined against and would understate the rate.
_KINDS = 10
_TRIGGERS_PER_KIND = 5  # 10 * 5 = 50 registered Triggers; <=5 substantive per append (F-PRED-1)
_BEAT_TYPES: tuple[type, ...] = tuple(
    type(f"Beat{i}", (Struct,), {"__annotations__": {"n": int}}, frozen=True) for i in range(_KINDS)
)


def _reference_topology(burst: int) -> object:
    """The N-PERF-1 shape: 10 Views + 50 Triggers across 10 event kinds (5 Triggers + 1 View
    per kind), one Producer round-robining the 10 kinds so subscription filtering yields <=5
    substantive Predicate evaluations per append (F-PRED-1)."""

    async def beater(_input: object) -> object:
        types = _BEAT_TYPES
        for n in range(burst):
            yield types[n % _KINDS](n=n)  # round-robin the 10 kinds

    def topo(b: object) -> None:
        b.producer_kind(  # type: ignore[attr-defined]
            "beater",
            schemas=list(_BEAT_TYPES),
            schema_version=1,
            factory=lambda: beater,
            deterministic=True,
        )
        for i, bt in enumerate(_BEAT_TYPES):
            kind = bt.__name__
            # one View per kind (10 total), subscription-filtered to that kind
            b.view(f"v{i}", api.KindCount(kind))  # type: ignore[attr-defined]
            # 5 Triggers per kind (50 total), each subscribed ONLY to that kind so the
            # subscription index consults exactly 5 per append; predicate stays False so the
            # measurement is pure cycle cost (no Producer-spawn).
            for j in range(_TRIGGERS_PER_KIND):
                b.trigger(  # type: ignore[attr-defined]
                    f"t{i}_{j}",
                    subscription=api.Subscription(kinds=frozenset({kind})),
                    predicate=lambda ctx: False,
                    starts="beater",
                    input_builder=lambda ctx: None,
                    policy=api.PerEvent(),
                )
        b.initial("beater", input=None)  # type: ignore[attr-defined]
        b.termination(api.threshold_count("substrate.ProducerCompleted", 1))  # type: ignore[attr-defined]

    return topo


async def measure_append_rate(root: Path, *, burst: int = _BURST) -> tuple[float, int]:
    """Run the reference-shape topology and return (appends_per_second, n_appends). NoFsync so
    the disk does not dominate the kernel-cycle measurement the N-PERF-1 floor is about."""
    topo = _reference_topology(burst)
    started = time.perf_counter()
    await api.Runtime(root, fsync=NoFsync(), admission=4096).run(topo)  # type: ignore[arg-type]
    elapsed = time.perf_counter() - started
    n = sum(1 for _ in api.read_record(root))
    rate = n / elapsed if elapsed > 0 else 0.0
    return rate, n
