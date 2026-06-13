# Substrate — Technical Specification

**Status:** DRAFT 4 · **Date:** 2026-06-11 · **Owner:** the spec maintainer · **Companions:** kernel specification (v14), product specification (DRAFT 6)

This document is the implementation contract for Substrate. It is self-contained: it restates the context it needs from the kernel and product specifications, so an engineer can read it, implement from it, and defend or challenge any decision in it without another document open. Where it cites a requirement ID (F-, N-, D-) it also states what the requirement is. Its own sections carry T-numbers; the conformance suite cross-references both.

**Normativity.** Sections marked *(normative)* bind the implementation; sections marked *(rationale)* explain why and bind nothing. MUST/SHOULD/MAY per RFC 2119. Byte counts are exact; defaults are named constants collected in §19.

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
15. Comparison report and the ground-truth harness
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

Substrate is a concurrent streaming dataflow runtime: an importable Python library plus a CLI. A user registers *Producer kinds* — computations that take a typed input and emit a stream of typed events; an LLM call, a parser, a test runner, a simulator, an embedded substrate. The runtime runs Producers concurrently and coordinates them through a single, totally-ordered, append-only event log called the *bus*. *Views* are incremental summaries over the bus. *Predicates* are cheap boolean questions over Views, asked when events land. *Triggers* are the only mechanism that creates Producers: predicate fires → input is built and sealed → Producer starts, and the decision, including the exact resolved input, is recorded on the bus as an event. *Routes* carry data from past events into the inputs of future Producers. A *TerminationPolicy* decides when the run ends, pauses, or continues. The persisted bus plus its metadata is the *run record*.

The product's central claim is that the run record is the canonical, machine-readable account of runtime causality — every consequential runtime decision is a typed, sequence-numbered event, designed to be read by programs and by LLM-based tools, not just by humans. Two consequences discipline everything in this document. First, *byte fidelity is a feature*: the product promises byte-identical replay, content-hash citations, and diffable records, so the on-disk format is not an implementation detail — it is the product surface, and this spec treats encoding decisions as load-bearing. Second, *nothing consequential may be silent*: validation failures, budget violations, quarantines, and terminations are events on the log, and any implementation path that would swallow one is a bug by definition.

### 1.2 The execution model in one paragraph

One Python process. One asyncio event loop. Inside it: exactly one *writer* task that owns the bus and is the only code that ever appends; N Producer tasks that emit by submitting events to a bounded admission queue the writer drains; and the writer's *append cycle* — the fixed sequence validate → assign sequence number → append → update Views → stage Routes → evaluate Predicates and fire Triggers → drain control events — which runs synchronously per event with no awaits inside, so every Predicate and every input builder sees one consistent snapshot of the world. Other *processes* (a tail, a UI, a reader model) observe a live run by reading its files read-only; they never talk to the writer.

### 1.3 Decisions inherited from the product spec *(normative, restated)*

These were resolved with evidence in the product spec (§11, D-1..D-9). This document implements them and does not reopen them; they are restated here so this document stands alone.

| ID | Decision | The one-sentence rationale |
|---|---|---|
| D-1 | License Apache-2.0 | Patent grant; resolved before first public commit by definition |
| D-2 | Distribution name from a verified-available shortlist; import name must not be bare `substrate` | PyPI `substrate` is taken; an import-name collision with an installed foreign package is unacceptable |
| D-3 | msgspec for validation and encoding; frozen Pydantic accepted at the boundary and converted | Measured 3.7× decode+validate, 8.1× encode vs Pydantic; frozen Structs enforce input immutability natively |
| D-4 | Run record = framed/CRC JSONL segments + manifest, directory of plain files; SQLite was runner-up | The product's promises are about bytes; the file must *be* the canonical bytes, and recovery must be exact, not heuristic |
| D-5 | TriggerFired resolved inputs: inline ≤ threshold, blob above; canonical-bytes hash always present | Citations and cross-run comparison key on the hash, so replay is insensitive to where the bytes live |
| D-6 | Python 3.12+ only | Narrower matrix; nothing demands 3.11 |
| D-7 | Canonical encoding = RFC 8785 (JCS); determinism guarantees scoped to a JCS-encodable type whitelist | Same logical event → identical bytes is the precondition for hashing, byte-identical replay, and divergence comparison |
| D-8 | Log equivalence = ordered equality of (event-kind sequence, decision-identity sequence, canonical payload hashes); supplementary metadata excluded | Wall-clock and host data must never make two identical computations "different" |
| D-9 | Predicate budgets enforced by wall-time measurement + hysteresis quarantine over mandatory subscriptions; measured ~99ns/check, ~800K appends/sec at the reference shape; first-stall non-abortable, accepted | Enforcement that cannot lie about its own cost; the restricted-predicate-algebra alternative solved a problem the measurements show does not exist |

### 1.4 What this document deliberately does not contain

Topology-layer concerns (prompt construction, model adapters, tool registries), the trace UI, schema-migration tooling, distributed execution, and Windows persistent-bus support are out of scope per the product spec; each is named again at the point in this document where an implementer might be tempted to smuggle it in.

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
        other processes, read-only: substrate tail, UI, reader model┘
