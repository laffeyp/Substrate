# API reference — `substrate.api`

The complete public surface (F-API-1). Everything else is private; the CLI imports only
this module (F-API-6). **This page is GENERATED from the live `substrate.api.__all__` and
the symbols' own docstrings** (`scripts/gen_api_docs.py`) so it cannot drift from the
code. Regenerate (`uv run python scripts/gen_api_docs.py`) after any public-surface change.

## Data types

### `Event(seq: int, kind: str, schema: str, producer: substrate.types.ProducerRef | None, t: float, payload: Any)`

One bus event, persisted as one frame (technical §3.4).

`seq` is the bus sequence number (identity + total order, assigned at append).
`kind` is the event kind ("substrate." prefix reserved). `schema` is "<kind>@<ver>".
`producer` is the emitting Producer's ref, or None for runtime-emitted events.
`t` is a supplementary wall-clock timestamp (never used for ordering; excluded
from the D-8 equivalence relation). `payload` is the inline payload or a blob
reference. The `crc` field is added by the record layer at frame time (§3.3),
not carried on the in-memory Event.

### `BlobRef(sha256: str, bytes: int)`

Reference to a content-addressed payload in the blob store (technical §3.7).

Serialized in an envelope payload as {"$blob": "sha256:<hex>", "bytes": n}; this
Struct is the typed in-memory form. `sha256` is the canonical-bytes hash; `bytes`
is the stored length.

### `ProducerRef(kind: str, instance: str, parent: str | None = None)`

A Producer's on-the-wire identity (envelope `producer` field, technical §3.4).

