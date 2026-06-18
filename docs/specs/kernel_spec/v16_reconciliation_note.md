# Kernel v16 — reconciliation note (flagged from the Sprint-0 Vocabulary Session)

**Status:** reconciliation input for a future kernel **v16**. Additive — does **not** modify `v15.md` (preserved as the current canonical kernel per the corpus's no-overwrite discipline). Cut a `v16.md` when these are folded in; until then v15 + this note are read together.

**Origin.** The Substrate Vocabulary Session (`substrate/signals/0.1.json`, locked 2026-06-12) surfaced that several v15 lifecycle events, as specified, do **not** carry the payload fields their own conformance checks (product spec DRAFT 7 §7) and reference topologies (§8) require. Per product principle 1 ("disagreement between spec and implementation is resolved *in the spec first*"), these were ratified into vocabulary v0.1 *and* flagged here so the kernel spec catches up rather than the vocabulary silently leading it. Each item cites the v15 location and the requirement that forces it.

---

## R-1 — Subject-Producer identity on the Producer lifecycle events  *(load-bearing; ratified as `P-SUBJECT-ID`)*

**Gap.** `substrate.ProducerStarted`, `ProducerCompleted`, `ProducerFailed`, `ProducerCancelled` are runtime-emitted, so the envelope `producer` field is `null` (technical §3.4 line 284), and the v15 lifecycle table (lines 481–485) assigns them no payload identifying the **subject** Producer. `F-PROD-4` types `ProducerId` `{kind, instance_id, parent_id, metadata}` but never states it rides the lifecycle-event payload.

**Why it's load-bearing.**
- **Check 11 (provenance closure)** — "every Producer traces to TriggerFired / resume / RunStarted; no dangling ProducerIds" — cannot be evaluated if a lifecycle frame doesn't identify which Producer instance it concerns. (Closure is *also* reachable via `TriggerFired` + the non-null `producer` on the Producer's own application events, but the lifecycle frames should be self-sufficient.)
- **R-1 (ensemble + adjudicator)** — the cohort-frontier predicate `count(Completed+Failed+Cancelled for kind K) == count(Started for K)` keys on `kind`; `cancel-all-others` must name *which* Producers were cancelled.
- **Check 1 (retry enrichment)** — scoping the retry to the failed unit of work needs the failed Producer's identity on `ProducerFailed`.

**v16 should specify.** Each of these four kinds carries `producer: ProducerRef {kind, instance, parent}` (the subject Producer), distinct from the envelope `producer` field (which stays `null` for runtime-emitted events). Equivalently: state that the envelope `producer` field *is* populated for these subject-bearing lifecycle kinds. Pick one and say so explicitly.

## R-2 — `InjectionApplied` payload fields  *(load-bearing; ratified as `P-INJECTION-FIELDS`)*

**Gap.** `F-ROUTE-2` mandates that each Route contribution is recorded as `substrate.InjectionApplied`, and v15 line 486 / technical §10 line 710 say it "records each Route contribution" — but enumerate **zero** payload fields. With `producer:null` and an empty payload, the frame proves only that *an* injection occurred at a seq, not which Route injected what into which Slot — so the staged-message half of input provenance (the Retry pattern, kernel lines 507–514) is not reconstructable from the record.

**v16 should specify.** `InjectionApplied` payload: `route_id` (str), `target_input_slot` (str), `message_sha256` (the canonical-bytes hash of the staged message, content-addressed like `TriggerFired.input_sha256` per D-5).

## R-3 — `ProducerEmittedInvalidEvent` and the emitting Producer's identity  *(ratified as `P-INVALID-PRODUCER-FIELD`)*

**Tension.** v15 §6.2 step 1 constructs the wrapper from a real (rejected) emission; the Retry pattern (line 508) keys `PerKey` on "the failed Producer's kind." But technical §3.4 says the envelope `producer` field is `null` for runtime-emitted events, and §8.1 specifies only `reason ∈ {unknown_kind, schema_violation, non_canonical_value}` + "raw payload preserved" — silent on the producer field.

**v16 should specify.** The wrapper **retains the emitting Producer's identity** (vocabulary v0.1 ratifies a `producer: ProducerRef` on this kind). State whether that rides the envelope `producer` field (i.e. this kind is exempt from "null for runtime-emitted") or a payload field, and resolve the §3.4-vs-§6.2-step-1 contradiction explicitly.

## R-4 — `TriggerFired.factory`  *(deferred; `P-TRIGGERFIRED-FACTORY`)*

**Drift.** The v15 lifecycle table (line 479) names `factory` among `TriggerFired`'s identified elements; technical §6.2 step 5 (line 501) omits it from the recorded payload (`trigger_id, firing_key, resolved_input|$blob, input_sha256`).

**v16 should resolve.** Either drop `factory` from the v15 table prose (the spawned Producer kind is recoverable via the trigger's `starts` in the `RunStarted` manifest, making `factory` redundant on the frame) or add it to the payload. Vocabulary v0.1 follows the technical-spec payload (no `factory`) and records the discrepancy rather than silently choosing.

---

*v16_reconciliation_note.md — four reconciliation items surfaced by the Substrate vocabulary lock. R-1..R-3 ratified into vocabulary v0.1 (2026-06-12); the kernel spec should fold them into a v16 so spec and vocabulary agree. R-4 deferred. Companion: `substrate/signals/0.1-rationale.md`, `substrate/signals/proposals.json`.*
