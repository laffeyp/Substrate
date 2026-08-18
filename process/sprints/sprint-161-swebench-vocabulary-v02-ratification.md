# Sprint 161 — swebench_solver vocabulary v0.2 ratification

---

```yaml
---
id: 161
status: pending
phase: 0
pass_kind: docs
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Consolidate two ratified vocabulary evolutions (H-1/H-2 + H-3) into the SWE-bench sub-topology's
locked vocabulary doc, and flip its header from `PROPOSED` to `RATIFIED`. Sprint 133 closed the
vocabulary session on 2026-06-27 but the header carried "PROPOSED" past ratification. Two
subsequent halts (H-1/H-2 on 2026-08-10, H-3 on 2026-08-10 extended 2026-08-11) added the
`Result.Verdict` enum and the `_HARNESS_REASONS` closed set at the general assay boundary; the
motivating use-case for both is SWE-bench, but neither was back-propagated into
`process/signals/swebench-solver-vocabulary.md`. This sprint closes both drifts in one file.

This is Sprint 0 of the SWE-bench rebuild chain per
`docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain.md` — corrected from the roadmap's
original "vocabulary session" label after the reviewer discovered Sprint 133 had already run one
(reviewer's correction recorded in the same doc's § "The reviewer's calibration lesson"). No new
tags authored; no code touched.

---

## prerequisites

- Sprint 133 close (2026-06-27).
- H-1 ratification in `## Decisions` (2026-08-10).
- H-2 ratification in `## Decisions` (2026-08-10, same entry).
- H-3 ratification in `## Decisions` (2026-08-10).
- H-3 `rate_limited` extension in `## Decisions` (2026-08-11).

---

## context_files

- `sdd-kit-2/AGENTS.md`
- `sdd-kit-2/grammar/PRINCIPLES.md` (commitment 1: vocabulary is the contract; commitment 3: workers cannot invent vocabulary)
- `process/signals/swebench-solver-vocabulary.md` (the doc modified)
- `process/signals/0.2-rationale.md` (shape reference for the additions section)
- `process/BLACKBOARD.md ## Decisions` (2026-08-10 and 2026-08-11 ratifications)
- `docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` § "The oracle contract"
- `docs/DESIGN-2026-08-11-responder-rate-limit-shim.md` § "Closed-set additions"
- `src/substrate/assay/oracle.py:36-105` (Verdict + Result)
- `src/substrate/assay/swebench.py:55-85` (_HARNESS_REASONS + REASON_* constants)
- `src/substrate/assay/swebench_errors.py` (typed exception hierarchy)
- `src/substrate/adapters/rate_limit.py` (ProviderRateLimited)

---

## signal contract

### Emits

None at runtime — docs sprint. The doc IS the deliverable.

### Consumes

- The source files listed in `context_files`, read directly.

### Invariants

- v0.1 sections A-D of the vocabulary doc byte-preserved (SEARCH/REPLACE, no rewriting).
- No new vocabulary tags authored; the additions are already-ratified constants and enum values.
- The additions' shape matches `signals/0.2-rationale.md`'s pattern (rationale + source citations + code homes).

---

## artifact contract

### Files modified

- `process/signals/swebench-solver-vocabulary.md` — flip status header to RATIFIED v0.2; add § E (v0.2 additions: E.1 Verdict enum, E.2 _HARNESS_REASONS closed set); add § F (ratification signature).

### Content assertions

- Header line 3 contains `**Status: RATIFIED — v0.2 (2026-08-12).**`.
- Doc contains a top-level `## E. v0.2 additions` section with `### E.1` and `### E.2` subsections.
- § E.1 tables the three `Verdict` values (`PASS`, `FAIL`, `NO_VERDICT`) with wire strings and meanings.
- § E.2 tables the seven `_HARNESS_REASONS` strings (`timed_out`, `container_crashed`, `docker_error`, `harness_error`, `git_error`, `firewall_violation`, `rate_limited`) with constants and typed exceptions.
- Doc contains a top-level `## F. Ratification signature` section naming v0.1 and v0.2 dates and sources.
- v0.1 sections A-D are byte-identical to their state before this sprint's edits.

### Command exit codes

- `test -f process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "Status: RATIFIED" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "### E.1" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "### E.2" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "## F. Ratification signature" process/signals/swebench-solver-vocabulary.md` returns 0.

---

## observation contract

Not applicable — docs sprint, no runtime behavior. Verification is the artifact contract plus the
Architect's read: does § E.1 and § E.2 accurately mirror the code at `assay/oracle.py:36-105` and
`assay/swebench.py:55-85`? Does the additions section's shape match `0.2-rationale.md`? Does the
v0.1 content survive byte-preserved?

---

## done criteria

The vocabulary doc's header reads RATIFIED; § E documents the two ratified additions with source
citations to code and design docs; § F records both ratification signatures; the pre-existing v0.1
sections A–D are unchanged. The Architect confirms the additions match the code and closes in
`## Decisions`; the Agent appends the Built entry to `## Sprint tail`.

---

## notes

- **Reviewer's correction folded.** The paper at
  `docs/review/PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` and the audit at
  `docs/review/AUDIT-2026-08-12-substrate-usage-in-swebench-work.md` both claimed the sub-topology
  had no Sprint 0 vocabulary session (both cited the 2026-08-09 conformance review's Gap 1). Reading
  the sprints directory during this sprint's setup showed
  `process/sprints/sprint-133-swebench-solver-vocabulary.md` exists and closed clean. The Aug-9
  conformance review's Gap 1 language ("no Sprint 0 vocabulary session") was wrong on this specific
  point. The real gap: the vocabulary doc's header was never flipped from PROPOSED, and two later
  ratified additions were never back-propagated. This sprint closes the real gap.
- The additions themselves are already in the code (`assay/oracle.py`, `assay/swebench.py`,
  `assay/swebench_errors.py`, `adapters/rate_limit.py`) — nothing is new. This sprint aligns the
  doc with the code.
- Roughly one hour of work total; a single-file edit sprint.

---

## plan-mode review checklist

- [ ] v0.1 sections A-D byte-preserved (no accreted-detail loss; SEARCH/REPLACE not rewrite).
- [ ] § E.1 Verdict table matches `oracle.py:36-52` enum values exactly.
- [ ] § E.2 _HARNESS_REASONS table matches `swebench.py:62-84` constants exactly.
- [ ] Every reason string in § E.2 has a corresponding typed exception class named.
- [ ] § F ratification dates match the `## Decisions` entries.
- [ ] No new vocabulary tags authored (commitment 3 respected).
- [ ] One concept (vocabulary consolidation), one file — within sweet spot.
