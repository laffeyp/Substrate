# Adding a topology

The [tutorial](tutorial.md) builds a two-Producer run from scratch and stops there. This guide is the
next step: how a real topology is *packaged* — as a reusable factory, run from the CLI, made dual-mode
(deterministic in CI, real models in a walkthrough), and added to the bundled catalogue so anyone can
run it by name. It walks the exact path the shipped topologies take, so `src/substrate/topologies/code_review.py`
is a working template you can read alongside this.

You need nothing beyond the tutorial's mental model: Producers emit typed Events; a Trigger fires a new
Producer when its Predicate holds over the Views; a TerminationPolicy ends the run.

## A topology is a function of the builder

A topology is one function: `topology(b: TopologyBuilder) -> None`. It registers Producer kinds (with
their event schemas), Triggers, Routes, Views, and a TerminationPolicy on the builder `b`. That's the
whole contract — the runtime calls it once at run start to freeze the registration set, then runs it.

Here is a complete, minimal one — two reviewers each emit a `Note`, and once both are in, a summarizer
fires. Save it as `review_poll.py`:

```python
from msgspec import Struct

from substrate import api
from substrate.reference._models import DeterministicResponder, Responder, call_responder

# 1. The events. Producer event schemas are frozen msgspec Structs. The bus validates every
#    emission against the kind's declared schema, so a typo or a wrong type becomes a logged
#    ProducerEmittedInvalidEvent, not silent corruption.
class Note(Struct, frozen=True):
    reviewer: str
    text: str

class Summary(Struct, frozen=True):
    text: str

# The MODEL SEAM. Topologies are written against a Responder (`respond(prompt) -> str`), never a
# specific model. CI hands it a DeterministicResponder (seeded, no network); a walkthrough hands it
# a real OllamaResponder. `call_responder` runs the call off the event loop so concurrent Producers
# actually overlap (a DeterministicResponder stays synchronous, preserving CI determinism).
_responder: Responder = DeterministicResponder(seed=0)

# 2. The Producers. A factory is a zero-arg callable returning the `start` async generator. Config
#    (here the reviewer's name) is closed over; it is topology configuration, not Producer input.
def _reviewer(name: str):
    async def review(_inp):
        text = await call_responder(_responder, f"review as {name}")
        yield Note(reviewer=name, text=text[:60])
    return lambda: review

def _summarizer():
    async def summarize(inp):
        notes = inp.get("notes", []) if hasattr(inp, "get") else []
        text = await call_responder(_responder, "summarize " + " ".join(n["reviewer"] for n in notes))
        yield Summary(text=text[:60])
    return lambda: summarize

# 3. The topology. Register the kinds, start the two reviewers, and wire one Trigger that fires the
#    summarizer once two Notes are on the bus.
def review_poll(b: api.TopologyBuilder) -> None:
    for name in ("alice", "bob"):
        b.producer_kind(f"reviewer-{name}", schemas=[Note], schema_version=1,
                        factory=_reviewer(name), deterministic=True)
        b.initial(f"reviewer-{name}", input=None)          # an initial Producer starts at run begin
    b.producer_kind("summarizer", schemas=[Summary], schema_version=1,
                    factory=_summarizer(), deterministic=True)
    b.view("notes", api.KindBuffer("Note"))                # a running list of every Note payload
    b.trigger(
        "summarize",
        subscription=api.Subscription(kinds=frozenset({"Note"})),   # only consulted on a Note
        predicate=lambda ctx: len(ctx.views["notes"].value()) >= 2,  # both reviewers in
        starts="summarizer",
        input_builder=lambda ctx: {"notes": list(ctx.views["notes"].value())},  # sealed input
        policy=api.Once(),                                  # fire once, not per Note
    )
    b.termination(api.all_completed())                      # finalise when every Producer has ended
```

