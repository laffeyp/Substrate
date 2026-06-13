# Substrate — Design Specification

**Status:** DRAFT 1 · **Owner:** the spec maintainer · **Companions:**
kernel specification (v15), product specification (DRAFT 7),
technical specification (DRAFT 5)

This is the third of three artifacts. It covers the **felt experience**
of using the substrate: how the API reads, how the CLI behaves, what
users see when things fail, and what a UI could look like even though
v1.0 ships none. It does not cover runtime semantics (kernel v15),
product requirements (product spec), or implementation internals
(technical spec).

**Format.** Adapted from the Rust RFC template (Motivation, Guide-level
explanation, Reference-level explanation, Rationale and alternatives,
Prior art, Unresolved questions, Future possibilities), with explicit
UX sections (CLI, error visibility) and user journeys grounded in
concrete walkthroughs. The split between guide-level (§3 first-hour
experience, §7 journeys) and reference-level (§4 API, §5 CLI, §6
error UX) follows Rust RFC discipline: teach the design narratively
first, pin it precisely second.

**Normativity.** §4 and §5 bind the implementation. §3 and §7 are
narrative — they describe the experience the design must produce but
don't add new contracts. §8 (alternatives) and §9 (prior art) explain
the design rather than constrain it.

---

## Contents

1. What this is
2. Design principles
3. First-hour experience (guide-level)
4. API design (reference-level)
5. CLI UX (reference-level)
6. Error and observability UX
7. User journeys
8. Future UI sketches
9. Rationale and alternatives
10. Prior art
11. Unresolved questions
12. Document history

---

## 1. What this is

