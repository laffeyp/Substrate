# Substrate

![Substrate — a Python runtime that coordinates models and anything else you want through a single append-only log](.github/assets/substrate-banner-1600x400.png)

[![PyPI](https://img.shields.io/pypi/v/substrate-kernel)](https://pypi.org/project/substrate-kernel/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)

A Python 3.12+ runtime for running many computations together. You hand it model calls, transforms, subprocesses, parsers, simulators — anything that takes typed input and emits typed events. It runs them concurrently and coordinates them through one append-only log. Every event, and every runtime decision about what to start next, lands on that log. You replay the log, diff it, or inspect any point.

## Quick start

```
pip install substrate-kernel          # import name is `substrate`
substrate demo replay code_review     # read a committed record; no model, no network
substrate demo run debate             # run one live
```

`demo replay` reads a run record shipped in the package. Every event is on it, numbered. The [tutorial](docs/tutorial.md) walks install to a two-Producer topology.

## The pieces

You hand the runtime a topology: a Python function that declares which computations can run and what starts them. Nine names carry the design.

A **Producer** takes typed input and streams typed **Events**. It is a callable — an LLM, an ML model, a deterministic transform, a subprocess, a parser, anything of that shape. Events land on the **Bus**: one totally-ordered append-only log per run. Producers coordinate only through it.

A **View** maintains a running summary over the log ("how many answers are in", "everything Producer X has emitted so far"). A **Predicate** is a yes/no over the Views, evaluated when an event lands. A **Trigger** starts a new Producer when its Predicate holds. After the initial Producers you name, Triggers are the only way new ones appear. A **Route** carries data from past events into a future Producer's input. A **TerminationPolicy** decides when the run ends or pauses for outside input.

The bus writes to a **run record** on disk: framed, CRC-protected JSONL, canonically encoded. Everything is on it. Nothing is left off.

## What you can build

Every topology is a short Python program. `substrate topology list` names the ones the package ships. `substrate demo replay <name>` reads any of them back.

`code_review` runs several cheap models on the same task, has a stronger model adjudicate, and cancels the losing runs when the verdict lands. `coding_flow` streams code from a writer Producer while a checker Producer fires on each complete declaration as it arrives — writer and checker run at the same time. The check is real: `ruff check && mypy --strict && pytest` on the code the writer produced.

`debate` puts two model Producers on opposite sides of a claim; the run ends on a convergence condition. `adversarial_pair` runs a writer and an attacker streaming from t=0. A planner-and-solver topology emits subtasks that each start solvers that can themselves emit more subtasks — recursion falls out because a Trigger can start its own kind. A simulation runs many Producers each tick against a shared world-state Producer.

`docs/walkthroughs/` ships a retry pipeline: the failure reason feeds into the next attempt, escalation after N tries, pause for a human when it cannot recover. `tool_loop` is model → tool → model as a chain of Producers; each call is independently replayable because each Producer instantiation is its own record entry.

## How it works

Every computation reads the log and writes typed events back to it. Producers never call each other. The log is the coordination surface, and it is the only one.

The set of running Producers is not fixed. You write conditions over the log — "once three answers are in", "when this step fails" — and when a condition holds, the runtime starts another Producer. A run's shape grows as it unfolds. Recursion is a Producer that starts more of itself.

Every event and every runtime decision lands on the log. Each Producer start, each condition that fires, how the run ends: on the log. You read back what happened and why. You replay it at any point. Nothing consequential lives in memory or in control flow.

If you have used a coding agent, the harness around the model is the product. Substrate lets you build your own — your models, your tools, your loop, every step on a replayable record. The agent shape is one arrangement of the pieces; the runtime covers many others.

## Status

1.0.0 on PyPI as `substrate-kernel`. Apache-2.0. Import name `substrate`.

Ships: the nine pieces above, both persistence modes, replay Levels 1, 2, and 3(a), the read projections (provenance, diff, narration, graphs), composition, the 17-check conformance suite, and the bundled topologies with committed records.

Deferred, with recorded rationale: byte-identical Level-3(b) re-execution, and the persistent bus on Windows.

`scripts/ci_local.sh` is the verification gate. It runs lint, format, strict types, tests, import contract, and conformance across Python 3.12/3.13/3.14. Check 15 (the throughput floor) is hardware-sensitive and grades on controlled hardware, not in the CI matrix. `CONTRIBUTING.md` has the details.

## Docs

| Doc | What it is |
|---|---|
| [docs/tutorial.md](docs/tutorial.md) | Install to a running two-Producer topology. Start here. |
| [docs/demo.md](docs/demo.md) | Three reference topologies annotated line by line against their committed records. Runnable: `bash demo.sh`. |
| [docs/adding-a-topology.md](docs/adding-a-topology.md) | Package a topology, run it from the CLI, register it in the bundled catalogue. Contributor on-ramp. |
| [docs/walkthroughs/](docs/walkthroughs/README.md) | Three worked topologies, each with a committed record and a reproducible real-model transcript. |
| [docs/replay.md](docs/replay.md) | The four replay fidelity levels and which ship in v1.0. |
| [docs/api.md](docs/api.md) | The public surface (`substrate.api`), generated from the code. |

## Develop

```
uv venv --python 3.12
uv pip install -e ".[dev]"
scripts/ci_local.sh
```

`CONTRIBUTING.md` has the gates, the spec corpus, and the layout.

## Layout

`src/` is the runtime. `docs/` is how to use it. `CONTRIBUTING.md` is how to develop. Four spec documents govern the code:

| Spec | Canonical |
|---|---|
| Kernel semantics | `docs/specs/kernel_spec/v15.md` |
| Product | `docs/specs/product_spec/draft7.md` + `A1`, `A2`, `A3` |
| Technical | `docs/specs/technical_spec/draft5.md` + `A1` |
| Design | `docs/specs/design_spec/draft1.md` |

Superseded drafts live under each spec dir's `history/`. `process/` holds the development record, append-only. Read it for the why; skip it to use or contribute.
