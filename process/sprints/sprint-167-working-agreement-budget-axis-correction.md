# Sprint 167 — WORKING_AGREEMENT Budget-axis correction (fold external review F8)

---

```yaml
---
id: 167
status: closed
phase: 0
pass_kind: docs
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Correct the Budget-axis names in `process/WORKING_AGREEMENT.md § "SWE-bench external substrates" → "Producer-authorship rules"`. Sprint 162 wrote "Budget (from the S1 kernel change: `docker_containers`, `wall_seconds`, `model_calls` caps)"; the shipped Sprint 164 API has `wall_seconds` and `event_counts` — with `docker_containers` and `model_calls` expressible as entries under `event_counts` keyed by event-kind name. The doc misled any producer author reading it. Sprint 167 rewrites the sentence to match the shipped shape, names the `Cap` struct from Sprint 166, and gives concrete patterns for `ContainerProducer`, `HarnessProducer`, `RateLimitProducer`.

Closes external review F8 at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`. Same 2026-08-12 date as Sprints 162, 164, 166 — this is a same-day catch-up on drift between two docs I authored back-to-back.

---

## prerequisites

- Sprint 162 (WORKING_AGREEMENT § "SWE-bench external substrates" section authored).
- Sprint 164 (Budget primitive shipped with `wall_seconds` + `event_counts`).
- Sprint 166 (Cap struct amendment).
- External review at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F8.

---

## context_files

- `process/WORKING_AGREEMENT.md` (file modified; § "Producer-authorship rules" bullet 1).
- `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F8.
- `src/substrate/kernel/topology.py` (source of truth for `Budget` and `Cap` shapes).
- `tests/test_kernel_budget.py` (canonical construction patterns).

---

## signal contract

### Emits

None at runtime — docs sprint.

### Consumes

Files listed in `context_files`.

### Invariants

- Every other section of `WORKING_AGREEMENT.md` byte-preserved via SEARCH/REPLACE.
- The Budget-axis description matches `topology.py`'s current `Budget` shape exactly.
- Concrete patterns for each producer type name the actual event-kind constants from vocab v0.3 § G.

---

## artifact contract

### Files modified

- `process/WORKING_AGREEMENT.md` — rewrite bullet 1 of § "Producer-authorship rules". Names both Budget axes (`wall_seconds`, `event_counts`), the `Cap` struct's shape, and three concrete patterns.

### Content assertions

- The bullet contains `wall_seconds: Cap | None`.
- The bullet contains `event_counts: dict[str, Cap] | None`.
- The bullet contains three concrete patterns naming `ContainerProducer`, `HarnessProducer`, `RateLimitProducer`.
- The bullet does NOT contain the stale `docker_containers` or `model_calls` phrases (unless as event-kind-name examples inside `event_counts`).
- Every other line of `WORKING_AGREEMENT.md` is unchanged.

### Command exit codes

- `grep -q "wall_seconds: Cap | None" process/WORKING_AGREEMENT.md` returns 0.
- `grep -q "event_counts: dict\[str, Cap\]" process/WORKING_AGREEMENT.md` returns 0.
- `grep -c "docker_containers\`\|\`docker_containers\|model_calls\` caps" process/WORKING_AGREEMENT.md` returns 0.

---

## observation contract

Not applicable — docs sprint. Verification is the Architect's read: does the bullet accurately describe `Budget` and `Cap`? Do the concrete patterns match how S5.x sprints will actually construct their budgets?

---

## done criteria

The WORKING_AGREEMENT bullet names the actual shipped Budget API (`wall_seconds` + `event_counts`), names `Cap`, and gives concrete patterns. Architect confirms; Sprint 167 closes.

---

## notes

- **F8 finding.** Reviewer at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md:123-133`: "A build-side worker for S5.3 (ContainerProducer) reads WORKING_AGREEMENT looking for the Budget API they must declare, finds `docker_containers` as a named axis, and writes `Budget(docker_containers=(1, ...))` — which is a TypeError. The doc looks authoritative and misleads the consumer."
- **Self-caught drift.** Sprint 162 and Sprint 164 landed same day; the doc named an API shape that turned out different from what I built one sprint later. Reviewer caught it. Same-day catch-up.
- Roughly 10 minutes; one-file docs edit.

---

## plan-mode review checklist

- [x] Every other section byte-preserved.
- [x] Budget axes named accurately (`wall_seconds` + `event_counts`).
- [x] `Cap` struct named.
- [x] Concrete patterns for the three producer types.
- [x] One concept (Budget-axis correction), one file — within sweet spot.
