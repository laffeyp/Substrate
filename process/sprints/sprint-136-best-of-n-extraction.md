# Sprint 136 — best-of-N + correction loop extraction (Wave-0)

---

```yaml
---
id: 136
status: closed
phase: 1
pass_kind: architecture
cadence_band: auto-within-phase
---
```

---

## scope

Extract coding_flow's best-of-N + correction loop into a reusable shared sub-topology
`topologies/best_of_n` (Wave-0 #15) so the swebench Repairer and code_evolution nest ONE loop, not a
third re-roll (review #57 / KIT_DIARY 12). The shared records (Draft/Candidate/Verdict/Solved/Exhausted)
are already reused (sprint 134); this extracts the WIRING — the seeder/drafter/validator/judge graph +
triggers + termination — into `best_of_n_correction(b, ...)`, parameterized by the caller's draft +
validate factories (the work), an optional judge (terminal policy), validator extra-schemas, and
termination. coding_flow is UNTOUCHED — its migration onto this module is a later behavior-preserving
refactor (#43); at most two copies of the wiring exist (coding_flow's original + this canonical), never
three.

---

## artifact contract

### Files created

- `src/substrate/topologies/best_of_n/__init__.py` — `best_of_n_correction` + `seeder_factory` +
  `select_first_judge_factory`.
- `tests/test_best_of_n.py` — the observation contract.

### Files modified

- `process/WORKING_AGREEMENT.md` — registry row for the shared loop builder (canonical home).

### Content assertions

- `best_of_n_correction(b, *, n, max_rounds, draft_factory, validate_factory, ...)` wires the shared loop;
  the records are reused from coding_flow (not re-authored).
- The validator's extra schemas are caller-overridable (swebench's `AppliedPatch` emission path).

---

## observation contract

Deterministic stand-in factories over the real Runtime; the record is the observable (#24/#38):
- `test_selects_the_passing_candidate` — 3 verdicts on the record, exactly one passes, judge -> Solved(slot).
- `test_correction_then_pass` — round 1 all fail -> failures fed back -> round 2 passes -> Solved(round=2);
  6 verdicts on the record.
- `test_exhausted_when_all_fail` — max_rounds=1, all fail -> Exhausted.
- `test_validator_extra_schema_reaches_the_record` — validator emits Verdict + an extra record (the
  swebench AppliedPatch path) -> the extra lands on the log.
- Regression: `test_coding_flow.py` stays green (coding_flow untouched).

---

## done criteria

The shared builder is extracted and verified (4 tests), coding_flow is untouched and still green (8 tests),
the builder is registered in WORKING_AGREEMENT. ruff + mypy --strict clean. The swebench Repairer (next)
nests it. No review gate (cadence: gate #3 is the first end-to-end gold-instance solve).
