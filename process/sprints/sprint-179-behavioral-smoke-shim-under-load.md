# Sprint 179 — Behavioral smoke: light topology + fixed shim + real Ollama (closes external round-2 M5)

---

```yaml
---
id: 179
status: closed
phase: 0
pass_kind: observation
---
```

## scope

Round-2 M5: last live assay run was 2026-08-11 20:41. Since then the tree accumulated a paper, an audit, two roadmap versions, twelve sprint cards, twenty-plus modified files. The verifiable-behavior surface moved zero. Sprint 168's semaphore-release fix is proved in a mock; nothing has verified it under real 300-call load at Pro tier.

Sprint 179 lands a 3-to-10-instance behavioral smoke. Fires the light topology (`swebench_repair_topology`) through the current `RateLimitedResponder` shim against the real Ollama Cloud endpoint on a small Lite sample. Reads the resulting cells for `verdict` / `reason` distribution; walks per-cell records for `SelectedPatch` / `ModelUsage` presence. Prints a rate-limit signal line: if `rate_limited` fraction > 20 percent, WARN — the shim's fix is insufficient at this N+tier+model, and Verified pass 1 should wait for roadmap v2 S5.2's `RateLimitProducer` proper.

The Architect fires this smoke against the real endpoint; the script itself is an observer around the confirmatory runner.

## files created

- `scripts/smoke_shim_under_load.py` — the smoke. Invokes the confirmatory runner (`scripts/assay_swebench_confirmatory.py`) as a subprocess with `SWEBENCH_LIMIT=N`, then reads the resulting `cells.jsonl` + per-cell records. Prints verdict / reason distributions and the rate-limit signal. Output under `process/smokes/<timestamp>_smoke/`.

## contracts

- Ruff clean; script parses.
- Consumes tier quota — run against the tier the confirmatory will fire on.
- No new tests — the smoke IS the test. The point is behavior verification, not unit coverage.

## how it runs

```
SUBSTRATE_SMOKE_N=5 \
SUBSTRATE_SMOKE_MODEL=deepseek-v4-pro:cloud \
SUBSTRATE_OLLAMA_TIER=pro \
OLLAMA_HOST=https://ollama.com \
OLLAMA_API_KEY=... \
uv run python scripts/smoke_shim_under_load.py
```

## what the output tells us

- `verdict distribution` per cell — how many PASS/FAIL/NO_VERDICT.
- `reason distribution` — every `reason` string that appeared on any NO_VERDICT cell.
- `per-cell record shape` — one line per cell: verdict, `SelectedPatch` count, `ModelUsage` count, wall_ms.
- **rate-limit signal** — the load-bearing line. `rate_limited_fraction > 20%` → WARN, do not fire Verified against the shim; wait for S5.2's producer. `≤ 20%` → OK, Sprint 168's semaphore-release does what the mock proved.

## what closes when the smoke fires

- **M5.** The verifiable-behavior surface moves for the first time in a day.
- **Sprint 168 verification.** The mock proof becomes a real-endpoint proof.
- **Standing shim rule.** The Architect's decision on whether Verified pass 1 waits for S5.2 gets data instead of intuition.

## done

One file. Behavior instrument, not a substrate topology. Ships as the fastest possible check on whether the shim's fix holds under real load, before committing to the S5.2 producer's design against the same misread invariant.
