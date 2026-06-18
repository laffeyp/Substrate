# Product Spec DRAFT 7 — Amendment A3 (additive)

**Status:** ADDITIVE AMENDMENT to `docs/specs/product_spec/draft7.md`. DRAFT 7 is preserved unchanged (audit trail / no deletions). Where this conflicts with DRAFT 7 prose, this amendment governs for the v1.0-milestone build. Cut 2026-06-18 under product principle 1 (a spec ↔ code disagreement is resolved IN THE SPEC, not in a code comment or a side doc). Surfaced by an external review (REVIEW.md, findings spec-fidelity-4/-5/-6). Companion to amendments A1 (replay-3b deferral, D-8 set) and A2 (N-PERF-1 floor).

These three items were already true of the code and honestly noted in code comments / CONTRIBUTING; this amendment lifts them into the spec corpus so the contract and the implementation agree, the same way A1/A2 did for replay-3b and the perf floor.

---

## A3.1 — Conformance check 5 gates the logical-cooldown half only; the wall-clock half is a documented deferral (amends §7 check 5)

### What DRAFT 7 says
§7 check 5 ("Quiescence") is a two-clause property: "a run with logical cooldowns finalises via quiescence-with-watchdog; **the same topology with a wall-clock cooldown reports the pending timer instead**."

### What this amendment rules
The shipped check 5 gates the **logical-cooldown finalisation** clause. The **wall-clock pending-timer** clause is **deferred** for the v1.0 milestone (the engine documents this at `runtime.py` — wall-clock-cooldown pending-timer quiescence is deferred; kernel F-TERM-2's pending-wall-clock clause is not separately evaluated). The conformance harness MUST present check 5 as covering the logical half only — it does not present partial coverage as full §7.5 conformance. Re-visit: implement a topology with a `WallClock` cooldown that surfaces a pending timer at quiescence, then gate it (or split check 5 into 5a-logical / 5b-wallclock with 5b marked deferred, mirroring check 6's 3b clause). Tracked in `process/BLACKBOARD.md ## Deferred`.

## A3.2 — F-LIFE-2 / F-TERM-1: `let-finish` and `subtree-cancellation` recipes are deferred to post-1.0 (amends F-LIFE-2, F-TERM-1)

### What DRAFT 7 says
F-LIFE-2 requires the standard recipes "cancel-all-others, **let-finish**, quiescence-with-watchdog, threshold-count, all-completed, **subtree-cancellation**" to ship as named library functions; F-TERM-1 lists `let-finish` among the returnable Decisions.

### What this amendment rules
For the v1.0 milestone, **`let_finish` and `subtree_cancellation` are DEFERRED to post-1.0** (relaxing F-LIFE-2 / F-TERM-1's "MUST ship" for those two to a SHOULD, reinstated when shipped). The shipped recipes are cancel-all-others, quiescence-with-watchdog, threshold-count, all-completed, plus `any_of`/`all_of` composition and `pause_await_input`. The deferral was previously recorded only in `CONTRIBUTING.md` and a Decision-enum docstring; per principle 1 it is recorded here in the spec corpus too. **Flow-back:** design spec §4.7's import example lists `let_finish` / `subtree_cancellation` as importable and SHOULD be corrected (or annotated "post-1.0") so it does not advertise un-shipped recipes. Re-visit when the two recipes ship.

## A3.3 — RunStarted manifest fidelity: producer-scoped trigger subscriptions and `source_sha256` are not serialized (clarifies F-OBS-1 / technical §7)

### What DRAFT 7 / technical §7 say
F-OBS-1 requires the `RunStarted` manifest to carry Trigger/Route fingerprints with `source_sha256` "where `inspect.getsource` succeeds", and the manifest is "the only place a run records its topology" (graph.py).

### What this amendment rules (documented limitation, not a change of intent)
For the v1.0 milestone, the manifest is **lossy in two known, non-correctness ways**, documented here rather than left as silent drift:
- A trigger's subscription is serialized as its `kinds` only; **`subscription.producers` (producer-scoped subscriptions) is dropped.** A producer-scoped trigger (e.g. the Routes that `instrument()` wires) records an empty subscription and projects no visible spawn-source edge in `topology_graph`.
- **`source_sha256` is not recorded** — the fingerprint carries `qualname` + `author_version` only; `inspect.getsource` is not invoked.
**Run correctness is unaffected** — the runtime executes the live `Subscription` and the live factories, never the manifest; this is an *observability / projection* gap, not a behavioural one. Re-visit (post-1.0): serialize the full `{kinds, producers}` subscription and render producer-scoped edges; add best-effort `source_sha256` per the F-OBS-1 failure-mode contract. Until then F-OBS-1's `source_sha256` clause and §7's full-subscription expectation are relaxed to SHOULD for the v1.0 milestone.

## A3.4 — Replay Level 1 is structural-integrity verification, not schema decode (clarifies technical §12)

### What technical §12 says
The Level-1 definition describes decoding each frame against the `RunStarted` schema descriptors.

### What this amendment rules
The shipped Level 1 verifies **structural integrity** — it walks the frames, tallies kinds, and confirms the run reached `RunFinalised` (completeness), but does **not** decode each frame against the manifest's schema descriptors. Per-frame schema-decode at Level 1 is **deferred**; the substantive replay tier that ships is **Level 2** (decision reconstruction + per-decision input-hash verification), with Level 3a (state hash) above it and 3b (full byte re-execution) deferred under amendment A1. The replay-tier ladder a consumer should rely on for v1.0 is: L1 = "the record is structurally whole", L2 = "every recorded decision verifies by hash", L3a = "state reconstructs to the same hash". Technical §12's Level-1 schema-decode clause is relaxed to a post-1.0 SHOULD.

## A3.5 — Public read API is `read_record` over envelope dicts, not `load_record` / `RunRecord` (clarifies technical §16)

### What technical §16 says
§16 names `load_record` returning a typed `RunRecord`, and replay/inspect taking that typed object.

### What this amendment rules
The shipped public surface (`substrate.api.__all__`) is **`read_record(root)`** returning an iterator of envelope dicts, with `replay` / `inspect` / the projections accepting a record-root path or an envelope iterable. The typed `load_record` / `RunRecord` names in §16 are **not** the shipped API; they are relaxed to the shipped names for v1.0. (A typed read-record object is a candidate post-1.0 ergonomic addition — see also REVIEW.md architecture-canon-1, the stringly-typed read surface — but it is additive, not a v1.0 contract.)

---

*Amendment A3 to product DRAFT 7. Additive; DRAFT 7 preserved. Five spec ↔ code reconciliations surfaced by REVIEW.md (check-5 wall-clock half; F-LIFE-2 let-finish/subtree-cancellation deferral; RunStarted manifest fidelity; Level-1 replay = structural integrity, not schema decode; public read API = read_record, not load_record/RunRecord). 2026-06-18.*
