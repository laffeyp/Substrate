# Sprint 165 — Vocabulary v0.3 typed-verdict amendment (fold external review F5)

---

```yaml
---
id: 165
status: closed
phase: 0
pass_kind: docs
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Amend the PROPOSED v0.3 additions in `process/signals/swebench-solver-vocabulary.md § G` to close external-review finding F5 (at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`). Replace the bare `verdict: str` and `reason: str` payload declarations in § G.5 (`HarnessCompleted`) and § G.6 (`GradeResult`) with typed forms — `Verdict` (the § E.1 enum) and `Reason` (a `str` restricted to the § E.2 `_HARNESS_REASONS` closed set). Add a "Type conventions in § G" note explaining both symbols. Rewrite the invariants of § G.5 and § G.6 to reference enum members and `REASON_*` constants instead of quoted wire strings. Update § F's v0.3 line to record the amendment. Sprint 163's PROPOSED status carries through; v0.3 remains awaiting Architect ratification, with the amended shape.

Amendment landed before ratification per the "no-in-place-edits" nuance for PROPOSED artifacts: a proposal may be edited in place while pending; only ratified content requires a round-N version. This matches the pattern `signals/0.2-rationale.md` uses for kernel-vocab proposals.

---

## prerequisites

- Sprint 163 (vocab v0.3 § G authored, PROPOSED).
- External review at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F5.

---

## context_files

- `process/signals/swebench-solver-vocabulary.md` (file modified; § E.1 for Verdict, § E.2 for the closed-set, § G for the payload declarations).
- `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md` finding F5 (source of the amendment).
- `src/substrate/assay/oracle.py:36-52` (Verdict enum definition).
- `src/substrate/assay/swebench.py:55-85` (_HARNESS_REASONS closed set + REASON_* constants).
- `src/substrate/topologies/swebench_solver/records.py::Reproduction` (precedent for enum-typed payload field).

---

## signal contract

### Emits

None at runtime — docs sprint.

### Consumes

Files listed in `context_files`.

### Invariants

- v0.1 § A–D and v0.2 § E byte-preserved (SEARCH/REPLACE, not rewrite).
- v0.3 § G structural additions (six subsections, 21 tags) byte-preserved except at the four amended lines and the two rewritten invariant paragraphs.
- The Verdict symbol names the enum in § E.1 with values matching `oracle.py:36-52`.
- The Reason symbol names the closed-set `str` matching `swebench.py:_HARNESS_REASONS`.
- No new tag added; no tag renamed.

---

## artifact contract

### Files modified

- `process/signals/swebench-solver-vocabulary.md` — four edits:
  1. § G opening gains a "Type conventions in § G" paragraph defining `Verdict` and `Reason`.
  2. § G.5 `HarnessCompleted` payload changed from `verdict: str, reason: str` to `verdict: Verdict, reason: Reason`.
  3. § G.5 invariants rewritten to reference `Verdict.PASS`, `Verdict.FAIL`, `Verdict.NO_VERDICT` and `REASON_TIMED_OUT`, `REASON_HARNESS_ERROR`, `REASON_CONTAINER_CRASHED`.
  4. § G.6 `GradeResult` payload changed to `verdict: Verdict, reason: Reason`; invariants rewritten in parallel.
  5. § F v0.3 line gains an "Amended 2026-08-12 by Sprint 165" clause naming the fold.

### Content assertions

- `grep -q "Type conventions in § G" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "verdict: Verdict, reason: Reason" process/signals/swebench-solver-vocabulary.md` returns 0 (matches both HarnessCompleted and GradeResult rows).
- `grep -q "verdict: str" process/signals/swebench-solver-vocabulary.md` returns non-zero (no bare `verdict: str` remains in the doc).
- § G.5 invariants reference `Verdict.PASS`, `Verdict.FAIL`, `Verdict.NO_VERDICT`; § G.6 invariants do the same.
- § F v0.3 line contains "Amended 2026-08-12 by Sprint 165".

### Command exit codes

- `grep -c "Type conventions in § G" process/signals/swebench-solver-vocabulary.md` returns 1.
- `grep -c "verdict: Verdict, reason: Reason" process/signals/swebench-solver-vocabulary.md` returns 2.
- `grep "verdict: str" process/signals/swebench-solver-vocabulary.md | wc -l` returns 0.

---

## observation contract

Not applicable — docs sprint. Verification is the Architect's read: do the `Verdict` payload declarations match `oracle.py:36-52`? Does `Reason` correctly reference `_HARNESS_REASONS`? Do the invariants read cleanly against the enum + closed set?

---

## done criteria

§ G's `HarnessCompleted` and `GradeResult` payloads reference the `Verdict` enum and the `Reason` closed-set symbol; the invariants use enum members and `REASON_*` constants; a "Type conventions" note at § G opening defines both symbols; § F records the amendment. Architect ratifies v0.3 (now including the F5 amendment) in `## Decisions`; header flips to `RATIFIED — v0.3`; producer sprints S5.2–S5.6 dispatch against the amended contract.

---

## notes

- **F5 finding.** The review at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md:78-86` names the issue: "Vocabulary v0.3 § G re-encodes the Verdict enum to str at the emit boundary." The reviewer identifies the same drift shape H-1 was written to prevent (two representations of one fact). The fix is a type-level enforcement at the payload boundary — msgspec supports enum-typed fields (precedent: `topologies/swebench_solver/records.py::TestResults.reproduction: Reproduction`).
- **Why not a `Reason` enum.** `Result.reason` at `oracle.py:93` is a bare `str` per H-3 ratification; converting to an enum would require a Result migration outside this sprint's scope. The `Reason` symbol names the closed-set discipline at the doc layer; enforcement at emit uses `assert reason in _HARNESS_REASONS or reason == ""`. Sprint 172 (a later cleanup) can consider promoting `Reason` to a proper enum if the drift pattern recurs.
- **In-place edit of a PROPOSED artifact.** v0.3 was PROPOSED at Sprint 163; Sprint 165 amends before ratification. The pattern matches `signals/0.2-rationale.md`'s handling of the kernel-vocab proposals — proposals are workable until ratified.
- Roughly 20 minutes; single-file docs edit sprint.

---

## plan-mode review checklist

- [x] § A–D and § E byte-preserved.
- [x] § G.5 and § G.6 payloads use typed forms.
- [x] Invariants reference enum members and REASON_* constants, not quoted wire strings.
- [x] Type conventions note defines both `Verdict` and `Reason`.
- [x] § F v0.3 line records the Sprint 165 amendment.
- [x] One concept (typed-verdict amendment), one file — within sweet spot.
