# Sprint 130 — Code review topology (5-LLM ensemble with role-distinct system prompts)

---

```yaml
---
id: 130
status: pending
phase: 2
pass_kind: functional
cadence_band: auto-within-phase
---
```

---

## scope

Build `substrate.topologies.code_review` — an N-LLM code review topology with role-distinct system prompts. Five reviewer Producer kinds (security, performance, style, correctness, clarity) stream critiques in parallel; a judge Producer fires on a fan-in predicate (≥K critiques received) and emits a verdict event; cancel-all-others on adjudication. CI mode uses deterministic canned critiques; walkthrough mode uses local LLMs via the `[openai-compat]` extra. Both modes ship with committed records.

This is the first of the priority topologies and the first user-facing demo of the substrate's concurrent-execution + adjudicator pattern with role differentiation.

---

## prerequisites

- Sprint 100 closed; this topology is on the ratified top-6 list.
- Sprint 110 closed; the TUI design spec exists so this topology's record renders well (the topology should not assume any TUI features that don't exist).
- The runtime ships v1.0 — all eight primitives, conformance gate green.

---

## context_files

- `kernel_spec/v15.md` §What this enables — the "Ensemble generation" and "Code teams" examples (composition of the two).
- `product_spec/draft7.md` §8 R-1 — the existing ensemble reference topology (this builds on R-1's shape with role differentiation).
- `design_spec/draft1.md` §4 — `TopologyBuilder` API patterns; the named-helper conventions for retry-with-failure-context, halt-with-resume, threshold-count.
- `docs/application-catalogue.md` — Sprint 100's catalogue entry for this topology.
- `docs/tui-design-spec.md` — for the rendering-friendly considerations (Producer-kind color assignment, max simultaneous emission streams the TUI handles).
- `src/substrate/topologies/r1_ensemble.py` (or wherever R-1 lives in the existing code) — for the existing ensemble pattern to extend.
- `src/substrate/api.py` — the public surface this topology uses.

---

## signal contract

### Emits

The topology declares these event kinds (Producer-declared, validated at the bus boundary per the kernel's mandatory schema enforcement):

- `CritiquePosted` — emitted by reviewer Producers; payload: `{role: str, severity: int, summary: str, line_refs: tuple[int, ...]}`
- `VerdictRendered` — emitted by the judge Producer; payload: `{decision: Literal["approve", "request-changes", "block"], cited_critiques: tuple[Citation, ...]}`
- `Citation` is a frozen msgspec.Struct: `{seq: int, role: str}`.

Plus the standard substrate.* lifecycle events (TriggerFired, ProducerStarted, ProducerCompleted, TerminationMatched, RunFinalised, etc.) which the runtime emits.

### Consumes

- The input event the user starts the run with: `{code: str, language: str, context: str | None}`.

### Invariants

- Every reviewer Producer kind declares its emittable schema as `[CritiquePosted]` only. Attempting to emit anything else produces `ProducerEmittedInvalidEvent`.
- The judge fires exactly once per run under the `Once` firing policy.
- The verdict cites at least one critique by sequence number (testable from the record).
- Cancel-all-others fires after `VerdictRendered` lands; reviewers that haven't completed are recorded as `ProducerCancelled`.
- CI mode and walkthrough mode produce records of the same shape (same event kinds in the same order modulo timing); only payload content differs.

---

## artifact contract

### Files created

- `src/substrate/topologies/code_review.py` — the topology factory:
  - `code_review_topology(roles: tuple[str, ...] = DEFAULT_ROLES, k_quorum: int = 3, walkthrough: bool = False)` returns a topology function taking a `TopologyBuilder`.
  - Producer factories per role: each closes over a system prompt and (in walkthrough mode) a model adapter; (in CI mode) a canned-response replayer.
  - Judge Producer factory: closes over the adjudication rubric.
  - TerminationPolicy: `cancel-all-others` on `VerdictRendered`; `quiescence-with-watchdog(60s)` as backstop.
- `src/substrate/topologies/code_review/prompts/` — five role-specific system prompts as plain-text files (security.md, performance.md, style.md, correctness.md, clarity.md). Plain text so anyone can edit them.
- `src/substrate/topologies/code_review/records/ci_mode.record/` — committed CI-mode run record (deterministic, byte-identical replay verified in tests).
- `src/substrate/topologies/code_review/records/walkthrough.record/` — committed walkthrough-mode run record (run against a real local model — see `walkthrough.txt` for the model + seed used).
- `src/substrate/topologies/code_review/records/walkthrough.txt` — narration: which model was used (e.g. `qwen2.5:1b-instruct-q4_K_M` via Ollama), the seed, the elapsed time, the human-judgeable quality of the verdict.
- `tests/test_code_review_topology.py` — unit + integration tests:
  - `test_judge_fires_once_at_quorum` (Once policy verified)
  - `test_verdict_cites_critiques` (citation invariant verified)
  - `test_cancel_others_records_cancellation` (cancel-all-others wiring verified)
  - `test_ci_record_replays_level_2` (Level-2 decision reconstruction on the committed CI record; Level-3(b) byte-identity is deferred post-v1.0 per amendment A1.1, so it is NOT a gate here)
  - `test_walkthrough_record_replays_level_2` (Level 2 deterministic decision reconstruction on the walkthrough record)
- `docs/walkthroughs/code-review.md` — user-facing walkthrough: what the topology does, how to run it (both modes), example output, what to look for in the record.

### Files modified

- `src/substrate/topologies/__init__.py` — register `code_review` in the bundled topology registry (Sprint 140 will formalize this; for now, register following the existing pattern in `r1_ensemble`).
- `BLACKBOARD.md` — append Sprint-130 close; surface any vocabulary additions for ratification (e.g. if `CritiquePosted.role` becomes a typed enum at the vocabulary layer).

### Content assertions

- `code_review_topology` returns a topology factory that registers exactly: 5 Producer kinds (one per role) + 1 judge Producer kind + 1 Trigger (the fan-in firing the judge) + 1 TerminationPolicy.
- The CI-mode record contains exactly 5 reviewer Producers started, ≥ k_quorum CritiquePosted events, exactly 1 VerdictRendered, ≥ 0 ProducerCancelled events for non-quorum reviewers, exactly 1 RunFinalised.
- The walkthrough-mode record validates the same shape but with real LLM-emitted payloads.

### Command exit codes

- `uv run pytest tests/test_code_review_topology.py` returns 0.
- `uv run substrate replay src/substrate/topologies/code_review/records/ci_mode.record --level 2` returns 0 and reports every decision reconstructed.
- `uv run substrate replay src/substrate/topologies/code_review/records/walkthrough.record --level 2` returns 0 and reports every decision reconstructed.

---

## done criteria

- All files in the artifact contract exist and pass their assertions.
- Conformance suite still passes (this topology doesn't break any existing check).
- Walkthrough mode actually executed against a real local LLM (Ollama or equivalent) — the walkthrough record is committed evidence, not skipped.
- `substrate tail` on either record renders without errors (the shipped CLI; the TUI hasn't shipped yet but the bundled CLI tail must work).
- Rubber Duck Pass clean: no silent no-ops; the cancel-all-others actually fires in the CI record (reviewer #9's finding pattern from Phase 1 — verified by reading the record back, not by trusting the test name).
