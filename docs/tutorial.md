# First topology: zero to a working two-Producer run

This walks from nothing to a running two-Producer topology and shows how to read what it
recorded. It mirrors the design-spec §3 shape: a counter Producer emits numbers, and a
Trigger fires a doubler Producer for each one.

Everything here uses only the public API, `substrate.api`.

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
        predicate=lambda event, views: True,                            # fire on every match
        starts="doubler",                                               # the kind it creates
        input_builder=lambda views, staged, event: {"n": event.payload["n"]},  # the input
        policy=PerEvent(),                                              # once per matching event
    )
    b.termination(quiescence_with_watchdog(seconds=2))                  # end when work settles
```

A Trigger has: a `subscription` (which event kinds/producers it watches), a `predicate` (a
cheap boolean over the event and the Views), an `input_builder` (builds the new Producer's
input from current state), the kind it `starts`, and a firing `policy`
(`PerEvent`/`Once`/`PerKey`/`WhileTrue`). This run emits three `CountReached` and three
`Doubled`, then goes quiescent and finalises.

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
from substrate.api import read_record, explain_producer, view_at, KindCount, first_divergence

events = list(read_record("./runs/first"))                 # every envelope, in seq order
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

- The eight primitives in depth: `kernel_spec/v15.md`.
- Worked reference topologies (ensemble+adjudicator, error cascade, composed code-synth),
  with real local-LLM runs: `docs/walkthroughs/README.md`.
- The full public API: `docs/api.md`.
