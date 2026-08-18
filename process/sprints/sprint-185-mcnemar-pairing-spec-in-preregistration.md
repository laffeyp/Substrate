# Sprint 185 — Pin McNemar pairing spec in Pass-1 pre-registration (closes external round-2 R5)

---

```yaml
---
id: 185
status: closed
phase: 0
pass_kind: docs
---
```

## scope

Round-2 R5: design v3's Pass 1 shape paragraph waves at "three-trial McNemar" without naming the pairing unit or the exact statistic. User's memory item `project-benchmarking-power-reality` names the class of trap ("bit-collapse+McNemar is conservative not inflated; pass^k vs pass@k trap"). Roadmap v2 defers to S10's pre-reg update; the gap is the deferral itself, since S10 will fire with whatever the runner defaults to.

Sprint 185 pins the spec in roadmap v2 § S10 so the pre-reg (when it lands) carries the block: pairing unit (instance-level), test statistic (`exact_mcnemar_p` at `assay/report.py:34`), primary endpoint currency (Δ-pass^k with k=1 via bootstrap TOST), what Pass 1 does NOT test (trial-level variance decomposition — that lives in Pass 2), grace clause (zero-discordant fallback via `equivalence_verdict`). Every value cites the code line the runner reads.

## files modified

- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` — § "Sprint 10" gains a "Statistical spec the pre-reg must pin before S10 dispatches" block with five bullets.

## contracts

- Doc-only change.
- Every value in the spec references the shipped implementation at a specific file:line. `exact_mcnemar_p` at `report.py:34`; `bootstrap_delta_pass_k` at `stats.py`; `equivalence_verdict` at `stats.py`.
- Pass 2's trial-level structure remains separately specified (out of scope here).
- When S10's pre-registration file lands (Pass 1 dispatch), it inherits this spec block verbatim; the `assay/preregistration.py::load_preregistration` gate refuses admission if the block is missing (follow-on to Sprint 170's `graded_rate_floor` gate; not implemented in Sprint 185 — Sprint 185 pins the requirement in the roadmap).

## done

One roadmap edit. The statistical decision is no longer deferred to ad-hoc handling at S10 dispatch time.
