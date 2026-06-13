# Substrate — Technical Specification

**Status:** DRAFT 5 · **Owner:** the spec maintainer · **Companions:**
kernel specification (v15), product specification (DRAFT 7)

This document is the implementation contract for Substrate. It is
self-contained: it restates the context it needs from the kernel and
product specifications, so an engineer can read it, implement from
it, and defend or challenge any decision in it without another
document open.

**Normativity.** Sections marked *(normative)* bind the
implementation; sections marked *(rationale)* explain why and bind
nothing. MUST/SHOULD/MAY per RFC 2119. Byte counts are exact;
defaults are named constants collected in §19.

**Changes from DRAFT 4:** references updated to kernel v15 (which
flattens `ProducerEvent`, adds `RunStarted`, adds `InputBuildFailed`);
§3.3 explicit two-canonical-forms note; §5.2 fsync-failure path
fixed (no record-of-death on a failed medium); §9 sidecar write
moved off the hot path; §4.2 adds fixed-size byte types (`bytes16`,
`bytes20`, `bytes32`); §10 PerKey extraction pinned to canonical
encoding, wall-clock cooldown carve-out called out; §17 adds
`--topology-module` security note; new §6.4 writer observability;
§22 rewritten — `rfc8785` and `python-ulid` are dependencies (not
vendored); CLI uses Click + Rich (F-API-6 doesn't restrict the CLI's
library choices, only its access to private substrate hooks);
benchmarking via `pytest-benchmark`; §16 specifies
`RunResult`; LLM-reader-specific sections removed in alignment with
product DRAFT 7's scope cuts.

---

## Contents

1. Context, restated
2. System overview
3. The run record on disk
4. Canonical encoding
5. Durability and fsync
6. The writer
7. RunStarted: the record's root
8. Validation at the boundary
9. Predicate budget enforcement
10. Trigger firing policies and runtime state
11. Locking and platform support
12. The replay engine
13. Live attach
14. Inspection, provenance, divergence
15. Test helpers
16. Public API
17. Security considerations
18. Performance model and verification
19. Constants
20. Composition internals
21. Conformance mapping and open questions
22. Technology selection — the bill of materials

---

## 1. Context, restated

### 1.1 What is being built

Substrate is a concurrent streaming dataflow runtime: an importable
Python library plus a CLI. A user registers *Producer kinds* —
computations that take a typed input and emit a stream of typed
events. The runtime runs Producers concurrently and coordinates them
through a single, totally-ordered, append-only event log called the
*bus*. *Views* are incremental summaries over the bus. *Predicates*
are cheap boolean questions over Views, asked when events land.
*Triggers* are the only mechanism that creates Producers: predicate
fires → input is built and sealed → Producer starts, and the
decision, including the exact resolved input, is recorded on the bus
as an event. *Routes* carry data from past events into the inputs of
future Producers. A *TerminationPolicy* decides when the run ends,
pauses, or continues. The persisted bus plus its metadata is the
*run record*.

Two consequences discipline everything in this document. First,
*byte fidelity is a feature*: the product promises byte-identical
replay, content-hash citations, and diffable records, so the on-disk
format is not an implementation detail — it is the product surface.
Second, *nothing consequential may be silent*: validation failures,
budget violations, quarantines, terminations, and input-builder
failures are events on the log, and any implementation path that
would swallow one is a bug by definition.

### 1.2 The execution model in one paragraph

One Python process. One asyncio event loop. Inside it: exactly one
*writer* task that owns the bus and is the only code that ever
appends; N Producer tasks that emit by submitting events to a
bounded admission queue the writer drains; and the writer's *append
cycle* — the fixed sequence validate → assign sequence number →
append → update Views → stage Routes → evaluate Predicates and fire
Triggers → drain control events — which runs synchronously per event
with no awaits inside, so every Predicate and every input builder
sees one consistent snapshot of the world. Other *processes* (a
tail, a UI, a replay tool) observe a live run by reading its files
read-only; they never talk to the writer.

### 1.3 Decisions inherited from the product spec *(normative, restated)*

These were resolved with evidence in the product spec (§11). This
document implements them.

| ID | Decision | Rationale |
|---|---|---|
| D-1 | License Apache-2.0 | Patent grant |
| D-2 | Distribution name from a verified-available shortlist; import name not bare `substrate` | PyPI collision avoidance |
| D-3 | msgspec for validation and encoding; frozen Pydantic accepted at the boundary | Measured 3.7× decode+validate, 8.1× encode vs Pydantic |
| D-4 | Run record = framed/CRC JSONL segments + manifest | The product's promises are about bytes; the file must *be* the canonical bytes |
| D-5 | TriggerFired resolved inputs: inline ≤ threshold, blob above; canonical-bytes hash always present | Citations key on the hash |
| D-6 | Python 3.12+ only | Narrower matrix |
| D-7 | Canonical encoding = RFC 8785 (JCS); JCS-encodable type whitelist | Same logical event → identical bytes |
| D-8 | Log equivalence = ordered equality of (event-kind sequence, decision-identity sequence, canonical payload hashes) | Wall-clock and host data never make identical computations "different" |
| D-9 | Predicate budgets enforced by wall-time measurement + hysteresis quarantine | Measured ~99ns/check, ~800K appends/sec at reference shape |

### 1.4 v15 changes the implementation honors

The kernel spec was cut from v14 to v15 to incorporate three changes
both this document and the product spec require:

- **`ProducerEvent` is flattened.** Application events are envelopes
  with a `producer` field; no wrapper kind. The kind namespace
  (`substrate.*` reserved) distinguishes runtime from application
  events; the act of being on the log after validation is what
  "post-validation" means.
- **`RunStarted` is the twelfth lifecycle kind.** Frame 0 carries the
  topology manifest.
- **`InputBuildFailed` is the thirteenth lifecycle kind.** A
  Trigger whose `input_builder` raises produces a typed event; no
  Producer starts; the failure is on the log.

### 1.5 What this document deliberately does not contain

Topology-layer concerns (prompt construction, model adapters, tool
registries), the trace UI, schema-migration tooling, distributed
execution, Windows persistent-bus support, and LLM-reader-specific
deliverables (comparison-report schemas, record-legibility eval
harnesses) are out of scope per the product spec. Each is named
again at the point in this document where an implementer might be
tempted to smuggle it in.

---

## 2. System overview *(rationale)*

