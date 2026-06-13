"""The public API surface (F-API-1). Everything else is private; the CLI is required
to import only from here (F-API-6, enforced by import-linter in CI)."""

from __future__ import annotations

from .attach import LiveRecord, attach
from .encoding import canonical_bytes, content_hash
from .inspect import (
    Divergence,
    Explanation,
    decisions_between,
    explain_producer,
    first_divergence,
    trace_ancestry,
    view_at,
)
from .policies import (
    Decision,
    TerminationPolicy,
    all_completed,
    all_of,
    any_of,
    pause_await_input,
    quiescence_with_watchdog,
    threshold_count,
)
from .protocols import Producer, View
from .record import Always, Interval, NoFsync, read_record, recover_open_segment
from .replay import HashMismatch, ReplayResult, assert_replayable, replay
from .runtime import Runtime, RunResult
from .sidecar import read_sidecar
from .testing import assert_event, assert_no_event, assert_sequence
from .topology import TopologyBuilder, get_topology, register_topology
from .triggers import Logical, Once, PerEvent, PerKey, WallClock, WhileTrue
from .types import BlobRef, Event, ProducerRef, Subscription
from .views import BufferView, KindCount, PerKindLatest, StartedCompletedCounts

__all__ = [
    # data
    "Event",
    "BlobRef",
    "ProducerRef",
    "Subscription",
    # primitives / protocols
    "Producer",
    "View",
    "BufferView",
    "KindCount",
    "PerKindLatest",
    "StartedCompletedCounts",
    "Once",
    "PerEvent",
    "PerKey",
    "WhileTrue",
    "Logical",
    "WallClock",
    "TerminationPolicy",
    "Decision",
    "threshold_count",
    "all_completed",
    "quiescence_with_watchdog",
    "pause_await_input",
    "any_of",
    "all_of",
    # topology + execution
    "TopologyBuilder",
    "register_topology",
    "get_topology",
    "Runtime",
    "RunResult",
    # records
    "read_record",
    "recover_open_segment",
    "Interval",
    "Always",
    "NoFsync",
    "canonical_bytes",
    "content_hash",
    # live attach (technical §13, F-PERS-4)
    "attach",
    "LiveRecord",
    # off-bus sidecars (technical §3.8, §6.4)
    "read_sidecar",
    # replay (technical §12)
    "replay",
    "assert_replayable",
    "ReplayResult",
    "HashMismatch",
    # inspection / provenance / divergence (technical §14)
    "explain_producer",
    "trace_ancestry",
    "view_at",
    "decisions_between",
    "first_divergence",
    "Explanation",
    "Divergence",
    # test helpers
    "assert_event",
    "assert_no_event",
    "assert_sequence",
]
