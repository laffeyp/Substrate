# Substrate — Technical Specification

**DRAFT 1.** Second of three artifacts. Implements the product spec (DRAFT 6) and the kernel spec (v14). The product spec says *what must be true*; this document says *how, exactly, in bytes and signatures*. Where the product spec resolved a question as D-n, this document implements that decision and does not reopen it. Requirement IDs (F-/N-) refer to the product spec; T-n IDs below are this document's own, cross-referenced by the conformance suite.

**Normativity:** Part A (formats) and Part B (kernel internals) are normative. Part C (API) is normative for signatures, informative for implementation sketches. §T-OPEN lists the implementation questions this draft leaves open — all are constants or library choices, none are kernel-shaped.

---

# Part A — Formats: the run record in bytes

## T-1 Run-record directory layout (implements D-4, F-PERS-1/2/4)

```
<run-root>/
  manifest.json              # T-3; temp+rename+dir-fsync on every update
  events-000001.jsonl        # sealed segment (immutable)
  events-000002.jsonl        # sealed segment (immutable)
  events-000003.open.jsonl   # hot segment (the only file being appended)
  blobs/
    sha256/
      ab/abf3…e1             # content-addressed payloads (T-5)
  sidecar/
    diagnostics-000001.jsonl # off-bus predicate-evaluation records (F-OBS-6)
  .lock                      # flock target, persistent mode only (T-12)
```

Rules: exactly one `.open` segment exists at any moment. Sealing = fsync segment → rename to drop `.open` → fsync directory → update manifest. Segment roll threshold: `SEGMENT_MAX_BYTES` (default 64 MiB, T-OPEN-1). A reader (UI, tail, replay) never needs the writer's cooperation: sealed segments are immutable; the hot segment is append-only JSONL whose last line may be incomplete and is ignored until newline-terminated (F-PERS-4).

## T-2 Frame format (implements D-4 framing; conformance check 16)

One event = one line = one frame. A frame is the canonical JSON (T-4) of the event envelope, with the CRC as the final key:

```
{"crc":"9af31c02",…envelope fields in JCS order…}\n
```

Precisely: serialize the envelope *without* `crc` to canonical bytes `B`; compute `crc32(B)` (zlib, hex, 8 chars); the frame on disk is the canonical serialization of the envelope *including* `crc` — which, under JCS key ordering, places `crc` deterministically. Recovery: scan lines in order; for each, parse, strip `crc`, re-canonicalize, compare. First mismatch or unterminated line ⇒ truncate there; everything before is intact by construction. No heuristics. `grep`/`cat`/`diff` continue to work because a frame is still one JSON object per line — framing costs one key, not readability.

## T-3 Envelope and manifest schemas (implements F-BUS-4, F-OBS-1, F-SCHEMA-1)

Envelope (every bus event):

```json
{
  "seq": 412,
  "kind": "RowTranslated",
  "schema": "RowTranslated@2",
  "producer": {"kind": "translator", "instance": "worker-3", "parent": "spawn-workers/1"},
  "t": 1786243712.4821,
  "payload": { … inline … } | {"$blob": "sha256:abf3…", "bytes": 188422},
  "crc": "9af31c02"
}
```

`seq` is identity; `t` is supplementary (D-8 excludes it from equivalence). Control-plane kinds live in the reserved namespace `substrate.*` (F-OBS-5): `substrate.RunStarted`, `substrate.TriggerFired`, etc.

`manifest.json`:

```json
{
  "format_version": 1,
  "run_id": "01JD…",
  "kernel_spec": "v14+RunStarted",
  "replay_ceiling": "3b",            // demoted by wall-clock cooldowns (F-TRIG-3)
  "sealed": [{"file": "events-000001.jsonl", "first_seq": 0, "last_seq": 14092}],
  "hot": "events-000003.open.jsonl",
  "runstarted_sha256": "sha256:…"    // hash of the RunStarted frame, the record's root
}
```

The `RunStarted` event itself (not the manifest file) carries the topology manifest per F-OBS-1: producer kinds with schema descriptors, trigger/route/view/policy identifiers with implementation fingerprints `{qualname, source_sha256?, author_version?}`, cooldown flags, baseline metadata. Schema descriptors are JSON Schema documents generated from the registered msgspec Structs (T-OPEN-2 fixes the draft/dialect), embedded in full — that is what makes the record self-describing (F-SCHEMA-1).

## T-4 Canonical encoding (implements D-7; gates N-DET-1, checks 6/9)

