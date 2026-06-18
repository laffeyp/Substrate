# Contributing to Substrate

## Spec corpus

Substrate implements a four-document spec corpus (in this repo); the code is held
accountable to it, not the other way round:

- `docs/specs/kernel_spec/v15.md` — the eight primitives, the append cycle, replay
  (+ `v16_reconciliation_note.md`).
- `docs/specs/product_spec/draft7.md` — requirements, the 17 conformance checks, reference
  topologies.
- `docs/specs/technical_spec/draft5.md` — byte layout, writer cycle, public API.
- `docs/specs/design_spec/draft1.md` — API ergonomics, CLI UX, error UX.

### Spec amendments

Changes to a shipped spec are made as **additive amendment files**, never by editing
the base draft (the base stays as the audit trail):

- `docs/specs/product_spec/draft7_amendment_A1_replay_3b.md` — replay Level 3(b) deferral +
  the D-8 supplementary-metadata exclusion set.
- `docs/specs/product_spec/draft7_amendment_A2_nperf1.md` — the N-PERF-1 throughput floor
  re-baseline.

## Signal-Driven Development

Built under Signal-Driven Development (`../sdd-kit-2/`). The locked signal
vocabulary is `signals/0.2.json` — an additive successor to `signals/0.1.json`,
which is retained as the v0.1 audit trail. The rationale for the 0.1 → 0.2
evolution is `signals/0.2-rationale.md`.

Implementation roadmap: `sprints/PHASE1_PLAN.md`. Working notes and per-wave
records live in `BLACKBOARD.md`.

## Gates

Every change must keep these green (they run in CI — `.github/workflows/ci.yml` — on
the matrix {ubuntu, macOS} × Python {3.12, 3.13, 3.14}):

```
uv run ruff check          # lint
uv run ruff format --check # format
uv run mypy                # type-check (strict)
uv run pytest              # tests
uv run lint-imports        # F-API-6: cli imports only substrate.api (import-linter)
uv run substrate conformance --no-perf   # the 17 conformance checks (perf floor skipped)
```

`substrate conformance` is the release gate (the 17 §7 checks). CI runs it with
`--no-perf` because the throughput floor (check 15 / N-PERF-1) is hardware-sensitive;
that makes check 15 an honest SKIP in CI. Verify the floor separately on controlled
hardware with `SUBSTRATE_PERF_GATE=1 uv run pytest tests/test_perf.py` (or the default
`uv run substrate conformance` without `--no-perf`).

The API reference (`docs/api.md`) is **generated** — never hand-edit it. After any
change to the public surface (`substrate.api.__all__`) or a public docstring, run
`uv run python scripts/gen_api_docs.py` and commit the regenerated file. The committed
walkthrough run records (`docs/walkthroughs/records/`) regenerate with
`uv run python scripts/gen_walkthrough_records.py`.

## Post-1.0 deferrals

Deliberately not shipped in v1.0 (deferred with cause, not gaps):

- **Replay Level 3(b)** — byte-identical substitution re-execution (needs a replay-mode
  writer that replays recorded `t`; amendment A1.1). Levels 1/2/3a + D-8 ship.
- **`let_finish` (F-LIFE-2 recipe) + the `let-finish` Decision** — the "drain in-flight
  then finalise" terminal has no runtime dispatch branch, so shipping the enum value /
  recipe would be a silent no-op. Removed for v1.0 and deferred until the dispatch +
  admission-stop mechanism is built. (`cancel_all_others`, `quiescence_with_watchdog`,
  `threshold_count`, `all_completed`, `pause_await_input`, `any_of`, `all_of` all ship.)
- **`subtree_cancellation`** — needs a 6th decision value / scope field (vocab-blocked).
- A **compiled JCS encoder** — the throughput lever beyond the current floor (A2).
