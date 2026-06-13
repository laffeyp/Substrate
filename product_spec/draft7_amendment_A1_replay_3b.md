# Product Spec DRAFT 7 — Amendment A1 (additive)

**Status:** ADDITIVE AMENDMENT to `product_spec/draft7.md`. DRAFT 7 is preserved unchanged (audit trail / no deletions). This note amends two normative items; where it conflicts with DRAFT 7 prose, this amendment governs for the v1.0-milestone build. Cut 2026-06-13 under Architect Ruling 2 (resolve-in-spec-first, product principle 1: a spec disagreement is resolved in the spec, not in a code comment).

---

## A1.1 — Replay Level 3(b) is an explicit, documented deferral (amends F-RPLY-1 and §7 conformance check 6)

### What DRAFT 7 says

- **F-RPLY-1** requires the four honesty tiers, with Level 3(b) substitution re-execution "MUST work for every recorded run" producing a byte-identical log.
- **§7 conformance check 6** ("Replay round-trip") makes Level-3(b) byte-identical substitution re-execution a v1.0 release gate.

### What this amendment rules

For the v1.0-milestone build, **Level 3(b) byte-identical substitution re-execution is DEFERRED to a later wave (pre-1.0), as an explicit, documented deferral** — not a silent failure. Concretely:

- Levels **1, 2, and 3(a)** ship and are required as DRAFT 7 specifies (state reconstruction; decision reconstruction incl. resolved-input hash verification; native re-execution with the determinism+ceiling precondition gate and honest refusal). These are unchanged.
- Level **3(b)** is implemented as an explicit `NotImplementedError` carrying its reason, until the t-replay decision below is made and the substitution re-executor is built. It is NOT faked and NOT silently returned as success.
- **Conformance check 6** is reclassified, in the conformance tracking, from a hard ship gate to **"deferred (spec-amended, A1.1)"** for this milestone. The conformance harness MUST surface check 6 as `deferred`, distinct from both `pass` and `fail` — a deferred check is neither silently passing nor failing.
- F-RPLY-1's "3(b) MUST work for every recorded run" is **relaxed to a SHOULD for the v1.0 milestone**, reinstated as a MUST when 3(b) ships.

### Why — the t-replay rationale (the real blocker)

Level 3(b) re-runs the kernel with every Producer replaced by a log-backed deterministic emitter replaying recorded emissions in recorded admission order, to a **byte-identical** log. Byte-identity is over the on-disk frame (`B_disk`), which includes the envelope's `t` (wall-clock seconds, `time.time()` at append). A re-execution re-sampling the clock produces different `t` values and therefore a non-byte-identical log — so 3(b) requires a **replay-mode writer that replays the recorded `t` values rather than re-sampling the clock** (a "t-replay" / clock-substitution mode). That writer mode is not yet specified.

Note the tension this exposes (resolved by A1.2 below): D-8 log-equivalence **excludes** `t` as supplementary, while check-6 byte-identity **includes** it. The two are different bars. 3(b) as written demands the stricter byte-identity bar, which needs the t-replay writer; D-8 equivalence (which Levels 1/2/3a already support via `first_divergence`) does not. The deferral keeps the honest tiers shipping while the byte-identity-specific mechanism is designed.

### Re-visit condition

Implement Level 3(b) + the t-replay writer in a later wave (the conformance/topologies wave or a dedicated replay wave). On ship, reinstate F-RPLY-1 3(b) as MUST and flip check 6 from `deferred` to a live gate. Tracked in `BLACKBOARD.md ## Deferred`.

---

## A1.2 — The D-8 log-equivalence exclusion set, enumerated (clarifies the D-8 decision and §7 check 13)

### What DRAFT 7 / the technical spec say

D-8 defines log equivalence as "ordered equality of (event-kind sequence, **decision-identity** sequence, canonical payload hashes), **supplementary metadata excluded**," naming `t`, host identifiers, and config echoes as excluded. The set is otherwise left as "and other supplementary metadata."

### What this amendment rules (enumeration, not a change of intent)

The D-8 comparison (`first_divergence`, conformance check 13) builds, per frame, `(kind, decision-identity payload hash)`. On **`substrate.*` lifecycle frames**, the following are **supplementary metadata and are EXCLUDED** from the decision-identity payload hash:

- `run_id`, `instance` — fresh ULIDs / the run id (per-run identity).
- `producer.instance`, `producer.parent` — the subject ref's run-specific ULIDs. `producer.kind` is **kept** (it is decision identity).
- `measured_us` (on `substrate.PredicateQuarantined`, budget path) — wall-clock microseconds of a predicate call; a timing **measurement**, not identity.
- `error` (on `InputBuildFailed` / `ProducerFailed` / `RunFinalised{reason:kernel_error}` / `PredicateQuarantined{reason:exception}`) — a `repr(exc)` that can embed temp paths or object addresses; **normalized to a stable sentinel** (the frame kind already carries "a failure of this class occurred here").
- `t` (envelope) — already excluded by DRAFT 7.

**Kept** (decision identity): `input_sha256`, `firing_key`, `reason`, `trigger_id`/`route_id`, `policy`/`decision`, `k` (a config constant), `view`/`seq` (real positions). The full payload of any **application** (non-`substrate.*`) frame is compared **verbatim** — application content IS the decision being compared and is never normalized.

### Why

Without enumerating and excluding `measured_us` and `error`, two runs of the same deterministic topology that both (e.g.) budget-quarantine the same predicate would carry different `measured_us` / `error` reprs and hash differently, producing a **spurious `first_divergence`** — a false conformance-check-13 positive. "Supplementary metadata excluded" is only honest if the set is enumerated; A1.2 enumerates it. This is the same exclusion documented in `signals/0.2-rationale.md`.

### Flow-back

The technical spec §14 ("Inspection, provenance, divergence") D-8 definition and the §"Log-equivalence relation" / D-8 decisions-table row should name this exclusion set rather than "and other supplementary metadata." See `technical_spec/draft5_amendment_A1.md`.

---

*Amendment A1 to product DRAFT 7. Additive; DRAFT 7 preserved. Ruling 2 (Level-3b deferral) + note (c) (D-8 exclusion-set enumeration). 2026-06-13.*
