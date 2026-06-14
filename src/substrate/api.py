"""The public API surface (F-API-1). Everything else is private; the CLI is required
to import only from here (F-API-6, enforced by import-linter in CI).

Public exception catch-surface (design §6.3): the exceptions an api-only consumer can
reasonably need to catch BY TYPE are re-exported here — the run/config errors
(SubstrateError + BusLockedError/RegistrationError/UnsupportedPlatformError/FsyncError),
the inspection errors (ProducerNotFound/SequenceOutOfRange), the input-sealing error
(InputTypeError), and the replay errors (ReplayError/RecordIncompleteError). DELIBERATELY
NOT re-exported (an explicit decision, not an oversight): the record-INTERNAL integrity
exceptions TornFrameError / CRCMismatchError / FrameTooLargeError, the cycle-internal
ReentrantAppendError, and the encoding-internal NonCanonicalValueError. These are not a
public catch surface — torn/crc faults are handled by recovery and surfaced as recovery
reports or RecordIncompleteError; a non-canonical emission becomes a recorded
ProducerEmittedInvalidEvent (never raised to the caller); FrameTooLargeError cannot reach a
caller (oversized payloads are blob-offloaded before framing); ReentrantAppendError is a
programming bug, not a condition to catch. All are reachable via the SubstrateError base if
truly needed."""

from __future__ import annotations

from .attach import LiveRecord, attach
from .composition import EmbeddedRunFailed, embedded_substrate
from .conformance import CheckResult, ConformanceReport, Status, run_conformance
from .encoding import canonical_bytes, content_hash
from .errors import (
    BusLockedError,
    FsyncError,
    InputTypeError,
    ProducerNotFound,
    RecordIncompleteError,
    SequenceOutOfRange,
    SubstrateError,
    UnsupportedPlatformError,
)
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
    cancel_all_others,
    pause_await_input,
    quiescence_with_watchdog,
    threshold_count,
)
from .protocols import Producer, View
from .record import Always, Interval, NoFsync, read_record, recover_open_segment
from .replay import HashMismatch, ReplayError, ReplayResult, assert_replayable, replay
from .runtime import Runtime, RunResult
from .sidecar import read_sidecar
from .testing import assert_event, assert_no_event, assert_sequence
from .topology import RegistrationError, TopologyBuilder, get_topology, register_topology
from .triggers import Logical, Once, PerEvent, PerKey, WallClock, WhileTrue
from .types import BlobRef, Event, ProducerRef, Subscription
from .views import BufferView, KindBuffer, KindCount, PerKindLatest, StartedCompletedCounts

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
    "KindBuffer",
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
    "cancel_all_others",
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
    # composition — substrate as a Producer (technical §20, F-COMP)
    "embedded_substrate",
    "EmbeddedRunFailed",
    # conformance suite — the v1.0 release gate (product §7)
    "run_conformance",
    "ConformanceReport",
    "CheckResult",
    "Status",
    # the public exception hierarchy (design §6.3) — so an api-only consumer (the CLI is
    # the standing proof) handles errors BY TYPE, not by string-matching class names.
    "SubstrateError",
    "BusLockedError",
    "RegistrationError",
    "UnsupportedPlatformError",
    "FsyncError",
    "ProducerNotFound",
    "SequenceOutOfRange",
    "InputTypeError",
    "ReplayError",
    "RecordIncompleteError",
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