Distinct from the in-memory ProducerId {kind, instance_id, parent_id, metadata}
(kernel Decision #2): the wire form carries only what a reader needs to identify
and link the Producer. `parent` is the spawning Producer's instance, or None for
topology-declared initial Producers.

### `Subscription(kinds: frozenset[str] = frozenset(), producers: frozenset[str] = frozenset())`

What a Predicate / View / Route is consulted on (technical §16, §6.5).

The writer's subscription index consults a subscriber only when an event matches
its `kinds` and/or `producers`. Both empty is a registration error (enforced at
topology registration, not here); "subscribe to everything" must be spelled
explicitly. Frozensets keep the subscription immutable and hashable.

## Primitives & protocols

### `Producer(*args, **kwargs)`

A callable `(input) -> AsyncIterable[Event]` (kernel §1; design §4.2/§9.6).

The factory returns this callable per instantiation; the runtime calls it with the
sealed, resolved input and consumes the event stream until the Producer completes,
fails, or is cancelled — emitting the corresponding lifecycle event. A Producer has
no runtime-level identity, planning, or goal state (kernel non-goals); state lives
on the log.

NOTE (flow-back): technical §16 shows the object-with-`.start()` form; design §9.6
chooses the callable form deliberately (simpler, asyncio-native, no class
hierarchy) and rejects the class form. We follow the design spec; technical §16
should be updated to the callable form to match.

### `View(*args, **kwargs)`

A deterministic incremental projection over the bus (kernel §4).

Updated synchronously in append-cycle step 3, before any Route or Predicate.
`deterministic` declares whether `value()` is composed of RFC-8785-encodable
types and so participates in N-DET-1 (byte-identical replay); a View holding
non-canonical types sets it False and is flagged `determinism: excluded` at
registration (technical §4.2).

### `BufferView(producer: 'str') -> 'None'`

Accumulated payloads from one Producer kind (kernel §4 — the most common View).

### `KindBuffer(kind: 'str') -> 'None'`

Accumulated payloads of one event KIND (a kind-subscribed sibling of BufferView, which
subscribes by Producer kind). Useful when several Producer kinds emit the same event kind
and a Predicate gates on the aggregate (e.g. R-1's "≥K Candidate answers" Bus-view).

### `KindCount(kind: 'str') -> 'None'`

Count of events of one kind.

### `PerKindLatest(kind: 'str') -> 'None'`

Latest payload seen for one kind.

### `StartedCompletedCounts() -> 'None'`

Per-Producer-kind started vs ended (completed+failed+cancelled) counts — the
substrate of the progress-gating / cohort-frontier predicate (kernel §"Progress
gating"). Keys on the subject Producer identity carried in the lifecycle payload
(P-SUBJECT-ID, ratified into vocabulary v0.1).

### `Once() -> 'None'`

First satisfaction fires; further satisfactions ignored.

### `PerEvent()`

Each newly-satisfying event fires the Trigger once.

### `PerKey(fn: 'Callable[[Event], Any]') -> 'None'`

One firing per distinct key extracted from the event (CEP window-and-key).

### `WhileTrue(cooldown: 'Cooldown | None' = None) -> 'None'`

Fires continuously while the predicate holds, throttled by a cooldown.

The cooldown is a TRIGGER-level concept (kernel §6 — "throttled by a cooldown"):
cooldown enforcement lives in the runtime, which owns the single, replayable
append-counter (subscription-matched cycles) and the wall-clock clock + replay-ceiling
demotion. WhileTrue therefore does NOT self-throttle (that would double-enforce);
`cooldown` is exposed so TopologyBuilder.trigger can lift it to the trigger level.

### `Logical(appends: int = 0)`

Cooldown counted in append cycles (deterministic, replayable).

### `WallClock(seconds: float = 1.0)`

Cooldown in seconds. Opt-in; flagged at registration; demotes replay to 3(b).

### `TerminationPolicy(name: 'str', fn: 'Callable[[TermContext], Decision]', resume_condition: 'str | None' = None, watchdog_seconds: 'float | None' = None, finalisation: 'Callable[[TermContext], Any] | None' = None) -> 'None'`

A named decision callback. `name` is recorded in substrate.TerminationMatched.

`watchdog_seconds`, when set, is the writer's idle-poll window (how often the
writer wakes to test quiescence when the inbox is idle) — set by
quiescence_with_watchdog(seconds=). None means "use the runtime default poll".

`finalisation`, when set, is a callable run at finalise-run time that produces the
run's final output payload; it is recorded in substrate.RunFinalised.finalisation_payload
and surfaced on RunResult.finalisation_payload. None → no payload (an empty RunFinalised).
The payload must be canonical (§4.2); a non-canonical payload is dropped to None with the
failure noted, never crashing finalisation.

### `Decision(*values)`

Create a collection of name/value pairs.

Example enumeration:

>>> class Color(Enum):
...     RED = 1
...     BLUE = 2
...     GREEN = 3

Access them by:

- attribute access:

  >>> Color.RED
  <Color.RED: 1>

- value lookup:

  >>> Color(1)
  <Color.RED: 1>

- name lookup:

  >>> Color['RED']
  <Color.RED: 1>

Enumerations can be iterated over, and know how many members they have:

>>> len(Color)
3

>>> list(Color)
[<Color.RED: 1>, <Color.BLUE: 2>, <Color.GREEN: 3>]

Methods can be added to enumerations, and members can have their own
attributes -- see the documentation for details.

## Termination recipes

### `threshold_count(kind: 'str', n: 'int') -> 'TerminationPolicy'`

Finalise once `n` events of `kind` have been appended.

### `all_completed() -> 'TerminationPolicy'`

Finalise on quiescence once every started Producer has ended.

### `quiescence_with_watchdog(seconds: 'float' = 30.0) -> 'TerminationPolicy'`

Finalise when the run goes quiescent (no work in flight). `seconds` is the
watchdog window the runtime uses to wake and test quiescence (it bounds the writer
idle-poll interval; see Runtime._poll_s).

### `pause_await_input(when: 'Callable[[TermContext], bool]', resume_condition: 'str') -> 'TerminationPolicy'`

Pause and emit a typed resume_condition when `when` holds (kernel halt-with-resume).

### `cancel_all_others(when: 'Callable[[TermContext], bool]') -> 'TerminationPolicy'`

Cancel every OTHER running Producer (all but the subject — the producer of the
just-appended event) when `when(ctx)` holds (kernel §8; F-LIFE-2). CANCEL_OTHERS does NOT
finalise: the cancelled Producers emit substrate.ProducerCancelled on the log and the run
continues (typically to quiescence). The canonical R-1 use: fire on the adjudicator's
completion, cancel the still-running candidates, then a quiescence/all-completed policy
finalises. Compose: any_of(cancel_all_others(adjudicated), all_completed()).

### `let_finish(when: 'Callable[[TermContext], bool]') -> 'TerminationPolicy'`

Let all running Producers finish (no cancellation), then finalise — when `when(ctx)`
holds (kernel §8; F-LIFE-2). LET_FINISH stops admitting new work and finalises once the
in-flight Producers drain; here modelled as: when `when` holds AND the run is quiescent
with all started Producers ended, finalise (the 'graceful drain' terminal).

### `any_of(*policies: 'TerminationPolicy') -> 'TerminationPolicy'`

Finalise/pause when any composed policy returns a non-CONTINUE decision.

### `all_of(*policies: 'TerminationPolicy') -> 'TerminationPolicy'`

Finalise only when all composed policies agree to finalise.

## Topology & execution

### `TopologyBuilder() -> 'None'`

_(no docstring)_

- `baseline(self, **metadata: 'Any') -> 'None'` — 
- `build(self) -> 'Registration'` — Freeze and statically validate (design §5.5). Raises RegistrationError.
- `initial(self, kind: 'str', *, input: 'Any' = None) -> 'None'` — 
- `producer_kind(self, kind: 'str', *, schemas: 'Sequence[type]', schema_version: 'int', factory: 'Callable[[], Producer]', deterministic: 'bool' = False, author_version: 'str | None' = None) -> 'None'` — 
- `route(self, id: 'str', *, subscription: 'Subscription', slot: 'str', transform: 'Callable[[Any], Any]') -> 'None'` — 
- `termination(self, policy: 'TerminationPolicy', *, scope: 'str' = 'run') -> 'None'` — 
- `trigger(self, id: 'str', *, subscription: 'Subscription', predicate: 'Callable[..., bool]', starts: 'str', input_builder: 'Callable[..., Any]', policy: 'FiringPolicy | None' = None, cooldown: 'Cooldown | None' = None) -> 'None'` — 
- `view(self, name: 'str', view: 'View') -> 'None'` — 

### `register_topology(name: 'str', factory: 'Callable[[TopologyBuilder], None]') -> 'None'`

_(no docstring)_

### `get_topology(name: 'str') -> 'Callable[[TopologyBuilder], None]'`

_(no docstring)_

### `Runtime(record_root: 'Path | str', *, persistent: 'bool' = False, fsync: 'FsyncPolicy' = Interval(milliseconds=100), admission: 'int' = 1024, budget_us: 'int' = 100, hysteresis_k: 'int' = 3, writer_stats: 'bool' = False, diagnostics: 'bool' = False) -> 'None'`

Executes one topology and produces one run record (single-use).

- `run(self, topology: 'Callable[[TopologyBuilder], None]') -> 'RunResult'` — 

### `RunResult(run_id: str, record_root: str, status: Literal['finalised', 'paused', 'failed'], final_event: substrate.types.Event | None, elapsed_seconds: float, finalisation_payload: typing.Any | None)`

A base class for defining efficient serializable objects.

Fields are defined using type annotations. Fields may optionally have
default values, which result in keyword parameters to the constructor.

Structs automatically define ``__init__``, ``__eq__``, ``__repr__``, and
``__copy__`` methods. Additional methods can be defined on the class as
needed. Note that ``__init__``/``__new__`` cannot be overridden, but other
methods can. A tuple of the field names is available on the class via the
``__struct_fields__`` attribute if needed.

Additional class options can be enabled by passing keywords to the class
definition (see example below). These configuration options may also be
inspected at runtime through the ``__struct_config__`` attribute.

Configuration
-------------
frozen: bool, default False
   Whether instances of this type are pseudo-immutable. If true, attribute
   assignment is disabled and a corresponding ``__hash__`` is defined.
order: bool, default False
   If True, ``__lt__``, `__le__``, ``__gt__``, and ``__ge__`` methods
   will be generated for this type.
eq: bool, default True
   If True (the default), an ``__eq__`` method will be generated for this
   type. Set to False to compare based on instance identity alone.
kw_only: bool, default False
   If True, all fields will be treated as keyword-only arguments in the
   generated ``__init__`` method. Default is False.
omit_defaults: bool, default False
   Whether fields should be omitted from encoding if the corresponding value
   is the default for that field. Enabling this may reduce message size, and
   often also improve encoding & decoding performance.
forbid_unknown_fields: bool, default False
   If True, an error is raised if an unknown field is encountered while
   decoding structs of this type. If False (the default), no error is raised
   and the unknown field is skipped.
tag: str, int, bool, callable, or None, default None
   Used along with ``tag_field`` for configuring tagged union support. If
   either are non-None, then the struct is considered "tagged". In this case,
   an extra field (the ``tag_field``) and value (the ``tag``) are added to the
   encoded message, which can be used to differentiate message types during
   decoding.

   Set ``tag=True`` to enable the default tagged configuration (``tag_field``
   is ``"type"``, ``tag`` is the class name). Alternatively, you can provide
   a string (or less commonly int) value directly to be used as the tag
   (e.g. ``tag="my-tag-value"``).``tag`` can also be passed a callable that
   takes the class qualname and returns a valid tag value (e.g.
   ``tag=str.lower``). See the docs for more information.
tag_field: str or None, default None
   The field name to use for tagged union support. If ``tag`` is non-None,
   then this defaults to ``"type"``. See the ``tag`` docs above for more
   information.
rename: str, mapping, callable, or None, default None
   Controls renaming the field names used when encoding/decoding the struct.
   May be one of ``"lower"``, ``"upper"``, ``"camel"``, ``"pascal"``, or
   ``"kebab"`` to rename in lowercase, UPPERCASE, camelCase, PascalCase,
   or kebab-case respectively. May also be a mapping from field names to the
   renamed names (missing fields are not renamed). Alternatively, may be a
   callable that takes the field name and returns a new name or ``None`` to
   not rename that field. Default is ``None`` for no field renaming.
repr_omit_defaults: bool, default False
   Whether fields should be omitted from the generated repr if the
   corresponding value is the default for that field.
array_like: bool, default False
   If True, this struct type will be treated as an array-like type during
   encoding/decoding, rather than a dict-like type (the default). This may
   improve performance, at the cost of a more inscrutable message encoding.
gc: bool, default True
   Whether garbage collection is enabled for this type. Disabling this *may*
   help reduce GC pressure, but will prevent reference cycles composed of only
   ``gc=False`` from being collected. It is the user's responsibility to ensure
   that reference cycles don't occur when setting ``gc=False``.
weakref: bool, default False
   Whether instances of this type support weak references. Defaults to False.
dict: bool, default False
   Whether instances of this type will include a ``__dict__``. Setting this to
   True will allow adding additional undeclared attributes to a struct instance,
   which may be useful for holding private runtime state. Defaults to False.
cache_hash: bool, default False
   If enabled, the hash of a frozen struct instance will be computed at most
   once, and then cached on the instance for further reuse. For expensive
   hash values this can improve performance at the cost of a small amount of
   memory usage.

Examples
--------
Here we define a new `Struct` type for describing a dog. It has three fields;
two required and one optional.

>>> class Dog(Struct):
...     name: str
...     breed: str
...     is_good_boy: bool = True
...
>>> Dog('snickers', breed='corgi')
Dog(name='snickers', breed='corgi', is_good_boy=True)

Additional struct options can be set as part of the class definition. Here
we define a new `Struct` type for a frozen `Point` object.

>>> class Point(Struct, frozen=True):
...     x: float
...     y: float
...
>>> {Point(1.5, 2.0): 1}  # frozen structs are hashable
{Point(x=1.5, y=2.0): 1}

## Records & encoding

### `read_record(root: 'Path | str') -> 'Iterator[dict[str, Any]]'`

Yield every recoverable envelope in seq order: sealed segments (by filename),
then the recoverable prefix of the hot segment. Does not depend on the manifest
(segments are authoritative, §3.5). Read-only, symlink-not-followed (§17); does not
modify anything.

### `recover_open_segment(root: 'Path | str') -> 'int'`

Writer-side recovery (run at restart/attach, §3.3): truncate the hot segment to
the last complete, crc-valid frame. Returns the number of frames kept. Sealed
segments are never touched.

### `Interval(milliseconds: int = 100)`

fsync at most every `milliseconds` (default 100); amortized throughput.

### `Always()`

fsync after every frame; zero complete frames lost, capped at device fsync rate.

### `NoFsync()`

OS page cache only; the disk never bottlenecks (loss = whatever the OS last flushed).

### `canonical_bytes(obj: 'Any') -> 'bytes'`

The canonical RFC-8785 bytes for a value (= B_hash for a crc-less object).
Deterministic: the same logical value yields identical bytes everywhere.

### `content_hash(obj: 'Any') -> 'str'`

The `sha256:<hex>` content hash over a value's canonical bytes — the identity
used for blob ids, input_sha256, message_sha256, and D-8 comparison (§3.3).

## Live attach (technical §13)

### `attach(root: 'Path | str', *, poll_ms: 'int' = 100) -> 'LiveRecord'`

Open a read-only follower over a run record that may still be growing (technical
§13, F-PERS-4). Read-only, lock-free, signal-free by construction.

### `LiveRecord(root: 'Path | str', *, poll_ms: 'int' = 100) -> 'None'`

A read-only follower over a (possibly still-growing) run record (technical §13).

Hold one per reader. `read_new()` returns every complete, CRC-valid frame appended
since the last call (sealed segments first, then the recoverable prefix of the hot
segment); the trailing partial line is ignored until it completes. `follow()` is a
blocking generator that polls for growth. The follower opens files read-only, takes
no lock, and never writes — F-PERS-4 by construction.

- `follow(self, *, until_finalised: 'bool' = True) -> 'Iterator[dict[str, Any]]'` — Blocking generator: yield frames as they appear, polling for growth. Stops after
- `read_new(self) -> 'list[dict[str, Any]]'` — Every complete frame appended since the last call, in seq order: all sealed

## Off-bus sidecars (technical §3.8 / §6.4)

### `read_sidecar(path: 'Path | str') -> 'list[dict[str, Any]]'`

Read an off-bus sidecar JSONL file into a list of records (read-only). Used by
`substrate stats` and dashboards; returns [] if the file does not exist.

## Composition (technical §20)

### `embedded_substrate(topology: 'Callable[[TopologyBuilder], None]', *, exports: 'dict[str, type | ExportRule] | None' = None, default_export: 'type | ExportRule | None' = None, inner_poll_ms: 'int' = 5) -> 'Callable[[Any], AsyncIterator[Any]]'`

Build a Producer (the `start` callable) that runs `topology` as an INNER substrate and
exports the mapped inner kinds onto the outer bus (technical §20).

`exports` maps an inner event kind to either an outer Struct TYPE (default transform =
splat the inner payload) or an `(outer_type, transform)` pair. Inner `substrate.*` kinds
NEVER cross unless explicitly mapped; unmapped application kinds never cross.

DEFAULT EXPORT (F-COMP-1 / §20: "default export = inner RunFinalised only"): the inner
`substrate.RunFinalised` is exported by default. Because an OUTER Producer kind may not
emit a `substrate.*` kind (reserved namespace, F-OBS-5), the default export needs an
author-named OUTER carrier Struct — pass it as `default_export` (a type, or an
(outer_type, transform) pair; the transform receives the inner RunFinalised payload,
which carries the inner root / finalisation_payload). When `default_export` is given and
`exports` does not already map RunFinalised, a RunFinalised→default_export rule is
installed. If NEITHER is given, the inner RunFinalised does not cross as a frame — the
inner root is still recorded in the outer TriggerFired resolved input (the §20 provenance
link) and the inner record is complete at its own root. (The "default export = RunFinalised"
wording assumes an outer carrier; that the carrier must be author-named is a tech-spec §20
flow-back — see BLACKBOARD.)

The returned callable is the Producer `start`: the outer runtime calls it with the sealed
resolved input (which carries the inner record root under input["inner_root"]) and
consumes the translated outer events under outer admission.

CONTRACT — every embedded-substrate topology MUST thread `inner_root` in the embedded
Producer's resolved input (e.g. `b.initial("embedded", input={"inner_root": str(path)})`,
or a trigger input_builder that supplies it). This is a deliberately STRICTER contract
than an optional fallback: it is the correct trade for run-granularity provenance — the
inner root is then unconditionally recorded in the outer TriggerFired.resolved_input, so
the inner run is always citable from the outer record (§20). Omitting it raises
InnerRootRequired, which surfaces as a recorded outer substrate.ProducerFailed (not a
fabricated, un-citable fallback root).

### `EmbeddedRunFailed(message: 'str', *, inner_run_id: 'str', inner_root: 'str') -> 'None'`

An embedded substrate's inner run did not finalise normally. Raised by the embedded
Producer so the OUTER runtime records ONE substrate.ProducerFailed carrying the inner
run_id (technical §20). The inner record stays complete at its own root.

## Conformance suite (product §7)

### `run_conformance(*, include_perf: 'bool' = True) -> 'ConformanceReport'`

Run all 17 conformance checks, each in its own temp record root. Returns a typed
report; the caller (the CLI / CI) decides the exit policy. `include_perf=False` skips the
perf floor probe (check 15) — used where the dedicated benchmark covers it.

### `ConformanceReport(results: 'tuple[CheckResult, ...]') -> None`

ConformanceReport(results: 'tuple[CheckResult, ...]')

### `CheckResult(number: 'int', name: 'str', status: 'Status', detail: 'str') -> None`

CheckResult(number: 'int', name: 'str', status: 'Status', detail: 'str')

### `Status(*values)`

Create a collection of name/value pairs.

Example enumeration:

>>> class Color(Enum):
...     RED = 1
...     BLUE = 2
...     GREEN = 3

Access them by:

- attribute access:

  >>> Color.RED
  <Color.RED: 1>

- value lookup:

  >>> Color(1)
  <Color.RED: 1>

- name lookup:

  >>> Color['RED']
  <Color.RED: 1>

Enumerations can be iterated over, and know how many members they have:

>>> len(Color)
3

>>> list(Color)
[<Color.RED: 1>, <Color.BLUE: 2>, <Color.GREEN: 3>]

Methods can be added to enumerations, and members can have their own
attributes -- see the documentation for details.

## Replay (technical §12)

### `replay(record: 'Any', level: 'ReplayLevel' = '1') -> 'ReplayResult'`

Replay a record at the given honesty tier (technical §12).

Level 1: stream + counts. Level 2: + verify every TriggerFired input hash (D-5).
Level 3a: + the native-re-execution PRECONDITION gate (all kinds deterministic AND
replay_ceiling=="3a"); this returns the gate result (preconditions_ok / refusal_reason)
rather than re-running — re-execution is the Runtime's job. Level 3b: DEFERRED, raises
NotImplementedError (needs a t-replay decision; not faked).

### `assert_replayable(record: 'Any', level: 'ReplayLevel') -> 'ReplayResult'`

Run the replay and raise if it is not honestly supported at `level`: a Level-2
hash mismatch or a failed Level-3(a) precondition raises ReplayError (honest refusal,
F-RPLY-1). Returns the ReplayResult on success.

### `ReplayResult(level: str, frame_count: int, counts: dict[str, int], complete: bool, decisions_verified: int = 0, mismatches: tuple[substrate.replay.HashMismatch, ...] = (), preconditions_ok: bool | None = None, refusal_reason: str | None = None)`

The typed outcome of a replay (technical §12). `level` is the tier actually run.
`counts` is the per-kind frame count (Level 1+). `decisions_verified` is the number of
TriggerFired input hashes checked (Level 2). `mismatches` is empty on success.
`preconditions_ok` / `refusal_reason` carry the Level-3(a) gate result.

### `HashMismatch(seq: int, trigger_id: str | None, recorded: str, recomputed: str)`

A Level-2 verification failure: a TriggerFired's recorded input hash does not match
the recomputed canonical hash of its recorded resolved input (D-5 broken).

## Inspection / provenance / divergence (technical §14)

### `explain_producer(record: 'Any', producer: 'str') -> 'Explanation'`

The typed cause of `producer`'s existence: the TriggerFired that scheduled it
(or the run open, for an initial Producer), with its resolved-input hash. O(record)
once. Raises ProducerNotFound if the instance has no firing on the record.

### `trace_ancestry(record: 'Any', producer: 'str') -> 'tuple[Explanation, ...]'`

The spawn chain from `producer` up to the root, root-LAST: index 0 is `producer`
itself, each subsequent entry its parent, ending at the initial Producer (cause
RunStarted). Acyclic by construction; a missing link raises ProducerNotFound. The
chain is the provenance-closure witness (conformance check 11).

### `view_at(record: 'Any', seq: 'int', view: 'View') -> 'Any'`

Reconstruct a View's state as observed at sequence `seq` (Level-1 replay truncated
at seq): fold every matching event with seq <= `seq` into the provided View instance
and return its value() (technical §14, conformance check 12 — view-at fidelity).

Takes a View INSTANCE, not a name: a record stores event payloads, not View code, so
the caller supplies the View whose update()/subscription define the fold. (Spec §16
signature is `view_at(record, seq, view: str)` assuming the topology's View code is
available by name; the instance form is the honest dependency — flagged as a tech-spec
flow-back in BLACKBOARD.) The View should be fresh; folding is not idempotent.

### `decisions_between(record: 'Any', a: 'int', b: 'int') -> 'tuple[Any, ...]'`

Every runtime decision (substrate.* frame) with a <= seq <= b, in seq order, as
reconstructed Event objects (technical §14). The kernel's decision record over a
sequence window — Level-2 reads, no re-execution.

### `first_divergence(rec_a: 'Any', rec_b: 'Any') -> 'Divergence | None'`

The first index where two records' D-8 comparison sequences differ, or None if
they are equivalent (technical §14, conformance check 13). The comparison sequence is
(kind, canonical payload hash) per frame in seq order; supplementary metadata (t,
host, config) is excluded by construction (it is never hashed here).

### `Explanation(kind: str, instance: str, parent: str | None, cause: str, trigger_id: str | None, firing_key: str | None, input_sha256: str | None, at_seq: int)`

The typed cause of one Producer's existence (technical §14: explain_producer).

`cause` is one of "TriggerFired" | "RunStarted" (an initial Producer's firing
attributes to the run open). `at_seq` is the seq of the firing frame. `input_sha256`
is the resolved-input content hash recorded at the firing — the citable identity of
what the Producer ran with.

### `Divergence(index: int, seq: int, kind_a: str | None, kind_b: str | None, hash_a: str | None, hash_b: str | None)`

The first point two records of the same topology diverge (technical §14 / D-8).

`index` is the position in the seq-ordered comparison sequence; `seq` is the bus
seq of the diverging frame in record A (or the shorter record's end). `kind_a` /
`kind_b` and `hash_a` / `hash_b` are the (kind, canonical payload hash) pair that
differs. When one record is a strict prefix of the other, the longer record's extra
frame is the divergence and the shorter side's fields are None.

## Test helpers (technical §15)

### `assert_event(rec: 'Any', kind: 'str', **partial: 'Any') -> 'dict[str, Any]'`

Assert at least one event of `kind` with the given partial payload exists;
return the first match. Raises AssertionError citing what was searched.

### `assert_no_event(rec: 'Any', kind: 'str', **partial: 'Any') -> 'None'`

_(no docstring)_

### `assert_sequence(rec: 'Any', kinds: 'Sequence[str]') -> 'list[dict[str, Any]]'`

Assert the record's event-kind sequence equals `kinds` exactly.

## Exceptions (design §6.3)

### `SubstrateError`

Base for all substrate-raised exceptions.

### `BusLockedError(message: 'str', advisory: 'dict[str, object] | None' = None) -> 'None'`

A persistent-bus root is already locked by another runtime (technical §11).
Carries the advisory lock contents (pid, hostname, start time).

### `RegistrationError`

A topology is malformed (design §6.1). Raised at build time, before any run.

### `UnsupportedPlatformError`

A correctness primitive is unavailable on this platform — e.g. persistent
buses on Windows (technical §11; N-PORT-1). Raised at configuration time.

### `FsyncError`

fsync failed; the medium is untrustworthy. The writer must NOT write
RunFinalised on it — close, crash, let recovery report the truncated tail
(technical §5.2, the fsyncgate lesson).

### `ProducerNotFound`

A provenance/inspection query named a Producer instance not in the record.

### `SequenceOutOfRange`

A view_at / inspection query named a sequence number outside the record.

### `InputTypeError`

A resolved Producer input contains a non-immutable / non-whitelisted type;
immutability is enforced by construction (technical §8.3 / F-PROD-3).

### `ReplayError`

A replay precondition failed or the requested level is unsupported for this
record (technical §12). Carries a typed reason; the run record path is the evidence.

### `RecordIncompleteError`

A record has no terminal substrate.RunFinalised (e.g. torn at seq N, §5.2).