```

A run begins when `Runtime.run(topology)` executes the topology factory against a `TopologyBuilder`, freezing the registration set (Producer kinds with schemas, Views, Triggers, Routes, policies). The writer appends `RunStarted` carrying the full topology manifest (§7), schedules the topology-declared initial Producers, and from then on the system is event-driven: emissions arrive through admission, each runs one append cycle, cycles fire Triggers, Triggers schedule Producers, the TerminationPolicy eventually returns finalise (or pause), the writer appends `RunFinalised`, seals the hot segment, and the record is complete. Crash at any instant loses at most the frames after the last fsync, and recovery is exact (§5, §6).

Three properties are worth holding in mind while reading everything below, because most design choices trace to one of them. **Single-writer totality:** there is exactly one append path; everything about consistency falls out of that, and any "optimization" that adds a second path is wrong. **Bytes are the contract:** the canonical encoding (§4) is decided *before* the storage format (§3) because frames are defined as CRC-protected canonical bytes — storage wraps encoding, never the reverse. **Readers are strangers:** every read path — live tail, replay, inspection, a UI, a model — works on files alone, with no IPC, no shared memory, and no writer cooperation; if a feature seems to need the writer's help to observe something, the feature is misdesigned (or the thing being observed is missing from the log, which is a worse bug).

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

**Why a directory and not a single file** *(rationale)*: three independent reasons, any one sufficient. (1) Live read-only attach: a follower can read sealed segments without ever touching the file under append, and the hot segment is append-only text, safe to tail. (2) Sealed segments are immutable, so they can be copied, shipped, content-hashed, or archived mid-run with no coordination — a single growing file can be none of those things. (3) Blobs deduplicate across events only if they live outside the event stream. The cost is that "the run record" is a directory, and a careless copy can take `manifest.json` without the newest segment; §3.5 makes the manifest advisory precisely so that a partial copy degrades loudly (missing segments are detectable) rather than silently lying.

### 3.2 Segments and the sealing protocol

A segment is a UTF-8 text file of newline-terminated frames (§3.3). The *hot* segment carries the `.open.` infix and is the only file the writer appends to. When the hot segment exceeds `SEGMENT_MAX_BYTES` after a frame is written, the writer runs the sealing protocol:

1. `fsync(hot_fd)` — the segment's bytes are durable.
2. `rename("events-N.open.jsonl" → "events-N.jsonl")` — atomic on POSIX.
3. `fsync(dirfd)` — the rename itself is durable. A rename without a directory fsync is not durable; both operations are mandatory.
4. Create `events-(N+1).open.jsonl`, `fsync(dirfd)` again.
5. Update `manifest.json` per §3.5.

**Crash-window analysis** *(rationale)*: crash before step 1 → frames since last fsync may be lost; recovery (§3.3) trims to the last valid frame of the `.open` file. Crash between 1 and 3 → recovery may see either name; both are handled, because recovery globs both patterns and the *contents* are already durable. Crash between 3 and 5 → manifest is stale; harmless, because the manifest is advisory (§3.5) and recovery rebuilds the segment list from the directory. There is no window in which a sealed name exists with non-durable contents — that is the point of the ordering.

Sealed segments MUST never be opened for writing again, by anyone, including recovery. Recovery operates only on the single `.open` segment.

### 3.3 The frame format

**The problem** *(rationale)*. A crash mid-append can tear a write: ext4 with default `data=ordered` can leave a file whose size grew but whose tail is garbage; on any filesystem, a partial line is possible. Bare JSONL has only a heuristic answer ("last line has no newline, drop it") which fails exactly when the torn write *includes* a newline from stale page contents. The classic fix is the LevelDB/RocksDB WAL: length-prefix + CRC per record — but binary framing destroys the property that the log is `cat`-able, `grep`-able, `diff`-able plain text, which the product explicitly sells. Three candidates were weighed: bare JSONL (rejected: heuristic recovery), binary length+CRC framing (rejected: kills inspectability), and CRC-inside-the-JSON (chosen: exact recovery, one extra key, still one JSON object per line).

**The format** *(normative)*. One event = one frame = one line. Construction:

1. Build the envelope (§3.4) without the `crc` field.
2. Serialize to canonical bytes `B` per §4.
3. Compute `c = crc32(B)` (zlib polynomial), rendered as exactly 8 lowercase hex digits.
4. The frame is the canonical serialization of the envelope *with* `crc: c` added, followed by `\n` (0x0A). Under JCS key ordering, `crc` lands at a deterministic position; nothing about canonicality is disturbed because the canonical form of the crc-bearing object is itself well-defined.

Recovery (run on the `.open` segment only, at attach or restart):

1. Read line by line. For each newline-terminated line: parse as JSON; reject if unparseable. Remove `crc`; re-serialize the remainder per §4; recompute crc32; compare.
2. The first line that is unterminated, unparseable, or crc-mismatched marks the cut point. Truncate the file there (`ftruncate`), `fsync`.
3. Everything before the cut point is intact **by construction**, not by assumption: each line independently proves itself.

Worked example. The envelope `{seq: 7, kind: "ProducerEmittedInvalidEvent", …}` canonicalizes to bytes `B`; `crc32(B) = 0x9af31c02`; the frame on disk begins `{"crc":"9af31c02","kind":"ProducerEmittedInvalidEvent",…}` — and an engineer with `grep -n '"seq":7,' events-*.jsonl` finds it, which is the inspectability the binary alternative would have spent.

**Edge cases** *(normative)*: A frame longer than `FRAME_MAX_BYTES` (default 1 MiB) MUST be rejected at validation — payloads that large belong in the blob store (§3.7), and an unbounded line length would make every reader's buffer policy a correctness question. CRC32 is an integrity check against torn writes, not an authenticity mechanism and not collision-proof against adversaries; the security posture (§17) does not rest on it — content *hashes* (sha256) do the identity work, CRC does the torn-tail work. Empty payloads are legal (`"payload":{}`). Non-ASCII is stored as UTF-8 per JCS rules, not `\u`-escaped, so logs remain human-readable in every locale-sane terminal.

### 3.4 The envelope

Every bus event is persisted as this envelope; field order on disk is JCS order, shown here in logical order:

| Field | Type | Semantics |
|---|---|---|
| `seq` | int | Bus sequence number; assigned by the writer at append; the event's identity and the record's total order. Dense (no gaps in a healthy record; a gap proves loss). |
| `kind` | str | Event kind. Kinds beginning `substrate.` are reserved for the kernel (the twelve lifecycle kinds: `substrate.RunStarted`, `.TriggerFired`, `.ProducerStarted`, `.ProducerEvent` wrapper semantics folded — see below —, `.ProducerEmittedInvalidEvent`, `.ProducerCompleted`, `.ProducerFailed`, `.ProducerCancelled`, `.InjectionApplied`, `.PredicateQuarantined`, `.TerminationMatched`, `.RunFinalised`). Producer-declared kinds MUST NOT use the prefix; registration rejects collisions. A reader distinguishes runtime events from application events by the kind alone. |
| `schema` | str | `"<kind>@<version>"`, resolving against the schema descriptors in `RunStarted` (§7). Self-description: replay decodes with the schemas the run was written with. |
| `producer` | object | `{kind, instance, parent}` — the emitting Producer's typed identity; `parent` is the spawning Producer's instance or `null` for runtime-emitted events. |
| `t` | float | Wall-clock seconds (Unix). **Supplementary**: excluded from equivalence (D-8), never used for ordering, present because humans and dashboards want it. |
| `payload` | object | Inline payload, or a blob reference `{"$blob": "sha256:<hex>", "bytes": n}` (§3.7). |
| `crc` | str | §3.3. |

A design note on the v14 `ProducerEvent` wrapper *(rationale)*: v14 lists `ProducerEvent` as a control-plane wrapper around application payloads. On disk, wrapping every application event in an envelope-inside-an-envelope would double parse cost and reads as noise; this spec flattens it — an application event *is* the envelope with the producer field filled in, and "was wrapped post-validation" is represented by the simple fact of being on the log at all (only validated events get sequence numbers). This is a representational choice, not a semantic change, and the kernel-spec maintainer should fold it into v15 wording.

### 3.5 The manifest

`manifest.json` is a small JSON document updated by write-to-temp → `rename` → directory fsync, never edited in place:

```json
{
  "format_version": 1,
  "run_id": "01JDQ3X8…",
  "kernel_spec": "v14+RunStarted",
  "replay_ceiling": "3b",
  "sealed": [
    {"file": "events-000001.jsonl", "first_seq": 0, "last_seq": 14092,
     "sha256": "sha256:77ab…", "bytes": 67108731}
  ],
  "hot": "events-000003.open.jsonl",
  "runstarted_sha256": "sha256:0c11…"
}
```

**The manifest is advisory; segments are authoritative** *(normative)*. Every reader MUST be able to operate with the manifest missing or stale: the segment list is recoverable by globbing `events-*.jsonl`, ordering by filename, and validating that `seq` ranges are contiguous; `runstarted_sha256` is recomputable from frame 0. The manifest exists to make the common case fast (skip hashing sealed segments you already trust; know where the hot segment is) and to make partial copies *detectable* (a missing segment breaks seq contiguity loudly). Putting authority in the manifest was rejected because it creates a single point whose corruption silently disowns durable data; putting none of this in a manifest was rejected because every reader would pay a full directory scan and hash on every attach. `replay_ceiling` records the honest-replay demotion: it starts at `3a` and drops to `3b` the moment any wall-clock cooldown is registered, so operational expectations are set by the record, not by memory.

### 3.6 What `seq` density buys *(rationale)*

Sequence numbers are dense and assigned only at append. Therefore: a gap proves data loss (recovery reports it rather than papering over it); `first_seq/last_seq` ranges make segment-level random access O(log segments) with no index files — Kafka needs sparse index sidecars because its offsets are byte positions; here the filename ordering plus dense seq *is* the index; and divergence comparison (§14) can align two records positionally without any joining logic.

### 3.7 The blob store

Payloads whose canonical encoding exceeds `BLOB_THRESHOLD_BYTES` are stored at `blobs/sha256/<first-2-hex>/<full-hex>` and referenced from the envelope. Rules *(normative)*:

- **Write-ahead blob rule:** the blob file is written and fsynced *before* the referencing frame is appended. Consequence: a frame on the log never dangles. Crash window: a blob may exist with no referencing frame (the crash hit between blob write and frame append) — harmless orphans, reported by `substrate validate`, garbage-collected never in v1.0 (GC requires liveness analysis across a record that is supposed to be append-only evidence; deleting anything from a run record is wrong on principle, and orphans cost bytes, not correctness).
- Blob files are immutable; a second write to an existing hash path is skipped after verifying size (dedup).
- The two-level fan-out (`ab/abf3…`) keeps directories small on filesystems that degrade with large directories; two hex chars = 256 subdirectories, sufficient for the design scale.
- Blob paths are *derived from the hash, never from payload content*; no user-controlled string ever becomes a path component (§17).

### 3.8 The diagnostic sidecar

Opt-in records of non-firing predicate evaluations (result, elapsed time, view version) and budget-violation observations, written as plain JSONL to `sidecar/`, keyed by the `seq` they observed but **never sequence-numbered themselves**. The invariant that justifies the sidecar's existence: enabling diagnostics MUST leave the bus log bit-identical (conformance check 14), because sequenced diagnostic events would change sequence assignment between diagnostic and production runs — destroying cross-run comparability — and Predicates could match them, making observation change behavior. The sidecar is the place where "what did the writer consider and reject" can live without polluting "what happened."

---

## 4. Canonical encoding *(normative)*

### 4.1 The requirement and the standard

The product promises byte-identical replay (two replays of a record produce identical bytes), content-hash citations (a hash names exactly one payload forever), and divergence comparison by payload hash. All three require one property: **the same logical event always serializes to the same bytes, on every OS, every Python 3.12+ minor version, every run.** Python's `json.dumps` does not promise this (dict order, float repr drift across versions, escaping choices). RFC 8785 — the JSON Canonicalization Scheme — does: lexicographic key ordering by UTF-16 code units, ES2015 shortest-round-trip number serialization, fixed minimal string escaping, UTF-8 output, no insignificant whitespace.

Pipeline: `event (msgspec Struct) → msgspec.to_builtins() → JCS encoder → bytes`. The JCS encoder is **vendored** (~120 lines), not a dependency: it is conformance-critical, and a dependency bump silently changing canonical bytes would corrupt every hash-based promise at once. The vendored encoder ships with RFC 8785's own test vectors in the conformance suite.

### 4.2 The type whitelist, with the reason for each rule

Types admitted into payloads, View state participating in determinism guarantees, and resolved inputs:

| Type | Rule | Why |
|---|---|---|
| `str` | Valid Unicode, stored UTF-8, JCS escaping | The base case |
| `bool`, `None` | As-is | — |
| `int` | MUST satisfy −(2⁵³−1) ≤ n ≤ 2⁵³−1; larger integers MUST be schema-typed as strings | JCS numbers are ES numbers (IEEE-754 doubles). A 64-bit id silently losing precision in canonical form is a correctness landmine; the rule converts it to a loud schema decision |
| `float` | Finite only; `-0.0` canonicalizes to `0`; NaN/Inf rejected at validation | JCS serializes ES numbers; NaN/Inf have no JSON form; allowing them would push the failure to encode time, after the event was already admitted — too late |
| `dict` | str keys only; JCS-ordered | — |
| `list`, `tuple` | Encoded as JSON arrays (tuples lose tuple-ness on disk, by design — the schema, not the container type, carries meaning) | — |
| `BlobRef` | Encoded as `{"$blob": …, "bytes": …}` | §3.7 |
| `bytes` | **Prohibited inline.** Blob, or an explicit base64 string field declared by the schema | Raw bytes have no canonical JSON form; "automatic base64" hides a 33% size cliff and an encoding decision the schema author should own |

Custom Views declare whether their `value()` participates in N-DET-1 (byte-identical replay of View states); a View holding non-whitelisted types is legal but flagged `determinism: excluded` at registration and excluded from check 9 — honesty over false guarantees.

Content hashes are `sha256:<64 lowercase hex>` over canonical bytes, everywhere a hash appears (blob ids, `input_sha256`, manifest segment hashes, D-8 comparison). One hash convention; no second algorithm in v1.0.

### 4.3 Failure paths

Whitelist violations are caught at two distinct moments, deliberately. At **registration**, schemas are walked: a schema declaring a field type outside the whitelist fails registration with the offending path named — topology authors find out before any run exists. At **emission**, values are validated against the schema (so a float NaN inside a declared-float field is caught) and the event becomes `substrate.ProducerEmittedInvalidEvent` with reason `non_canonical_value` — the run continues, the evidence is on the log, and the topology decides what to do, exactly like any other invalid emission (§8.2).

---

## 5. Durability and fsync *(normative)*

### 5.1 Policies and exactly what each guarantees

| Policy | Mechanism | Loss window on crash | Throughput character |
|---|---|---|---|
| `none` | OS page cache only | Everything since the OS last flushed (seconds to minutes) | Disk is never the bottleneck |
| `interval(ms)` *(default, 100ms)* | A writer-side timer fsyncs the hot segment at most every `ms` | ≤ `ms` of frames | Amortized; one fsync covers many frames |
| `always` | fsync after every frame | Zero complete frames lost | Caps at device fsync rate (~1–5K/s on commodity SSDs; ~100/s under macOS full flush). Documented, not hidden |

The policy governs the *hot segment* only. Three operations fsync unconditionally under every policy, because they are structural rather than data-rate-bound: sealing (§3.2), manifest updates (§3.5), and blob writes (§3.7). The `RunFinalised` append always fsyncs, so a completed run is durable regardless of policy.

### 5.2 Platform realities

**macOS:** `fsync()` flushes to the drive, not through the drive's cache; durable writes require `fcntl(F_FULLFSYNC)`. The implementation exposes `durable_fsync: bool` (default true for `always`, false for `interval` — matching what each policy is for) and documents the cost rather than silently choosing speed.

**fsync error semantics ("fsyncgate"):** on Linux, a failed fsync may mark dirty pages clean, so *retrying fsync after failure and believing the success is a data-loss bug* (the PostgreSQL 2018 lesson). The writer treats any fsync failure as fatal: append a best-effort `substrate.RunFinalised {reason: "io_failure"}` *without* trusting further fsyncs, close, and crash loudly. The record is then whatever recovery proves (§3.3); pretending to continue would manufacture a record that lies.

**Directory durability:** every `rename` is followed by `fsync(dirfd)` (§3.2, §3.5). On filesystems where directory fsync is a no-op, the implementation is no worse than the platform; on those where it matters (ext4), skipping it is the canonical "my file vanished after the crash" bug.

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

`bus.submit(event)` from Producer tasks awaits `admission.put(event)` on a bounded `asyncio.Queue(maxsize=ADMISSION_BOUND)`. **Blocking submit is the backpressure mechanism**: a flooding Producer waits at the door; the log is never trimmed, sampled, or dropped. Bounded-queue-with-blocking was chosen over the alternatives — unbounded queue (memory blowup is just backpressure deferred to the OOM killer), dropping (a runtime whose product is a complete record cannot drop), per-producer fairness queues (complexity with no demonstrated need at v1 scale; revisit with evidence) — because it is the only one of the four that is simultaneously bounded, lossless, and simple.

**Control events bypass admission.** Events the cycle itself generates (`TriggerFired`, `PredicateQuarantined`, `TerminationMatched`, lifecycle events from the Producer host) go to an internal control queue drained at the end of the current cycle — each drained event runs its own full append cycle, in FIFO order, before the next admitted event. Rationale, restated from the kernel spec because it is the single most important deadlock argument in the system: if control events competed for admission slots, a full admission queue would block the writer's own bookkeeping on the writer's own progress — a self-deadlock. The control queue is unbounded, and safely so, because its growth is bounded by the work the cycle itself generates, which is finite per cycle by construction (Triggers fire at most once per policy evaluation per cycle).

### 6.2 The append cycle, step by step, with invariants

For event `e` (admitted or control):

1. **Validate** (§8). On failure, `e` is *replaced* by the `ProducerEmittedInvalidEvent` wrapper and the cycle continues with the wrapper. Invariant: nothing unvalidated ever receives a sequence number.
2. **Assign `seq`,** frame (§3.3), append to the hot segment buffer. Invariant: `seq` order on disk equals processing order equals (by definition) the bus total order.
3. **Update Views.** Look up `by_kind[e.kind]` and `by_producer[e.producer]` in the subscription index; call `view.update(e)` on each match. Synchronous. Invariant established: all Views reflect exactly events `≤ seq`.
4. **Stage Routes.** Same index structure; matching Routes compute `transform(e)` and append to their slot's staging list. Staged before Predicates run, so a Trigger firing in step 5 of *this* cycle sees messages staged from *this* event — this ordering is what makes the retry-with-failure-context pattern work in one cycle instead of two.
5. **Evaluate Predicates and fire Triggers.** For each subscribed, non-quarantined Predicate, evaluate under the budget protocol (§9). For each firing Trigger (per its firing policy — §10): run `input_builder(views, staged)`, seal the input (§8.3), enqueue `substrate.TriggerFired {trigger_id, firing_key, resolved_input | $blob, input_sha256}` on the control queue, and put the Producer start on the post-cycle schedule list. Invariant: every Predicate and every input_builder in this cycle saw the same world — Views as of `seq`, staged messages as of step 4.
6. **Drain the control queue** FIFO; each event = its own full cycle (recursively, steps 1–6; the recursion terminates because control events do not validate against Producer schemas and generate further control events only through Trigger firings, which policies bound).

**Producers start after the cycle, never inside it** *(rationale)*: starting a task mid-cycle would interleave Producer execution with bus bookkeeping and reintroduce exactly the snapshot ambiguity the single-writer design exists to kill. The scheduled list is flushed between cycles; a started Producer's emissions arrive through admission like everyone else's.

**Reentrancy guard:** a `_in_cycle` flag; any `submit()` reached synchronously from View/Predicate/input_builder/transform code raises `ReentrantAppendError` immediately. This is a programming-error signal, not a recoverable condition — the topology author wrote a component that tries to be a Producer; the fix is to make it one.

### 6.3 Exception handling inside the cycle *(normative)*

- **A View raises in `update()`:** fatal for the run. Views are the substrate's own bookkeeping; a View that cannot process a validated event means the world-state is undefined for every subsequent Predicate, and "skip and continue" would corrupt silently. The writer appends `substrate.RunFinalised {reason: "view_failure", view, seq, error}` and terminates the run. Views must be total functions over their subscribed kinds; the standard library Views are; custom Views are told this in their protocol docs and the lint.
- **A Predicate raises:** quarantine path, immediately (no hysteresis — an exception is not a slow call, it is a broken call). `substrate.PredicateQuarantined {predicate_id, reason: "exception", error}` and the run continues. Rationale: a Predicate is advisory ("should something fire?"), so the safe degradation is "this question is no longer asked, and that fact is on the record," which the TerminationPolicy can escalate on.
- **An input_builder or Route transform raises:** the firing (or staging) is abandoned and recorded — `substrate.TriggerFired` is *not* emitted; instead `substrate.PredicateQuarantined` semantics would be wrong (the predicate was fine), so this is its own event: reuse `ProducerFailed`? No — nothing started. This draft introduces **`substrate.InputBuildFailed {trigger_id, firing_key, error}`** as a thirteenth lifecycle kind, flagged for v15 alongside `RunStarted`; silently not-firing is exactly the hidden-decision bug this product exists to make impossible.
- **The writer itself raises** (a kernel bug): crash loudly per §5.2's fsync-failure path. The record up to the last durable frame is intact and trustworthy; a kernel that continues past an unreportable fault produces a record that misrepresents the run.

### 6.4 The subscription index

Built once at registration freeze, immutable for the run: `by_kind: dict[kind, list[subscriber]]` and `by_producer: dict[producer_key, list[subscriber]]`, where subscriber ∈ {View, Predicate-bearing Trigger, Route}. Lookup per event is two dict gets plus iteration over actual matches — O(matches), not O(registered) — which is the entire difference between the measured ~1.2µs cycle and the naive 50-predicate sweep the product spec's N-PERF-1 arithmetic warns about. Subscriptions are mandatory at registration (a Trigger with no subscription is a registration error); "subscribe to everything" is spellable (`kinds=ALL`) but must be spelled, because it is a per-event cost someone should have to type.

---

## 7. RunStarted: the record's root *(normative)*

Frame 0 of every record is `substrate.RunStarted`, and it carries enough that **the record plus nothing else** suffices to interpret every subsequent frame:

```json
{
  "seq": 0, "kind": "substrate.RunStarted", "schema": "substrate.RunStarted@1",
  "payload": {
    "run_id": "01JDQ3X8…",
    "topology": {
      "producer_kinds": [
        {"kind": "translator", "schema_version": 2,
         "schemas": [ {…full JSON Schema for RowTranslated@2…} ],
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

**Schema descriptors are full JSON Schema documents** (draft 2020-12, generated from the registered msgspec Structs), embedded, not referenced — a version label alone would make "self-describing" an overclaim, because reading an old record would require the old code. Embedding costs kilobytes once per run and buys archival replay forever.

**Implementation fingerprints are best-effort identification, and say so.** `qualname` where the callable has one; `source_sha256` where `inspect.getsource` succeeds (it fails for lambdas defined in REPLs, C extensions, generated functions — recorded as `null`, not faked); `author_version` if the topology supplies one. The runtime does not pretend it can hash arbitrary Python semantics — closures over mutable state are *why* Level 3(a) replay has preconditions instead of promises. Fingerprints answer "which code was this, probably?" for provenance; they are not an integrity mechanism.

**Why frame 0 and not a separate file** *(rationale)*: provenance closure requires every Producer to trace to a causal root *on the log* — initial Producers attribute to `RunStarted` itself. A separate topology file could drift from the record it describes; frame 0, CRC-framed and hash-pinned in the manifest, cannot.

---

## 8. Validation at the boundary *(normative)*

### 8.1 Emission validation

At registration, each `(kind, schema_version)` gets a pre-built `msgspec.json.Decoder` (measured ~0.2µs per decode+validate, D-3). At step 1 of the cycle, the emission is decoded against its declared schema. The three failure classes each carry a typed reason: `unknown_kind` (the kind was never declared, or uses the reserved prefix), `schema_violation` (decoder rejection, with msgspec's path-precise message preserved), `non_canonical_value` (passed the schema but violates §4.2 — e.g., NaN). All three produce `substrate.ProducerEmittedInvalidEvent` with the raw payload preserved (inline if small, blob if large) — the misbehavior becomes evidence, never an exception path, never a dropped event. Untrusted Producers are the design's first-class citizens: a malformed emission costs its emitter nothing but reputation on the record.

### 8.2 Why validation cannot be disabled *(rationale)*

Every downstream guarantee — typed Views, Predicate semantics, replay decoding, schema self-description — quantifies over "validated events." An opt-out would make every one of them conditional. There is no `--fast-mode`. The 0.2µs cost is the price of the product being the product, and it is two orders of magnitude below the cycle budget.

### 8.3 Input sealing

When a Trigger fires, the resolved input is sealed by a recursive structural walk before the Producer ever sees it: accepted nodes are frozen `msgspec.Struct`, `tuple`, `frozenset`, the §4.2 scalars, and `BlobRef`; frozen Pydantic models were already converted to Structs at registration (via their declared schema, not duck-typing); *anything else* — a list, a dict, an open file, a client object — raises `InputTypeError` naming the exact path (`input.rows[3].meta`). The walk is the enforcement of "immutability by construction": there is no deep-freeze attempt, because deep-freezing arbitrary Python honestly is not possible, and a MUST enforced by convention is a fiction. Execution resources (connections, handles) belong in topology configuration, closed over by Producer factories — they are how a Producer *works*, not what it was *asked*, and only the latter is evidence.

---

## 9. Predicate budget enforcement *(normative; implements D-9)*

The protocol per subscribed, non-quarantined Predicate, per event:

```
t0 = perf_counter()
fired = predicate(event, views)          # exceptions: §6.3, immediate quarantine
elapsed = perf_counter() - t0
if elapsed > BUDGET (default 100µs):
    violations[predicate] += 1           # consecutive; reset on a within-budget call
    sidecar.write({seq, predicate_id, elapsed_us})
    if violations[predicate] >= K (default 3):
        quarantine.add(predicate)
        control.enqueue(substrate.PredicateQuarantined
                        {predicate_id, trigger_id, measured_us, k: K})
else:
    violations[predicate] = 0
```

The measured facts this design rests on (D-9 prototype; re-verify on 3.12 in CI): the `perf_counter` pair costs ~99ns — 0.1% of budget; the full reference shape (10 Views, 50 registered/~5 substantive Predicates) ran at ~804K appends/sec with enforcement on, 160× the 5K floor; a deliberately-500µs Predicate quarantined after exactly K=3 with throughput restored.

**What this deliberately does not do, and why** *(rationale)*: no thread-based abort, no signal tricks, no `sys.settrace` — the first overrun cannot be interrupted, so a pathological Predicate (an accidental network call) holds the writer once for its own duration, up to K times before quarantine. The alternatives were measured or analyzed and rejected: tracing costs ~10× across the board (paying 1000% always to bound a rare event); thread-abort of arbitrary Python is unsound (state corruption mid-bytecode); a restricted predicate algebra would statically bound cost but solves a problem the measurements show does not exist at this scale, at the price of the host-language expressiveness the kernel spec made load-bearing. The residual exposure is documented as a risk, mitigated by lint (`substrate validate` flags I/O imports in predicate modules), configuration (budget and K), and the sidecar's per-violation timings. Hysteresis (consecutive-K) rather than first-strike *(rationale)*: GC pauses and cache-cold first calls produce isolated spikes that are not the predicate's fault; quarantining on noise would make the enforcement itself the flakiest component in the system.

---

## 10. Trigger firing policies and runtime state *(normative)*

Four policies, their state, and their replay story:

| Policy | Fires | Writer-side state | Level-2 reconstruction |
|---|---|---|---|
| `Once` | First satisfaction only | one bool | "has a TriggerFired with this trigger_id occurred?" |
| `PerEvent` | Every satisfying event | none | trivially |
| `PerKey(fn)` | Once per distinct key | `set[key]` | the set of `firing_key`s in prior TriggerFired events |
| `WhileTrue(cooldown)` | Continuously while true, throttled | last-fired append counter | last TriggerFired's seq + recorded cooldown config |

The column that matters is the last one: **every piece of firing state is a pure function of the record prefix.** That is not an accident; it is the rule — if a proposed policy needed state that could not be reconstructed from prior `TriggerFired` events plus `RunStarted` config, it would create hidden runtime state, violating the product's core principle, and must be redesigned until it doesn't. Cooldowns are logical (append-counted) by default; registering any wall-clock cooldown flips the record's `replay_ceiling` to `3b` at `RunStarted` time (§3.5), because wall-clock state is precisely the thing a re-execution cannot reproduce.

`InjectionApplied` events record each Route contribution at firing time, making the staged-message half of input provenance explicit on the log (the other half is the resolved input itself in `TriggerFired`).

---

## 11. Locking and platform support *(normative)*

Persistent mode acquires `fcntl.flock(LOCK_EX | LOCK_NB)` on `<root>/.lock` before any read-modify of the root; failure raises `BusLockedError` carrying the advisory contents (PID, hostname, start time) the holder wrote into the file. The lock is advisory and same-machine — sufficient because the persistent bus is a local artifact by design (§2: no servers). Per-run mode needs no lock: the run root is freshly created under a ULID run_id; collisions do not occur.

Windows: per-run mode is best-effort and CI-smoke-tested; persistent mode raises `UnsupportedPlatformError` **at configuration time**, not at first write — failing at the moment the user expresses the intent, with the reason (no flock; a PID-file fallback has a TOCTOU window, and a correctness primitive with a race window corrupts buses) in the message. Network filesystems are explicitly unsupported for persistent roots (flock semantics over NFS are unreliable and explicitly unsupported); `Runtime` warns when it can detect one.

---

## 12. The replay engine *(normative)*

Replay levels, restated and then mechanized:

- **Level 1 — state reconstruction.** Read frames in seq order (recovery first if a hot segment exists), decode each against the `RunStarted` schema descriptors, feed Views. Deterministic by §4: same bytes, same decoding, same View updates. Yields: any View's state at any seq (`view_at`), all derivations.
- **Level 2 — decision reconstruction.** Level 1 plus interpretation of the `substrate.*` events: every Trigger firing with its exact resolved input (inline or via blob), every injection, quarantine, termination decision. Level 2 is the product's primary replay guarantee, and it requires *no re-execution at all* — the decisions were recorded when they happened; replay reads them. This is why the writer records resolved inputs rather than the cheaper "trigger X fired": Level 2's value is reconstructing *what the Producer was given*, and recomputing it would require Level 3.
- **Level 3(a) — native re-execution.** Re-run the topology with real Producers and compare records. Preconditions, verified from `RunStarted` before attempting: every Producer kind flagged deterministic by its author, `replay_ceiling == "3a"`. The runtime checks and refuses rather than producing a divergence and calling it a bug.
- **Level 3(b) — substitution re-execution.** Re-run the *kernel* with every Producer replaced by a log-backed deterministic emitter: a generated Producer that replays its recorded emissions, in recorded relative order, yielding at recorded admission points. Admission order is the seq order — the record *is* the schedule — so the kernel re-makes every decision against identical inputs in identical order, and the output record is byte-identical to the input record (conformance check 6). What 3(b) actually tests, and why it exists: it proves the *kernel's* decision logic is a pure function of the record, catching exactly the class of bug where an implementation accidentally consults wall-clock, dict order, or hidden state.

---

## 13. Live attach *(normative)*

`attach(root)` opens a record that may still be growing. Sealed segments are read normally. The hot segment is tailed: read complete lines, CRC-verify each (a follower applies the same §3.3 verification as recovery — torn tails and in-flight lines are indistinguishable to a reader, and the CRC makes the distinction irrelevant), ignore the trailing partial line. Change detection is polling (`POLL_INTERVAL_MS`, default 100): the hot segment is append-only, so `stat().st_size` growth is a complete signal; inotify/FSEvents were considered and deferred — platform-specific machinery to shave ≤100ms off a follower's latency is not v1.0 complexity. The follower never opens any file for writing, never takes the lock, never signals the writer; F-PERS-4's contract — readers need *no coordination* beyond ignoring an incomplete final frame — is satisfied by construction, and it is the entire UI story: a UI is a follower plus rendering.

---

## 14. Inspection, provenance, divergence *(normative)*

All functions are deterministic queries over a loaded (or attached) record, returning typed structures that cite sequence numbers — never natural language. Algorithms:

- `explain_producer(id)` — one pass building `spawn_index: {producer_instance: seq of its TriggerFired | RunStarted | resume event}`; returns the typed cause with its resolved-input hash. O(record) once, O(1) thereafter.
- `trace_ancestry(id)` — follow `producer.parent` and `spawn_index` links to `RunStarted`. Acyclic by construction: parents precede children in seq, and seq strictly increases.
- `view_at(seq, view)` — Level 1 replay truncated at `seq`, materializing only the requested View (subscription index makes partial replay cheap).
- `decisions_between(a, b)` — filter `substrate.*` frames in `[a, b]`.
- `first_divergence(r1, r2)` — per D-8: for each record, build the comparison sequence `(kind, decision_identity, payload_sha256)` over frames in seq order, where `decision_identity` is `trigger_id + firing_key` for firings, `predicate_id` for quarantines, `policy_id + decision` for terminations, `null` for application events; return the first index where the sequences differ, citing both records' frames at that index. Supplementary metadata (`t`, host, config echoes) never enters the comparison — two runs of the same computation on different days MUST compare equal, or drift detection drowns in timestamp noise.

Worked example: two runs of §0.1's topology (product spec), one with a perturbed worker-3. Both records begin identically; at index 7 record A has `(substrate.ProducerEmittedInvalidEvent, null, sha256:9af…)` while record B has `(RowTranslated, null, sha256:22c…)` — `first_divergence` returns index 7 with both frames cited, and a reader (human or model) starts the investigation at the exact first fact that differs, not at a dashboard.

---

## 15. Comparison report and the ground-truth harness *(normative)*

The standard diagnosis payload — shared by test helpers and reader Producers, so a test and a resident reader speak the same schema:

```python
class Citation(Struct, frozen=True):
    seq: int
    record: str | None = None          # None = "this record"

class DeltaEntry(Struct, frozen=True):
    kind: str                          # "missing" | "unexpected" | "payload_mismatch" | "order"
    expected: str | None
    observed: str | None
    cites: tuple[Citation, ...]

class ComparisonReport(Struct, frozen=True):
    observed: tuple[str, ...]          # kind sequence, compressed
    expected: tuple[str, ...]
    delta: tuple[DeltaEntry, ...]
    hypothesis: str | None             # the one free-text slot, and it must cite
    cites: tuple[Citation, ...]
```

The record-legibility harness has two layers with different epistemic status, kept apart on purpose. The **ground-truth layer** (a release gate) generates question/answer pairs mechanically: provenance questions from every `TriggerFired` ("why did `worker-3-retry` start?" → answer: the typed `explain_producer` result), first-occurrence questions from `ProducerEmittedInvalidEvent`, divergence questions from record pairs via `first_divergence`. Answers are computed by §14 functions; the layer gates because it is deterministic. The **LLM-reader layer** (published, never pass/fail) puts the same questions and a record excerpt to a local open-weights model, requires sequence citations for every claim, and grades by citation-set equality against ground truth — informative because model churn and hardware variance make it unsuitable as a gate, published because "a model can answer provenance questions from the record alone" is the product's thesis and deserves a number per release rather than a vibe.

---

## 16. Public API *(signatures normative)*

The public surface is deliberately small: the eight primitives, the runtime, the record functions, the assertion helpers. Everything else is private, and the CLI is required to be implemented exclusively against this surface — enforced in CI by an import-lint rule (`substrate.cli` may import only `substrate.api`), which makes the CLI the standing, machine-checked existence proof that a third-party UI needs no private hooks.

```python
# ── data ────────────────────────────────────────────────────────────────────
class Event(Struct, frozen=True):
    seq: int; kind: str; schema: str
    producer: ProducerRef; t: float; payload: Any

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
class Runtime:
    def __init__(self, record_root: Path, *, persistent: bool = False,
                 fsync: FsyncPolicy = Interval(100), admission: int = 1024,
                 budget_us: int = 100, hysteresis_k: int = 3): ...
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

CLI mapping (each subcommand is a thin argparse layer over one function above): `run`→`Runtime.run`, `replay`→`replay`, `validate`→registration dry-run + lints, `conformance`→the suite, `tail`→`attach` + formatting, `inspect`→`explain_producer`/`view_at`/`first_divergence`.

---

## 17. Security considerations *(normative)*

Emissions are data, never code: no `eval`, no `pickle` anywhere in any code path, including the pluggable-encoding seam (a binary encoding plugin that deserializes to arbitrary objects would be rejected in review; the plugin contract returns builtins). Blob paths derive only from content hashes — no user-controlled string is ever a path component, which forecloses traversal by construction. Symlinks inside a run root are not followed by readers (`O_NOFOLLOW` where available; lstat checks otherwise) — a record someone hands you should not be able to read your filesystem. Subprocess Producers inherit no credentials beyond what the topology explicitly passes; that is topology-layer responsibility, stated here because passing the full environment is a common and dangerous default. The runtime provides **no sandbox** for Producer code — a Producer is arbitrary Python by design, and claiming isolation the runtime does not provide would misrepresent the security boundary; topologies running untrusted code bring their own isolation (subprocess, container), and the docs say so in exactly those words. CRC32 is torn-write detection, not authentication (§3.3); sha256 content hashes are collision-resistant identity; neither is a signature — federation's signed handoffs (product spec §0.5) are future work and nothing in v1.0 claims them.

---

## 18. Performance model and verification *(rationale + normative targets)*

Per-cycle budget at the reference shape (10 Views, 50 registered / ~5 substantive Predicates), assembled from measurements: validation ~0.2µs (D-3) + View updates ~1µs + enforced predicate evaluations ~1µs (D-9: ~99ns instrumentation × 5 + bodies) + JCS framing + CRC ~1–2µs + amortized interval-fsync ≈ **target <10µs/cycle**, against a ceiling of 200µs/cycle (= the 5K appends/sec floor, N-PERF-1). The 20–40× margin is held against what the prototype did not model: asyncio queue hops, task scheduling, real View bodies, GC. Two CI gates make the model honest: the absolute floor (5K/sec on the reference shape, every commit) and the regression gate (≤20% slower than the previous release tag, every release — conformance check 15) — because a performance model that is not continuously measured is an assumption, not a model.

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

Settle final values during 0.x against real topologies; each constant's row names the tradeoff its tuning moves.

## 20. Composition internals *(normative)*

An embedded substrate is a Producer whose factory constructs an inner `Runtime` at its own record root (recorded in the outer `TriggerFired`'s resolved input, so the cross-record link is itself evidence). The boundary translator is an inner-side subscriber to exactly the export-mapped kinds; per matching inner event it builds the outer-schema event, stamps `{inner_run_id, inner_seq}` into producer metadata, and submits on the *outer* bus through ordinary admission — which is the entire backpressure story: outer congestion slows the translator's submits, the translator stops draining its inner subscription promptly, and the inner run proceeds untouched, throttled only at its exit. Unmapped kinds — including every inner `substrate.*` event — never cross; the inner record stays complete at its own root; outer `RunFinalised`-mapped exports carry the inner root path. Inner run failure surfaces as `substrate.ProducerFailed` on the outer bus with the inner `run_id` in the payload — two hops of recorded provenance from an outer symptom to a complete inner record, which is what makes composed systems recursively explicable rather than recursively opaque (product spec §0.5).

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
| 14 diagnostic invariance | §3.8 |
| 15 perf regression | §18 |
| 16 torn-tail recovery | §3.3 |

**Open implementation questions** — all constants or library picks, none kernel-shaped: final constant values (§19); JSON Schema generator stability across msgspec versions (pin or vendor); the import-lint tool choice; whether `attach()` ships a convenience async iterator (`async for event in live`) in v1.0 or 0.x+1.

## 22. Technology selection — the bill of materials *(normative)*

This section enumerates the complete technology selection — every runtime dependency, vendored component, load-bearing standard-library module, development tool, and optional extra — together with the rejected alternatives and the reason for each rejection. The governing policy: the kernel's runtime dependency count is **one**. Everything else is stdlib, vendored, or fenced into extras and dev tooling. A runtime whose product is trust does not get to have a deep dependency tree — every transitive package is surface area for supply-chain risk (§17) and for silent behavior drift under upgrade (§4.1's reason for vendoring applies generally).

### 22.1 Language and runtime

| Choice | What, exactly | Why — and why not the alternative |
|---|---|---|
| CPython 3.12+ (CI matrix: 3.12, 3.13, 3.14) | The only supported interpreter | msgspec is a C extension (no PyPy); 3.12 brings per-task eager execution and the `type` statement; D-6 fixed the floor. PyPy rejected: the kernel's hot path is already dominated by C (msgspec, zlib) and PyPy forfeits msgspec entirely |
| asyncio, stdlib | TaskGroup-based structured concurrency for Producer supervision; one event loop; writer as a plain coroutine | The kernel's concurrency is coordination-bound, not throughput-bound; structured cancellation (TaskGroup) maps 1:1 onto ProducerCancelled semantics. Trio rejected: a hard dependency and ecosystem fork for guarantees TaskGroup now covers; anyio rejected: an abstraction layer over a thing we use directly |
| uvloop | **Not in core.** Permitted as a user opt-in (`asyncio.set_event_loop_policy`) and benchmarked in CI as an FYI lane | Loop choice never touches record bytes (§4 owns those), so it is a pure perf knob; core takes no native dep for a knob, and uvloop has no Windows support, which would silently fork the support matrix |

### 22.2 The one runtime dependency

| Package | Pin | Used for | Boundary of trust |
|---|---|---|---|
| `msgspec` | `>=0.21,<0.22` measured at 0.21.1 (D-3 benchmarks); upper bound advances only after re-running the D-3 suite and the schema-generation stability check (T-OPEN) | Struct definitions (frozen) for every envelope and payload schema; `msgspec.json.Decoder` per (kind, version) for boundary validation (~0.2µs measured); `to_builtins` as the bridge into the JCS encoder; `msgspec.json.schema()` for the RunStarted schema descriptors | msgspec is trusted for *validation and object↔builtins conversion only*. It is deliberately **not** trusted for canonical bytes — its JSON output is fast but not RFC 8785, so the canonical path is ours (§22.3). If msgspec's schema generator proves unstable across versions, the generator gets vendored too, per T-OPEN |

Pydantic (frozen models) is accepted at the topology boundary and converted at registration (§8.3) but is not a dependency — the conversion path imports it only if the user's topology already did.

### 22.3 Vendored components (in-tree, tested, never auto-upgraded)

| Component | Size | Why vendored rather than depended on |
|---|---|---|
| RFC 8785 (JCS) encoder | ~120 lines | Conformance-critical: a dependency bump that changes one byte of canonical output silently invalidates every content hash and byte-identical-replay promise at once. Ships with RFC 8785's own test vectors in the conformance suite, plus Hypothesis property tests (§22.5). The PyPI `rfc8785` package was evaluated and is the fallback if the vendored encoder fails conformance — but the default posture is that the project owns its canonical bytes |
| ULID generator | ~40 lines | run_ids need lexicographically-sortable, collision-free ids; the specification is small enough to implement and test exhaustively; a runtime dependency for 40 lines of code is not justified |
| CRC framing + recovery (§3.3) | ~80 lines | This *is* the durability story; zlib.crc32 does the arithmetic (stdlib, C-speed), our code owns the scan-verify-truncate protocol |

### 22.4 Stdlib inventory (the load-bearing modules, named)

`hashlib` (sha256 for every content hash), `zlib` (crc32), `fcntl` (flock + F_FULLFSYNC via `fcntl.fcntl` on macOS), `os` (`fsync`, `O_NOFOLLOW`, `rename`, dirfd ops), `pathlib`, `time.perf_counter` (budget enforcement — measured 99ns/pair, D-9), `inspect` (`getsource` for fingerprints, with its documented failure modes treated as data, §7), `argparse` (the CLI — typer/click/rich rejected: three dependencies to prettify a thin layer over the public API whose entire design goal is to prove the public API suffices; CLI output is plain, line-oriented, and greppable on principle), `json` (reading only — never for canonical writing), `tempfile` + `os.replace` (manifest updates), `asyncio.Queue` (admission).

### 22.5 Development and verification toolchain *(dev-only; never shipped)*

| Tool | Role | Notes |
|---|---|---|
| `uv` | Environment + lockfile (`uv.lock` for dev/CI reproducibility; consumers get the loose pin of §22.2) | Chosen for speed and lockfile determinism; plain pip remains sufficient for contributors who refuse it |
| `hatchling` | Build backend, `pyproject.toml`-native | Deliberately conventional; legacy setuptools and Poetry's custom resolver were both rejected |
| `ruff` | Lint + format, one tool | black+flake8+isort as three tools rejected; config lives in pyproject |
| `mypy --strict` | Type gate on the public API (`py.typed` is a product requirement) | One checker, run in CI; running two (mypy+pyright) reports conflicts, not bugs |
| `import-linter` | The F-API-6 contract: `substrate.cli` may import only `substrate.api` | This is the machine-checked existence proof that a UI needs no private hooks; a custom AST check is the fallback if contracts prove too coarse |
| `pytest` + `pytest-asyncio` | Conformance suite (the 16 checks), unit tests | Conformance tests are named `test_check_NN_*` and cross-reference product-spec §7 in docstrings |
| `hypothesis` | Property tests where the spec makes universal claims | The two that matter most: (1) JCS round-trip — ∀ whitelisted value: decode(encode(v)) == v and encode is byte-stable across runs; (2) torn-tail — ∀ record, ∀ truncation point: recovery yields exactly the longest valid frame prefix. These are the spec's "by construction" claims, mechanically attacked |
| benchmark harness (in-repo script, not pytest-benchmark) | N-PERF-1 floor + check-15 regression gate | Custom because the regression gate compares against a *baseline JSON committed at the previous release tag* — a stored-artifact comparison pytest-benchmark does not model cleanly |
| `coverage.py` | Branch coverage on kernel modules; the writer's cycle and recovery paths must hit 100% branch | Coverage elsewhere is informative, not gated |
| `mkdocs-material` + `mkdocstrings` | N-DOC-1: docs site, API reference generated from the typed docstrings | Sphinx rejected on authoring friction; the tutorial and walkthroughs are markdown-first like everything else in this project |
| GitHub Actions | CI matrix {ubuntu-latest, macos-latest} × {3.12, 3.13, 3.14}; jobs: ruff → mypy → import-linter → pytest (unit + conformance) → bench (floor + regression) → docs build. Release: PyPI **trusted publishing** (OIDC) — no long-lived tokens anywhere | Windows job runs per-run-mode smoke tests only, per N-PORT-1 |

### 22.6 Extras (optional installs; the kernel imports none of them)

| Extra | Contents | Technology |
|---|---|---|
| `[openai-compat]` | Producer adapters for OpenAI-compatible local endpoints | `httpx` for streaming HTTP; targets llama.cpp server, vLLM, Ollama — named because open-weights-local is the product's primary deployment story, and the walkthroughs (R-1, R-4) run on it; the eval harness's LLM-reader layer uses the same adapter |
| `examples/` (in-repo, not an extra) | The four reference topologies | R-3's parser Producer uses `tree-sitter` + `tree-sitter-python` wheels (examples-only dependency); CI mode replaces every model and parser with deterministic in-repo stand-ins so the kernel's CI has zero native deps beyond msgspec |

### 22.7 Rejected technology, with reasons on the record

Recorded so that future proposals encounter the existing argument rather than restarting it: **SQLite** (D-4 runner-up — hides the bytes; the canonical stream must *be* the file); **orjson/ujson** (fast JSON that is not canonical JSON; msgspec already covers fast, §4 covers canonical); **Pydantic in core** (D-3 measurements; accepted at the boundary instead); **protobuf / Arrow / Parquet** (binary encodings forfeit grep-ability, the product's stated trade; the encoding seam stays pluggable for post-1.0 cold storage); **Kafka / Redis / NATS** (the bus is in-process by architecture — §0.3 of the product spec exists to kill exactly this picture); **structlog / OpenTelemetry in the kernel** (the bus *is* the telemetry; an OTel bridge is a fine topology-layer Producer someone can write in an afternoon, and that sentence is the design working as intended); **tenacity** (retry is a recorded topology pattern, not a hidden library loop — an invisible retry is a hidden decision, the exact bug class this product exists to eliminate); **the `python-ulid` and `rfc8785` libraries** (their functionality is vendored in-tree instead, §22.3 — PyPI itself is the project's publication target, §22.5, and nothing here rejects it); **typer/click/rich** (§22.4); **trio/anyio/uvloop-in-core** (§22.1); **inotify/watchdog** (§13 — polling an append-only file is correct and sufficient at v1.0).


---

## Document history

- **DRAFT 1** — initial outline; superseded.
- **DRAFT 2** — full self-contained synthesis: context restated (§1–2) so the document stands alone; every format specified to the byte with alternatives-considered and crash-window analyses (§3, §5); the canonical-encoding whitelist with per-rule rationale (§4); writer internals with previously unspecified failure-mode behavior decided and defended — View exceptions fatal, Predicate exceptions quarantine, `InputBuildFailed` introduced as a thirteenth lifecycle kind for v15, manifest demoted to advisory with segments authoritative, blob orphans documented as never-GC'd evidence (§3.5, §3.7, §6.3); budget enforcement with measurements and rejected alternatives (§9); firing-policy state proven replay-derivable (§10); replay levels mechanized including what 3(b) actually tests (§12); live attach as the whole UI story (§13); divergence with a worked example (§14); the two-layer legibility harness with its epistemic split (§15); full API signatures with the machine-checked CLI proof (§16); security posture including what is *not* claimed (§17); a measured performance model with its own honesty gates (§18); every constant named with the tradeoff it tunes (§19); composition internals closing the recursive-explicability loop (§21).

- **DRAFT 3** — adds §22, the technology bill of materials: the one-runtime-dependency policy stated and enforced (msgspec, pinned, with its trust boundary drawn at validation/conversion — canonical bytes stay vendored); the three vendored components with the supply-chain rationale; the load-bearing stdlib inventory; the full dev/CI toolchain (uv, hatchling, ruff, mypy --strict, import-linter as the F-API-6 proof, pytest + hypothesis with the two property tests that attack the spec's "by construction" claims, custom benchmark harness for the baseline-comparison regression gate, mkdocs, GitHub Actions matrix with trusted publishing); extras fenced (httpx-based OpenAI-compat adapters; tree-sitter in examples only); and the rejected-technology list with reasons on the record so arguments are found, not re-had.

- **DRAFT 4** — editorial pass for review quality: status block and table of contents added; composition internals moved ahead of the conformance mapping (§20/§21 swapped) so normative design precedes the test index; §22.7 reworded so the in-tree vendoring of two small libraries cannot be read as a rejection of PyPI — PyPI is the publication target; informal register removed throughout. No technical changes.

*Flows back into the kernel spec (v15): `RunStarted` (from the product spec); `InputBuildFailed` (new, §6.3); the `ProducerEvent` flattening note (§3.4). Flows back into the product spec (next synthesis): the thirteenth lifecycle kind; F-LIFE-1's count language.*
