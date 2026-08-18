# Sprint 198 — Per-cell wall-clock from the per-repo timeout table (roadmap v2 S8)

Small honest fix: the confirmatory runner's per-cell `asyncio.wait_for` timeout used a hardcoded `RUN_TIMEOUT=1800` for every cell. A sympy cell needs 90 min honestly; a small-repo cell needs 10. The per-repo table at `assay/swebench_timeouts.json` + the existing `timeout_for_instance` helper at `assay/swebench.py:107` already carried the per-repo numbers; the runner just wasn't calling them.

## files touched

- `scripts/assay_swebench_confirmatory.py` — import `timeout_for_instance`; at the per-cell `asyncio.wait_for` site, compute `cell_timeout = min(RUN_TIMEOUT, timeout_for_instance(instance_id))` and pass to `wait_for`. `RUN_TIMEOUT` remains as an operator-settable ceiling.
- `tests/test_per_cell_timeout.py` (new) — four tests: table lookup returns per-repo value; missing entry returns default (60 min); shipped `swebench_timeouts.json` parses; source-scan pin that the runner reads `timeout_for_instance` at the wait_for site.

## contracts

- 4/4 new tests pass; 27 across the touched assay+timeout modules pass.
- Ruff clean.
- No behavior change on cells whose repo is not in the table (fall back to `_DEFAULT_TIMEOUT_SECONDS = 3600`, capped at `RUN_TIMEOUT`).
- Sympy / django / astropy cells (repos in the shipped table) now get their declared per-repo timeouts instead of the runner's flat 1800s.

## done

Two files. Real fix: per-cell wall-clock now honors the per-repo table the runner was ignoring.