RFC 8785 (JCS) over the output of `msgspec.to_builtins(event)`. Encodable types (the determinism whitelist): `str` (must be valid Unicode; stored as-is, JCS escaping), `bool`, `None`, `int` in [-(2^53−1), 2^53−1] (larger integers MUST be carried as strings by the schema author — JCS number normalization is ES2015, and silent precision loss is worse than a rule), finite `float` (JCS shortest-round-trip formatting; `-0.0` normalizes to `0`; NaN/Inf rejected at validation), `dict[str, …]`, `list` (tuples encode as lists), and `BlobRef`. `bytes` are prohibited inline — blob or explicit base64 string field. Custom Views participating in N-DET-1 must hold only whitelisted types; the registry flags violators at registration. Content hashes everywhere are `sha256:<hex>` over canonical bytes (D-5, D-8).

Implementation: a vendored JCS encoder (~120 lines: sorted keys, ES number formatting via `repr`-compatible shortest float, string escaping per RFC 8785 §3.2.2) sitting on msgspec's converter; candidates evaluated in T-OPEN-3.

## T-5 Blob store (implements F-PERS-3, D-5)

Threshold: payload whose canonical encoding exceeds `BLOB_THRESHOLD_BYTES` (default 16 KiB, T-OPEN-1) is written to `blobs/sha256/<2-hex>/<hex>` **before** the referencing frame is appended (write-ahead blob rule — a frame on the log never dangles), then referenced as `{"$blob": "sha256:…", "bytes": n}`. Blobs are immutable and deduplicated by content. `TriggerFired.resolved_input` follows D-5: inline below threshold, blob above, `input_sha256` present in both cases.

## T-6 Fsync policy (implements D-4; N-REL-1)

`fsync_policy ∈ {none, interval(ms=100), always}`, default `interval`. `always` fsyncs after every frame (caps at device fsync rate; documented, not hidden). On macOS, durable mode uses `F_FULLFSYNC` per N-PORT-1, exposed as `durable_fsync=True`. Directory fsync after every rename (sealing, manifest update) on all policies — rename without dir-fsync is not durable, and the implementation treats that as law, not folklore.

---

# Part B — Kernel internals

## T-7 Writer loop (implements F-BUS-1/2/3; v14 append cycle)

One asyncio task owns the bus. Producers call `await bus.submit(event)` → bounded `asyncio.Queue` (default 1024, T-OPEN-1). The writer drains it; per admitted event it runs the v14 cycle synchronously (no awaits between validate and control-queue drain — atomicity by construction):

```
validate (T-8) → assign seq, frame, append to hot segment buffer →
update Views (subscription index) → stage Routes →
evaluate Predicates (subscription index, budget per T-9) →
enqueue control events → drain control queue (each = full cycle) →
fsync per policy
```

Reentrancy guard: a `_in_cycle` flag; any `submit` from inside View/Predicate/input_builder raises `ReentrantAppendError` (F-BUS-2). Subscription index: two dicts, `by_kind: dict[str, list[Sub]]` and `by_producer: dict[ProducerKey, list[Sub]]`, built at registration, immutable per run — lookup is O(matching subscribers), which is what makes N-PERF-1's shape real (D-9 measured the whole cycle at ~1.2µs under it).

## T-8 Boundary validation (implements F-BUS-6, F-PROD-2/3)

Emissions decode against the registered msgspec Struct for `(kind, schema_version)` via a pre-built `msgspec.json.Decoder` per kind (~0.2µs/event, D-3). Failure ⇒ wrap as `substrate.ProducerEmittedInvalidEvent` with raw payload preserved (as blob if oversized) and typed reason (`unknown_kind | schema_violation | non_canonical_type`), then process the wrapper through the normal cycle. Producer inputs are validated structurally at instantiation: a recursive walk accepting frozen `msgspec.Struct`, frozen Pydantic `BaseModel` (converted via `model_dump` → registered Struct at registration time), `tuple`, `frozenset`, whitelisted scalars, `BlobRef`; anything else ⇒ `InputTypeError` naming the offending path (F-PROD-3).

## T-9 Predicate budget enforcement (implements D-9, F-PRED-1; check 8)

Per subscribed predicate call: `t0 = perf_counter(); fired = pred(ev, views); dt = perf_counter() - t0`. If `dt > budget` (default 100µs): increment `violations[pred]`; write the observation to the diagnostic sidecar; at `k` consecutive violations (default 3) add to the quarantine set and enqueue `substrate.PredicateQuarantined {predicate_id, trigger_id, measured_us, k}`. Measured overhead of the instrumentation itself: ~99ns/call (D-9) — charged to the cycle, not the predicate. The residual first-stall exposure is R-RISK-3 and is not papered over here: there is deliberately no thread-based abort, no signal trickery, no tracer.

## T-10 Producer host, Triggers, Routes (implements F-PROD-1, F-TRIG, F-ROUTE)

