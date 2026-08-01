# Sprint 140 — W1.INT: the application library, mounted end-to-end

---

```yaml
---
id: 140
status: closed
phase: 2
pass_kind: observation
cadence_band: plan-mode-per-sprint
---
```

---

> REWRITE NOTE (2026-07-31, review F-23): this card was committed at ZERO BYTES in 63fba04 — the
> opening heredoc that authored it silently failed and the write was never verified, while the board
> entry described a full card. The content below is reconstructed from the plan and the code that
> actually landed. The lesson is logged in KIT_DIARY (verify the write, not the echo).

## why

The wave-boundary integration sprint for phase W1 (technique #16 / N.INT): assert the three W1
applications are mounted, wired, and runnable as a SET — not just each alone — and make the library
visible in the docs. Produces no new topology; it verifies the wave and documents it.

## scope

`tests/test_applications_integration.py` — one test that builds and runs all three W1 topologies
deterministically (fanout_review on a throwaway repo, best_of_n_verified with a deterministic check,
research_sweep over in-memory docs) and asserts each reaches its terminal with its signature output.
`docs/applications.md` — the library page. A pointer from `docs/application-catalogue.md`.

## signal contract

No new event kind. The test asserts each app's existing signature kind (VerdictRendered / Solved /
Synthesis) and `RunFinalised`, on one invocation.

## artifact contract

### Files created

- `tests/test_applications_integration.py` — the three-app end-to-end integration test.
- `docs/applications.md` — the application-library page (originally `docs/workflows.md`; renamed under
  review F-16 because "workflow" is a banned lexicon term).

### Files modified

- `docs/application-catalogue.md` — a pointer to `docs/applications.md`.

### Command exit codes

- `uv run python -m pytest tests/test_applications_integration.py -q` returns 0
- `scripts/ci_local.sh` returns 0 (all six gates, both Python versions)

## observation contract

`pass_kind: observation` — the sprint IS the observation contract. Behavior: the three applications,
mounted together, each run to their terminal on one test invocation.

- fanout_review → VerdictRendered + RunFinalised
- best_of_n_verified → Solved + RunFinalised
- research_sweep → Synthesis + RunFinalised

## done criteria

The three W1 applications run end-to-end as a set in one test (green); the library is documented in
`docs/applications.md` and linked from the catalogue; full gate green. W1 closes.

## honest scope notes (added in the 2026-07-31 remediation)

- The plan's phase-W1 gate was `substrate run fanout_review --repo <path> --n 5`. That never worked:
  the apps are NOT in `BUNDLED`, so they are not `substrate run --topology` targets — they launch via
  `scripts/run_*.py` (review F-19). "PHASE W1 COMPLETE" was declared against a gate that could not run.
  The apps are complete AS A SCRIPT-LAUNCHED LIBRARY; registering them in `BUNDLED` is a separate,
  unstarted piece. The catalogue and this card now say so.
- Committing deterministic CI records under `docs/walkthroughs/records/` was deferred (currency-gate
  machinery, KIT_DIARY #9); the integration test is this wave's durable CI proof.