```
                         one Python process
  ┌──────────────────────────────────────────────────────────────┐
  │   Producer task A ──┐                                        │
  │   Producer task B ──┼──▶ admission queue (bounded) ──▶ WRITER│
  │   Producer task C ──┘         ▲ blocks when full       task  │
  │                               │                          │   │
  │        control events bypass ─┘            append cycle  │   │
  │                                                          ▼   │
  │                                 Views (RAM, incremental)     │
  │                                 hot segment buffer ──fsync──▶│──┐
  └──────────────────────────────────────────────────────────────┘  │
                                                                    ▼
        <run-root>/  manifest.json   events-*.jsonl   blobs/   sidecar/
                                                                    ▲
                          other processes, read-only: tail, UI, replay ┘
```

A run begins when `Runtime.run(topology)` executes the topology
factory against a `TopologyBuilder`, freezing the registration set
(Producer kinds with schemas, Views, Triggers, Routes, policies). The
writer appends `substrate.RunStarted` carrying the full topology
manifest (§7), schedules the topology-declared initial Producers, and
from then on the system is event-driven: emissions arrive through
admission, each runs one append cycle, cycles fire Triggers, Triggers
schedule Producers, the TerminationPolicy eventually returns finalise
(or pause), the writer appends `substrate.RunFinalised`, seals the
hot segment, and the record is complete. Crash at any instant loses
at most the frames after the last fsync, and recovery is exact (§5,
§6).

Three properties trace most design choices. **Single-writer
totality:** there is exactly one append path; everything about
consistency falls out of that, and any "optimization" that adds a
second path is wrong. **Bytes are the contract:** the canonical
encoding (§4) is decided *before* the storage format (§3) because
frames are defined as CRC-protected canonical bytes — storage wraps
encoding, never the reverse. **Readers are strangers:** every read
path — live tail, replay, inspection, a UI — works on files alone,
with no IPC, no shared memory, and no writer cooperation.

---

## 3. The run record on disk *(normative)*

### 3.1 Directory layout

```
<run-root>/
  manifest.json                 §3.5  advisory index; rebuildable from segments
  events-000001.jsonl           §3.2  sealed segment — immutable forever
  events-000002.jsonl                 sealed segment
  events-000003.open.jsonl            hot segment — append-only, exactly one
  blobs/
    sha256/
      ab/
        abf3…e1                 §3.7  content-addressed payload, immutable
  sidecar/
    diagnostics.jsonl           §3.8  off-bus, never sequence-numbered
  .lock                         §11   persistent mode only
```

### 3.2 Segments and the sealing protocol

A segment is a UTF-8 text file of newline-terminated frames (§3.3).
The *hot* segment carries the `.open.` infix and is the only file
the writer appends to. When the hot segment exceeds
`SEGMENT_MAX_BYTES` after a frame is written, the writer runs the
sealing protocol:

1. `fsync(hot_fd)` — the segment's bytes are durable.
2. `rename("events-N.open.jsonl" → "events-N.jsonl")` — atomic on
   POSIX.
3. `fsync(dirfd)` — the rename itself is durable.
4. Create `events-(N+1).open.jsonl`, `fsync(dirfd)` again.
5. Update `manifest.json` per §3.5.

Sealed segments MUST never be opened for writing again, by anyone,
including recovery. Recovery operates only on the single `.open`
segment.

### 3.3 The frame format

One event = one frame = one line. Construction:

1. Build the envelope (§3.4) without the `crc` field.
2. Serialize to canonical bytes `B_hash` per §4.
3. Compute `c = crc32(B_hash)` (zlib polynomial), rendered as exactly
   8 lowercase hex digits.
4. The frame on disk is the canonical serialization of the envelope
   *with* `crc: c` added (= `B_disk`), followed by `\n` (0x0A). Under
   JCS key ordering, `crc` lands at a deterministic position.

**Two canonical forms exist per event, and the implementation MUST
keep them distinct:**

- `B_hash` — canonical bytes of the envelope **without** `crc`. This
  is what content hashes (sha256) are computed over, everywhere a
  hash appears: blob ids, `input_sha256`, manifest segment hashes,
  D-8 comparison.
- `B_disk` — canonical bytes of the envelope **with** `crc`. This is
  what the disk frame is, what readers see, what `tail` displays.

A verifier re-hashing on read MUST strip the `crc` field before
re-encoding for hash comparison. The recovery protocol does this
correctly. Independent implementations of inspection tools or
verifiers MUST adopt the same rule.

Recovery (run on the `.open` segment only, at attach or restart):

1. Read line by line. For each newline-terminated line: parse as
   JSON; reject if unparseable. Remove `crc`; re-serialize the
   remainder per §4 to recover `B_hash`; recompute crc32; compare.
2. The first line that is unterminated, unparseable, or crc-mismatched
   marks the cut point. Truncate the file there (`ftruncate`),
   `fsync`.
3. Everything before the cut point is intact **by construction**, not
   by assumption: each line independently proves itself.

**Edge cases:** A frame longer than `FRAME_MAX_BYTES` (default 1 MiB)
MUST be rejected at validation — payloads that large belong in the
blob store (§3.7). CRC32 is an integrity check against torn writes,
not authenticity; content hashes (sha256) do identity work.

### 3.4 The envelope

Every bus event is persisted as this envelope; field order on disk
is JCS order, shown here in logical order:

| Field | Type | Semantics |
|---|---|---|
| `seq` | int | Bus sequence number; assigned by the writer at append; the event's identity and the record's total order. Dense (no gaps in a healthy record). |
| `kind` | str | Event kind. Kinds beginning `substrate.` are reserved for the kernel (the thirteen lifecycle kinds: `RunStarted`, `TriggerFired`, `InputBuildFailed`, `ProducerStarted`, `ProducerEmittedInvalidEvent`, `ProducerCompleted`, `ProducerFailed`, `ProducerCancelled`, `InjectionApplied`, `PredicateQuarantined`, `TerminationMatched`, `RunFinalised`). Producer-declared kinds MUST NOT use the prefix; registration rejects collisions. |
| `schema` | str | `"<kind>@<version>"`, resolving against the schema descriptors in `RunStarted` (§7). Self-description: replay decodes with the schemas the run was written with. |
| `producer` | object \| null | `{kind, instance, parent}` — the emitting Producer's typed identity; `parent` is the spawning Producer's instance or `null` for topology-declared initial Producers; the whole field is `null` for runtime-emitted events. |
| `t` | float | Wall-clock seconds (Unix). **Supplementary**: excluded from equivalence (D-8), never used for ordering. |
| `payload` | object | Inline payload, or a blob reference `{"$blob": "sha256:<hex>", "bytes": n}` (§3.7). |
| `crc` | str | §3.3. |

