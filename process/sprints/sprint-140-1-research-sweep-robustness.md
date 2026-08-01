# Sprint 140.1 — research_sweep: a failed reader must not stall the sweep

---

```yaml
---
id: 140.1
status: closed
phase: 2
pass_kind: functional
cadence_band: hardening
---
```

---

## why

Pressure-testing W1 (after sprint 140) found a silent-failure hole, proved by running it: the fan-in
trigger fires the critic only when `len(findings) >= n` (n = document count). If ONE reader yields no
Finding — an empty read, an error, a model refusal, all routine for real models — the count never
reaches n, the critic never fires, no synthesis is produced, and the run STILL reports
`status="finalised"` via `all_completed`. A caller sees "finalised" and gets no answer. The happy-path
integration test never exercised it (DeterministicResponders always yield).

## the fix

`_reader_factory` now yields exactly one Finding per ReadRequest even on reader failure: the model call
is wrapped, an exception becomes a recorded `(read failed: <Type>)` note, an empty reply becomes
`(no contribution)`. The fan-in count always reaches n, so a dead reader is a recorded gap the
completeness critic then names — not a run that finalises with no answer. This is the substrate-correct
shape: every ReadRequest deterministically produces exactly one Finding.

## artifact contract

- `src/substrate/topologies/workflows/research_sweep.py` — `_reader_factory` wrapped; one Finding per request.
- `tests/test_research_sweep.py` — `test_a_failed_reader_still_synthesizes_not_a_silent_no_answer`: a
  reader that raises on every document still yields 3 Findings (failures recorded on the note) and a
  Synthesis. Proven red without the fix, green with it.

## done criteria

A reader that fails still lets the sweep reach a synthesis; the failure is on the record, not swallowed;
full suite green.
