# Substrate

A Python runtime for orchestrating LLMs and other computations where **the log is
the product**.

When you wire LLMs and agents together, the hard part isn't running them — it's
having a trustworthy account of *what happened and why* when a run misbehaves.
Tools like LangGraph, AutoGen, and Aider hold that state in memory and Python
control flow, so a bad run leaves you with logs to grep, not a record to replay.
Substrate inverts this: every decision the runtime makes is a recorded event, and
the persisted **run record** is the canonical, replayable, citable account of the
run — not a side-effect of it.

## How it works

You bring computations — LLMs, ML models, deterministic transforms, subprocesses,
parsers — as **Producers**: callables that take typed input and emit a stream of
typed **Events**. The runtime runs them concurrently and coordinates them through a
single totally-ordered append-only **Bus**; new Producers are created dynamically
when conditions over the log are met. Everything — every event, every firing, every
termination decision — lands on the **run record**, a framed, CRC-protected,
canonically-encoded JSONL log. *Nothing consequential is silent.*

(That's the front door. The full vocabulary — Views, Predicates, Triggers, Routes,
TerminationPolicy — is introduced where it's load-bearing, in the tutorial.)

## What you can build

The reference topologies (with real recorded LLM runs) show the shape. An
ensemble-and-adjudicator run, for example, records each weak model genuinely
disagreeing and a stronger model adjudicating — on its own replayable log:

```
Candidate m0: 'Charisma'   Candidate m1: 'Vision'   Candidate m2: 'Integrity'
VERDICT: m2 -> 'Integrity'
CANCELLED (lingering loser): member-slowA   member-slowB
```

The error-cascade reference (R-2) records an invalid emission, a retry enriched
with the failure reason, an exhausted-retry escalation, a pause awaiting human
input, and a resume — all as events on one continuous record. See
`docs/walkthroughs/README.md`.

## Docs

- **First topology** — zero to a working two-Producer run: `docs/tutorial.md`.
- **Reference topologies (R-1/R-2/R-3)** — CI + real-LLM walkthroughs with actual
  recorded runs: `docs/walkthroughs/README.md`.
- **What replay means** — the four replay tiers and what ships in v1.0:
  `docs/replay.md`. (Short version: Levels 1/2/3a + D-8 log-equivalence ship;
  full byte-identical re-execution is post-1.0 — don't rely on byte-for-byte
  replay in v1.0.)
- **API reference** — the public surface (`substrate.api`): `docs/api.md`.
- **Conformance** — `uv run substrate conformance` runs the 17-check release gate.

## Develop

```
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest
```

Built under Signal-Driven Development against a four-document spec corpus; layout,
SDD notes, and the spec amendments are in `CONTRIBUTING.md`. Working name
"substrate" (official package name deferred). Apache-2.0.
