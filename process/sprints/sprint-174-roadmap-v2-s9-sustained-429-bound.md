# Sprint 174 — Roadmap v2 S9 observation contract gains sustained-429 bound (fold external F12)

---

```yaml
---
id: 174
status: closed
phase: 0
pass_kind: docs
---
```

## scope

Close F12. Extend the roadmap v2 S9 (Lite N=300 wire-check) observation contract with a
sustained-rate-limit bound that measures 429-denial rate across rolling 30-minute windows,
not just per-cell counts.

## rationale

Reviewer at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md:170-177`:
"A 300-cell wire-check that respects a ≤10 per-cell 429 count can still burn tier throughput
at 82% (300 cells × 10 denials × ~30 minutes ≈ 100/min denial rate — a saturation pattern).
The gate should read the sustained rate, not a per-cell count." Matches KIT_DIARY 39's
observation-contract-second-purpose rule: every gate is sized both for the primary claim's
CI AND for the second-order failures the run's scale exposes.

## files modified

- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` — one paragraph added
  to § "Sprint 9" observation-contract additions naming the sustained-rate bound (rolling
  30-min window, `RateLimitDenied / RateLimitAttempted < 0.20`), the publish-refusal
  connection (Sprint 170's branch fires on crossing), and the per-model-per-minute denial
  curve dumped for the postmortem.

## contracts

- Doc-only change; nothing to test.
- Roadmap v2 S9 now covers both per-cell alarms AND tier-saturation patterns.

## done

One doc edit. Reviewer's F12 folded into the roadmap the same day it landed.