Application events are envelopes with a non-null `producer` field
and a user-declared `kind`. The v14 `ProducerEvent` wrapper is gone
(v15 change); the envelope itself carries everything the wrapper used
to.

### 3.5 The manifest

`manifest.json` is a small JSON document updated by write-to-temp →
`rename` → directory fsync, never edited in place. The manifest is
**advisory**; segments are **authoritative**. Every reader MUST be
able to operate with the manifest missing or stale: the segment list
is recoverable by globbing `events-*.jsonl`, ordering by filename,
and validating that `seq` ranges are contiguous; `runstarted_sha256`
is recomputable from frame 0.

`replay_ceiling` records the honest-replay demotion: starts at `3a`,
drops to `3b` the moment any wall-clock cooldown is registered.

### 3.6 What `seq` density buys *(rationale)*

Sequence numbers are dense and assigned only at append. Therefore: a
gap proves data loss (recovery reports it); `first_seq/last_seq`
ranges make segment-level random access O(log segments) with no
index files; divergence comparison (§14) can align two records
positionally without joining logic.

### 3.7 The blob store

Payloads whose canonical encoding exceeds `BLOB_THRESHOLD_BYTES` are
stored at `blobs/sha256/<first-2-hex>/<full-hex>` and referenced from
the envelope. Rules:

- **Write-ahead blob rule:** the blob file is written and fsynced
  *before* the referencing frame is appended.
- Blob files are immutable; a second write to an existing hash path
  is skipped after verifying size (dedup).
- The two-level fan-out keeps directories small.
- Blob paths are *derived from the hash, never from payload content*;
  no user-controlled string ever becomes a path component (§17).

### 3.8 The diagnostic sidecar

Opt-in records of non-firing predicate evaluations (result, elapsed
time, view version) and budget-violation observations, written as
plain JSONL to `sidecar/`, keyed by the `seq` they observed but
**never sequence-numbered themselves**. The invariant: enabling
diagnostics MUST leave the bus log bit-identical (conformance check
14).

**The sidecar write is off the hot path** (§9): violation records
are buffered in memory and flushed by a background task or at fsync
boundaries. The writer's cycle never does sidecar I/O.

---

## 4. Canonical encoding *(normative)*

### 4.1 The requirement and the standard

The product promises byte-identical replay, content-hash citations,
and divergence comparison by payload hash. All three require: **the
same logical event always serializes to the same bytes, on every OS,
every Python 3.12+ minor version, every run.** Python's `json.dumps`
does not promise this. RFC 8785 — the JSON Canonicalization Scheme —
does.

Pipeline: `event (msgspec Struct) → msgspec.to_builtins() → JCS
encoder → bytes`. The JCS encoder is `rfc8785` from PyPI, pinned to a
specific version in the lockfile. Output stability is verified in CI
by running the RFC 8785 conformance test vectors on every commit; an
upgrade that changes any byte fails CI before it merges.

### 4.2 The type whitelist

Types admitted into payloads, View state participating in
determinism guarantees, and resolved inputs:

| Type | Rule | Why |
|---|---|---|
| `str` | Valid Unicode, stored UTF-8, JCS escaping | Base case |
| `bool`, `None` | As-is | — |
| `int` | MUST satisfy −(2⁵³−1) ≤ n ≤ 2⁵³−1; larger integers MUST be schema-typed as strings | JCS numbers are IEEE-754 doubles; precision loss is a correctness landmine |
| `float` | Finite only; `-0.0` canonicalizes to `0`; NaN/Inf rejected at validation | JCS has no NaN/Inf form |
| `dict` | str keys only; JCS-ordered | — |
| `list`, `tuple` | Encoded as JSON arrays | — |
| `BlobRef` | Encoded as `{"$blob": …, "bytes": …}` | §3.7 |
| `bytes16`, `bytes20`, `bytes32` | Schema-declared fixed-size byte fields; encoded as lowercase hex strings of length 32, 40, 64 | Small binary identifiers (UUIDs, git SHAs, hashes, signatures) without base64 inflation or blob-store spam — see rationale below |
| `bytes` (variable-length, inline) | **Prohibited.** Blob, or explicit schema-declared base64 string field | Raw bytes have no canonical JSON form; "automatic base64" hides a 33% size cliff |

