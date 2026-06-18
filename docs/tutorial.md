# First topology: zero to a working two-Producer run

The plain version first: two small computations where one reacts to the other, and a
complete, replayable record of what happened. That's the whole of this tutorial. In
Substrate's words — a counter *Producer* emits numbers, and a *Trigger* fires a doubler
*Producer* for each. New to the eight words? The [README glossary](../README.md#the-pieces)
names them all, in order, first.

This walks from nothing to a running two-Producer topology and shows how to read what it
recorded. It mirrors the design-spec §3 shape: a counter Producer emits numbers, and a
Trigger fires a doubler Producer for each one.

Everything here uses only the public API, `substrate.api`.

## 0. Install

From the `substrate/` directory, create a Python 3.12 environment and install the package
(editable, with dev extras) so the imports below resolve:

```
uv venv --python 3.12
uv pip install -e ".[dev]"
```

Then save each snippet to a file (e.g. `first.py`) and run it with `python first.py`.

## 1. A single Producer

A **Producer** is a callable that takes a typed input and yields a stream of typed
**Events** (msgspec `Struct`s). The simplest topology runs one:

```python
import asyncio
from msgspec import Struct
from substrate.api import Runtime, TopologyBuilder, threshold_count


class CountReached(Struct, frozen=True):
    n: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


def topology(b: TopologyBuilder) -> None:
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)                 # start one counter at run open
    b.termination(threshold_count("substrate.ProducerCompleted", 1))  # end after it completes


async def main():
    result = await Runtime("./runs/first").run(topology)
    print(result.status, result.record_root)


asyncio.run(main())
```

Run it: `python first.py` prints `finalised ./runs/first`. The run is now a **record** on
disk under `./runs/first/`.

Notes on what you just declared:

- `producer_kind` registers a Producer KIND: its name, the event `schemas` it may emit (each
  a frozen `Struct`), a `schema_version`, and a `factory` returning the `start` callable.
- Event schemas must be `frozen=True` — that is how the runtime enforces input immutability
  by construction (F-PROD-3).
- `b.initial(kind, input=...)` schedules one Producer of that kind at run open.
- The `TerminationPolicy` decides when the run ends. `threshold_count(kind, n)` finalises
  after `n` events of `kind`; here, after the counter's one `substrate.ProducerCompleted`.

## 2. Add a Trigger and a second Producer

A **Trigger** creates new Producers when a **Predicate** over the bus holds. Here, fire a
`doubler` for each `CountReached`:

```python
from substrate.api import PerEvent, Subscription, quiescence_with_watchdog


class Doubled(Struct, frozen=True):
    original: int
    doubled: int


async def doubler(inp):
    yield Doubled(original=inp["n"], doubled=inp["n"] * 2)


def topology(b: TopologyBuilder) -> None:
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("doubler", schemas=[Doubled], schema_version=1, factory=lambda: doubler)
    b.initial("counter", input=None)
    b.trigger(
        "double-each",
        subscription=Subscription(kinds=frozenset({"CountReached"})),   # what it watches
        predicate=lambda ctx: True,                                     # fire on every match
        starts="doubler",                                               # the kind it creates
        input_builder=lambda ctx: {"n": ctx.event.payload["n"]},        # the input
        policy=PerEvent(),                                              # once per matching event
    )
    b.termination(quiescence_with_watchdog(seconds=2))                  # end when work settles
```

A Trigger has: a `subscription` (which event kinds/producers it watches), a `predicate` (a
cheap boolean over the context), an `input_builder` (builds the new Producer's input from the
context), the kind it `starts`, and a firing `policy`
(`PerEvent`/`Once`/`PerKey`/`WhileTrue`). This run emits three `CountReached` and three
`Doubled`, then goes quiescent and finalises.

Both callbacks take ONE argument — a `TriggerContext`, here called `ctx`:

- `ctx.event` — the event that matched the subscription.
- `ctx.views` — the named Views; read `ctx.views["name"].value()`.
- `ctx.staged` — the Route slots staged for this firing (see §2.6).

> **`finalised` does not mean "it worked".** A run finalises whenever it reaches a terminal —
> even if a Producer raised, an `input_builder` raised, or a predicate quarantined. Those are on
> the record (`substrate.ProducerFailed` / `InputBuildFailed` / `PredicateQuarantined`), and the
> CLI prints a `WARNING: N ProducerFailed` line on `run` — but `result.status` is still
> `finalised`. After a run, read the warning, inspect the record, or assert with
> `assert_event` / `assert_no_event`. `substrate run --strict` makes any such failure a nonzero
> exit.

## 2.5 Gate on accumulated state (Views + Predicates)

A predicate that is always `True` fires on every event. The point of a **View** is to gate on
*accumulated* state — "fire once three are in":

```python
from substrate.api import KindCount


def topology(b: TopologyBuilder) -> None:
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("doubler", schemas=[Doubled], schema_version=1, factory=lambda: doubler)
    b.initial("counter", input=None)
    b.view("seen", KindCount("CountReached"))                       # a deterministic projection
    b.trigger(
        "when-three",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: ctx.views["seen"].value() >= 3,       # gate on the View
        starts="doubler",
        input_builder=lambda ctx: {"n": ctx.views["seen"].value()},
        policy=PerEvent(),
    )
    b.termination(quiescence_with_watchdog(seconds=2))
```

A View (`KindCount`, `KindBuffer`, `PerKindLatest`, …) is a deterministic incremental projection
over the bus; the predicate reads `ctx.views[name].value()`. Forgetting `.value()` (reading the View
object itself) quarantines the predicate — surfaced as the `WARNING` above.

## 2.6 Carry context forward (Route + `staged`)

A **Route** stages data from an event into a named *slot* so a later Trigger's `input_builder`
can read it (that is `ctx.staged`) — how context flows into a Producer's *next* instantiation.
A Route's own `transform` takes the event directly (`lambda event: ...`), since it runs per event
before any Trigger:

```python
b.route(
    "carry",
    subscription=Subscription(kinds=frozenset({"Doubled"})),
    slot="last_doubled",
    transform=lambda event: event.payload["doubled"],
)
# ... a later input_builder reads it:  ctx.staged.get("last_doubled")
```

The staging is recorded as `substrate.InjectionApplied`, so the context that reached a Producer
is on the log. (The bundled `pair_coding` topology is a worked example — a navigator's suggestion
Routed into the driver's next chunk.)

## 3. Read the record

The record is the product. Read it with the CLI or the API.

```
$ uv run substrate tail ./runs/first
seq=0   substrate.RunStarted        (topology=..., baseline=...)
seq=1   substrate.TriggerFired      trigger=__initial__  factory=counter
seq=2   substrate.ProducerStarted   producer=counter[01J...]
seq=3   CountReached                producer=counter[01J...]  n=1
...
seq=N   substrate.RunFinalised
```

Filter at bus volumes: `--kind CountReached`, `--producer counter`, `--since 100` (compose
with AND); `--format jsonl` for the raw on-disk bytes (pipe into `jq`).

`tail` is every frame. To read the run as a *story* — the plot, not the heartbeat — use
`narrate`:

```
$ uv run substrate narrate ./runs/first
seq     0  Run started (run_id=01J...).
seq     1  Initial trigger starts counter.
seq     3  counter -> CountReached (n=1)
seq    12  Trigger double-each fired -> starts doubler.
seq    14  doubler -> Doubled (original=2, doubled=4)
seq     N  Run finalised.
```

It renders the substrate causal beats in prose and the application events as the work,
suppressing the producer-lifecycle bracketing (`--lifecycle` restores every frame). `--summary`
answers *did it work?* at a glance:

```
$ uv run substrate narrate ./runs/first --summary
Run finalised: 14 events.
  producers: 4 started, 4 completed, 0 cancelled, 0 failed
  work: CountReached=3, Doubled=3
```

Every authoring failure is shown, and finalising is not the same as working: when a run
finalises with failures, the summary header says so on line one — `Run finalised WITH 2
FAILURES: ...` — so a broken run looks broken at a glance, not green.

Ask *why* a Producer existed:

```
$ uv run substrate inspect ./runs/first --producer "doubler[01J...]" --why
producer=doubler[01J...]
parent=counter[01J...]
caused_by:
  seq=12  TriggerFired   trigger=double-each   resolved_input={"n": 2}   input_sha256=sha256:...
```

Or in code:

```python
from substrate.api import read_record, explain_producer, narrate, view_at, KindCount

events = list(read_record("./runs/first"))                 # every envelope, in seq order
story = list(narrate("./runs/first"))                      # NarrationLine(seq, kind, text) per beat
exp = explain_producer("./runs/first", "doubler[01J...]")  # typed cause, cites the firing seq
count_at = view_at("./runs/first", 5, KindCount("CountReached"))  # a View's state as of seq 5
```

## 4. Replay and diff

```
$ uv run substrate replay ./runs/first --level 2
[OK] Level 2 replay successful.
Frames replayed: 9
Decisions verified: 4 (all inputs verified by hash)
```

Levels 1, 2, and 3(a) ship in v1.0, along with **D-8 log-equivalence** for diffing two
records (`substrate inspect <a> --diff <b>`, or `first_divergence(a, b)`), which compares
runs modulo supplementary metadata (wall-clock `t`, run ids, per-run instance ids). **Level
3(b) byte-identical re-execution is post-1.0** (see the README and product amendment A1.1) —
`--level 3b` reports the deferral explicitly rather than faking it.

## Next

- The eight primitives in depth: `docs/specs/kernel_spec/v15.md`.
- Worked reference topologies (ensemble+adjudicator, error cascade, composed code-synth),
  with real local-LLM runs: `docs/walkthroughs/README.md`.
- The full public API: `docs/api.md`.
- Evolving your event schemas without breaking old records: `docs/schema-evolution.md`.
- A custom LLM backend: implement `Responder` (`from substrate.reference import Responder`).
