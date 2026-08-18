# Sprint 180 — `container_arm` observation contract at N=5 (closes external round-2 R1)

---

```yaml
---
id: 180
status: closed
phase: 0
pass_kind: observation
---
```

## scope

Round-2 R1: the paper's natural-experiment claim leans on `container_arm` in three places without a resolve number. The arm has been in the matrix since commit 2f311d6 (2026-08-11); no assay run has isolated its behavior. The only observation contract for it is `assert producer_kinds == ["solve"]` — a shape check, not a behavior check.

Sprint 180 lands the behavior check. A 5-instance smoke fires `container_arm` on Lite through the confirmatory runner, filters to container_arm rows, reads the per-cell records for `SelectedPatch` presence, tallies verdicts, computes a smoke-scale resolve rate (±40 points at n=5 — not confirmatory), and prints OK / WARN based on whether every cell emitted `SelectedPatch` with zero NO_VERDICT.

Either outcome answers the paper's counter-argument: OK → the natural-experiment claim gets its first evidence; WARN → the claim needs a caveat or the arm needs a fix.

## files created

- `scripts/smoke_container_arm_n5.py` — the observer. Invokes the confirmatory runner in matrix mode with SWEBENCH_LIMIT=5, then filters rows to `arm == "tool_loop_container"` and walks per-cell records.

## contracts

- Ruff clean; script parses.
- Requires live Ollama + Docker + swebench harness (Architect's box).
- No new tests — the smoke IS the observation contract.

## how it runs

```
SUBSTRATE_ARM_N=5 \
SUBSTRATE_ARM_MODEL=deepseek-v4-pro:cloud \
SUBSTRATE_OLLAMA_TIER=pro \
OLLAMA_HOST=https://ollama.com \
OLLAMA_API_KEY=... \
uv run python scripts/smoke_container_arm_n5.py
```

## what closes when the smoke fires

- **R1.** `container_arm` has behavioral evidence beyond a shape check.
- **Paper § 2 natural-experiment claim.** Either the counter-argument's evidence lands, or the claim narrows to a caveat about `container_arm`'s unproven behavior.
- **Roadmap v2 T5 mechanism claim.** The paper's argument that Substrate proves the assay pattern generalizes gets one more topology-shape data point.

## done

One file. Behavior instrument. Runs against real endpoint + real Docker + real harness. Ships as the smallest possible evidence for a paper claim currently unfounded.
