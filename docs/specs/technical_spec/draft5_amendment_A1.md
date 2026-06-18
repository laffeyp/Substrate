# Technical Spec DRAFT 5 — Amendment A1 (additive)

**Status:** ADDITIVE AMENDMENT to `docs/specs/technical_spec/draft5.md`. DRAFT 5 is preserved unchanged. Companion to `docs/specs/product_spec/draft7_amendment_A1_replay_3b.md` (the normative product ruling). Cut 2026-06-13 under Architect Ruling 2 (+ Ruling 3 flow-back). Where this conflicts with DRAFT 5 prose, this amendment governs for the v1.0-milestone build.

---

## A1.a — §12 Replay: Level 3(b) deferred (refines §12)

§12 specifies Level 3(b) as "re-run the kernel with every Producer replaced by a log-backed deterministic emitter replaying recorded emissions in recorded order ... the output is byte-identical to the input." For the v1.0 milestone, **Level 3(b) is deferred** (see product amendment A1.1). Implementation notes carried forward for the later wave that builds it:

- **Byte-identity includes the envelope `t`.** A re-executor must replay the recorded `t` (a **replay-mode writer** / t-replay), not re-sample `time.time()`, or the on-disk `B_disk` frames will not be byte-identical. This is the single missing mechanism; admission order is already seq order (the record is the schedule), and Levels 1/2/3a are unaffected.
- Until then, `replay(record, level="3b")` raises `NotImplementedError` with the reason; `assert_replayable(..., "3b")` likewise. Levels 1, 2, 3(a) are complete.

## A1.b — §14 D-8: enumerate the supplementary-metadata exclusion set (refines §14 + the D-8 row)

§14's `first_divergence` "build the comparison sequence `(kind, decision_identity, payload_sha256)` ... supplementary metadata (`t`, host, config echoes) never enters comparison" — the **`decision_identity`** term is what distinguishes the compared payload from its supplementary fields. This amendment enumerates the supplementary set excluded on `substrate.*` lifecycle frames (full list + rationale in product amendment A1.2):

- Excluded: `run_id`, `instance`, `producer.{instance,parent}`, `measured_us` (PredicateQuarantined budget path), `error` (normalized to a sentinel), and `t` (already in DRAFT 5).
- Kept as decision identity: `input_sha256`, `firing_key`, `reason`, `trigger_id`/`route_id`, `policy`/`decision`, `k`, `view`/`seq`, `producer.kind`.
- **Application (non-`substrate.*`) payloads are compared verbatim** — never normalized.

The D-8 decisions-table row (DRAFT 5 line ~117) and the §14 `first_divergence` bullet should reference this enumeration rather than "and other supplementary metadata."

## A1.c — §16 `view_at` signature: instance form (Ruling 3 flow-back)

§16 lists `view_at(record: RunRecord, seq: int, view: str) -> Any` (by view name). The shipped signature is `view_at(record, seq, view: View)` — a **View instance**, because a record stores event payloads, not View code, so the caller must supply the View whose `update()`/`subscription` define the fold. The `view: str` form would additionally require a live topology registry to resolve the name to code. §16 should show the instance-form signature (or document the name form's registry dependency). No behavior change; documentation flow-back only.

---

*Amendment A1 to technical DRAFT 5. Additive; DRAFT 5 preserved. §12 (3b deferral), §14 (D-8 exclusion-set enumeration), §16 (view_at signature). 2026-06-13.*
