# Sprint 163 — Vocabulary v0.3: boundary event tags

---

```yaml
---
id: 163
status: pending
phase: 0
pass_kind: architecture
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Add § G to `process/signals/swebench-solver-vocabulary.md` naming the six
event families the boundary producers (roadmap v2 S5.2–S5.6 + S6) will emit
onto the record: `RateLimit*` (four tags), `Container*` (four tags),
`Image*` (three tags), `RepoClone*` (four tags), `Harness*` (five tags), and
the topology-level `GradeResult` (one tag). Each subsection carries payload
shapes, strata, invariants, and rationale. Update § F to record v0.3 as
PROPOSED pending Architect ratification. No producer code authored; this
sprint is the Layer-1 / Layer-2 vocabulary work that gates every S5.x
producer sprint per `grammar/PRINCIPLES.md` commitment 3 (workers cannot
invent vocabulary).

This is Sprint 0.75 of the SWE-bench rebuild chain per roadmap v2
(`docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md`).

---

## prerequisites

- Sprint 161 close (vocabulary v0.2 consolidation, `## Surfaced for review` 2026-08-12).
- Sprint 162 close (boundary bridge mapping in `WORKING_AGREEMENT.md`, `## Surfaced for review` 2026-08-12).
- Roadmap v2 ratified verbally 2026-08-12.

---

## context_files

- `sdd-kit-2/grammar/PRINCIPLES.md` (Layer 1 lexical + Layer 2 payload discipline; commitment 3).
- `sdd-kit-2/grammar/BOOTSTRAP.md` § "Step 2 — Layer 1" and § "Step 3 — Layer 2" (the halt conditions for each layer).
- `process/signals/swebench-solver-vocabulary.md` (the file modified; § E is the shape reference for the addition).
- `process/signals/0.2-rationale.md` (kernel-vocab rationale shape for the additions section).
- `process/WORKING_AGREEMENT.md` § "SWE-bench external substrates" (Sprint 162 output; names the boundaries the events map to).
- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` § "Sprint 0.75" and § "Sprint 5.1 through 5.6" and § "Sprint 6".
- `src/substrate/assay/swebench.py:55-85` (the `_HARNESS_REASONS` closed set the reason strings draw from).
- `src/substrate/adapters/rate_limit.py` (the shim the RateLimitProducer supersedes; slot-holding bug the 2026-08-12 halt named).
- `src/substrate/topologies/swebench_solver/records.py` (the msgspec.Struct shape every payload type follows).

---

## signal contract

### Emits

None at runtime — docs sprint. The section IS the contract every producer sprint reads before authoring its Struct.

### Consumes

Files listed in `context_files`.

### Invariants

- Existing § A–F of the vocabulary doc byte-preserved via SEARCH/REPLACE.
- Every reason string used in a payload example exists verbatim in `_HARNESS_REASONS` at `swebench.py:62-84`.
- Every event tag follows PascalCase per grammar convention.
- Every payload field name follows snake_case per grammar convention.
- No new reason strings authored; the closed set is § E.2 from v0.2.
- v0.3 status is PROPOSED, not RATIFIED — awaits Architect sign-off in `## Decisions` before flipping.

---

## artifact contract

### Files modified

- `process/signals/swebench-solver-vocabulary.md` — insert a new § G (v0.3 additions) between the existing end-of-§ D and § F. Update § F to add a v0.3 line marking the additions as PROPOSED with the promotion condition.

### Content assertions

- Doc contains a top-level `## G. v0.3 additions — boundary event tags` section.
- § G has six subsections: `### G.1 RateLimitProducer events`, `### G.2 ContainerProducer events`, `### G.3 ImageProducer events`, `### G.4 RepoCloneProducer events`, `### G.5 HarnessProducer events`, `### G.6 Grade projection event`.
- § G.1 tables four tags: `RateLimitAttempted`, `RateLimitGranted`, `RateLimitDenied`, `RateLimitRetried`.
- § G.2 tables four tags: `ContainerRequested`, `ContainerStarted`, `ContainerExited`, `ContainerKilled`.
- § G.3 tables three tags: `ImageRequested`, `ImagePulled`, `ImageMissing`.
- § G.4 tables four tags: `RepoCloneRequested`, `RepoCloneCached`, `RepoCloned`, `RepoCloneFailed`.
- § G.5 tables five tags: `HarnessCallFired`, `HarnessReportRead`, `HarnessCompleted`, `HarnessTimeout`, `HarnessError`.
- § G.6 tables one tag: `GradeResult`.
- Each subsection has an "Invariants" paragraph naming the ordering rules over its tags.
- § F gains a v0.3 line: `- **v0.3** — PROPOSED 2026-08-12 by Sprint 163 (roadmap v2 S0.75). ...`.
- v0.1 sections A–D and § E (v0.2 additions) are byte-identical to their pre-sprint state.

### Command exit codes

- `grep -q "^## G. v0.3 additions" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -c "^### G\." process/signals/swebench-solver-vocabulary.md` returns 6.
- `grep -q "RateLimitAttempted" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "ContainerRequested" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "HarnessCallFired" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "GradeResult" process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "PROPOSED 2026-08-12 by Sprint 163" process/signals/swebench-solver-vocabulary.md` returns 0.

---

## observation contract

Not applicable — docs sprint, no runtime behavior. Verification is the artifact
contract plus the Architect's read against grammar/PRINCIPLES.md and the
producer sprints' scoped work: do the tag names follow PascalCase? Do the payload
fields snake_case? Do the invariants over each event family cover the
success + failure + retry paths? Do the reason strings match the `_HARNESS_REASONS`
closed set exactly?

---

## done criteria

§ G exists with six subsections covering 21 new event tags across five
producers plus the topology-level `GradeResult`; each subsection carries
payload shapes, strata, invariants, and rationale; § F records v0.3 as
PROPOSED; § A–E survive byte-preserved. Architect ratifies in `## Decisions`;
the doc's status header flips from `RATIFIED — v0.2` to `RATIFIED — v0.3`;
Agent appends Built entry; Sprint 163 closes. Producer sprints S5.2–S5.6
may then dispatch.

---

## notes

- All 21 event tags are additive to the sub-topology vocabulary; no existing
  tag renamed, moved, or deprecated. Every payload field is a primitive or
  a foreign-key reference to a value in a v0.2 closed set (`_HARNESS_REASONS`,
  `Verdict`).
- The topology-level `GradeResult` is the pivot event enabling S6's move to
  `LogProjectionOracle`. Its payload deliberately mirrors the shape a
  `Result` reads at the oracle — `verdict` + `reason` map straight through.
- Producer sprints (S5.2–S5.6) each declare their producer's `Budget` per S1;
  the tag families' payloads carry no budget-specific fields because
  `substrate.BudgetExceeded` is a kernel-level event, not a producer-level one.
- Roughly half a day of work; single-file docs edit sprint that gates the
  producer chain.

---

## plan-mode review checklist

- [ ] § A–F pre-sprint content byte-preserved (SEARCH/REPLACE, not rewrite).
- [ ] Six subsections G.1–G.6 present with the exact tag counts specified.
- [ ] Every reason string referenced in payloads matches `_HARNESS_REASONS` at `swebench.py:62-84`.
- [ ] Every tag follows PascalCase; every payload field follows snake_case.
- [ ] Each subsection's invariants cover the success path, the failure path, and (where applicable) the retry path.
- [ ] § F gains a v0.3 PROPOSED line with the ratification promotion condition.
- [ ] One concept (v0.3 boundary event vocabulary), one file — within sweet spot.