Each Producer runs as an asyncio task wrapping `start(input)`; the host consumes the async iterator and `submit`s emissions tagged with the ProducerId. Exceptions ⇒ `substrate.ProducerFailed {error_type, message, traceback_sha256→blob}`; cancellation ⇒ `substrate.ProducerCancelled`. Trigger firing inside the cycle: evaluate predicate → `input_builder(views, staged)` → seal input (T-8 walk) → enqueue `substrate.TriggerFired {trigger_id, resolved_input | $blob, input_sha256, firing_key}` → schedule the Producer task for *after* cycle completion (tasks never start mid-cycle; the cycle is pure bookkeeping). Firing-policy state (Once flag, PerKey set, WhileTrue cooldown counters in appends) lives in the writer, serialized into `RunStarted`-anchored replay by virtue of being decision-derivable (Level 2 reconstructs it from `TriggerFired` history, not from hidden counters).

## T-11 Export-map translation (implements F-COMP-1..3; check 7)

An embedded substrate Producer wraps an inner `Runtime`. The boundary translator subscribes (inner-side) to mapped kinds only; per mapped inner event it constructs the outer-schema event, stamps provenance metadata `{inner_run_id, inner_seq}`, and `submit`s it on the outer bus — through admission like any Producer, which is exactly how outer congestion throttles the boundary without touching the inner run (F-COMP-2). Unmapped inner kinds, including all inner `substrate.*` control events, never cross. The inner run record persists at its own root, referenced from the outer `RunFinalised` payload — provenance across the boundary is two hops, both recorded (§0.5 of the product spec depends on precisely this).

## T-12 Locking and platforms (implements F-PERS-2; N-PORT-1)

Persistent mode: `fcntl.flock(root/.lock, LOCK_EX | LOCK_NB)` at startup; failure ⇒ `BusLockedError` naming the holder's PID from the lock file's advisory contents (check 10). Windows: persistent mode raises `UnsupportedPlatformError` at configuration time — not at first write. Per-run mode has no lock (the run root is freshly created, collision-free by run_id).

## T-13 Inspection, provenance, divergence (implements F-OBS-2/3, D-8; checks 11–13)

All functions are pure over a loaded record (or live attach). `explain_producer(id)`: index `substrate.TriggerFired`/`RunStarted`/resume events by spawned ProducerId; return the typed chain. `trace_ancestry(id)`: walk `parent` links + firing events to `RunStarted`; cycle-free by construction (parents precede children in seq). `view_at(seq, view)`: replay Level 1 to `seq` with the named View only. `decisions_between(a, b)`: filter `substrate.*` in [a, b]. `first_divergence(r1, r2)`: per D-8, build per-record tuples `(kind, decision_identity, payload_sha256)` in seq order — `decision_identity` is `trigger_id+firing_key` for firings, `predicate_id` for quarantines, `policy_id+decision` for terminations, `None` otherwise — and return the first index where they differ, with both events cited. Supplementary metadata (`t`, host) never enters the tuple.

## T-14 Comparison report and ground-truth harness (implements F-API-4, F-OBS-7)

```python
class Citation(Struct, frozen=True):   seq: int; record: str | None = None
class DeltaEntry(Struct, frozen=True): kind: str; expected: str | None; observed: str | None; cites: tuple[Citation, ...]
class ComparisonReport(Struct, frozen=True):
    observed: tuple[str, ...]; expected: tuple[str, ...]
    delta: tuple[DeltaEntry, ...]; hypothesis: str | None; cites: tuple[Citation, ...]
```

The F-OBS-7 ground-truth layer generates question/answer pairs mechanically from a record via T-13 (provenance questions from `TriggerFired` events, first-invalid from `ProducerEmittedInvalidEvent`, divergence from record pairs); the grader scores an LLM reader's answer by citation-set equality against ground truth (gate) and answer-text match (informative only).

---

# Part C — Public API (signatures normative)

## T-15 Core surface

