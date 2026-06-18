# Substrate

Substrate is a Python runtime for running many computations together — LLMs, ML
models, deterministic transforms, subprocesses, parsers, simulators: anything that
takes typed input and emits typed events — and coordinating them through a single
shared, append-only log.

## What it is

Say you have several computations that need to work together: a few models
answering the same question, or a parser feeding a checker feeding a fixer, or a
planner that hands pieces of work to solvers. The awkward part is rarely running
any one of them — it's getting them to coordinate, and being able to say afterward
what actually happened.

The usual ways to wire that up are to connect the pieces directly to each other, or
to let them share and mutate some common state. Both get tangled as the number of
pieces grows, and both leave the history of a run implicit — spread across logs,
in-memory state, and control flow you can't replay.

Substrate takes one approach throughout: everything goes through a single,
totally-ordered, append-only log. Each computation reads from the log and emits
typed events back onto it; none of them talk to each other directly. That one
shared log is the only place coordination happens.

The set of running computations isn't fixed ahead of time. Instead of declaring a
static graph, you write small conditions over the log — "once three answers are
in", "when this step fails" — and when a condition holds, the runtime starts
another computation. The shape of a run grows as it unfolds, including computations
that start more of themselves (so recursion falls out for free).

What you actually write is called a **topology**: a small Python program that
declares which computations can run, which conditions start them, and how data
flows between them. You hand the topology to the runtime; it executes it and
produces the log.

And because every event *and* every decision the runtime makes — each time a
computation starts, each condition that fires, how the run ends — is written onto
that same log, the log is a complete, ordered account of the run. You can read back
exactly what happened and why, replay it, or inspect any point in it. Nothing
important is stranded in memory or hidden in control flow.

That combination — concurrent computations, one shared log, conditions that create
new work as the run goes, and a complete replayable record of it — is what makes
ensembles-with-adjudication and retry-with-context straightforward to build (see the
next section).

## The pieces

A topology is assembled from a small, fixed set of named pieces:

- **Producer** — a callable that takes typed input and emits a stream of typed
  **Events**. An LLM, an ML model, a transform, a subprocess, a parser — anything
  with that shape.
- **Event** — one typed, numbered fact on the log (e.g. `AnswerEmitted`, `RowParsed`).
- **Bus** — the single totally-ordered, append-only log every event goes onto.
  There is exactly one; Producers coordinate only through it.
- **View** — a running summary maintained over the log as events land (e.g.
  "everything Producer X has emitted so far", "how many answers are in").
- **Predicate** — a cheap yes/no question asked of the Views when an event lands.
- **Trigger** — starts a new Producer when its Predicate holds. Aside from the
  initial Producers you declare to start the run, a Trigger is the only way new
  Producers are created.
- **Route** — carries data from past events into the input of a future Producer.
- **TerminationPolicy** — decides when the run ends, or pauses to wait for outside
  input.
- **run record** — the log persisted to disk: framed, CRC-protected,
  canonically-encoded JSONL. Every event and every decision is on it; nothing
  consequential is left off.

## What you can build

Each of these is a topology — a short Python program against the runtime:

- An ensemble of several cheap models on the same task, with a stronger model
  adjudicating and the losing runs cancelled once a verdict lands.
- A pipeline that retries a failed step with the failure reason fed back in,
  escalates after N attempts, and pauses for a human when it can't recover.
- A code-writing setup where one Producer streams code while a checker Producer
  fires on each complete declaration as it arrives — running concurrently with the
  still-streaming writer. (The shipped reference uses a deterministic stand-in
  checker, `ast.parse`; swap in a real type/test checker in your own topology.)
- A planner that emits subtasks, each starting a solver that can itself emit more
  subtasks — recursive decomposition to arbitrary depth.
- An adversarial pair — one Producer writes, another attacks — streaming at each
  other from the start.
- A simulation: many Producers acting each tick against a shared world-state
  Producer, the whole run replayable from the log.
- A conversation between models as alternating Producers, ended on a convergence
  condition.
- A tool-using loop as a chain of model → tool → model Producers, each call
  independently replayable.

Runnable versions of the first three ship with the runtime (the reference
topologies), with committed run records you can read back; the rest are sketches of
the same shape. See Docs.

## Docs

- **Run a bundled demo** — `substrate topology list` to see them, then
  `substrate demo replay code_review` (tail a committed record, no run) or
  `substrate demo run debate` (live). Runnable demonstration topologies, no network, each
  producing a replayable record; the `natural_conversation` ablation (vs
  `natural_conversation_bare`) shows what the instruments buy, and `substrate score <root>`
  surfaces the calibration payoff. See `src/substrate/topologies/README.md`.
- **See it run** — `docs/demo.md` (or `bash demo.sh`): a guided read of the
  runtime working — three reference topologies, their logs annotated line by line,
  replay and provenance queries, and the conformance gate. All against committed
  records, no LLM or network. The fastest way to see what the thing actually does.
- **Write your first topology** — `docs/tutorial.md`: from install to a running
  two-Producer topology, step by step. Start here.
- **Add a topology** — `docs/adding-a-topology.md`: the next step after the
  tutorial — package a topology as a factory, run it from the CLI, make it
  dual-mode (deterministic in CI, real models in a walkthrough), and register it
  in the bundled catalogue. The contributor on-ramp.
- **Worked example topologies** — `docs/walkthroughs/README.md`: three complete
  topologies that ship with the runtime — an ensemble-and-adjudicator, an
  error-cascade pipeline, and code-synthesis with concurrent checking. Each ships
  with a committed (deterministic, CI-mode) run record you can read back, plus an
  illustrative transcript from a real local-LLM run you can reproduce.
- **What replay means** — `docs/replay.md`: replaying a run from its log has four
  levels of fidelity; this explains which ship in v1.0. (Short version: state and
  decision reconstruction plus log-equivalence diffing ship; full byte-for-byte
  re-execution is post-1.0 — don't rely on it yet.)
- **API reference** — `docs/api.md`: the public surface (`substrate.api`),
  generated from the code.
- **Conformance** — `uv run substrate conformance` runs the release gate: a suite
  of checks that exercises the runtime against the spec's required behaviors (one
  canonical topology per property). It runs in CI on every push. (The throughput
  floor is hardware-dependent, so it's checked on controlled hardware, not the CI
  matrix — see `CONTRIBUTING.md`.)

## Develop

```
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest
```

## Repository layout

To use or contribute, you need `src/` (the runtime), `docs/` (how to use it), and
`CONTRIBUTING.md` (how to develop). Everything else is the development record.

The runtime implements a four-document spec corpus. The **canonical** drafts are:

| Spec | Canonical |
|---|---|
| Kernel semantics | `docs/specs/kernel_spec/v15.md` |
| Product (requirements, conformance, reference topologies) | `docs/specs/product_spec/draft7.md` + amendments `A1`, `A2` |
| Technical (byte layout, writer cycle, public API) | `docs/specs/technical_spec/draft5.md` + amendment `A1` |
| Design (API ergonomics, CLI/error UX) | `docs/specs/design_spec/draft1.md` |

Everything else under `docs/specs/` is history, not load-bearing: superseded drafts
are relocated into each spec dir's `history/` (kept, not deleted — the audit trail).
And `docs/proof/`, plus the top-level `signals/`, `sprints/`, `archive/`,
`BLACKBOARD.md`, and `KIT_DIARY.md`, are the Signal-Driven Development record of how
it was built — read them for the *why*, skip them to use or contribute.
`CONTRIBUTING.md` has the full layout + the SDD notes.

Working name "substrate" (official package name deferred). Apache-2.0.