**Fixed-size byte types** *(rationale)*. Topologies emit small binary
identifiers constantly: 16-byte UUIDs, 20-byte git SHAs, 32-byte
hashes, signatures. The two naive options — every identifier as a
blob (60-byte path + filesystem directory entry for 16 bytes of
content) or base64 in payloads (33% size cliff applied to every
event) — are both bad. Declared fixed-size byte fields encoded as
lowercase hex strings give: canonical, JCS-encodable, no inflation
beyond 2× (acceptable for identifiers), no blob-store spam, and
schema-typed (the field is `bytes16`, not "a 32-char hex string the
author hopes is hex"). Length is enforced at validation.

Custom Views declare whether their `value()` participates in N-DET-1;
a View holding non-whitelisted types is legal but flagged
`determinism: excluded` at registration.

Content hashes are `sha256:<64 lowercase hex>` over canonical bytes
(`B_hash` per §3.3), everywhere a hash appears.

### 4.3 Failure paths

Whitelist violations are caught at two distinct moments. At
**registration**, schemas are walked: a schema declaring a field type
outside the whitelist fails registration with the offending path
named. At **emission**, values are validated against the schema and
the event becomes `substrate.ProducerEmittedInvalidEvent` with
reason `non_canonical_value` — the run continues, the evidence is on
the log.

---

## 5. Durability and fsync *(normative)*

### 5.1 Policies

| Policy | Mechanism | Loss window | Throughput |
|---|---|---|---|
| `none` | OS page cache only | Whatever the OS last flushed | Disk never bottlenecks |
| `interval(ms)` *(default, 100ms)* | A writer-side timer fsyncs at most every `ms` | ≤ `ms` of frames | Amortized |
| `always` | fsync after every frame | Zero complete frames lost | Capped at device fsync rate |

The policy governs the *hot segment* only. Sealing (§3.2), manifest
updates (§3.5), and blob writes (§3.7) fsync unconditionally.

### 5.2 Platform realities and the fsync-failure path

**macOS:** `fsync()` flushes to the drive, not through the drive's
cache; durable writes require `fcntl(F_FULLFSYNC)`. The implementation
exposes `durable_fsync: bool` (default true for `always`, false for
`interval`).

**fsync error semantics ("fsyncgate"):** on Linux, a failed fsync
may mark dirty pages clean, so retrying fsync after failure and
believing the success is a data-loss bug (the PostgreSQL 2018
lesson).

**The fsync-failure path:** on `fsync` failure, the writer treats the
hot segment as compromised and the medium as untrustworthy.

1. **Do not append `RunFinalised` to the failed medium.** Writing a
   record-of-death on a medium that just demonstrated it can't be
   trusted is a category error — the frame may be lost; recovery
   would see a truncated run with no termination event and no
   evidence of why.
2. Close the file descriptor without retrying fsync.
3. Crash the writer process. The OS exit code propagates failure to
   the launcher.

Recovery on the next start reads the truncated record and reports
"incomplete run — no `RunFinalised` — torn at seq N." That is
accurate. Operators get the truth from the record, not from a
manufactured death note that may or may not have made it to disk.

**Directory durability:** every `rename` is followed by `fsync(dirfd)`
(§3.2, §3.5). Skipping it is the canonical "my file vanished after
the crash" bug.

---

## 6. The writer *(normative)*

### 6.1 Structure

The writer is one asyncio task in a loop:

```
while True:
    event = await admission.get()          # the only await in steady state
    run_append_cycle(event)                # synchronous, no awaits inside
    maybe_fsync(); maybe_roll_segment()
    start_scheduled_producers()            # tasks created after the cycle
```

`bus.submit(event)` from Producer tasks awaits `admission.put(event)`
on a bounded `asyncio.Queue(maxsize=ADMISSION_BOUND)`. Blocking
submit is the backpressure mechanism.

**Control events bypass admission.** Events the cycle itself
generates go to an internal control queue drained at the end of the
current cycle — each drained event runs its own full append cycle,
in FIFO order, before the next admitted event. If control events
competed for admission slots, a full admission queue would
self-deadlock.

### 6.2 The append cycle, step by step

For event `e` (admitted or control):

1. **Validate** (§8). On failure, `e` is *replaced* by the
   `substrate.ProducerEmittedInvalidEvent` wrapper and the cycle
   continues with the wrapper.
2. **Assign `seq`,** frame (§3.3), append to the hot segment buffer.
3. **Update Views.** Look up `by_kind[e.kind]` and
   `by_producer[e.producer]` in the subscription index; call
   `view.update(e)` on each match. Synchronous.
4. **Stage Routes.** Matching Routes compute `transform(e)` and
   append to their slot's staging list. Staged before Predicates run.
5. **Evaluate Predicates and fire Triggers.** For each subscribed,
   non-quarantined Predicate, evaluate under the budget protocol
   (§9). For each firing Trigger:
   - Run `input_builder(views, staged)`. If it raises: enqueue
     `substrate.InputBuildFailed {trigger_id, firing_key, error}`
     on the control queue; do not schedule a Producer.
   - On success: seal the input (§8.3), enqueue
     `substrate.TriggerFired {trigger_id, firing_key, resolved_input
     | $blob, input_sha256}` on the control queue, and put the
     Producer start on the post-cycle schedule list.
6. **Drain the control queue** FIFO; each event = its own full cycle.

**Producers start after the cycle, never inside it.** The scheduled
list is flushed between cycles.

**Reentrancy guard:** a `_in_cycle` flag; any `submit()` reached
synchronously from View/Predicate/input_builder/transform code
raises `ReentrantAppendError` immediately.

### 6.3 Exception handling inside the cycle

- **A View raises in `update()`:** fatal for the run. The writer
  appends `substrate.RunFinalised {reason: "view_failure", view,
  seq, error}` and terminates the run.
- **A Predicate raises:** quarantine path, immediately (no
  hysteresis). `substrate.PredicateQuarantined {predicate_id, reason:
  "exception", error}` and the run continues.
- **An `input_builder` raises:** the firing produces
  `substrate.InputBuildFailed` instead of `TriggerFired`; no Producer
  starts; run continues per its TerminationPolicy.
- **A Route `transform` raises:** the staging is abandoned, recorded
  via the same `InputBuildFailed`-shaped event scoped to the route
  (`substrate.InputBuildFailed {route_id, …}` with route_id present
  instead of trigger_id).
- **The writer itself raises** (a kernel bug): crash loudly per
  §5.2's fsync-failure path; do not write `RunFinalised` if fsync
  has just failed.

### 6.4 Writer-level observability *(new)*

The writer exposes operational metrics for the operator. These are
not bus events — they are not consequential decisions, just
runtime-internal state — but operators need them to diagnose
substrate-level slowdowns (which look identical to slow-Producer
slowdowns without writer metrics).

The standard metric set, written periodically to `sidecar/writer_stats.jsonl`
when `--writer-stats` is enabled:

| Metric | Meaning |
|---|---|
| `cycles_per_sec` | Append cycles completed per wall-clock second, EWMA over 1s window |
| `admission_depth` | Current admission queue depth (lag indicator) |
| `control_queue_depth` | Current control queue depth (cascade indicator) |
| `fsync_latency_p50_us` / `_p99_us` | Hot-segment fsync latency, microseconds |
| `view_update_p99_us` | Aggregate View update cost per cycle |
| `predicate_eval_p99_us` | Aggregate Predicate evaluation cost per cycle |
| `quarantined_count` | Number of quarantined predicates (cumulative this run) |

Frequency and field set are configurable; defaults at §19. The
sidecar file is read-only-safe for any consumer; a dashboard, a
log shipper, or `tail` can monitor it without touching the writer.

### 6.5 The subscription index

Built once at registration freeze, immutable for the run: `by_kind:
dict[kind, list[subscriber]]` and `by_producer: dict[producer_key,
list[subscriber]]`. Lookup per event is two dict gets plus iteration
over actual matches — O(matches), not O(registered). Subscriptions
are mandatory at registration; "subscribe to everything" is spellable
(`kinds=ALL`) but must be spelled.

---

## 7. RunStarted: the record's root *(normative)*

Frame 0 of every record is `substrate.RunStarted`. It carries enough
that **the record plus the topology code suffices to interpret every
subsequent frame** — replay reads schemas the run was written with,
not the schemas the current codebase has:

```json
{
  "seq": 0, "kind": "substrate.RunStarted", "schema": "substrate.RunStarted@1",
  "producer": null,
  "payload": {
    "run_id": "01JDQ3X8…",
    "topology": {
      "producer_kinds": [
        {"kind": "translator", "schema_version": 2,
         "schemas": [ {…JSON Schema for RowTranslated@2…} ],
         "fingerprint": {"qualname": "csvtopo.make_translator",
                          "source_sha256": "sha256:…", "author_version": "1.3.0"}}
      ],
      "triggers": [ {"id": "retry-row", "subscription": {"kinds": ["substrate.ProducerEmittedInvalidEvent"]},
                     "firing_policy": "PerKey(row)", "cooldown": {"basis": "logical", "appends": 0},
                     "fingerprint": {…}} ],
      "routes": [ … ], "views": [ … ], "policies": [ … ]
    },
    "baseline": {"fixtures": "orders-2026-06.csv@sha256:…", "seed": 41, "env": {"python": "3.12.6"}},
    "config": {"fsync": "interval(100)", "admission": 1024, "budget_us": 100, "hysteresis_k": 3}
  }
}
```

**Schema descriptors are full JSON Schema documents** (draft 2020-12,
generated from registered msgspec Structs), embedded.

**Implementation fingerprints are best-effort identification, and
say so.** `qualname` where the callable has one; `source_sha256`
where `inspect.getsource` succeeds; `author_version` if the topology
supplies one. The runtime does not pretend it can hash arbitrary
Python semantics — closures over mutable state are *why* Level 3(a)
replay has preconditions instead of promises.

---

## 8. Validation at the boundary *(normative)*

### 8.1 Emission validation

At registration, each `(kind, schema_version)` gets a pre-built
`msgspec.json.Decoder` (~0.2µs per decode+validate). At step 1 of
the cycle, the emission is decoded against its declared schema.
Three failure classes carry typed reasons: `unknown_kind`,
`schema_violation`, `non_canonical_value`. All three produce
`substrate.ProducerEmittedInvalidEvent` with the raw payload
preserved.

### 8.2 Why validation cannot be disabled *(rationale)*

Every downstream guarantee — typed Views, Predicate semantics, replay
decoding, schema self-description — quantifies over "validated
events." An opt-out would make every one of them conditional. There
is no `--fast-mode`.

### 8.3 Input sealing

When a Trigger fires, the resolved input is sealed by a recursive
structural walk: accepted nodes are frozen `msgspec.Struct`, `tuple`,
`frozenset`, the §4.2 scalars, fixed-size byte types, and `BlobRef`;
frozen Pydantic models were already converted to Structs at
registration; *anything else* raises `InputTypeError` naming the
exact path. The walk is the enforcement of "immutability by
construction." Execution resources (connections, handles) belong in
topology configuration, closed over by Producer factories.

---

## 9. Predicate budget enforcement *(normative; implements D-9)*

The protocol per subscribed, non-quarantined Predicate, per event:

```
t0 = perf_counter()
fired = predicate(event, views)          # exceptions: §6.3, immediate quarantine
elapsed = perf_counter() - t0
if elapsed > BUDGET (default 100µs):
    violations[predicate] += 1           # consecutive; reset on within-budget call
    sidecar_buffer.append({seq, predicate_id, elapsed_us})   # IN-MEMORY ONLY
    if violations[predicate] >= K (default 3):
        quarantine.add(predicate)
        control.enqueue(substrate.PredicateQuarantined
                        {predicate_id, trigger_id, measured_us, k: K})
else:
    violations[predicate] = 0
```

**The sidecar write is off the hot path.** Violation records append
to an in-memory buffer; a background task flushes the buffer to disk
at fsync boundaries or periodically (`SIDECAR_FLUSH_MS`, default
500). The writer's cycle never does filesystem I/O for advisory
records. Under simultaneous GC pressure causing many Predicates to
exceed budget in one cycle, the cost is bounded list-append per
violation, not synchronous file writes.

The measured facts: `perf_counter` pair ~99ns — 0.1% of budget; the
reference shape ran at ~804K appends/sec with enforcement on; a
deliberately-500µs Predicate quarantined after exactly K=3.

**What this does not do:** no thread-based abort, no signal tricks,
no `sys.settrace`. The first overrun cannot be interrupted; a
pathological Predicate holds the writer once for its own duration,
up to K times. Documented as R-RISK-3.

---

## 10. Trigger firing policies and runtime state *(normative)*

Four policies, their state, and their replay story:

| Policy | Fires | Writer-side state | Level-2 reconstruction |
|---|---|---|---|
| `Once` | First satisfaction only | one bool | "has a TriggerFired with this trigger_id occurred?" |
| `PerEvent` | Every satisfying event | none | trivially |
| `PerKey(fn)` | Once per distinct canonical key | `set[canonical_key]` | the set of `firing_key`s in prior TriggerFired events |
| `WhileTrue(cooldown)` | Continuously while true, throttled | last-fired append counter | last TriggerFired's seq + recorded cooldown config |

**Every piece of firing state is a pure function of the record prefix
— with one explicit exception: wall-clock cooldowns.** A topology
that registers any wall-clock cooldown flips the record's
`replay_ceiling` to `3b` at `RunStarted` time (§3.5). Wall-clock state
is precisely the thing a re-execution cannot reproduce; the demotion
is what makes the substrate honest about it. Logical cooldowns
(append-counted) reconstruct from the record.

**PerKey extraction is canonical.** A topology's `PerKey(fn)`
returns a key value; that value is **canonically encoded per §4
before deduplication and before recording as `firing_key` in
`TriggerFired`**. Two implementations that extract the same key
value produce the same canonical bytes, the same `firing_key` on
disk, and the same dedup behavior. Without this rule, a key that
contains a float, a dict, or a custom struct could produce
implementation-divergent behavior across implementations — exactly
the kind of hidden runtime variance the substrate exists to prevent.

`substrate.InjectionApplied` events record each Route contribution at
firing time, making the staged-message half of input provenance
explicit on the log.

---

## 11. Locking and platform support *(normative)*

Persistent mode acquires `fcntl.flock(LOCK_EX | LOCK_NB)` on
`<root>/.lock` before any read-modify of the root; failure raises
`BusLockedError` carrying advisory contents (PID, hostname, start
time). The lock is advisory and same-machine.

Per-run mode needs no lock: the run root is freshly created under a
ULID run_id.

Windows: per-run mode is best-effort and CI-smoke-tested; persistent
mode raises `UnsupportedPlatformError` **at configuration time**.
Network filesystems are explicitly unsupported for persistent roots.

---

## 12. The replay engine *(normative)*

Replay levels:

- **Level 1 — state reconstruction.** Read frames in seq order
  (recovery first if a hot segment exists), decode each against the
  `RunStarted` schema descriptors, feed Views. Yields: any View's
  state at any seq, all derivations.
- **Level 2 — decision reconstruction.** Level 1 plus interpretation
  of `substrate.*` events: every Trigger firing with its exact
  resolved input, every injection, quarantine, termination,
  input-builder failure. Level 2 requires *no re-execution* — the
  decisions were recorded when they happened; replay reads them.
- **Level 3(a) — native re-execution.** Re-run the topology with
  real Producers. Preconditions, verified from `RunStarted`: every
  Producer kind flagged deterministic by its author, `replay_ceiling
  == "3a"`. The runtime checks and refuses rather than producing a
  divergence.
- **Level 3(b) — substitution re-execution.** Re-run the *kernel*
  with every Producer replaced by a log-backed deterministic emitter
  replaying recorded emissions in recorded order. Admission order is
  seq order — the record *is* the schedule — so the output is
  byte-identical to the input.

---

## 13. Live attach *(normative)*

`attach(root)` opens a record that may still be growing. Sealed
segments are read normally. The hot segment is tailed: read complete
lines, CRC-verify each (same §3.3 verification as recovery), ignore
the trailing partial line. Change detection is polling
(`POLL_INTERVAL_MS`, default 100): the hot segment is append-only,
so `stat().st_size` growth is a complete signal.

The follower never opens any file for writing, never takes the lock,
never signals the writer. F-PERS-4's contract is satisfied by
construction.

---

## 14. Inspection, provenance, divergence *(normative)*

All functions are deterministic queries over a loaded (or attached)
record, returning typed structures that cite sequence numbers.

- `explain_producer(id)` — typed cause with resolved-input hash.
  O(record) once, O(1) thereafter.
- `trace_ancestry(id)` — follow `producer.parent` and the spawn
  index. Acyclic by construction.
- `view_at(seq, view)` — Level 1 replay truncated at `seq`.
- `decisions_between(a, b)` — filter `substrate.*` frames in `[a,
  b]`.
- `first_divergence(r1, r2)` — per D-8: build the comparison sequence
  `(kind, decision_identity, payload_sha256)` over frames in seq
  order, return the first index where the sequences differ.
  Supplementary metadata (`t`, host, config echoes) never enters
  comparison.

---

## 15. Test helpers *(normative)*

The library ships record-assertion helpers — `assert_event(rec,
kind, **partial_payload)`, `assert_no_event(rec, kind, **partial)`,
`assert_sequence(rec, [kinds])` — operating uniformly over live
buses and recorded run records. A confirmed-good run record is
directly usable as a regression fixture by passing it to these
helpers in tests.

The helpers return matched `Event` objects (or raise
`AssertionError` with sequence-number-cited context), so tests can
chain assertions: get the matched event, then assert on a downstream
state. This is enough surface for normal pytest workflows;
no further test framework is provided.

---

## 16. Public API *(normative signatures)*

```python
# ── data ────────────────────────────────────────────────────────────────────
class Event(Struct, frozen=True):
    seq: int; kind: str; schema: str
    producer: ProducerRef | None
    t: float; payload: Any

class BlobRef(Struct, frozen=True):
    sha256: str; bytes: int

class Subscription(Struct, frozen=True):
    kinds: frozenset[str] = frozenset()
    producers: frozenset[str] = frozenset()      # both empty is a registration error

# ── topology authoring ──────────────────────────────────────────────────────
class Producer(Protocol):
    def start(self, input: Any) -> AsyncIterable[Event]: ...

class View(Protocol):
    subscription: Subscription
    deterministic: bool                           # participates in N-DET-1?
    def update(self, event: Event) -> None: ...
    def value(self) -> Any: ...

class TopologyBuilder:
    def producer_kind(self, kind: str, *, schemas: Sequence[type[Struct]],
                      schema_version: int, factory: Callable[..., Producer],
                      deterministic: bool = False,
                      author_version: str | None = None) -> None: ...
    def view(self, name: str, view: View) -> None: ...
    def trigger(self, id: str, *, subscription: Subscription,
                predicate: Callable[[Event, Views], bool],
                input_builder: Callable[[Views, Staged], Any],
                starts: str,                       # producer kind
                policy: FiringPolicy = PerEvent(),
                cooldown: Cooldown = Logical(0)) -> None: ...
    def route(self, id: str, *, subscription: Subscription, slot: str,
              transform: Callable[[Event], Any]) -> None: ...
    def termination(self, policy: TerminationPolicy, *, scope: str = "run") -> None: ...
    def export(self, inner_kind: str, *, outer_schema: type[Struct]) -> None: ...
    def baseline(self, **metadata: Any) -> None: ...

# ── execution ───────────────────────────────────────────────────────────────
class RunResult(Struct, frozen=True):
    """Outcome of a single `Runtime.run` call. The record-root path is the
    durable artifact; everything else is convenience for the caller."""
    run_id: str
    record_root: Path                              # the on-disk record
    status: Literal["finalised", "paused", "failed"]
    final_event: Event                             # RunFinalised, TerminationMatched(pause-await-input), or terminal failure
    elapsed_seconds: float
    finalisation_payload: Any | None               # whatever the topology's RunFinalised carries

class Runtime:
    def __init__(self, record_root: Path, *, persistent: bool = False,
                 fsync: FsyncPolicy = Interval(100), admission: int = 1024,
                 budget_us: int = 100, hysteresis_k: int = 3,
                 writer_stats: bool = False): ...
    async def run(self, topology: Callable[[TopologyBuilder], None]) -> RunResult: ...

# ── records ─────────────────────────────────────────────────────────────────
def load_record(root: Path) -> RunRecord: ...
def attach(root: Path, *, poll_ms: int = 100) -> LiveRecord: ...
def replay(record: RunRecord, level: Literal["1","2","3a","3b"]) -> ReplayResult: ...
def explain_producer(record: RunRecord, producer: str) -> Explanation: ...
def trace_ancestry(record: RunRecord, producer: str) -> tuple[Explanation, ...]: ...
def view_at(record: RunRecord, seq: int, view: str) -> Any: ...
def decisions_between(record: RunRecord, a: int, b: int) -> tuple[Event, ...]: ...
def first_divergence(a: RunRecord, b: RunRecord) -> Divergence | None: ...
def assert_event(rec, kind: str, **partial) -> Event: ...
def assert_no_event(rec, kind: str, **partial) -> None: ...
def assert_sequence(rec, kinds: Sequence[str]) -> tuple[Event, ...]: ...
```

The public surface is deliberately small. Everything else is
private, and the CLI is required to be implemented exclusively
against this surface — enforced in CI by an import-lint rule
(`substrate.cli` may import only `substrate.api`).

---

## 17. Security considerations *(normative)*

Emissions are data, never code: no `eval`, no `pickle` anywhere in
any code path, including the pluggable-encoding seam. Blob paths
derive only from content hashes — no user-controlled string ever
becomes a path component. Symlinks inside a run root are not
followed by readers (`O_NOFOLLOW` where available). Subprocess
Producers inherit no credentials beyond what the topology
explicitly passes.

**The CLI's `--topology-module` loads arbitrary Python.** When a
user invokes `substrate run --topology-module path/to/mod.py`, the
runtime calls `importlib` on the given path and executes whatever
module-level code it contains with the invoker's privileges. This is
not a sandbox; the path's contents are user-provided code, treated as
trusted by the invocation. Users running this on paths they did not
author (a downloaded topology, a colleague's untrusted code, content
fetched over the network) are running that code with their own
shell-level privileges, file access, and network reach. The runtime
provides no isolation; topology code that needs isolation brings its
own (subprocess, container, sandboxed Python interpreter).

The runtime provides **no sandbox** for Producer code in general — a
Producer is arbitrary Python by design. CRC32 is torn-write
detection, not authentication; sha256 content hashes are
collision-resistant identity; neither is a signature.

---

## 18. Performance model and verification *(rationale + normative targets)*

Per-cycle budget at the reference shape (10 Views, 50 registered /
~5 substantive Predicates), assembled from measurements: validation
~0.2µs (D-3) + View updates ~1µs + enforced predicate evaluations
~1µs (D-9) + JCS framing + CRC ~1–2µs + amortized interval-fsync
≈ **target <10µs/cycle**, against a ceiling of 10µs/cycle for 100K
appends/sec (N-PERF-1 product spec floor). Two CI gates make the
model honest: the absolute floor (100K/sec on the reference shape,
every commit) and the regression gate (≤20% slower than the previous
release tag, every release — conformance check 15).

---

## 19. Constants *(normative defaults; all configurable)*

| Constant | Default | Bound by |
|---|---|---|
| `SEGMENT_MAX_BYTES` | 64 MiB | seal cadence vs file-count noise |
| `FRAME_MAX_BYTES` | 1 MiB | reader buffer policy (§3.3) |
| `BLOB_THRESHOLD_BYTES` | 16 KiB | frame size vs blob-store churn |
| `ADMISSION_BOUND` | 1024 events | backpressure latency vs burst absorption |
| `FSYNC_INTERVAL_MS` | 100 | loss window vs throughput |
| `BUDGET_US` | 100 | N-PERF-2 |
| `HYSTERESIS_K` | 3 | noise tolerance vs exposure (§9) |
| `POLL_INTERVAL_MS` | 100 | follower latency (§13) |
| `SIDECAR_FLUSH_MS` | 500 | sidecar latency vs writer overhead (§9) |
| `WRITER_STATS_INTERVAL_MS` | 1000 | writer-observability cadence (§6.4) |

---

## 20. Composition internals *(normative)*

An embedded substrate is a Producer whose factory constructs an
inner `Runtime` at its own record root (recorded in the outer
`TriggerFired`'s resolved input). The boundary translator is an
inner-side subscriber to exactly the export-mapped kinds; per
matching inner event it builds the outer-schema event, stamps
`{inner_run_id, inner_seq}` into producer metadata, and submits on
the *outer* bus through ordinary admission — which is the entire
backpressure story: outer congestion slows the translator's submits,
the translator stops draining its inner subscription promptly, and
the inner run proceeds untouched, throttled only at its exit.

Unmapped kinds — including every inner `substrate.*` event — never
cross; the inner record stays complete at its own root.
`RunFinalised`-mapped exports carry the inner root path. Inner run
failure surfaces as `substrate.ProducerFailed` on the outer bus with
the inner `run_id` in the payload.

---

## 21. Conformance mapping and open questions

| Conformance check (product spec §7) | Implemented/tested by |
|---|---|
| 1 retry enrichment; 2 single cascade | §6.2 steps 4–6 ordering; control-queue FIFO |
| 3 backpressure liveness | §6.1 admission; §3.2 segments |
| 4 invalid-emission cascade | §8.1 |
| 5 quiescence | §6.1 + §10 cooldown state |
| 6 byte-identical 3(b); 9 determinism | §4 + §12 |
| 7 export boundary | §20 |
| 8 quarantine visibility | §9 |
| 10 locking | §11 |
| 11–13 provenance/view-at/divergence | §14 |
| 14 diagnostic invariance | §3.8 + §9 (sidecar off hot path) |
| 15 perf regression | §18 |
| 16 torn-tail recovery | §3.3 |
| 17 InputBuildFailed visibility | §6.2 step 5 |

**Open implementation questions** — all constants or library picks,
none kernel-shaped: final constant values (§19); JSON Schema
generator stability across msgspec versions (pin or vendor); the
import-lint tool choice; whether `attach()` ships a convenience
async iterator in v1.0 or 0.x+1.

---

## 22. Technology selection — the bill of materials *(normative)*

Standard professional Python project. Pinned runtime dependencies in
a lockfile, audited on upgrade. The list below is short, not because
of policy, but because the kernel doesn't need much.

### 22.1 Language and runtime

| Choice | What | Why |
|---|---|---|
| CPython 3.12+ (CI matrix: 3.12, 3.13, 3.14) | The only supported interpreter | msgspec is a C extension; 3.12 brings per-task eager execution |
| asyncio, stdlib | TaskGroup-based structured concurrency for Producer supervision; one event loop; writer as a plain coroutine | TaskGroup maps 1:1 onto ProducerCancelled semantics |
| uvloop | **Not in core.** Permitted as a user opt-in | No Windows support |

### 22.2 Runtime dependencies

| Package | Pin | Used for |
|---|---|---|
| `msgspec` | `>=0.21,<0.22` (lockfile pins the exact patch) | Struct definitions, schema validation at the bus boundary, `to_builtins` for the JCS pipeline, `msgspec.json.schema()` for `RunStarted` descriptors |
| `rfc8785` | pinned in lockfile | RFC 8785 canonical JSON encoding (the bytes everything hashes over) |
| `python-ulid` | pinned in lockfile | `run_id` generation |
| `click` | pinned in lockfile | CLI argument parsing |
| `rich` | pinned in lockfile | Terminal output for `rostrum tail`, `inspect`, `replay --diff` |

Output stability for `rfc8785` is verified in CI by running the
RFC 8785 conformance test vectors on every commit; an upgrade that
changes any byte fails CI before it merges. That's the discipline —
not vendoring.

F-API-3 stands: no model-provider SDK. F-API-6 stands: the CLI uses
only public substrate APIs (it doesn't reach into kernel internals);
Click and Rich are external libraries, not substrate-private hooks,
so using them doesn't violate the contract.

### 22.3 In-tree code (not dependencies; just code we wrote)

The CRC framing and torn-tail recovery (§3.3) are ~80 lines of code
in the kernel, built on `zlib.crc32` from stdlib. Not a vendored
library — original code that implements the §3.3 protocol.

### 22.4 Stdlib inventory

`hashlib` (sha256), `zlib` (crc32), `fcntl` (flock + F_FULLFSYNC),
`os` (`fsync`, `O_NOFOLLOW`, `rename`, dirfd ops), `pathlib`,
`time.perf_counter` (budget enforcement), `inspect.getsource` (for
fingerprints, with documented failure modes), `json` (reading only —
never for canonical writing; canonical encoding goes through
`rfc8785`), `tempfile` + `os.replace` (manifest updates),
`asyncio.Queue` (admission).

### 22.5 Development and verification toolchain *(dev-only; never shipped)*

| Tool | Role |
|---|---|
| `uv` | Environment + lockfile |
| `hatchling` | Build backend |
| `ruff` | Lint + format |
| `mypy --strict` | Type gate on the public API (`py.typed`) |
| `import-linter` | F-API-6 contract: `substrate.cli` may import only `substrate.api` (Click/Rich allowed; substrate-private modules forbidden) |
| `pytest` + `pytest-asyncio` | Conformance suite + unit tests |
| `pytest-benchmark` | N-PERF-1 floor + check-15 regression gate (stores baseline, compares against previous release) |
| `hypothesis` | Property tests for canonical encoding round-trip and torn-tail recovery |
| `coverage.py` | Branch coverage on kernel modules; writer's cycle and recovery paths must hit 100% |
| `mkdocs-material` + `mkdocstrings` | Docs site |
| GitHub Actions | CI matrix {ubuntu-latest, macos-latest} × {3.12, 3.13, 3.14}. Release via PyPI trusted publishing (OIDC) — no long-lived tokens |

### 22.6 Extras (optional installs; the kernel imports none of them)

| Extra | Contents | Technology |
|---|---|---|
| `[openai-compat]` | Producer adapters for OpenAI-compatible local endpoints | `httpx`; targets llama.cpp server, vLLM, Ollama |
| `examples/` (in-repo) | The three reference topologies | R-3's parser uses `tree-sitter` + `tree-sitter-python` wheels (examples-only); CI mode replaces every model and parser with deterministic stand-ins |

### 22.7 Rejected technology, with reasons

**SQLite** (D-4 runner-up — hides the bytes); **orjson/ujson** (fast
JSON that is not canonical JSON; `rfc8785` is the canonical path);
**Pydantic in core** (D-3 measurements; accepted at the boundary
instead); **protobuf / Arrow / Parquet** (binary encodings forfeit
grep-ability); **Kafka / Redis / NATS** (the bus is in-process by
architecture); **structlog / OpenTelemetry in the kernel** (the bus
*is* the telemetry; OTel bridge is a topology-layer Producer);
**tenacity** (retry is a recorded topology pattern emitting events
on the bus, not a hidden library loop — this is a substrate design
constraint, not anti-dependency posturing); **trio/anyio in core**
(asyncio is sufficient); **inotify/watchdog** (polling an append-only
file is correct and sufficient at v1.0).

---

## Document history

- **DRAFT 1** — initial outline; superseded.
- **DRAFT 2** — full self-contained synthesis: context restated,
  every format specified to the byte, writer internals,
  budget enforcement, replay levels, live attach, public API.
- **DRAFT 3** — added §22 technology BOM.
- **DRAFT 4** — editorial pass for review quality.
- **DRAFT 5** — engineering fixes from the DRAFT 4 review pass.
  Kernel reference updated v14 → v15 (which flattens
  `ProducerEvent`, adds `RunStarted` and `InputBuildFailed`);
  §3.3 explicit two-canonical-forms note (`B_hash` vs `B_disk`,
  which one hashes are over); §5.2 fsync-failure path corrected
  (do not write `RunFinalised` on a failed medium; close, crash,
  let recovery report the truncated tail accurately); §9 sidecar
  write moved off the hot path (buffer in memory, background
  flush); §4.2 fixed-size byte types added (`bytes16`, `bytes20`,
  `bytes32`, hex-encoded) so small binary identifiers avoid both
  base64 inflation and blob-store spam; §10 `PerKey` extraction
  pinned to canonical encoding (so dedup is implementation-stable),
  wall-clock cooldown carve-out called out explicitly; §17 adds
  `--topology-module` security note (arbitrary Python execution);
  new §6.4 writer observability (cycles/sec, fsync latency,
  admission/control queue depth, etc., off-bus, opt-in); §22
  rewritten to drop the vendoring posture — `rfc8785` and
  `python-ulid` are normal pinned dependencies; the CLI uses Click
  + Rich; benchmarks use `pytest-benchmark`. §16 specifies
  `RunResult` type; LLM-reader-specific deliverables removed in
  alignment with product DRAFT 7. Performance model and N-PERF-1
  recalibrated to 100K appends/sec floor (was 5K) with 8× headroom
  over the D-9 prototype (was 160×).
