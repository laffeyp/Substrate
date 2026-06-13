# Contributing to Substrate

## Spec corpus

Substrate implements a four-document spec corpus (in this repo); the code is held
accountable to it, not the other way round:

- `kernel_spec/v15.md` — the eight primitives, the append cycle, replay
  (+ `v16_reconciliation_note.md`).
- `product_spec/draft7.md` — requirements, the 17 conformance checks, reference
  topologies.
- `technical_spec/draft5.md` — byte layout, writer cycle, public API.
- `design_spec/draft1.md` — API ergonomics, CLI UX, error UX.

### Spec amendments

Changes to a shipped spec are made as **additive amendment files**, never by editing
the base draft (the base stays as the audit trail):

- `product_spec/draft7_amendment_A1_replay_3b.md` — replay Level 3(b) deferral +
  the D-8 supplementary-metadata exclusion set.
- `product_spec/draft7_amendment_A2_nperf1.md` — the N-PERF-1 throughput floor
  re-baseline.

## Signal-Driven Development

Built under Signal-Driven Development (`../sdd-kit-2/`). The locked signal
vocabulary is `signals/0.2.json` — an additive successor to `signals/0.1.json`,
which is retained as the v0.1 audit trail. The rationale for the 0.1 → 0.2
evolution is `signals/0.2-rationale.md`.

Implementation roadmap: `sprints/PHASE1_PLAN.md`. Working notes and per-wave
records live in `BLACKBOARD.md`.

## Gates

Every change must keep all four gates green:

```
uv run pytest                       # tests
uv run mypy src                     # type-check (strict)
uv run ruff check src tests scripts # lint
uv run ruff format --check src tests
```

Plus the release gate: `uv run substrate conformance` (the 17 conformance checks).

The API reference (`docs/api.md`) is **generated** — never hand-edit it. After any
change to the public surface (`substrate.api.__all__`) or a public docstring, run
`uv run python scripts/gen_api_docs.py` and commit the regenerated file.
