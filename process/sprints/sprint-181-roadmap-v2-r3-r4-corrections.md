# Sprint 181 — Roadmap v2 corrections: audit-vs-grade replay (R3) + realistic runner line-count target (R4)

---

```yaml
---
id: 181
status: closed
phase: 0
pass_kind: docs
---
```

## scope

Two doc corrections to `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md`, both flagged by round-2 review.

**R3.** Roadmap v2 § "Shape v2 lands" (also cited in the Consequences bullet) claimed the S6 collapse to `LogProjectionOracle` moves the grade "replayable at Level 1." What becomes L1-replayable is the AUDIT of the grade — the recorded `GradeResult` event replays deterministically as a projection of prior events. The GRADE ITSELF (pytest inside a Docker container) remains non-deterministic; two identical patches graded twice may still produce different `report.json` outcomes on rare pytest-side flake. The genuine post-hoc payoff is `explain_producer` walking a `GradeResult` back through `HarnessProducer` events. Sprint 181 rewrites both mentions to distinguish audit-replay from grade-replay.

**R4.** Roadmap v2 § "Sprint 7" and the Consequences bullet claimed "972 → roughly 150 lines." An honest line count separates boundary except-branches (producer-authoring absorbs those) from the survivors: env parsing, arm building, prep sweep, image pre-pull, cases sidecar writer, config fingerprint + preregistration wiring, the cell inner function, the row writer, the `_run` outer function + salvage + batch-grade paths. Roughly 580 lines survive under any redesign that keeps the runner's job. The 150 target is optimistic by 2×; ~350–400 is defensible. Sprint 181 resets the target at all three mention sites.

## files modified

- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` — three edits:
  1. Consequences bullet: 972 → 150 replaced with 972 → 350-400, with an explanatory paragraph. R4 fold noted inline.
  2. Consequences bullet: "grade replayable at Level 1" replaced with "AUDIT of the grade replayable at Level 1" plus the distinction explained. R3 fold noted inline.
  3. § Sprint 7 file list: "roughly 150 lines" → "roughly 350–400 lines".
  4. § "Shape v2 lands": `assert_replayable` claim rewritten to name the audit-vs-grade distinction.

## contracts

- Doc-only change.
- Every claim on the roadmap that carried the R3 or R4 defect now names the honest number or the honest distinction.
- Any downstream doc citing the roadmap's 150-line or L1-grade-replay numbers as authority reads the corrected values.

## done

One file. Two honest corrections at three sites. The S7 sprint's own artifact-contract line-count target (when S7 dispatches) matches what a runner rewrite will actually produce.