A design spec for the surface a user touches. v1.0's surfaces are a
Python library (the eight primitives + runtime + record functions +
test helpers) and a CLI (`run`, `replay`, `inspect`, `validate`,
`tail`, `conformance`). The future-UI section exists not to design
something that ships in v1.0 but to make F-API-6 ("any UI buildable
on public surfaces alone") concrete — if sketching a UI reveals a
missing public hook, that's a v1.0 design bug found cheaply.

The product spec is what the substrate IS and what it does. The
technical spec is what bytes go on disk and what the writer cycle
looks like. The design spec is what code a user writes and what they
see when they run it.

---

## 2. Design principles

These are cross-cutting commitments that the API, CLI, and future UI
all share. They're upstream of every specific design choice in §4
and §5.

**Vocabulary consistency with the kernel.** Producer, Bus, View,
Predicate, Trigger, Route, TerminationPolicy, Topology. The library
uses these words. The CLI uses these words. Error messages use these
words. No anthropomorphic synonyms (no "agent", "actor", "speaker"),
no marketing reframes (no "workflow", "step", "task"). The kernel spec
has eight words; the design spec keeps them eight.

**Structured output everywhere.** The runtime never returns natural
language. `explain_producer` returns a typed `Explanation` record, not
a string. The CLI's `inspect --why` prints structured fields, not
prose. Error messages have typed fields (`error_kind`, `at_path`,
`sequence`) that downstream tools can parse. A user who wants prose
asks an LLM-reader Producer to generate it; the substrate doesn't.

**Errors are events when possible, typed exceptions when they can't
be.** A failed Producer emission becomes
`substrate.ProducerEmittedInvalidEvent` on the log. A failed
`input_builder` becomes `substrate.InputBuildFailed` on the log. A
Predicate exceeding budget becomes `substrate.PredicateQuarantined`
on the log. Things that happen before a run starts (registration
errors, file-not-found, lock contention) are typed Python
exceptions — but they carry the same fields the log events would.

**Sequence numbers everywhere identification happens.** Anything the
user looks at — error messages, inspect output, replay output,
divergence reports — cites sequence numbers. "At seq 1247" is the
universal precise referent. Never "around the third trigger" or "in
that section."

**One way to do common things, escape hatches for uncommon things.**
Retry-with-failure-context is a named helper, one line to register.
Halt-with-resume is a named helper, one line to register. Custom
behavior is possible — Triggers, Routes, and TerminationPolicies are
callables — but the common case is short.

**The CLI is implementable on public APIs alone.** F-API-6 in the
product spec is normative: the CLI uses no private hooks. This is a
design constraint on the public API surface — if the CLI needs
something, it must be exposed publicly. The CLI is the standing
existence proof.

**Names are nouns; methods are verbs that match.** `Runtime.run()`,
`Record.attach()`, `Record.replay()`, `RunResult.record_root`,
`Producer.start()`. No `do_run` or `process_event_loop` or
`execute_topology_pipeline`.

**Type ergonomics matter.** The public API is fully typed (`py.typed`,
F-API-1). Generics are used where they buy something — `View[T]`
parameterizes on payload — and avoided where they don't. A user
writing a topology should see clean type-checker output, not
`Generic[A, B, Generic[C, D]]` casserole.

**Failure paths are as designed as success paths.** What the user sees
when their topology fails to register, when their Predicate gets
quarantined, when their run pauses for input, when their record gets
corrupted — all are specified here, not left to the implementation.

---

## 3. First-hour experience (guide-level)

The canonical "from zero to a working topology in under an hour"
walkthrough. This section is narrative and uses placeholder import
name `rostrum` per the naming run (or whichever name is final at
implementation time). Every code block compiles and runs against the
v1.0 implementation.

### 3.1 Install

```
$ pip install rostrum
```

That's it. One runtime dependency (msgspec, per D-3) installed
transitively. No model SDK, no broker, no daemon.

### 3.2 The smallest topology

A topology with one Producer and one TerminationPolicy. Counts to
three and finalises.

```python
# count_to_three.py
import asyncio
from pathlib import Path
from msgspec import Struct
from rostrum import Runtime, TopologyBuilder, AsyncIterator

class CountReached(Struct, frozen=True):
    n: int

async def counter(input: None) -> AsyncIterator:
    for n in range(1, 4):
        yield CountReached(n=n)

def topology(b: TopologyBuilder) -> None:
    b.producer_kind(
        "counter",
        schemas=[CountReached],
        schema_version=1,
        factory=lambda: counter,
    )
    b.initial("counter", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", n=1))

async def main():
    rt = Runtime(record_root=Path("./run-001"))
    result = await rt.run(topology)
    print(f"finalised: {result.record_root}")

asyncio.run(main())
```

Run it:

```
$ python count_to_three.py
finalised: run-001
```

Look at the record:

```
$ ls run-001/
manifest.json  events-000001.open.jsonl
```

Open the events file:

```
$ cat run-001/events-000001.open.jsonl
{"crc":"...","kind":"substrate.RunStarted","producer":null,"schema":"substrate.RunStarted@1","seq":0,"t":1718000000.0,"payload":{...}}
{"crc":"...","kind":"substrate.TriggerFired","producer":null,"schema":"substrate.TriggerFired@1","seq":1,"t":1718000000.1,"payload":{...}}
{"crc":"...","kind":"substrate.ProducerStarted","producer":{"kind":"counter","instance":"01...","parent":null},"schema":"substrate.ProducerStarted@1","seq":2,"t":1718000000.1,"payload":{...}}
{"crc":"...","kind":"CountReached","producer":{"kind":"counter","instance":"01...","parent":null},"schema":"CountReached@1","seq":3,"t":1718000000.2,"payload":{"n":1}}
{"crc":"...","kind":"CountReached","producer":{"kind":"counter","instance":"01..."},"schema":"CountReached@1","seq":4,"t":1718000000.3,"payload":{"n":2}}
{"crc":"...","kind":"CountReached","producer":{"kind":"counter","instance":"01..."},"schema":"CountReached@1","seq":5,"t":1718000000.4,"payload":{"n":3}}
{"crc":"...","kind":"substrate.ProducerCompleted","producer":{"kind":"counter","instance":"01..."},"schema":"substrate.ProducerCompleted@1","seq":6,"t":1718000000.5,"payload":{}}
{"crc":"...","kind":"substrate.TerminationMatched","producer":null,"schema":"substrate.TerminationMatched@1","seq":7,"t":1718000000.5,"payload":{"policy":"threshold_count","decision":"finalise-run"}}
{"crc":"...","kind":"substrate.RunFinalised","producer":null,"schema":"substrate.RunFinalised@1","seq":8,"t":1718000000.5,"payload":{}}
```

Or look at it with `tail`:

```
$ rostrum tail run-001/
seq=0  substrate.RunStarted               (topology=count_to_three, baseline=...)
seq=1  substrate.TriggerFired             trigger=__initial__  factory=counter
seq=2  substrate.ProducerStarted          producer=counter[01JF...]
seq=3  CountReached                       producer=counter[01JF...]  n=1
seq=4  CountReached                       producer=counter[01JF...]  n=2
seq=5  CountReached                       producer=counter[01JF...]  n=3
seq=6  substrate.ProducerCompleted        producer=counter[01JF...]
seq=7  substrate.TerminationMatched       policy=threshold_count  decision=finalise-run
seq=8  substrate.RunFinalised
```

That's a run. Every event has a sequence number. The Producer is
identified consistently. Lifecycle events use the reserved
`substrate.` prefix; application events (`CountReached`) don't.

### 3.3 Two Producers with a Trigger

Counter Producer A emits even numbers. A Trigger on each
`CountReached` event fires Producer B, which doubles the number.

```python
class CountReached(Struct, frozen=True):
    n: int

class Doubled(Struct, frozen=True):
    original: int
    doubled: int

async def counter(input: None):
    for n in range(1, 4):
        yield CountReached(n=n)

async def doubler(input: dict):
    yield Doubled(original=input["n"], doubled=input["n"] * 2)

def topology(b: TopologyBuilder):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1,
                    factory=lambda: counter)
    b.producer_kind("doubler", schemas=[Doubled], schema_version=1,
                    factory=lambda: doubler)
    b.initial("counter", input=None)
    b.trigger(
        "double-each",
        subscription=Subscription(kinds={"CountReached"}),
        predicate=lambda event, views: True,         # fire on every match
        starts="doubler",
        input_builder=lambda views, staged, event: {"n": event.payload.n},
        policy=PerEvent(),
    )
    b.termination(quiescence_with_watchdog(seconds=5))
```

A Trigger has a subscription (what kinds of events it's watching), a
predicate (a yes/no question on the event), an `input_builder` (how
to construct the spawned Producer's input from current state), and a
firing policy. The `PerEvent` policy fires the Trigger once per
matching event; `Once` fires only the first time; `PerKey(fn)` fires
once per distinct extracted key; `WhileTrue(cooldown)` fires
continuously while the predicate holds.

### 3.4 Inspecting why a Producer started

```
$ rostrum inspect run-002 --producer doubler[01JF...] --why
producer=doubler[01JF...]
parent=counter[01JF...]
caused_by:
  seq=12  substrate.TriggerFired
    trigger=double-each
    firing_key=null
    resolved_input={"n": 2}
    input_sha256=sha256:7a2f...
```

The cause is one Trigger firing. The resolved input is the literal
dict that was passed to the doubler Producer. The hash makes it
citeable across runs.

### 3.5 Replay

```
$ rostrum replay run-002 --level 2
[OK] Level 2 replay successful.
9 frames replayed.
All decisions reconstructed; resolved inputs verified by hash.
```

Level 2 reconstructs every Trigger firing, every injection, every
termination decision from the recorded events — without re-running
any Producer. The decisions are on the log; replay reads them.

`--level 3b` re-executes the kernel with every Producer substituted
by a log-backed emitter replaying its recorded emissions. The output
record is byte-identical to the input record. This is conformance
check 6.

---

## 4. API design (reference-level)

The public surface, with the design decisions behind each piece.

### 4.1 `TopologyBuilder`

Method-call style, not decorator-based. Each registration is one
method call:

```python
def my_topology(b: TopologyBuilder) -> None:
    b.producer_kind("writer", schemas=[CodeChunk], schema_version=1,
                    factory=writer_factory)
    b.producer_kind("checker", schemas=[CheckResult], schema_version=1,
                    factory=checker_factory)
    b.view("writer_buffer", BufferView(producer="writer"))
    b.trigger("check-on-chunk",
              subscription=Subscription(kinds={"CodeChunk"}),
              predicate=on_complete_declaration,
              starts="checker",
              input_builder=build_checker_input,
              policy=PerEvent())
    b.route("attach-buffer",
            subscription=Subscription(kinds={"CodeChunk"}),
            slot="prior_writer_text",
            transform=lambda event: event.payload.text)
    b.termination(quiescence_with_watchdog(seconds=10))
```

**Why not decorators.** Decorators put registration at module-import
time, which makes registration order depend on import order. With
method calls on a builder, registration order is explicit in the
topology function. Topologies are functions of the builder; that's
the contract.

**Why one builder method per primitive, not a unified `b.register(...)`**.
The primitive names are the substrate's vocabulary; the builder
methods *are* the vocabulary. `b.producer_kind` is the only way to
register one. `b.trigger` is the only way. The IDE's autocomplete
becomes the discovery surface.

**Names are kebab-case strings.** `"check-on-chunk"`, `"attach-buffer"`.
Used as identifiers in the record (`trigger_id`, `route_id`, etc.).
Mechanically convertible to filenames and log keys. snake_case was
considered but conflicts visually with Python identifiers; CamelCase
was considered but reads as a Python class name.

**`b.initial(kind, input=...)`** registers an initial Producer that
starts at run begin. Distinct from `b.trigger` because there's no
predicate — it's the root, attributed to `RunStarted`. Calling
`b.initial` multiple times registers multiple initial Producers; they
all start in parallel at run begin.

### 4.2 Producer kinds

A Producer is anything implementing `start(input) ->
AsyncIterator[Event]`. The factory pattern is used because Producers
often need configuration captured at registration but not at every
spawn:

```python
def writer_factory(model_endpoint: str, max_tokens: int):
    async def writer(input: WriterInput) -> AsyncIterator[Event]:
        async with httpx.stream("POST", model_endpoint, ...) as response:
            async for chunk in response.aiter_text():
                yield CodeChunk(text=chunk)
    return writer

b.producer_kind(
    "writer",
    schemas=[CodeChunk],
    schema_version=1,
    factory=lambda: writer_factory(model_endpoint=ENDPOINT, max_tokens=4096),
)
```

The factory is called once per Producer instantiation; it returns the
`start` callable, which is then called with the resolved input. The
configuration (`model_endpoint`, `max_tokens`) is closed over by the
factory — it's topology configuration, not Producer input
(per F-PROD-3 enforcement).

**`schemas` is a list of msgspec.Struct classes.** All the application
event kinds the Producer is allowed to emit. An attempt to emit
anything else triggers `substrate.ProducerEmittedInvalidEvent`. The
list is authoritative — adding a new event kind means bumping
`schema_version` and re-registering.

**Schemas must be frozen Structs.** `msgspec.Struct` subclasses with
`frozen=True`. Mutable Structs are rejected at registration with a
typed error pointing at the violating class.

```python
class CodeChunk(Struct, frozen=True):   # OK
    text: str
    line_start: int
    line_end: int

class CodeChunkV2(Struct):              # rejected — not frozen
    text: str
```

```
RegistrationError at "writer".schemas[0]:
  CodeChunk is not frozen.
  Producer event schemas must be declared with `frozen=True` so
  the runtime can enforce input immutability by construction
  (product spec F-PROD-3).
  Add `frozen=True` to the Struct declaration:

      class CodeChunk(Struct, frozen=True):
                              ^^^^^^^^^^^^
```

The error names the kind, the field, the constraint it violates, the
upstream requirement it's enforcing, and shows the fix inline. This
is the standard registration-error shape.

### 4.3 Predicates

Predicates are callables `(event, views) -> bool`. Subscription is
declared at registration time:

```python
def on_complete_declaration(event: Event, views: Views) -> bool:
    if event.kind != "CodeChunk":
        return False
    text = views["writer_buffer"].value()
    return text.rstrip().endswith(("\n}", "\n;"))

b.trigger(
    "check-on-chunk",
    subscription=Subscription(kinds={"CodeChunk"}),
    predicate=on_complete_declaration,
    starts="checker",
    input_builder=build_checker_input,
    policy=PerEvent(),
)
```

The subscription pre-filters: the writer only consults
`on_complete_declaration` when a `CodeChunk` event lands. Inside the
predicate, the event-kind check is technically redundant given the
subscription, but it documents intent and survives subscription
edits.

**Predicates are budget-enforced** (D-9, 100µs default). The
runtime measures wall-time per call, accumulates consecutive
violations, and quarantines after k=3. A quarantined predicate yields
`substrate.PredicateQuarantined` on the log; subsequent matching
events skip it. A topology should not call `httpx.get()` from a
predicate (it will quarantine immediately). The standard library
ships built-in predicates that are guaranteed sub-budget:
`EventKindMatches`, `BufferCrosses`, `KindCountReaches`, etc., for
when the predicate logic is simple.

**Predicate composition.** `AnyOf(p1, p2, ...)`, `AllOf(...)`,
`Not(p)`. These short-circuit, so `AllOf(cheap, expensive)` skips
`expensive` when `cheap` returns False.

### 4.4 Triggers

`b.trigger(id, subscription=..., predicate=..., starts=..., input_builder=...,
policy=..., cooldown=...)`. All keyword-only after the id.

**`starts`** names the Producer kind to instantiate. The kind must be
registered (via `b.producer_kind`); the builder checks this at
topology-function exit and raises `UnknownProducerKind` if not.

**`input_builder(views, staged, event) -> input`** constructs the
Producer's input. `event` is the event that fired the Trigger;
`views` are all registered Views (Mapping by name); `staged` are
messages staged by Routes targeting this Trigger's slots. The
returned input is sealed (F-PROD-3) and recorded in `TriggerFired`.

**Firing policies as importable classes:**

```python
from rostrum import Once, PerEvent, PerKey, WhileTrue

b.trigger(..., policy=Once())
b.trigger(..., policy=PerEvent())
b.trigger(..., policy=PerKey(lambda event: event.payload.row_id))
b.trigger(..., policy=WhileTrue(cooldown=Logical(appends=10)))
```

`PerKey` takes a key-extraction callable. The extracted key is
canonically encoded (per D-7) before deduplication, so two
implementations of the same `PerKey(fn)` produce the same firing
behavior. The key value is recorded as `firing_key` in `TriggerFired`.

**Cooldowns:**

```python
from rostrum import Logical, WallClock

b.trigger(..., cooldown=Logical(appends=100))   # every 100 appends max
b.trigger(..., cooldown=WallClock(seconds=1))   # every 1s max — DEMOTES REPLAY
```

`WallClock` is opt-in and flagged at registration. The runtime emits
a warning at registration and records the flag in `RunStarted`; the
record's `replay_ceiling` drops to `3b`. Users who don't want the
demotion get a typed error if they try to add a wall-clock cooldown
to a topology marked `replay_3a_required`.

### 4.5 Routes

```python
b.route(
    "failure-context",
    subscription=Subscription(kinds={"substrate.ProducerFailed"}),
    slot="failure_context",
    transform=lambda event: event.payload.error,
)
```

A Route stages a message into a named slot when its source predicate
matches. The next Trigger that fires whose `input_builder` reads
`staged["failure_context"]` gets the staged message. The retry
pattern:

```python
b.trigger(
    "retry-on-failure",
    subscription=Subscription(kinds={"substrate.ProducerFailed"}),
    predicate=lambda e, v: e.payload.producer.kind == "translator",
    starts="translator",
    input_builder=lambda v, staged, e: TranslatorInput(
        row=v["pending"].value()[e.payload.producer.instance],
        failure_context=staged.get("failure_context"),
    ),
    policy=PerKey(lambda e: e.payload.producer.instance),
)
```

The `staged` dict is populated by Routes whose source predicate
matched in the same cycle (or earlier cycles where the staging
persists). Routes that don't match are absent from `staged`; the
`input_builder` uses `.get()` for optional injection.

**Named retry helper.** The retry pattern is common enough to ship as
a named helper:

```python
from rostrum.patterns import retry_with_failure_context

retry_with_failure_context(
    b,
    of_kind="translator",
    max_attempts=3,
    failure_context_slot="failure_context",
)
```

This registers the Trigger and the Route in two lines. Power users
who need custom behavior write them out explicitly.

### 4.6 Views

```python
from rostrum.views import BufferView, KindCount, PerKindLatest

b.view("writer_buffer", BufferView(producer="writer"))
b.view("chunk_count", KindCount(kind="CodeChunk"))
b.view("last_check", PerKindLatest(kind="CheckResult"))
```

Standard Views ship in `rostrum.views`. Custom Views implement
`update(event)` and `value()`:

```python
class RetryCountView:
    deterministic = True
    subscription = Subscription(kinds={"substrate.ProducerFailed"})

    def __init__(self):
        self._counts: dict[str, int] = {}

    def update(self, event: Event) -> None:
        kind = event.payload.producer.kind
        self._counts[kind] = self._counts.get(kind, 0) + 1

    def value(self) -> Mapping[str, int]:
        return MappingProxyType(self._counts)

b.view("retry_counts", RetryCountView())
```

The `deterministic` attribute declares whether the View's
`value()` state is canonically-encodable (D-7) and participates in
N-DET-1 (byte-identical replay). A View holding non-canonical types
sets `deterministic=False`; the runtime accepts it but excludes it
from determinism guarantees (and flags this in `RunStarted`).

### 4.7 TerminationPolicy

```python
from rostrum.policies import (
    cancel_all_others, let_finish, quiescence_with_watchdog,
    threshold_count, all_completed, subtree_cancellation,
    pause_await_input,
)

b.termination(all_completed())  # simple
b.termination(quiescence_with_watchdog(seconds=30))
b.termination(
    pause_await_input(
        when=lambda state: state.has_event_of_kind("HumanReviewRequested"),
        resume_condition="architect provides DecisionMade event",
    )
)
```

Standard policies compose:

```python
from rostrum.policies import any_of, all_of

b.termination(any_of(
    all_completed(),
    quiescence_with_watchdog(seconds=60),
))
```

`any_of` finalises when any composed policy fires; `all_of` waits for
all. Per-Producer scoping:

```python
b.termination(cancel_all_others(), scope="run")
b.termination(let_finish(), scope=Producer("translator"))
```

The scope parameter controls whether the policy applies run-wide or
to the subtree of a specific Producer kind. Per the kernel spec,
per-Producer policies are evaluated first; per-run policies interpret
the aggregate; per-run overrides.

### 4.8 Running

```python
from rostrum import Runtime, Interval, Always

rt = Runtime(
    record_root=Path("./run-001"),
    persistent=False,                # default per-run
    fsync=Interval(milliseconds=100),  # default
    admission=1024,                  # default
    budget_us=100,                   # default
    hysteresis_k=3,                  # default
    writer_stats=False,              # opt-in
)
result = await rt.run(my_topology)
print(result.status)                 # "finalised" | "paused" | "failed"
print(result.record_root)            # Path("./run-001")
print(result.final_event)            # the final Event
print(result.elapsed_seconds)
```

`Runtime(...)` validates configuration at construction (e.g., `fsync`
type, `admission > 0`). `rt.run(topology)` is awaitable; it executes
the topology factory against a `TopologyBuilder`, runs the run, and
returns `RunResult`. The runtime is single-use — calling
`rt.run(...)` a second time raises `RuntimeAlreadyUsedError`.

### 4.9 Loading and inspecting records

```python
from rostrum import load_record, attach, replay
from rostrum import explain_producer, trace_ancestry, view_at
from rostrum import decisions_between, first_divergence

rec = load_record(Path("./run-001"))                  # closed record
live = attach(Path("./run-001"))                      # live record (follower)

explanation = explain_producer(rec, "doubler[01JF...]")
ancestors = trace_ancestry(rec, "doubler[01JF...]")
state_at = view_at(rec, seq=42, view="writer_buffer")
decisions = decisions_between(rec, a=10, b=50)
diff = first_divergence(rec_a, rec_b)

result = replay(rec, level="2")
```

Each function returns a typed structure. `Explanation`,
`Ancestor`, `Divergence` are msgspec Structs — accessed by field, not
by string keys. Errors are typed exceptions:
`ProducerNotFound`, `SequenceOutOfRange`, `RecordIncomplete`.

### 4.10 Test helpers

```python
from rostrum.testing import assert_event, assert_no_event, assert_sequence

def test_count_to_three():
    rec = load_record(Path("./fixtures/count_to_three"))
    e = assert_event(rec, "CountReached", n=3)
    assert e.seq > 0
    assert_no_event(rec, "substrate.ProducerFailed")
    assert_sequence(rec, [
        "substrate.RunStarted",
        "substrate.TriggerFired",
        "substrate.ProducerStarted",
        "CountReached",
        "CountReached",
        "CountReached",
        "substrate.ProducerCompleted",
        "substrate.TerminationMatched",
        "substrate.RunFinalised",
    ])
```

Assertions return the matched event (or raise `AssertionError` citing
sequence numbers). They work on live attached records too, so you
can write integration tests that observe a run as it happens.

---

## 5. CLI UX (reference-level)

Every subcommand, its surface, and its output shape.

### 5.1 `rostrum run`

```
$ rostrum run --topology my_topology
```

```
$ rostrum run --topology-module ./my_module.py:my_topology
```

The first form looks up `my_topology` in the bundled topology
registry. The second loads a Python module from a path and finds the
named function. **Security note (technical spec §17):** the path
is executed with the user's privileges. No sandbox.

**Output format.** Default is no live output — the runtime exits when
`RunFinalised` lands. Add `--tail` to stream events to stderr while
the run progresses (same format as `rostrum tail`). Add `--verbose`
to also print substrate.* lifecycle events.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Run finalised normally (`substrate.RunFinalised`) |
| 1 | Run failed (e.g., View update raised, writer crashed) |
| 2 | Run paused awaiting input (`pause-await-input` policy) |
| 64 | Configuration error (CLI args, topology import failed, registration error) |
| 65 | Persistent-bus lock contention |
| 130 | SIGINT (user pressed Ctrl-C; runtime shuts down cleanly, record is complete to last fsync) |

The record root path is printed to stdout on every exit (success or
failure), so shell scripts can use it:

```
$ rostrum run --topology my_topology
./runs/01JFAB8C5...
$ rostrum tail $(rostrum run --topology my_topology)
```

### 5.2 `rostrum tail`

```
$ rostrum tail ./run-001/
```

Streams events from a live or closed record to stdout. Default format:
one event per line, columns aligned.

```
seq=0   substrate.RunStarted               (topology=count_to_three)
seq=1   substrate.TriggerFired             trigger=__initial__
seq=2   substrate.ProducerStarted          producer=counter[01JF...]
seq=3   CountReached                       producer=counter[01JF...]  n=1
```

**Filters (required for usability at bus volumes):**

```
$ rostrum tail ./run-001/ --kind CountReached
$ rostrum tail ./run-001/ --producer counter
$ rostrum tail ./run-001/ --since 100
$ rostrum tail ./run-001/ --kind CountReached --producer counter --since 100
```

Filters compose with AND. `--kind` accepts comma-separated names.
`--producer` accepts a kind prefix (matches all instances) or a full
producer ref. `--since` takes a sequence number.

**Output format flags:**

| Flag | Effect |
|---|---|
| (default) | Aligned human-readable; payload fields shown after the kind column |
| `--format=jsonl` | Raw JSONL (the on-disk bytes; pipeable into jq) |
| `--format=long` | Multi-line per event with full payload |
| `--no-color` | Strip ANSI colors (auto-detected when not a TTY) |
| `--follow` | Stay attached past current end (default for live records) |

**Color choices.** When the output is a TTY: sequence number dim;
`substrate.*` kinds in muted blue (control-plane); application kinds
in default color (data-plane); Producer ids dim until referenced
twice in a session; payload field names dim, values default. The
intent: at a glance, runtime events recede and application events
stand out, with Producer ids picked up by the eye when they appear
repeatedly.

### 5.3 `rostrum inspect`

```
$ rostrum inspect ./run-001/ --producer doubler[01JF...] --why
```

```
producer=doubler[01JF...]
parent=counter[01JF...]
caused_by:
  seq=12  substrate.TriggerFired
    trigger=double-each
    firing_key=null
    resolved_input={"n": 2}
    input_sha256=sha256:7a2f...
```

`--why` returns the proximate cause (one Trigger firing, or
`RunStarted` for initial Producers, or a resume event for resumed
Producers). For full causal chain to `RunStarted`:

```
$ rostrum inspect ./run-001/ --producer doubler[01JF...] --ancestry
```

```
doubler[01JF...]
  ↑ caused by TriggerFired at seq=12 (trigger=double-each)
counter[01JF...]
  ↑ caused by TriggerFired at seq=1 (trigger=__initial__)
__root__
  ↑ caused by RunStarted at seq=0
```

Other inspect modes:

| Command | Output |
|---|---|
| `inspect <rec> --producer X --why` | proximate cause |
| `inspect <rec> --producer X --ancestry` | full causal chain |
| `inspect <rec> --seq N` | the event at sequence N, full payload |
| `inspect <rec> --seq N --view V` | the value of View V as of sequence N |
| `inspect <rec> --between A B` | substrate.* decisions in [A, B] |
| `inspect <rec> --diff <other-rec>` | first_divergence between two records |

Every output cites sequence numbers. Output is plain text in the
default format; `--format=jsonl` gives a typed JSON record per
inspection result for tool integration.

### 5.4 `rostrum replay`

```
$ rostrum replay ./run-001/ --level 2
[OK] Level 2 replay successful.
Frames replayed: 9
Producers: 2
Triggers fired: 2
Resolved inputs: 2 (all verified by hash)
```

Replay produces an exit code: 0 on success, non-zero on failure.
A Level 3(a) replay attempted on a record with wall-clock cooldowns
fails fast:

```
$ rostrum replay ./run-001/ --level 3a
[FAIL] Level 3(a) replay not supported for this record.
The record's replay_ceiling is "3b" because:
  - Trigger "rate-limit" registered a WallClock cooldown
    (visible in RunStarted at seq=0, payload.topology.triggers[2])
Use --level 3b for substitution replay, which is always supported.
```

`--diff` compares two records:

```
$ rostrum replay ./run-001/ --diff ./run-002/
First divergence at sequence index 7:
  ./run-001/  seq=7  substrate.ProducerEmittedInvalidEvent  producer=worker-3[01JF...]
  ./run-002/  seq=7  RowTranslated                          producer=worker-3[01JF...]
Equivalent under D-8 up to index 6.
```

### 5.5 `rostrum validate`

```
$ rostrum validate --topology-module ./my_module.py:my_topology
```

Static topology lint. Doesn't run anything; just exercises
registration and reports issues.

```
[OK] Topology validates.
4 Producer kinds, 6 Triggers, 3 Routes, 5 Views, 1 TerminationPolicy.
1 WallClock cooldown registered → replay ceiling = "3b".
```

On failure:

```
[FAIL] 2 issues:

  RegistrationError at trigger "check-on-chunk":
    starts="checkr" — unknown Producer kind.
    Did you mean "checker"?

  RegistrationError at trigger "retry-on-failure".subscription:
    Predicate references kind "FailEvent" which is not declared by any
    registered Producer kind.
    Either declare it (Producer kind needs `schemas=[..., FailEvent]`)
    or remove the predicate's reference.
```

Lints catch the common errors that the runtime would otherwise raise
at run start (when it's more expensive to fix).

### 5.6 `rostrum conformance`

```
$ rostrum conformance
Running 17 conformance checks against installed kernel 1.0.0...
  [01/17] Retry enrichment                      ... PASS (0.04s)
  [02/17] Single legal cascade                  ... PASS (0.03s)
  ...
  [17/17] InputBuildFailed visibility           ... PASS (0.02s)

All checks passed. Kernel matches spec.
```

On failure, the failing check prints the specification reference and
the divergence:

```
  [06/17] Replay round-trip                     ... FAIL

Conformance check 6 (product spec §7, technical spec §12, §21):
  Level 3(b) substitution replay produced bytes diverging from the
  original record at sequence index 47.
  First diverging frame:
    original:   <hex bytes>
    re-executed: <hex bytes>
  Difference: payload.text field, originating msgspec.Struct fields
              ordering.
  Likely cause: canonical encoding not stable across Python versions
                (D-7 violation).
```

Exit code 0 if all pass, non-zero if any fail. Used in CI as the
release gate.

---

## 6. Error and observability UX

How errors surface; how operators see what's happening; what users see
when things go wrong.

### 6.1 Registration errors

Caught synchronously when the topology function returns. Before any
run starts, before any file is written. Format:

```
RegistrationError at <where>:
  <one-line summary>
  <explanation of what's wrong>
  <reference to upstream constraint>
  <fix shown inline, if obvious>
```

Where is a path: `producer_kind "writer"`, `producer_kind "writer".schemas[0].field "metadata"`,
`trigger "check-on-chunk".predicate`. Errors prevent the topology from
running.

### 6.2 Runtime errors that become bus events

Per the load-bearing commitment ("nothing consequential is silent"),
runtime errors during a run land on the log:

| Situation | Event |
|---|---|
| Producer emits undeclared kind | `substrate.ProducerEmittedInvalidEvent` |
| Producer emits malformed payload (schema fails) | `substrate.ProducerEmittedInvalidEvent` |
| Producer raises during `start()` | `substrate.ProducerFailed` |
| Producer cancelled by policy | `substrate.ProducerCancelled` |
| Predicate exceeds budget k times | `substrate.PredicateQuarantined` |
| `input_builder` raises | `substrate.InputBuildFailed` |
| Route `transform` raises | `substrate.InputBuildFailed` (scoped to route_id) |
| Termination policy fires | `substrate.TerminationMatched` |

Each carries typed fields including reason, sequence number, and
relevant identifiers. Users discover problems by querying the record:

```
$ rostrum tail ./run-001/ --kind substrate.ProducerEmittedInvalidEvent
seq=42  substrate.ProducerEmittedInvalidEvent  producer=worker-3[01JF...]  reason="schema_violation"  detail="row at $.row.price: expected float, got str"
```

### 6.3 Runtime errors that don't become bus events

A small set, because the bus itself is the failure surface:

| Situation | Surface |
|---|---|
| View raises in `update()` | run terminates; `substrate.RunFinalised {reason: "view_failure"}` |
| Writer crashes | run terminates; the writer can't record its own death (technical spec §5.2 — do not write `RunFinalised` on a failed medium). Recovery on next start reports the truncated tail |
| Reentrant append from inside cycle | `ReentrantAppendError` raised; programming bug |
| Persistent-bus lock contention | `BusLockedError` raised at `Runtime(...)` construction |
| Fsync failure | process crashes; technical spec §5.2 |

Operators get the truth from the record (for graceful failures) or
from the OS exit code and recovery output (for ungraceful ones). No
ghost "I think this happened" messages.

### 6.4 Writer-stats sidecar

When `Runtime(writer_stats=True)` is set, the writer periodically
writes operational metrics to `sidecar/writer_stats.jsonl`:

```
$ tail -f run-001/sidecar/writer_stats.jsonl | jq
{"t": 1718000010.0, "cycles_per_sec": 8421, "admission_depth": 3, "control_queue_depth": 0, "fsync_p50_us": 47, "fsync_p99_us": 120, "view_update_p99_us": 2, "predicate_p99_us": 4, "quarantined": 0}
{"t": 1718000011.0, "cycles_per_sec": 9112, ...}
```

Operators monitoring a live run pipe this to their dashboard. The CLI
also surfaces a quick summary:

```
$ rostrum stats run-001/
Live stats (last 1s window):
  cycles/sec     : 9,112
  admission depth: 3 / 1024
  control depth  : 0
  fsync p50/p99  : 47µs / 120µs
  quarantined    : 0
```

`rostrum stats` reads the sidecar; the writer is not consulted.

### 6.5 Halt-with-resume UX

A run that pauses on `pause-await-input`:

```
$ rostrum run --topology with_human_review
Run paused awaiting input.
record_root: ./runs/01JFAB...
pause_condition: architect provides DecisionMade event at /tmp/decision.json
exit code: 2
```

The exit code 2 indicates pause (not failure). The user provides the
expected event (mechanism is topology-defined — could be a file, a
webhook, a CLI command). To resume:

```
$ rostrum resume ./runs/01JFAB.../ --input /tmp/decision.json
```

Resume reattaches to the persistent bus, appends the resume event,
the resume Trigger fires, and the run continues.

The appended resume event is an application event the resume Trigger
subscribes to. It is **canonical-checked** (§4.2 whitelist) and
**reserved-kind-refused** (a `substrate.*` kind is rejected so it cannot
forge a lifecycle frame) — but it is NOT schema-typed-validated the way a
Producer *emission* is, because an external injection has no registered
producer_kind to validate against (it routes through the lifecycle-append
path with a `<kind>@1` schema string).

**Resumable-terminal constraint.** A pausable topology MUST finalise on a
**process-local** condition — quiescence (`quiescence_with_watchdog`) or a
count threshold (`threshold_count`) — and MUST NOT use `all_completed`.
`all_completed` compares started-vs-ended counts, but a pause trips while
the emitting Producer is still inflight, so its `ProducerStarted` has no
durable end across the pause: on resume the restored `started > ended` and
`completed >= started` can never be met, and the run would never finalise.
The runtime guards this — a resumed run that goes fully quiescent while its
policy still returns CONTINUE is recorded as a `RunFinalised` with reason
`"stuck_quiescent"` and FAILS loudly rather than hanging — but the correct
fix is to choose a process-local terminal. (The reference R-2 pipeline does
this and documents why.)

---

## 7. User journeys

Five canonical paths the design must make smooth. Each exercises a
specific slice of the surface.

### 7.1 First topology

**Goal:** from `pip install` to a working two-Producer pipeline, in
under an hour.

**Path:**

1. Install. `pip install rostrum` works on Linux/macOS/Windows.
2. Tutorial. `N-DOC-1` shipped: "First topology" walks through
   declaring two Struct schemas, writing two Producers, registering
   one Trigger, running, looking at the record.
3. Smell test. The user can read their own log file by eye and
   understand what happened.
4. Modify. The user adds a third Producer; nothing breaks.

**Critical UX touchpoints:** the registration error message when they
forget `frozen=True`, the tail output the first time they see it, the
inspect output when they ask "why did this Producer start."

### 7.2 Debugging a failed run

**Goal:** my run halted, I need to find out why and what to do.

**Path:**

1. The run exits non-zero.
2. User runs `rostrum tail <record> --kind substrate.ProducerEmittedInvalidEvent`
   or similar to find the first failure.
3. User runs `rostrum inspect <record> --seq <failed_seq> --why` to
   see the cause.
4. User runs `rostrum inspect <record> --producer <involved> --ancestry`
   to trace upstream.
5. User identifies the bug (in their topology, in a Producer, in
   their data).
6. User runs again, possibly under `rostrum run --tail` to watch
   live.

**Critical UX touchpoints:** the failure must be findable without
grepping through unstructured output. `--kind` filter is mandatory.
`--why` returns a typed cause, not a vague summary. Sequence numbers
make every reference unambiguous.

### 7.3 Replaying to understand a decision

**Goal:** something interesting happened in a past run; I want to
understand why a specific Trigger fired with the specific input it
got.

**Path:**

1. User runs `rostrum tail <record> --kind substrate.TriggerFired` to
   find the firing of interest.
2. User runs `rostrum inspect <record> --seq <firing_seq>` to see the
   full payload (including resolved input).
3. User runs `rostrum inspect <record> --seq <firing_seq> --view <relevant_view>`
   to see the state the input_builder saw.
4. If the user wants to test "what if the input had been different,"
   they fork and replay with alternates — currently extra work, see
   §8 alternatives.

**Critical UX touchpoints:** resolved inputs visible in `TriggerFired`
events; View state reconstructable at any sequence.

### 7.4 Composing for sharing

**Goal:** I built a useful topology; I want to publish it for others
to use as a Producer in their topology.

**Path:**

1. User wraps their topology with an export map:
   ```python
   class MyAnswer(Struct, frozen=True):
       text: str
       confidence: float

   b.export(inner_kind="FinalAnswer", outer_schema=MyAnswer)
   ```
2. User publishes as a Python package (or shares the module).
3. Consumer installs and registers as a Producer kind:
   ```python
   from my_topology import answer_substrate_producer
   b.producer_kind("answer", schemas=[MyAnswer], schema_version=1,
                   factory=answer_substrate_producer)
   ```
4. Consumer's outer bus sees only `MyAnswer` events; inner bus is
   complete at its own root.

**Critical UX touchpoints:** the export-map declaration is one line.
The consumer wires it like any other Producer. The inner record is
inspectable independently for debugging.

### 7.5 Diagnosing slowness

**Goal:** my topology is running, but it feels slow. Where's the time
going?

**Path:**

1. User adds `writer_stats=True` to the runtime config, reruns.
2. User pipes `sidecar/writer_stats.jsonl` to their dashboard, or
   runs `rostrum stats` for a quick snapshot.
3. User identifies the bottleneck:
   - High admission depth → a Producer is emitting too fast for the
     writer. Look at which kind dominates.
   - High control queue depth → cascading Triggers are firing.
   - High fsync latency → durability policy too aggressive for the
     disk.
   - Quarantined predicates → user has a slow predicate. Look at the
     sidecar diagnostic records for which one.
4. User tunes: change fsync policy, add `--diagnostics` to find the
   slow predicate, increase admission bound.

**Critical UX touchpoints:** writer-stats sidecar is the only path to
substrate-level performance visibility. Without it, users can't
distinguish "my Producer is slow" from "the substrate is slow."

---

## 8. Future UI sketches

v1.0 ships no UI. This section sketches what a UI could look like,
to make F-API-6 (UI buildability on public APIs alone) concrete. If
sketching reveals a missing public surface, the API has a bug.

### 8.1 Trace UI

A timeline view of a run. X-axis is sequence number (not wall-clock —
sequence is the substrate's identity). Y-axis lists Producers, with
the runtime control plane as a special row at top. Each event is a
mark on the row of its Producer at its sequence.

```
                ↓ seq=0                                 seq=N ↓

  __runtime__   ▌RS  ▌TF  ▌PS  ▌PS  ▌PS                ▌TM ▌RF
  counter[01]              ━━━━━━●●●○
  doubler[02]                          ━━●○
  doubler[03]                              ━●○
  doubler[04]                                  ━●○
```

- ▌ = control-plane event
- ━ = Producer alive
- ● = ProducerEvent (application emission)
- ○ = ProducerCompleted
- Click on any mark → call `explain_producer` / `inspect`, show the
  payload in a side panel.
- Hover → tooltip with seq number and kind.

**Built on:** `attach(record)`, `decisions_between`, `explain_producer`,
the lifecycle vocabulary. All public.

### 8.2 Topology visualizer

A graph of the topology, generated from `RunStarted` (which carries
the full topology manifest). Nodes are Producer kinds; edges are
Triggers (with predicate identifiers) and Routes (with slot names).

```
   ┌─────────┐  task_assigned   ┌─────────┐  CodeChunk   ┌──────────┐
   │ planner ├──────[T1]───────▶│ writer  ├────[T2]─────▶│ checker  │
   └─────────┘                   └─────────┘             └──────────┘
                                      ▲                       │
                                      │      failure_context  │
                                      └─────────[R1]──────────┘
```

Clicking a Producer kind shows: schema descriptors, fingerprint,
all event kinds it can emit. Clicking a Trigger shows: predicate
identifier, firing policy, input slots. Clicking a Route shows:
source predicate, target slot.

**Built on:** the `RunStarted` payload structure. All public.

### 8.3 Diff viewer

Two records side by side, aligned on `first_divergence`. Up to the
divergence, the records are identical (the UI just shows them in
sync). At divergence, the two diverge visually — different colors,
side-by-side panels.

```
        Run A                            Run B
seq=0   substrate.RunStarted             substrate.RunStarted              [identical]
seq=1   substrate.TriggerFired           substrate.TriggerFired             [identical]
...
seq=7   ⚠ substrate.ProducerEmittedInvalidEvent  ⚠ RowTranslated row=3      ← FIRST DIVERGENCE
              reason=schema_violation              n=6
              detail="missing field price"
seq=8   substrate.TriggerFired (retry)   ─                                   ← A only
seq=9   ─                                substrate.TriggerFired (next)       ← B only
```

**Built on:** `first_divergence`, `load_record`, `decisions_between`.
All public.

### 8.4 Operator dashboard

A live view of a running substrate. Reads the writer-stats sidecar
and the live record:

```
┌─ Run 01JFAB... (live, 14:32:01) ────────────────────────────────────┐
│                                                                      │
│  Cycles/sec    █████████ 8,421                                       │
│  Admission     ▌▌▌▌▌▌      6 / 1024 (latency ok)                    │
│  Control queue ▌            1                                        │
│  Fsync p99     ▌▌▌         120µs                                     │
│  Quarantined   ─           0                                         │
│                                                                      │
│  Recent events (last 5):                                             │
│  seq=14782  RowTranslated  row=4521  worker-2                        │
│  seq=14783  RowTranslated  row=4522  worker-1                        │
│  ...                                                                 │
└──────────────────────────────────────────────────────────────────────┘
```

**Built on:** sidecar/writer_stats.jsonl + `attach()` for the recent
events. All public.

### 8.5 What's missing

Each sketch lists what public surface it uses. Across all four, every
needed function or file is public. **No missing surfaces in v1.0** —
F-API-6 is achievable with the current design. If a sketch had
needed e.g. "writer subscribes to a debug channel," that would be a
v1.0 API bug. None of these do.

---

## 9. Rationale and alternatives

Why this design, what was considered, why not.

### 9.1 Builder methods vs decorators

**Chosen:** builder methods (`b.producer_kind(...)`).

**Considered:** decorator-based registration (`@producer_kind("writer")`).

**Rejected because:** decorators bind registration to module import,
making registration order depend on import order. Topologies-as-
functions make registration order explicit and code-reviewable. The
builder is a small typed object; the decorator approach hides registration
in import side effects.

### 9.2 Single-pass topology factory vs incremental config

**Chosen:** topology factory function that fully registers everything
in one call.

**Considered:** Runtime methods like `runtime.add_producer(...)` that
incrementally configure.

**Rejected because:** the kernel's `RunStarted` event captures the
full topology manifest at run start. Incremental configuration during
a run breaks that contract. The factory pattern matches the kernel
semantics.

### 9.3 Click vs Typer vs argparse

**Chosen:** `click` for argument parsing, `rich` for terminal
output.

**Considered:** `typer` (modern, decorator-based), stdlib `argparse`.

**Rejected stdlib argparse because** the CLI deserves a real CLI
library. Click is the mature, widely used Python CLI library;
substrate is a normal Python project and uses it like every other
normal Python project does.

**F-API-6 doesn't restrict library choice.** F-API-6 says: a UI built
on the substrate must be buildable against public substrate APIs
alone, with no private hooks. Click and Rich are external libraries,
not substrate-private hooks. The CLI using Click doesn't prevent
anyone from building a UI on the substrate's public API; the CLI is
still the existence proof that the public API is sufficient.

**Typer rejected** for the same reason most projects choose Click
over Typer: marginally more conventional, longer-supported, no
preference for either at the level that matters here.

### 9.4 Color in tail output

**Chosen:** muted colors that recede the control plane and surface
the data plane.

**Considered:** rainbow-by-Producer (every Producer instance gets a
distinct color).

**Rejected because:** with many short-lived Producer instances (the
common case in fan-out topologies), color exhaustion makes colors
meaningless. Color-by-kind would also work but conflicts with the
"runtime recedes" principle. The current choice supports the most
common reading pattern: scan for application events, drill into
specific Producers by id when needed.

### 9.5 Trigger registration: positional kind vs explicit `starts=`

**Chosen:** `starts="kind"` keyword-only argument.

**Considered:** `b.trigger("id", "kind_to_start", ...)` positional.

**Rejected because:** the `id` and the `starts` are both strings, both
identifiers, and positional ordering invites bugs ("which one did I
mean?"). Keyword-only forces clarity at the call site.

### 9.6 Producer factory returning callable vs Producer class

**Chosen:** factory returns a callable (`async def start`).

**Considered:** factory returns a Producer class instance with a
`start` method.

**Rejected because:** the callable form is simpler and asyncio-native.
Producer state, if any, lives in closures over the factory. A class-
based approach adds ceremony without enabling new patterns; the
substrate's load-bearing commitment ("all state lives on the log")
discourages Producer-internal state anyway.

### 9.7 Replay output format

**Chosen:** structured success/failure with sequence-cited divergence
locations.

**Considered:** silent on success, verbose only on failure.

**Rejected because:** users running `replay --level 3b` in CI need to
see what was replayed (frame count, Trigger count, hash verification
result). Silent success makes "did it actually do the check?"
ambiguous.

---

## 10. Prior art

Existing tools influenced — positively or negatively — the design
choices.

**LangGraph.** The closest existing thing in shape. Sequential
node-at-a-time execution; mutable shared state; statically declared
graph. Substrate deliberately rejects all three: concurrent
execution, append-only event log, dynamic Triggers. LangGraph's
Python API style (typed state objects, named nodes) is reasonable; we
take less from its decorator-based registration (see §9.1).

**Temporal SDK (Python).** Strong on persistence and replay. Workflow
decorators encapsulate long-running state. Substrate's run record is
similar in spirit (an event-sourced log that replays) but Temporal's
execution is sequential and broker-based. The SDK's `@workflow`
decorator pattern was considered (§9.1) and rejected for the
import-order reason.

**Pytest.** Heavily influenced the test-helpers design (F-API-4). The
`assert_event(rec, kind, **partial)` shape is pytest-fixture-style.
Pytest's "fixture is just a function" pattern is what Substrate
extends to Producers and Predicates — no class hierarchy.

**Click / Rich.** The standard Python CLI stack. Click handles
argument parsing, command groups, help text generation, exit codes.
Rich handles formatted terminal output (colors, tables, panels) with
proper TTY detection so output degrades cleanly when piped to a
file or grep. Substrate's CLI uses both like any other Python
project does (§9.3).

**OpenAPI.** Considered for documenting the API. Rejected because
OpenAPI is HTTP-shaped and Substrate is a library, not a service.
The `py.typed` marker plus generated docstring reference (mkdocstrings,
per technical spec §22.5) is the right shape.

**Datadog / Honeycomb dashboards.** Influenced the writer-stats
sidecar design. We do not ship a dashboard; we ship the underlying
JSONL stream and a quick `rostrum stats` command, and document the
fields so anyone can build a dashboard.

**The Unix philosophy.** `tail`, `grep`, `diff`, `find`. The CLI's
single-purpose subcommands and pipeable output (JSONL, `--no-color`,
exit codes) follow this tradition. `rostrum tail | jq` should work.

**The Bezos 6-pager / narrative-prose-over-bullets discipline.**
Influenced this document's structure: prose paragraphs over dense
bulleted reference, with concrete code blocks and terminal outputs
that show rather than tell.

---

## 11. Unresolved questions

Resolve during 0.x against real topology authoring.

**Q-1.** Should `b.initial(kind, input=...)` accept a builder function
for the input, like Triggers do? Today the input is constructed at
factory-call time (registration), not at run-start time. A run-start
builder would parallel the Trigger `input_builder` shape.

**Q-2.** Should there be a `b.alias(name, target)` for naming common
patterns? E.g., `b.alias("on_failure_of", lambda kind: Trigger(...))`.
Or do we let users write helpers as ordinary Python functions?

**Q-3.** What does `inspect` default to — short form (one-line per
field) or long form (full payload)? Short is greppable; long is
readable. Currently leaning short with `--long` flag.

**Q-4.** Should `rostrum tail` follow live records by default and
require `--no-follow` to stop, or stop at end-of-record by default and
require `--follow` to continue? `tail -f` precedent says follow by
default, but live-attaching to a closed record is also surprising.

**Q-5.** Color by kind (every kind gets a stable color) vs muted
recede (the current choice). Real users will tell us; both are
implementable.

**Q-6.** Should the `Subscription` API support glob patterns
(`Subscription(kinds={"checker.*"})`) for hierarchical kind
namespaces? Currently kinds are flat strings; a topology with many
related kinds will hit the friction.

**Q-7.** Should `rostrum resume` be a separate subcommand, or
`rostrum run --resume <record_root>`? `resume` is more discoverable;
`run --resume` is more parallel.

**Q-8.** Whether `rostrum tail --format=long` should also pretty-print
JSON payloads with syntax highlighting. Yes is more useful; no avoids
the dependency.

**Q-9.** Should there be a `rostrum new-topology` scaffolder that
generates a starter file? Convenient for first-hour UX; ceremony for
no-one-else.

**Q-10.** Naming: in the `Runtime` constructor, `record_root` vs
`root` vs `path`. `record_root` is explicit and matches the technical
spec; `root` is shorter; `path` is most familiar.

---

## 12. Document history

- **DRAFT 1** — first synthesis. Format adapted from Rust RFC
  (Motivation/Guide-level/Reference-level/Alternatives/Prior art/
  Unresolved/Future possibilities) with explicit UX/journey sections
  (§3 first-hour, §5 CLI UX, §6 error UX, §7 user journeys, §8 future
  UI sketches). Builds on kernel v15, product DRAFT 7, technical
  DRAFT 5. Establishes the felt-experience contract: API ergonomics
  with concrete code examples; CLI UX with concrete terminal output;
  error visibility per principle 2 ("all state lives on the log");
  future UI sketches that prove F-API-6 buildability. Ten unresolved
  questions filed for 0.x.

---

*Flows back into the product spec (DRAFT 8, when cut): the named
helper `retry_with_failure_context` deserves a mention in §5.10
(named policy recipes carry over). The `b.alias` question (Q-2) is
a topology-authoring concern the next product-spec revision should
address.*

*Flows back into the technical spec (DRAFT 6, when cut): the writer-
stats sidecar field set (§6.4 of this design spec) needs alignment
with technical spec §6.4 metric set; the resume subcommand (Q-7) is
a CLI surface the technical spec §5.11 / F-CLI-3 list does not
currently include.*

Sources for format research (see chat transcript):

Sources:
- [The Rust RFC Book — RFC 2333 Prior Art](https://rust-lang.github.io/rfcs/2333-prior-art.html)
- [Rust RFC template (0000-template.md)](https://github.com/rust-lang/rfcs/blob/master/0000-template.md)
- [arc42 template overview](https://arc42.org/overview)
- [arc42-template GitHub](https://github.com/arc42/arc42-template)
- [API Ergonomics — tychoish](https://tychoish.com/post/api-ergonomics/)
- [Stripe documentation teardown — Mintlify](https://www.mintlify.com/blog/stripe-docs)
- [How to Write API Documentation — AltexSoft](https://www.altexsoft.com/blog/api-documentation/)
