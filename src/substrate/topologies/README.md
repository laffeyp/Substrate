# Bundled topologies

Runnable demonstration topologies, built only on the public `substrate.api` surface (the same
surface a third-party author has). Each runs with no network and no config — deterministic
stand-in Producers — and produces a replayable run record.

## Layout

Each topology is a **self-contained package** — its code (`<name>/__init__.py`) and its committed
CI-mode record (`<name>/records/ci_mode.record/`) live together under `<name>/`. Shared
infrastructure sits alongside them: `conversation.py` (the N-speaker turn engine the four
conversation demos configure), `instruments/` (the side-Producers the natural-conversation ablation
composes), and `bundled.py` (the `--topology <name>` registry). `natural_conversation_bare/` holds
only a record — it is the WITHOUT arm of the ablation, the same `natural_conversation` code run with
`instruments=False`.

## Run one

    substrate topology list                        # the bundled topologies
    substrate demo replay code_review              # tail the committed CI record (no run)
    substrate demo run    debate                   # run it live, streamed to stderr
    substrate run --topology natural_conversation --root /tmp/nc
    substrate score  /tmp/nc                        # the calibration payoff (scoring-on demos)
    substrate replay /tmp/nc --level 2              # verify every recorded decision by hash

The `natural_conversation` vs `natural_conversation_bare` pair is the emergence ablation: run
both and compare — same prompts, but the instrumented arm accretes common ground, fires a
repair detector, and grades each turn; the bare arm is parallel monologues.

## Read a committed record without running anything

Every topology ships a committed CI-mode record you can tail / replay / inspect directly:

    src/substrate/topologies/<name>/records/ci_mode.record/

e.g. `substrate tail src/substrate/topologies/code_review/records/ci_mode.record`.

## What each demonstrates

| Topology | Shows |
|---|---|
| `code_review` | N role-distinct reviewers → a quorum predicate fires a judge (Once) → cancel-all-others on adjudication |
| `pair_coding` | driver streams chunks; a navigator's suggestion is Routed into the driver's next instantiation |
| `recursive_decomposition` | one recursive Trigger spawns solvers at any depth, bounded by a depth-budget guard |
| `tool_loop` | the model -> tool -> model agent loop: a ToolCall fires a tool Producer, its ToolResult re-fires the model with the result appended; failed tools surface as typed observations, bounded by a step budget that ends on a FinalAnswer |
| `game_of_life` | a tick-based simulation: a world Producer fans the shared grid out as one CellTick per cell; a cell Producer per cell applies Conway's Life rule concurrently; a step Trigger assembles the next generation once all cells report, bounded by a generation budget — every grid on the record |
| `debate` / `prisoners_dilemma` / `intel_asymmetry` | the conversation substrate under positional / payoff / information asymmetry |
| `natural_conversation` (+ `natural_conversation_bare`) | the emergence ablation — common-ground + repair instruments toggled; the delta is the demo. The `_bare` variant is the WITHOUT arm. |
| `adversarial_pair` | a writer vs a vulnerability-finder in an attempt-count-bounded refinement loop (GAN / red-team shape) |
| `game_of_life_glider` | `game_of_life` seeded with an asymmetric moving glider (the fixture that catches a mirror-render bug the symmetric blinker cannot) |
| `coding_flow` | best-of-N codegen over a model ENSEMBLE → build-validation (a real gate) → correction loop. A run-and-observe app, **not** a committed record — see below. |

All twelve `BUNDLED` topologies (runnable via `substrate run --topology <name>`) are represented above —
some rows fold in variants (the two `natural_conversation` arms, the two `game_of_life` seeds) or the
three conversation asymmetries. `coding_flow` is the run-and-observe exception below, not in `BUNDLED`.

### `coding_flow` — a run-and-observe app, not a committed record

`coding_flow` is the exception: it validates each candidate by running a REAL gate (`ruff check &&
mypy --strict && pytest`) in a subprocess, so its run is not byte-reproducible — it is
`deterministic=False`, is **not** in the `bundled` registry, and ships no `records/` snapshot. Run it
and watch: a seeder fans out N drafters (one per model in a heterogeneous ensemble), each emits a
Candidate, a validator runs the gate on each in parallel, and when a round's verdicts are all in the
judge selects the gate-passing candidate — or, if none pass, feeds every failure back into a fresh
round (bounded), or gives up (Exhausted). CI proves the wiring on canned candidates against the real
gate; the `@realmodel` walkthrough runs a real local-coder ensemble. Code + tests:
`topologies/coding_flow/` and `tests/test_coding_flow.py`.

## Walkthrough mode (real local LLMs)

The conversation demos and the Wave-11 topologies accept `walkthrough=True`, which swaps a real
local LLM (Ollama, `OllamaResponder`) for the deterministic stand-in:

    python -c "import asyncio; from substrate.api import Runtime; \
      from substrate.topologies.debate import debate_topology; \
      asyncio.run(Runtime('/tmp/debate').run(debate_topology(walkthrough=True)))"
