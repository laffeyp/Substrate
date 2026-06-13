"""The public API surface (F-API-1). Everything else is private; the CLI is required
to import only from here (F-API-6, enforced by import-linter in CI)."""
from __future__ import annotations

from .encoding import canonical_bytes, content_hash
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
from .runtime import Runtime, RunResult
from .testing import assert_event, assert_no_event, assert_sequence
from .topology import TopologyBuilder, get_topology, register_topology
from .triggers import Logical, Once, PerEvent, PerKey, WallClock, WhileTrue
from .types import BlobRef, Event, ProducerRef, Subscription
from .views import BufferView, KindCount, PerKindLatest, StartedCompletedCounts

__all__ = [
    # data
    "Event", "BlobRef", "ProducerRef", "Subscription",
    # primitives / protocols
    "Producer", "View",
    "BufferView", "KindCount", "PerKindLatest", "StartedCompletedCounts",
    "Once", "PerEvent", "PerKey", "WhileTrue", "Logical", "WallClock",
    "TerminationPolicy", "Decision",
    "threshold_count", "all_completed", "quiescence_with_watchdog",
    "pause_await_input", "any_of", "all_of",
    # topology + execution
    "TopologyBuilder", "register_topology", "get_topology",
    "Runtime", "RunResult",
    # records
    "read_record", "recover_open_segment", "Interval", "Always", "NoFsync",
    "canonical_bytes", "content_hash",
    # test helpers
    "assert_event", "assert_no_event", "assert_sequence",
]
