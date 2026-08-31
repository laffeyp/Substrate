# Sprint 133 — swebench_solver Vocabulary Session

---

```yaml
---
id: 133
status: closed
phase: 0
pass_kind: architecture
cadence_band: plan-mode-per-sprint
---
```

---

## scope

The founding act for the `swebench_solver` topology (the vanilla non-agentic SWE-bench solver,
`docs/swebench/swebench-solver-design.md`). Lock the topology's records — their names + payload fields — BEFORE
any topology code (#1), run the #25 dual-contract audit (every behavior record paired with a
record-observable), make the review-#57 shared-contract reconciliation decision (reuse coding_flow's
`Draft/Candidate/Verdict/Solved/Exhausted` as the canonical 3-consumer best-of-N+correction contract), and
register the records + the shared sub-topology owner in `process/WORKING_AGREEMENT.md` (#22). No topology
logic this sprint. The skeleton (sprint 134) builds against the locked vocabulary.

This is review gate #1 (the vocabulary-session lock) under the key-moments-only cadence.

---

## context_files

- `docs/swebench/swebench-solver-design.md` (the reviewed design, §1-§8)
- `src/substrate/topologies/coding_flow/__init__.py` (the shared records to reconcile against)
- `process/sprints/sprint-000-vocabulary-session.md` (the vocabulary-session form)
- `process/WORKING_AGREEMENT.md` (canonical home registry; record-as-view-side override; strict posture)
- `sdd-kit-2/TECHNIQUES.md` (#1, #6, #22, #24, #25, #38)

---

## signal contract

### Emits

None at runtime — content/architecture sprint. The locked records are the deliverable, not emissions.

### Consumes

- The design doc + coding_flow's records, read directly.

### Invariants

- Every record's fields are minimal-but-complete (#6) — exactly enough to reconstruct the decision.
- No shared record re-authored: the best-of-N+correction contract REUSES coding_flow's records (#57/#12).
- Every behavior record has a record-observable in the dual-contract audit (#25), never a stochastic claim.
- The SELECT regression set is repo-derived, NOT the `PASS_TO_PASS` grade field (firewall, design §4).

---

## artifact contract

### Files created

- `process/signals/swebench-solver-vocabulary.md` — the locked records + #25 audit + reconciliation. (done)

### Files modified

- `process/WORKING_AGREEMENT.md` — canonical-home-registry rows for the shared sub-topology contract + the
  swebench_solver records.
- `process/KIT_DIARY.md` — the sprint-133 close entry.

### Content assertions

- `swebench-solver-vocabulary.md` defines, with locked fields: the 6 shared records (Draft, Candidate,
  Verdict, Solved, Exhausted, ModelUsage) + the swebench-specific records (SuspectFiles, SuspectElements,
  EditLocations, AppliedPatch, TestResults, SelectedPatch).
- It contains a "#25 dual-contract audit" table pairing EVERY behavior record with a record-observable.
- It states the shared-contract reconciliation decision (reuse-as-canonical) and that the terminal policy
  is a sprint-4 topology parameter, not a record change.
- `WORKING_AGREEMENT.md` canonical home registry contains rows for the shared sub-topology contract and the
  swebench_solver records.

### Command exit codes

- `test -f process/signals/swebench-solver-vocabulary.md` returns 0.
- `grep -q "swebench_solver" process/WORKING_AGREEMENT.md` returns 0.

---

## observation contract

Not applicable — content/architecture sprint, no runtime behavior. Verification is the artifact contract +
the reviewer's read (gate #1): are the records minimal-complete and audited, or merely named (review #56's
nominal-vs-real test). The observation contracts for the BEHAVIOR sprints (134+) are pre-specified in the
vocabulary doc's audit table (assert on record + deterministic seams, never stochastic quality).

---

## done criteria

The records are locked with payload fields, the #25 audit pairs every behavior record with a
record-observable, the shared-contract reconciliation is decided and registered in WORKING_AGREEMENT, and
the reviewer (gate #1) confirms the contract — including the shared 3-consumer set — is minimal-complete,
not nominal. Sprint 134 (the topology skeleton) may then dispatch.

---

## plan-mode review checklist

- [ ] Records minimal-but-complete (#6); no field that doesn't reconstruct a decision.
- [ ] Shared best-of-N+correction contract reused, not re-authored (#57/#12); locked in WORKING_AGREEMENT.
- [ ] Every behavior record has a record-observable (#25); none asserts on stochastic quality (#56).
- [ ] Firewall preserved in the vocabulary (regression repo-derived, not PASS_TO_PASS; TestResults
      replayable=False).
- [ ] One concept (the founding grammar), no implementation — within the sweet spot (#12).