```python
class Event(Struct, frozen=True): …                       # envelope, T-3
class BlobRef(Struct, frozen=True): sha256: str; bytes: int

class Producer(Protocol):
    def start(self, input: Any) -> AsyncIterable[Event]: ...

class View(Protocol):
    subscription: Subscription
    def update(self, event: Event) -> None: ...
    def value(self) -> Any: ...                           # whitelisted types for N-DET-1

Subscription = msgspec.Struct  # kinds: frozenset[str], producers: frozenset[str]

class TopologyBuilder:
    def producer_kind(self, kind: str, schemas: list[type[Struct]],
                      schema_version: int, factory: ProducerFactory) -> None: ...
    def view(self, name: str, view: View) -> None: ...
    def trigger(self, id: str, subscription: Subscription,
                predicate: Callable[[Event, Views], bool],
                input_builder: Callable[[Views, Staged], Any],
                factory_kind: str, policy: FiringPolicy,
                cooldown: Cooldown = Logical(0)) -> None: ...
    def route(self, id: str, subscription: Subscription, slot: str,
              transform: Callable[[Event], Any]) -> None: ...
    def termination(self, policy: TerminationPolicy, scope: str = "run") -> None: ...
    def export(self, inner_kind: str, outer_schema: type[Struct]) -> None: ...
    def baseline(self, **metadata: Any) -> None: ...      # F-OBS-1 fixtures/seeds

class Runtime:
    def __init__(self, record_root: Path, *, persistent: bool = False,
                 fsync: FsyncPolicy = Interval(100), admission: int = 1024): ...
    async def run(self, topology: Callable[[TopologyBuilder], None]) -> RunResult: ...

# record side
def load_record(root: Path) -> RunRecord: ...
def attach(root: Path) -> LiveRecord: ...                 # F-PERS-4, read-only
def replay(record: RunRecord, level: Level) -> ReplayResult: ...
def explain_producer(record, producer_id) -> Explanation: ...
def first_divergence(a: RunRecord, b: RunRecord) -> Divergence | None: ...
def assert_event(record_or_bus, kind: str, **partial) -> Event: ...
def assert_no_event(record_or_bus, kind: str, **partial) -> None: ...
def assert_sequence(record_or_bus, kinds: list[str]) -> list[Event]: ...
```

The CLI (F-CLI-1..5) is a thin argparse layer over exactly these functions — F-API-6's existence proof is enforced by an import-linter rule: `substrate.cli` may import only the public API module.

## T-16 Performance budgets (implements N-PERF-1/2; informs check 15)

Per-cycle budget at the N-PERF-1 shape, from D-9 and D-3 measurements: validation ~0.2µs + 10 View updates ~1µs + ~5 predicate evaluations with enforcement ~1µs + framing/CRC ~1µs + amortized fsync (interval policy) ≈ **<5µs/cycle target, 200µs/cycle ceiling** (= 5K/sec floor) — a 40× engineering margin held in reserve for asyncio scheduling and admission hops, which the simulation did not model. The CI benchmark (check 15) runs the real writer, not the simulation, and compares against the previous release tag.

---

## T-OPEN — open implementation questions (constants and library choices only)

1. **Constants:** `SEGMENT_MAX_BYTES` (64 MiB?), `BLOB_THRESHOLD_BYTES` (16 KiB?), admission default (1024?), fsync interval (100ms?). Settle during 0.x against real topologies.
2. **Schema-descriptor dialect:** JSON Schema draft 2020-12 generated via `msgspec.json.schema()` — verify its output is stable across msgspec versions, else pin and vendor the generator.
3. **JCS implementation:** vendor (~120 lines) vs depend (`rfc8785` on PyPI — audit maintenance status). Vendoring favored: the encoder is conformance-critical and must not drift under a dependency bump.
4. **Live-attach change notification:** polling interval for `attach()` followers (simple) vs inotify/FSEvents (platform-specific). Polling first; the hot segment is append-only so polling is cheap and correct.
5. **Import-linter tooling** for the F-API-6 CLI rule: import-linter vs a custom AST check in CI.

## Conformance mapping

| Checks | Implemented by |
|---|---|
| 1, 2 | T-7, T-10 (cycle ordering, control queue) |
| 3 | T-7 (admission), T-1 (segments) |
| 4 | T-8 |
| 5 | T-7, T-10 (cooldown state), F-TERM-2 |
| 6, 9 | T-2, T-4, T-13 (replay) |
| 7 | T-11 |
| 8 | T-9 |
| 10 | T-12 |
| 11–13 | T-13 |
| 14 | T-9 (sidecar writes), F-OBS-6 |
| 15 | T-16 |
| 16 | T-2 (scan-verify-truncate) |

---

## Document history

- **DRAFT 1** — first technical spec, written against product spec DRAFT 6 with all D-1..D-9 decisions in hand: run-record directory and frame format in bytes (CRC-as-final-JCS-key, preserving grep-ability); envelope/manifest schemas with reserved `substrate.*` namespace; JCS whitelist with the 2^53 integer rule; write-ahead blob rule; fsync policy incl. macOS F_FULLFSYNC; writer-loop internals with subscription indexing and the D-9 enforcement implementation; boundary validation; export-map translation with two-hop cross-boundary provenance; locking per platform; inspection/divergence algorithms per D-8; comparison-report Structs; ground-truth harness mechanics; public API signatures with the import-linter enforcement of F-API-6; per-cycle performance budget; five open implementation questions, all constants or library picks.

*Flows back into the product spec (next synthesis): none yet identified. Flows into kernel v15: unchanged from product spec DRAFT 6 footer.*
