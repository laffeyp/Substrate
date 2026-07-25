# Substrate

![Substrate — a Python runtime that coordinates models and anything else you want through a single append-only log](.github/assets/substrate-banner-1600x400.png)

[![PyPI](https://img.shields.io/pypi/v/substrate-kernel)](https://pypi.org/project/substrate-kernel/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)

Substrate is a Python runtime for running many computations together — LLMs, ML
models, deterministic transforms, subprocesses, parsers, simulators: anything that
takes typed input and emits typed events — and coordinating them through a single
shared, append-only log.

## Quick start

```
pip install substrate-kernel          # the import name is `substrate`
substrate demo replay code_review     # read a committed run record back — no model, no network
substrate demo run debate             # run one live
```

`demo replay` reads back a run record that ships with the package: every event and
every runtime decision from a real run, numbered and replayable offline.
[docs/tutorial.md](docs/tutorial.md) goes from install to a running two-Producer
topology, step by step.

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
  still-streaming writer.
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

All of these ship as runnable code. Most are bundled topologies with committed run
records — `substrate topology list` to browse, `substrate demo replay <name>` to
read one back. The retry/escalate/pause pipeline ships as a reference walkthrough
(`docs/walkthroughs/`); `coding_flow` runs a real
`ruff check && mypy --strict && pytest` gate on generated code.

## How it works

If you use a coding agent — Claude Code, Codex, and their kin — you already know
the shape: a model that can only read and write text, wrapped in a harness of
tools and procedures that decides how that text becomes work on a computer. The
harness is most of the product. Substrate lets you build your own — your models,
local or cloud, your tools, your loop — with a property none of those harnesses
have: every step of the run lands on a replayable record. And because the harness
is just one arrangement of the same pieces, the runtime covers much more than the
agent loop.

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
totally-ordered, append-only log — think of an accountant's ledger, where you only
ever add a new entry, never erase an old one, and any total you care about is
*derived* by replaying the entries rather than kept on the side. Each computation
reads from the log and emits typed events back onto it; none of them talk to each
other directly. That one shared log is the only place coordination happens.

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

## Status

1.0.0. Ships: the eight pieces above, both persistence modes, replay Levels 1,
2, and 3(a), the read projections (provenance, diff, narration, graphs),
composition, the 17-check conformance suite, and the bundled topologies with their
committed records. Deferred, with recorded rationale: byte-identical Level-3(b)
re-execution, and the persistent bus on Windows.

The verification gate is `scripts/ci_local.sh` — the full stack (lint, format,
strict types, tests, import contract, conformance) across Python 3.12/3.13/3.14.
The conformance throughput floor is hardware-dependent and is graded on controlled
hardware rather than in the matrix (`CONTRIBUTING.md`).

## Docs

| Doc | What it is |
|---|---|
| [docs/tutorial.md](docs/tutorial.md) | Install to a running two-Producer topology, step by step. Start here. |
| [docs/demo.md](docs/demo.md) | A guided read of three reference topologies against their committed records — logs annotated line by line, replay and provenance queries. Also runnable: `bash demo.sh`. |
| [docs/adding-a-topology.md](docs/adding-a-topology.md) | Package a topology, run it from the CLI, register it in the bundled catalogue. The contributor on-ramp. |
| [docs/walkthroughs/](docs/walkthroughs/README.md) | Three complete worked topologies, each with a committed record and a reproducible real-model transcript. |
| [docs/replay.md](docs/replay.md) | The four replay fidelity levels and which ship in v1.0. |
| [docs/api.md](docs/api.md) | The public surface (`substrate.api`), generated from the code. |

## Develop

```
uv venv --python 3.12
uv pip install -e ".[dev]"
scripts/ci_local.sh
```

`CONTRIBUTING.md` has the gates, the spec corpus, and the layout.

## Repository layout

To use or contribute, you need `src/` (the runtime), `docs/` (how to use it), and
`CONTRIBUTING.md` (how to develop). The runtime implements a four-document spec
corpus; the canonical drafts:

| Spec | Canonical |
|---|---|
| Kernel semantics | `docs/specs/kernel_spec/v15.md` |
| Product (requirements, conformance, reference topologies) | `docs/specs/product_spec/draft7.md` + amendments `A1`, `A2`, `A3` |
| Technical (byte layout, writer cycle, public API) | `docs/specs/technical_spec/draft5.md` + amendment `A1` |
| Design (API ergonomics, CLI/error UX) | `docs/specs/design_spec/draft1.md` |

Superseded drafts live in each spec dir's `history/`, kept, not deleted. Everything
under `process/` is the development record — how this was built, kept append-only.
Read it for the why; skip it to use or contribute.

---

Substrate. On PyPI as `substrate-kernel` (the import name is `substrate`). Apache-2.0.
