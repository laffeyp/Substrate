# Sprint 162 — SWE-bench boundary-as-producer bridge mapping

---

```yaml
---
id: 162
status: pending
phase: 0
pass_kind: bridge
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Add a "SWE-bench external substrates (boundary-as-producer mapping)" section to
`process/WORKING_AGREEMENT.md` naming the six external non-deterministic
substrates that sit under the SWE-bench assay (B1–B6): LLM via provider,
provider rate limits, Docker daemon, Docker image registry, GitHub for repo
clones, swebench harness subprocess. Each row names the non-determinism, the
current defense, the scheduled producer sprint (S5.1–S5.6), and the reason
string from `_HARNESS_REASONS` that fires on failure. Also lands three
producer-authorship rules and three cross-cutting invariants that gate every
subsequent boundary-producer sprint.

This is Sprint 0.5 of the SWE-bench rebuild chain per roadmap v2
(`docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md`). No new
producers authored; the section is the contract every producer sprint reads
before dispatching.

---

## prerequisites

- Sprint 161 close (vocabulary v0.2 consolidation, `## Surfaced for review` 2026-08-12).
- 2026-08-12 halt at `## Surfaced for review` (design pass ratified by
  Architect verbally per the "yes! sounds good" ruling on roadmap v2).

---

## context_files

- `sdd-kit-2/AGENTS.md` § "External SDK bridge mappings" + halt condition `bridge_mapping_required`.
- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` § "Sprint 0.5" and § "Sprint 5.1 through 5.6".
- `process/WORKING_AGREEMENT.md` (the file modified; existing bridge-mapping section is the shape reference).
- `process/signals/swebench-solver-vocabulary.md` § E.2 (`_HARNESS_REASONS` closed set, source of truth for reason strings).
- `src/substrate/assay/swebench.py:55-85` (the `_HARNESS_REASONS` frozenset + REASON_* constants).
- `src/substrate/adapters/rate_limit.py` (current B2 defense; slot-holding bug the 2026-08-12 halt named).
- `src/substrate/assay/swebench.py:397` (current `run_swebench_one`, B3+B6 defense).
- `src/substrate/assay/swebench_suite.py:_mother_clone` (current B5 defense).

---

## signal contract

### Emits

None at runtime — docs sprint. The section IS the contract every producer sprint reads.

### Consumes

Files listed in `context_files`.

### Invariants

- Existing sections of `WORKING_AGREEMENT.md` byte-preserved via SEARCH/REPLACE (no rewriting).
- Every reason string in the boundary table exists verbatim in `_HARNESS_REASONS` at `swebench.py:62-84`.
- Every scheduled producer sprint number matches roadmap v2's numbering (S5.1–S5.6).

---

## artifact contract

### Files modified

- `process/WORKING_AGREEMENT.md` — insert a new section titled `## SWE-bench external substrates (boundary-as-producer mapping)` between the existing `## External SDK bridge mappings` section (ends ~line 106) and the `## Vocabulary discipline overrides` section (starts ~line 108).

### Content assertions

- The new section header reads exactly `## SWE-bench external substrates (boundary-as-producer mapping)`.
- The boundary table contains six rows, labeled B1 through B6, each with columns: Boundary, Non-determinism, Current defense, Producer (roadmap v2), Reason string.
- The B2 row names `RateLimitProducer` and the four events `RateLimitAttempted / Granted / Denied / Retried`.
- The B3 row names `ContainerProducer` and the four events `ContainerRequested / Started / Exited / Killed`.
- The B6 row names `HarnessProducer` and the events `HarnessCallFired / Completed / Timeout / Error`.
- Every reason string in the table appears in `_HARNESS_REASONS` at `src/substrate/assay/swebench.py:62-84`.
- A `### Producer-authorship rules` subsection follows the table with four bullets.
- A `### Cross-cutting invariants` subsection follows with four bullets.
- Pre-existing sections (SDK bridge mappings, Vocabulary discipline overrides, and everything above/below) are byte-identical to their pre-sprint state.

### Command exit codes

- `grep -q "## SWE-bench external substrates" process/WORKING_AGREEMENT.md` returns 0.
- `grep -q "RateLimitProducer" process/WORKING_AGREEMENT.md` returns 0.
- `grep -q "ContainerProducer" process/WORKING_AGREEMENT.md` returns 0.
- `grep -q "HarnessProducer" process/WORKING_AGREEMENT.md` returns 0.
- `grep -c "^| B[1-6]" process/WORKING_AGREEMENT.md` returns 6.

---

## observation contract

Not applicable — docs sprint, no runtime behavior. Verification is the artifact
contract plus the Architect's read: does each boundary row accurately name the
current defense's location? Do the producer names match roadmap v2? Do the reason
strings match the `_HARNESS_REASONS` closed set exactly?

---

## done criteria

The `WORKING_AGREEMENT.md` section exists with six boundary rows, four
authorship rules, and four cross-cutting invariants; the pre-existing sections
survive byte-preserved; every reason string in the table exists in
`_HARNESS_REASONS`; every producer name matches roadmap v2. Architect confirms;
Agent appends the Built entry; Sprint 162 closes.

---

## notes

- The section deliberately spans the entire boundary surface even for boundaries
  whose producer is scheduled far out (S5.5 RepoCloneProducer wraps an
  already-shipped mother-clone cache, so the "producer" is largely a wrapper).
  Naming every boundary in one table makes the surface legible; scheduling
  producers as a series makes the work bounded.
- The three-rule + three-invariant coda gates every S5.x sprint. A producer that
  fails an invariant halts with `dual_contract_fail` at its own sprint close.
- Roughly one hour of work total; single-file edit sprint.

---

## plan-mode review checklist

- [ ] Pre-existing sections byte-preserved (SEARCH/REPLACE not rewrite).
- [ ] Boundary table has six rows (B1–B6).
- [ ] Every reason string in the table exists in `_HARNESS_REASONS` at `swebench.py:62-84`.
- [ ] Every producer name matches roadmap v2's naming (RateLimitProducer, ContainerProducer, ImageProducer, RepoCloneProducer, HarnessProducer).
- [ ] Producer-authorship rules include the `Budget` requirement (dependency on S1).
- [ ] Cross-cutting invariants ban `except BaseException` and mandate `bridge_mapping_required` halt on any boundary interaction outside its producer.
- [ ] One concept (the boundary contract), one file — within sweet spot.
