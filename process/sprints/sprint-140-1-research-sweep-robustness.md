# Sprint 140.1 — research_sweep: a failed reader must not stall the sweep

---

```yaml
---
id: 140.1
status: closed
phase: 2
pass_kind: functional
cadence_band: auto-within-phase
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

## context_files

- `src/substrate/topologies/applications/research_sweep.py` (the topology being hardened — the three
  model-call producers reader/critic/synthesizer + the fan-in trigger `len(findings) >= n`)
- `tests/test_research_sweep.py` (the observation contract this extends)
- `process/KIT_DIARY.md` finding 16 (death-resilience is a CLASS — audit model-call producers as a SET)

## signal contract

No new event kind. The existing `Finding` is now emitted EXACTLY ONCE per `ReadRequest` — its
`note` carries `(read failed: <Type>)` on a raising reader or `(no contribution)` on an empty reply,
so the fan-in count reaches `n` unconditionally. Invariant: the sweep always reaches `Synthesis`
(never the `all_completed` silent-no-answer terminal), for any reader behaviour.

## observation contract

`pass_kind: functional`. Behavior: a reader that fails on every document still drives the sweep to a
synthesis. `tests/test_research_sweep.py::test_a_failed_reader_still_synthesizes_not_a_silent_no_answer`
— a `_FailingReader` (raises on every call) over 3 documents ⇒ 3 `Finding` (each `note` contains
"read failed") ⇒ 1 `Gaps` ⇒ 1 `Synthesis` ⇒ `status="finalised"`. Proven RED without the fix
(reverting `research_sweep.py:_reader_factory` turns it red at the assertion), GREEN with it.

## artifact contract

- `src/substrate/topologies/applications/research_sweep.py` — `_reader_factory` wrapped; one Finding per request.
- `tests/test_research_sweep.py` — `test_a_failed_reader_still_synthesizes_not_a_silent_no_answer` (above).

## done criteria

A reader that fails still lets the sweep reach a synthesis; the failure is on the record, not swallowed;
full suite green.