A Trigger is `(subscription, predicate, starts, input_builder, policy)`. The subscription pre-filters
which events even consult the predicate (required — it's what keeps predicate evaluation cheap). The
predicate and input_builder both take one `ctx` exposing `ctx.event` (the event that fired it),
`ctx.views` (by name), and `ctx.staged` (messages Routes staged). The input_builder's return value is
*sealed* — frozen at instantiation — and recorded in the `TriggerFired` event, so replay knows exactly
what the summarizer was given.

## Run it and read the record

No registration needed to run a module directly:

```
$ substrate run --topology-module review_poll.py:review_poll --root ./run
[finalised] ./run
$ substrate tail ./run --kind Note,Summary
```

The record is the whole point — every consequential step is a typed, numbered event:

```
seq=1   substrate.TriggerFired   factory=reviewer-alice   trigger=__initial__
seq=4   Note                     reviewer=alice  text=stub[0]:261360c13c09
seq=7   Note                     reviewer=bob    text=stub[0]:5b8305e9b9c0
seq=8   substrate.TriggerFired   trigger=summarize  resolved_input={notes:[alice, bob]}
seq=11  Summary                  text=stub[0]:a164e81ab55a
seq=14  substrate.RunFinalised
```

`stub[0]:...` is the DeterministicResponder — the wiring runs, reproducibly, with no model. Ask the
record why the summarizer started: `substrate inspect ./run --producer summarizer --why` points at the
firing at seq 8 and the exact notes it resolved.

## Make it dual-mode (real models)

CI mode proves the *wiring*; it deliberately does not prove the *claim* (a deterministic stub doesn't
review anything). The discipline (product spec §8) is that a topology is **dual-mode**: the same
topology, handed real models, demonstrates what it exists for. The only change is which Responder the
Producers get — so take it as a parameter instead of hard-coding `DeterministicResponder`:

```python
def review_poll(b, *, responder=None):
    r = responder or DeterministicResponder(seed=0)   # CI default
    # ... pass `r` into the factories instead of the module-level _responder ...
```

A walkthrough then hands it `OllamaResponder("llama3.2:1b")` (the rebuilt adapter sets `think=False`
+ `num_ctx` + retry so real local models actually work). `code_review.py` is the fuller worked example
— per-role reviewers, an adjudicating judge, and cancel-all-others when the quorum fires — and
`src/substrate/reference/walkthrough.py` shows the three reference topologies run for real.

The rule of thumb the catalogue follows: a Producer is a **model** only where the work is genuinely
generative or judgement (a reviewer, a writer, a debater). Everything deterministic — a validator, a
payoff calculator, a typechecker, a transform — is **plain code**. Producers are heterogeneous by
design; reaching for a model to do a deterministic job is the wrong tool.

## Add it to the catalogue

To make it runnable by name (`substrate run --topology review_poll`), register it in
`src/substrate/topologies/bundled.py` — add a zero-arg factory returning the CI-configured topology to
the `BUNDLED` dict. The registry is the single source: the committed CI record and the live run come
from the same factory, so `demo replay <name>` always matches `demo run <name>`.

Then three mechanical steps, mirroring every shipped topology:

1. **Commit a CI record.** `uv run python scripts/gen_topology_records.py` regenerates the deterministic
   `records/ci_mode.record` for each bundled topology from the registry. (The record embeds per-run
   ULIDs and timestamps, so its bytes change every regeneration; equivalence is by D-8, not byte
   identity — the tests check structure, not bytes.)
2. **Add a test.** Run the topology and assert the record with the shipped helpers —
   `assert_event(rec, "Summary")`, `assert_sequence(...)` — or read events directly as the conformance
   tests do. Assert *substance* (the claim happened), not just that an event exists.
3. **If it runs real models**, add a gated walkthrough demo (see `tests/test_realmodel_demos.py`): it
   skips when the model is absent, hard-fails when the model is present but the claim isn't
   demonstrated, and verifies the claim from the record with a deterministic predicate — never an
   LLM-as-judge.

## Where to look

- `src/substrate/topologies/code_review.py` — the canonical template (roles, adjudication, cancellation).
- `src/substrate/topologies/bundled.py` — how topologies are registered.
- `docs/api.md` — the full public surface (`Subscription`, the firing policies, the standard Views and
  policies, the record/inspection functions).
- `docs/specs/product_spec/draft7.md` §8 — the dual-mode discipline, normatively.
