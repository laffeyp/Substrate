# Substrate

A concurrent streaming dataflow runtime: an importable Python 3.12+ library plus
a CLI. You bring computations — LLMs, ML models, deterministic transforms,
subprocesses, simulators, parsers, sensors — as **Producers** that take typed
input and emit a stream of typed **Events**; the runtime runs them concurrently,
coordinates them through a single totally-ordered append-only **Bus**, and
creates new Producers dynamically when **Predicates** over **Views** of the log
are satisfied (**Triggers**). **Routes** carry data into future instantiations;
a **TerminationPolicy** decides when the run ends. The load-bearing commitment:
*all state lives on the log, and nothing consequential is silent* — the persisted
**run record** is the canonical account of what happened.

Working name "substrate" (official package name deferred — B-Q-1). Apache-2.0.

## Spec corpus

This package implements a four-document spec corpus (in this repo):

- `kernel_spec/v15.md` — the eight primitives, the append cycle, replay (+ `v16_reconciliation_note.md`).
- `product_spec/draft7.md` — requirements, the 17 conformance checks, reference topologies.
- `technical_spec/draft5.md` — byte layout, writer cycle, public API.
- `design_spec/draft1.md` — API ergonomics, CLI UX, error UX.

Built under Signal-Driven Development (`../sdd-kit-2/`); the locked signal
vocabulary is `signals/0.1.json`. Implementation roadmap: `sprints/PHASE1_PLAN.md`.

## Develop

```
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest
```
