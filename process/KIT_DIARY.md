# process/KIT_DIARY.md — Substrate

*Per-sprint or per-phase: what worked, what got in the way, what this says about the next kit version. The diary is this project's accumulating memory about how sdd-kit-2 serves the work. Maintained with the discipline that produced soundfield's ~130 numbered findings.*

---

## Hypothesis tracking

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | A project whose subject matter IS a typed event vocabulary (Substrate's kernel) makes the Vocabulary Session unusually high-fidelity, because Layers 0–2 are transcribed from the spec rather than inferred. | **confirmed** | Layers 0–2 transcribed near-verbatim from kernel v15 / tech §3.4; authoring effort went to Layers 4–7 + gap-surfacing (round-0 Sprint-0 entry). |
| H2 | The kit's Section-3 deferral of orchestration (teams, worktrees, best-of-N) composes cleanly: layering it as project techniques (CT-1..CT-5) preserves the dual contract + Rubber Duck Pass while adding parallelism. | **confirmed** | Ran the whole build as background-builder + responsive-supervisor with parallel subagent review passes (Rubber Duck-as-independent-reviewer) and a duplex FIFO external-review channel; the dual contract + Rubber Duck Pass held every wave (every BLACKBOARD ## Built entry carries both contracts + a pass). Orchestration never bypassed the vocabulary lock or the dual contract (drift watch item held). |
| H3 | The dual contract's "view-side counterpart" generalizes from UI view-tags to "reconstructable from the run record" (replay Level 1/2) for a runtime project with no UI. | **confirmed** | The signal contract was discharged every wave as "this sequence is observable on the record" and verified by replay (`substrate replay --level 2` reconstructs state + re-hashes every decision); the demo session made it concrete — the committed records ARE the view-side, read back by tail/inspect/replay. No UI ever needed; the record carried the whole observation contract. |
| H4 | "Originals over summaries" (hard rule 11) is mechanically load-bearing for *subagents*: agents briefed with file paths to read outperform agents briefed with the Supervisor's summary. Worth a paired comparison. | **partially** | Drafters read originals; verifiers cited exact spec lines, enabling precise gap-detection; the audit/review agents reasoned from spec mechanism to untested paths repeatedly. Still no paired control run (summary-briefed vs original-briefed on the same task), so not fully confirmed. |

---

## Entries

---

### 2026-06-12 (round 0) — Project bootstrap + Sprint 0 framing

**What happened:** First session on a greenfield Substrate project that already had a mature four-document spec corpus (kernel v15, product DRAFT 7, technical DRAFT 5, design DRAFT 1) but zero kit scaffolding. Read the full sdd-kit-2 (AGENTS/CLAUDE, foundations 01–04, grammar PRINCIPLES + BOOTSTRAP, TECHNIQUES, all six templates, lib/sdd.py, process-not-prompt research, the full `example/`) and the four canonical specs in full. Bootstrapped BLACKBOARD (with COMPREHENSION_AFFIRMATION + proposed scope Decision), WORKING_AGREEMENT, this diary, and the Sprint-0 card. Architect directed: bootstrap + start the session; maximize parallel agent teams + worktrees; brief every agent on the actual techniques (originals, not summaries); do a real academic/best-practices research pass and re-ground in the originals before settling the grammar; strict validator-extras.

**What worked:**
- The kit's first-session ritual (read AGENTS → read BLACKBOARD → foundations → vocabulary → working agreement → sprint card) mapped cleanly onto a fresh project: the absence of `process/signals/0.1.json` plus the absence of a `COMPREHENSION_AFFIRMATION` bullet correctly identified this as a first session and routed straight to hard rule 12 (Sprint-0 gates implementation).
- The substrate's specs are unusually rigorous and internally cross-referenced (requirement IDs, decision IDs, conformance checks) — the kind of input BOOTSTRAP Step 0 wants and rarely gets. Thin-docs compensation (the anti-pattern of inventing entities) is not a risk here; the opposite (faithful transcription) is the discipline.

**What got in the way:**
- The kit's templates assume a UI-or-not binary for the dual contract's view-side. A *runtime* project (no UI, but a canonical on-disk record) needed an explicit override: "view-side counterpart" = "reconstructable from the run record." Recorded in WORKING_AGREEMENT; flagged as H3 and a kit-suggestion below.
- "Use teams + worktrees" sits in TECHNIQUES Section 3 (deliberately-not-in-the-kit). The Architect wants them used heavily and reflected "in the kit." Resolved by layering them as project techniques (CT-1..CT-5) and logging a propagation candidate here — NOT editing the read-only kit (hard rule 1).

**What this says about the next kit version:**
- 1. `grammar/BOOTSTRAP.md` Step 9 (dual-contract audit) assumes a view category. Add a note: for runtime/library/CLI projects with no UI, the behavior-tag counterpart is "reconstructable from the persisted record / replay," and the audit pairs each behavior tag with a record-observable assertion. (Generalizes the soundfield UI-centric framing.)
- 2. Candidate upstream: a short `TECHNIQUES.md` Section-2 subsection for "runtime / event-sourcing / orchestration-substrate" projects — the substrate is the first project of this class to run the kit, and several patterns (record-as-observation-surface, conformance-suite-as-acceptance-spine, lifecycle-vocabulary-from-spec) recur.
- 3. Section 3 names orchestration techniques as "compose with any orchestrator" but ships no project-side template for *how*. CT-1..CT-5 here are a candidate seed for a `templates/ORCHESTRATION_OVERLAY.md` that keeps the dual contract intact while adding parallelism — answering "what does composing look like without bypassing the discipline."

---

### 2026-06-12 (round 0) — Sprint 0 candidate produced (Vocabulary Session)

**What happened:** Ran the Vocabulary Session as a 15-agent parallel workflow (CT-1): 4 research strands → 6 per-subsystem drafters (each reading originals, CT-2) → 1 synthesizer → 4 adversarial verifiers. First launch aborted mid-synthesis; resumed from the journal (9 cached agents replayed instantly, tail re-ran). Produced the candidate `process/signals/0.1.json` + rationale + proposals + research-pass.

**What worked:**
- The adversarial-verify phase earned its cost immediately: it caught the synthesizer asserting two inferences as spec fact (a fabricated `vocab_version` attribute; a contested `ProducerEmittedInvalidEvent` producer-field claim) and over-claiming reconstructability in the dual-contract audit. Exactly the intrinsic-self-critique-is-weak / needs-external-check-surface lesson (TECHNIQUES #0.5): the verifiers were grounded against the specs + the 17 conformance checks, not opinion.
- Journal-based resume after the abort was lossless — re-running cost only the tail. CT-1 + workflow resumability composes cleanly with the kit.
- The highest-value output was not the vocabulary itself but the **spec gap it surfaced**: the lifecycle events can't key conformance checks 1/11/R-1 without a subject-Producer-identity payload the kernel never names. The founding act did its job — surfaced a real spec bug as a typed proposal rather than letting it detonate at sprint ~40.

**What got in the way:**
- The synthesizer (one agent holding the global view) is where fabrication crept in — under pressure to produce a complete artifact it filled two gaps by assertion. Mitigation worked (verifiers caught both), but it argues for the verify phase being non-optional whenever a single agent synthesizes.

**What this says about the next kit version:**
- 4. `grammar/BOOTSTRAP.md` should name an explicit anti-fabrication verify pass as part of the session (the kit folds the Rubber Duck Pass into sprint *close* but the Vocabulary Session’s synthesis step has no analogous adversarial check). A "spec-fidelity verifier" grounded against the source docs is the cheapest guard against the exact failure mode commitment 3 warns about.

**Hypotheses updated:** H1 (substrate-is-a-vocabulary → high-fidelity transcription) — **confirmed**: Layers 0–2 transcribed near-verbatim from kernel v15 / tech §3.4; the real authoring work was Layers 4–7 + surfacing gaps. H4 (originals-over-summaries for subagents) — **partially**: every drafter read originals and the verifiers cited exact spec lines/sections, which is what made the gap-detection precise; no paired control run, so not fully confirmed.

---

### 2026-06-13 (round 5) — Priority-1 robustness hardening + the between-wave Rubber Duck Pass as a bug-finder

**What happened:** Took an external code review of the live runtime (waves 0–5) into 6 prioritized fixes (try/finally run body; one shared sanitize-or-log helper across 5 ingestion points; blob offload wiring; four silent no-ops; ruff-gate reconciliation; empty-View guard). Implemented, then ran the between-wave Rubber Duck Pass as TWO independent adversarial review agents (CT-1 + CT-2: each briefed with file paths to the originals, not my summary), addressed their findings, ran a second verification pass, then committed. 59 tests / four gates green.

**What worked:**
- **The adversarial Rubber Duck Pass found two genuine blockers my own implementation missed**, both grounded in the locked vocabulary's state-transition rules and payload schema: (a) a mid-cascade view-failure could append queued control events *after* the terminal RunFinalised (violates RUN-BOUNDARY at-most-once); (b) an oversized TriggerFired resolved_input was nested inside `resolved_input` instead of the top-level `$blob` field the schema makes mutually exclusive. Neither was caught by the passing test suite — they needed an external check surface (the vocabulary's own invariants). This is exactly the mechanism AGENTS.md claims for the pass ("grounded in external check surfaces, not intrinsic self-critique") and it earned its keep here.
- **One reviewer finding was itself wrong, and the originals settled it.** The reviewer flagged "hash the sealed object, not the unsealed" as a correctness fix; checking against the real `seal()` + `msgspec` behavior showed `to_builtins` cannot encode the sealed `MappingProxyType` at all, so hashing pre-seal is *necessary* and the canonical bytes are identical regardless. The discipline ("verify against real API behavior, don't accept a plausible claim") caught a confident-but-wrong review note — the adversarial space cuts both ways.
- **Carry-ahead-with-proposal is the right move for Architect-directed fields under strict validator-extras.** `instance` on TriggerFired closes provenance (F-OBS-2/check 11) and was Architect-directed, but isn't in v0.1. Rather than silently emit it (invent vocabulary) or drop it (lose the capability), filed P-TRIGGERFIRED-INSTANCE and carried it implemented-ahead-of-ratification — the same path P-SUBJECT-ID took into v0.1. The proposal taxonomy IS the mechanism for "load-bearing but not yet ratified."

**What got in the way:**
- The runtime emits lifecycle frames that bypass `_resolve`'s schema validation, so strict validator-extras is *not actually enforced* on `substrate.*` payloads at runtime — the only thing that catches an uncatalogued field is a human/agent reading the vocab. Logged as a Drift watchlist item; the real fix is a conformance-harness check that re-validates every lifecycle frame against the RunStarted manifest schemas (Wave 9), which would mechanize the strict posture the project claims.

**What this says about the next kit version:**
- 5. The between-wave Rubber Duck Pass is documented in AGENTS.md as a *sprint-close* self-review; this round shows its highest value is as a **separate adversarial agent pass briefed on the originals**, run between waves on a behavior-touching change. Candidate: TECHNIQUES.md should name "independent-reviewer-on-the-originals" as a distinct, higher-power variant of the pass for behavior-touching/architecture sprints, distinct from the author's own close-out narration.
- 6. A review finding being *plausible and well-cited* is not the same as it being *correct* — the "hash the sealed object" note was both, and still wrong. The kit's adversarial-information-space posture (verify against real behavior, not against a confident claim) should extend explicitly to *review findings*, not just to library hype. Candidate note for the Rubber Duck Pass disposition step: a finding is `resolved-here` only after the underlying claim is verified against the real API/spec, not merely because a reviewer asserted it.

---

### 2026-06-13 (round 6) — the safety net that should have come first, and a class of bug tests can't catch

**What happened:** A third review pass (Architect-run, external channel) caught that an earlier non-terminating revision of mine had spun orphaned pytest processes to load-avg 66 on a shared machine, plus five correctness defects. Priority A (a hard test timeout + liveness regression tests) was sequenced FIRST, then B (PerKey/cooldown data loss, lock-outside-try leak, swallowed kernel errors, dead finalisation_payload, overloaded $blob), then a hard-gated God-module refactor before any more features.

**What worked:**
- **A hard `timeout` in the test config is the cheapest possible safety net and it was missing.** The bug class that bit here — a never-quiescent writer / self-feeding Trigger — manifests as a HANG, not a failed assertion, so the entire green test suite said nothing while the machine drowned. `pytest-timeout` + a 30s suite cap + per-test 10s marks on the liveness tests turns "wedge the box" into "one red test in 2s." This belongs in the kit's default project scaffold for any project with a concurrency/event-loop runtime, not as a thing you add after the first hang.
- **Test the hazard the spec NAMES.** The kernel explicitly says a self-feeding Trigger "will fire unboundedly… the substrate does not detect it." That sentence is a test spec: the liveness suite encodes the three sanctioned bounds (Once / cooldown / PerKey-dedup) and asserts termination + finite counts. A spec sentence describing a hazard the system deliberately does NOT guard is exactly where a timeout-backed regression test earns its place.

**What got in the way:**
- **Ordering side effects vs. gates is a silent-data-loss trap.** The PerKey+cooldown bug (admit consumes the key, THEN the cooldown suppresses the firing → key consumed but never fired) is invisible to a count-only assertion and only shows up when the same key recurs after the window. The general lesson: when two gates compose and one has a side effect, the side-effecting one must run last. Worth a TECHNIQUES note for stateful-policy composition.
- **Two-phase construction made the run() method's failure paths fragile** (the lock-outside-try leak, the `getattr(self,"_record",…)` defensiveness, the swallowed-error branch needing existence guards). All of it is symptomatic of ~25 run-state attributes living on the Runtime instance instead of a per-run state object — which is exactly the God-module the Architect then hard-gated for refactor. The correctness fixes are real, but several of them are patches over a structural smell; the refactor is the actual fix.

**What this says about the next kit version:**
- 7. Ship a default `pytest-timeout`+timeout in the kit's project scaffold for runtime/event-loop/concurrency project classes. A hung test on a shared or CI machine is a denial-of-service the green-suite invariant cannot see.
- 8. "Nothing consequential is silent" is a product principle here, but it has to be enforced uniformly across EVERY ingestion/drop point or it rots: the review found the finalisation-payload drop was the one path in the sanitize-or-log cluster that still vanished silently. A checklist-grade rule ("every drop/skip of user data emits a typed record") is more reliable than per-site judgement.

---

### 2026-06-13 (round 7) — Wave 6, and when "implemented ahead of the vocabulary" is the honest state

**What happened:** Built the read-side (replay Levels 1/2/3a + inspection/provenance/divergence), held it uncommitted through the Priority-A/B/refactor detour, then ran the between-wave independent review and committed. The review found two real code bugs (a D-8 normalization that stripped fields too broadly; a Level-2 path that skipped a malformed firing) and three NON-code items: two payload fields and a public signature the implementation depends on that the locked v0.1 vocabulary doesn't yet sanction.

**What worked:**
- **The review separated "code is wrong" from "vocabulary hasn't caught up."** The provenance subsystem is correct relative to the runtime that writes the records — but `TriggerFired.instance` (which it keys on) isn't in locked v0.1. That's not a bug to fix in code; it's a ratification to request. Naming that distinction explicitly (and routing it to `## Surfaced for review` for an Architect ruling, not silently "fixing" it) is exactly the supervised-grammar-evolution discipline working as designed. The danger would have been treating the green test suite as license to call Wave 6 "done" — the tests pass *because* the runtime emits the unratified fields; they can't see that the contract doesn't bless them.
- **The D-8 over-broad-strip bug is a good example of a correctness gap a test suite structurally cannot catch without an adversarial reader.** Stripping every key named `instance`/`run_id` makes the common case (lifecycle frames) work and only fails when an *application* payload happens to use those names — which no existing test does. The reviewer reasoned from the spec's definition of D-8 ("supplementary metadata," not "arbitrary keys") to the false-negative, not from a failing test. Scope-the-normalization-to-lifecycle-frames is the fix.

**What got in the way:**
- **A deferral can collide with a MUST.** Level 3(b) is genuinely blocked on an unspecified t-replay decision, and faking it would be worse — but F-RPLY-1 says 3(b) "MUST work for every recorded run" and check 6 is a ship gate. An honest `NotImplementedError` + a BLACKBOARD note does not waive a normative MUST; that needs an Architect-sanctioned spec amendment. The lesson: when you defer something the spec marks MUST, the deferral isn't complete until the spec is amended to permit it — otherwise you've just moved the contradiction into the code.

**What this says about the next kit version:**
- 9. The Rubber Duck Pass should have an explicit disposition bucket for "correct-against-the-implementation, unsanctioned-by-the-contract" — distinct from `resolved-here`/`surfaced`. A field the code emits and depends on but the locked vocabulary doesn't list is a specific, recurring SDD state (it happened here three times); it routes to a ratification request, and the wave can't be called conformant until the version bumps. Worth naming in AGENTS.md alongside the four disposition states.
- 10. "Deferred" needs a sub-distinction: deferring a SHOULD is a scheduling choice; deferring a MUST is a spec change in disguise and must be surfaced for an explicit amendment, not just logged.

---

### 2026-06-13 (round 8) — the first vocabulary evolution, done by the book

**What happened:** The Architect ratified the three carry-ahead TriggerFired proposals and ruled the bump be ADDITIVE: new `process/signals/0.2.json` (`prior_version:"0.1"`), v0.1 retained as audit trail, `0.2-rationale.md` recording the changes, proposals marked ratified. Built it by copying v0.1 → mutating exactly the metadata + the TriggerFired tag, and diff-verified nothing else changed. Folded external-review #1's D-8 honesty findings in at the same time (equivalence-relation concerns = vocabulary territory).

**What worked:**
- **The carry-ahead → ratify → additive-bump loop closed exactly as the methodology predicts.** Fields were implemented-ahead-of-ratification with typed proposals (Waves 5–6), surfaced for a ruling, and the ruling produced a real version bump with a rationale — not a silent edit to a locked file. v0.1 is untouched; a future session can diff 0.1→0.2 and read the why. The compounding-stability claim made concrete.
- **Diff-verifying the additive bump caught nothing — which is the point.** Asserting `0.1 == 0.2` everywhere except {metadata, TriggerFired} is a cheap mechanical guard against an "additive" edit that silently perturbs an unrelated tag.
- **The D-8 `measured_us` leak is the THIRD instance of one pattern:** a run-varying value leaking into an identity/comparison that should be stable (run_id at frame 0 → the global-key-strip over-reach → a wall-clock measurement). The equivalence relation's exclusion set is load-bearing and under-specified by the spec; enumerating it (rationale + amendment) is what makes check 13 honest.

**What this says about the next kit version:**
- 11. A version bump should ship with a machine-checkable "additive diff" assertion (old == new outside the declared change set) as part of its dual contract — the rationale says *what* changed; the diff proves *nothing else* did.
- 12. "Supplementary metadata excluded" in an equivalence relation is a spec smell unless the exclusion set is enumerated. Every timing/identity/host-derived field that can reach a compared payload must be named; "etc." in an equivalence definition is where false-positives/negatives hide.

---

### 2026-06-13 (round 9) — Wave 7, and the bug the small test always hides

**What happened:** Built the reader surfaces — read-only follower, off-bus sidecars, the 8-command CLI — folding external-review #2's two fixes (v0.2 surgical diff, D-8 `finalisation_payload_dropped`) in first. The between-wave review found a BLOCKER the whole green suite missed: the attach follower re-yields a segment's frames when it seals, because the cursor was keyed by basename and the basename changes on roll.

**What worked:**
- **The review reasoned from the spec mechanism to a path the tests structurally cannot reach.** Every test topology emits a handful of events, far under SEGMENT_MAX_BYTES, so no test ever triggered a segment roll — and the double-yield only happens across a roll. The reviewer didn't find it by running anything; it traced "cursor keyed by `path.name`" against "the writer renames `.open.jsonl`→`.jsonl` on seal" and saw the key change. The fix (key on the roll-stable numeric index) plus a regression test that *forces* rolls by shrinking the segment cap is the durable close. Lesson restated: a passing suite over small fixtures is silent about exactly the size-threshold-crossing paths; review against the mechanism, and write the test that crosses the threshold.
- **"Bit-identical" claims need a serializer pin, not just a diff.** Fix A (the v0.2 ensure_ascii churn) is the second time a claim of byte-equality was made without controlling the serializer. Pinning `ensure_ascii=True` + no-trailing-newline and re-diffing made the lock surgical. A version-bump's dual contract should include the additive-diff assertion.
- **Honest "not yet wired" beats a stub that reads green.** `conformance`/`resume` exit 64 with a clear message rather than printing success — directly serving carry-forward (b) (the deferred-must-be-a-real-third-state rule). The CLI holds that line until Wave 9 builds the harness.

**What got in the way:**
- **Two read paths, one §17 rule, only one honored it.** The follower opened O_NOFOLLOW from day one; `read_record` (the closed-record reader the CLI also routes into) used plain `open()` and followed symlinks. Same security rule, uneven application — exactly the kind of gap that hides when a guarantee is implemented per-call-site instead of once. Fixed both to share an O_NOFOLLOW read helper.
- **`mix_stderr` churn:** Click 8.2 removed `CliRunner(mix_stderr=...)`; stderr is separate by default now. A small reminder that "verify the installed API, don't code from memory" applies to test harnesses too.

**What this says about the next kit version:**
- 13. For any append-log / segmented-store project, the test kit should ship a "force a roll" fixture (shrink the segment cap) so reader/follower tests cross the seal boundary by default. The roll is where cursor/dedup/ordering bugs live, and the natural test fixtures never reach it.
- 14. A security/IO invariant (read-only, no-follow-symlink, no-lock) should be implemented in ONE helper and reused, not re-stated at each call site — uneven application is the failure mode (here: two read paths, one honored §17).

---

### 2026-06-13 (round 10) — Wave 8, and a spec that wants a field the envelope can't hold

**What happened:** Built composition (substrate-as-Producer). The between-wave review found four divergences from §20; the headline one (a BLOCKER) was that §20 says the boundary translator "stamps {inner_run_id, inner_seq} into producer metadata" on each exported event — but the LOCKED wire ProducerRef is exactly `{kind, instance, parent}`, with no metadata slot, and an outer kind can't be `substrate.*`. The spec asks for something the current envelope physically cannot carry.

**What worked:**
- **The right move for "spec wants X, the locked contract can't express X" is to SURFACE, not invent.** I did not bolt a `metadata` field onto ProducerRef to satisfy §20 — that's a wire-envelope change to a locked vocabulary, exactly the unilateral invention the discipline forbids. Filed `P-COMPOSITION-INNER-PROVENANCE` with the three resolution options (add ProducerRef.metadata / a composition envelope field / rule the run-granularity link sufficient) and verified that run-GRANULARITY provenance already holds (inner root in the outer TriggerFired.resolved_input; inner_run_id on ProducerFailed). So the wave ships a real, useful provenance link, with the per-frame gap tracked for an Architect ruling. This is the third time the pattern recurred (instance/factory; view_at; now inner provenance) — the methodology's evolution path absorbing implementation reality without silent drift.
- **"Default export = RunFinalised" exposed a latent spec assumption.** The spec phrase assumes an outer carrier exists, but outer kinds can't be `substrate.*`, so the carrier must be author-named. Implementing `default_export=` (the author names the outer Struct) made the requirement real AND surfaced the assumption as a §20 flow-back. The spec said *what* should cross by default; it didn't say *into what* — building it forced the question.
- **The review caught that `b.export` was dead code I'd written.** I added `embedded_substrate(exports=)` as the per-embedding map and left `b.export`/`Registration.exports` unconsumed — two ways to declare, one working, no error on the dead one. Wiring `b.export` into the RunStarted manifest (so the boundary is observable per check 7) gave it a real job, and the two-source-of-truth risk is now a tracked Drift item.

**What got in the way:**
- **A timing-lucky test hid a robustness bug.** The inner_run_id was scraped from the polled RunStarted frame; the failure test passed only because the inner producer emitted 3 events before failing, giving the 5ms poller time to see RunStarted. The robust source was right there — `RunResult.run_id` from the inner `run()`. Lesson: when a value is available authoritatively (a return value) AND incidentally (a polled side-channel), use the authoritative one; a test that passes via the incidental path is timing-lucky, not correct.

**What this says about the next kit version:**
- 15. The "surface, don't invent" disposition has now fired three times on this project for the same shape: an implementation needs a field/signature the locked contract doesn't have. The Rubber Duck Pass should have a named bucket for it — "contract-cannot-express" — distinct from "unsanctioned-but-expressible" (finding-9, round 7). The former blocks on a vocab/envelope change; the latter just needs ratification.
- 16. A normative spec sentence of the form "X is exported/stamped/carried by default" should be audited for "into what carrier?" — defaults that assume an unnamed target are where implementation discovers the spec is underspecified.

---

### 2026-06-13 (round 11) — Wave 9 Batch A: the gate measures the truth, and the truth is the floor isn't met

**What happened:** Assembled the 17-check conformance harness behind `substrate conformance`. 15 PASS, check 6 a genuine DEFERRED third state, and check 15 (N-PERF-1) **FAIL with a real measured ~32K appends/sec against a 100K floor.** Profiled it: not the predicate/view load (44K bare → 32K loaded), but the per-event asyncio round-trip. Surfaced to the Architect with the numbers and a recommended fix; did not fudge the floor, did not weaken the check.

**What worked:**
- **The whole point of "honesty over green-ness" paid off here.** A conformance harness that prints all-green is worthless if a check can't actually pass; the instruction to make check 6 a genuine third state and to report check 15's real number meant the gate told the truth on its first real run — the floor gap surfaced immediately instead of being papered over with a fudged threshold or a skip-that-reads-green. The honest harness found a real architectural cost in its first execution.
- **Profiling before surfacing turned "it's slow" into a decision.** Measuring bare (44K) vs loaded (32K) localized the cost to the per-event asyncio hop, not the cycle work — which both rules out the obvious suspect (predicate load) and names a concrete, semantics-preserving fix (batch the inbox drain). A surfaced blocker with a root cause + a specific recommended fix is an Architect *decision*, not a vague "perf is bad."
- **The F-API-6 AST lint caught my own violation in the act.** Wiring the harness, I wrote `from substrate import conformance` inside cli.py — a private-module import. The import-lint test failed instantly, and the fix (break the api↔conformance cycle by having conformance import concrete modules directly, route the CLI through `api.run_conformance`) is the right shape. The lint is doing exactly its job: keeping the CLI an honest existence-proof of the public surface.

**What got in the way:**
- **A wired feature breaks the stub's test, and the stub's test was asserting the stub.** `test_conformance_reports_not_wired` asserted exit-64; wiring the harness correctly made it exit-0/1. The test had to be rewritten to assert the NEW honest behavior (deferred shown distinctly, real perf number). Reminder: a placeholder's test encodes the placeholder; replacing the placeholder means replacing its test, and the replacement test must assert the *real* contract, not just flip the expected exit code.

**What this says about the next kit version:**
- 17. A conformance/acceptance harness should be built with a THREE-state result (pass/fail/deferred) and REAL measured numbers from day one, not pass/fail booleans. The moment a gate can only say green/red, the pressure to make everything green corrupts it (fudge the threshold, skip-as-green). The three-state + measured-number design is what let this gate stay honest under a real shortfall.
- 18. "Surface a blocker" is far more useful as "surface a blocker WITH a root cause and a specific, semantics-preserving recommended fix." The profiling step (bare vs loaded) is cheap and converts a complaint into a decision. Worth naming as the expected form of a perf/halt surface.

---

### 2026-06-13 (round 12) — Wave 9 completion + the perf floor that was a spec bug

**What happened:** Finished Wave 9 — the cancel-others/let-finish termination paths, the three reference topologies R-1/R-2/R-3 in CI mode AND run for real against local Ollama, the export-map single-source reconciliation, the N-DOC-1 docs, and the persistent pause/resume that cleared the one base-spec MUST gap (F-TERM-3). The headline event was the N-PERF-1 floor: the honest harness from round 11 reported a real ~37K appends/sec against a 100K floor. Under the Architect's "optimize first" ruling I profiled it, found the dominant cost was the pure-Python rfc8785 (JCS) canonical encode (not asyncio, which my first guess blamed), applied a behavior-preserving crc-splice that lifted it to ~56K — still under floor — and surfaced for a re-baseline decision. The Architect ruled the 100K floor was derived from a D-9 prototype that never measured the required canonical encode, recalibrated it to 40K via an additive spec amendment (A2), and the gate passed honestly.

**What worked:**
- **"Optimize first, then decide" turned a number into a diagnosis.** Forcing the optimization pass before the re-baseline discussion is what disproved my asyncio root-cause (the batch-drain gave zero gain) and pinned the real cost on the JCS encoder. A re-baseline argued from "we measured the encoder is 75% of writer time and it's D-7-required" is a spec correction; a re-baseline argued from "100K is hard" is fudging. The ruling could be principled because the measurement was.
- **A floor derived from an unrepresentative prototype is a spec bug, and the additive-amendment path fixed it without rewriting history.** The 100K came from a prototype that skipped the canonical encode the product *requires* for byte-identity — so the floor measured a system the product doesn't ship. Cutting `draft7_amendment_A2_nperf1.md` (100K→40K, with the rationale that the encoder is the cost and a compiled JCS encoder is the post-1.0 lever) preserved the base draft and recorded *why*. The gate stayed a real regression gate (~28% margin), not a rubber stamp.
- **The crc-splice is the model of a safe in-wave perf win:** behavior-preserving (guarded by a byte-identity test + a fail-loud guard that the spliced frame equals a full re-encode), it halved encodes-per-frame without touching the correctness-critical encoder. The unsafe levers (a C/Rust JCS dependency; a fused encode pass) were named and deferred, not attempted under wave pressure.

**What got in the way:**
- **My first root-cause was confidently wrong.** I attributed the shortfall to per-event asyncio round-trips and recommended a batch-drain; the batch-drain proved it with zero improvement. The lesson is the cheap one — profile before you attribute — but it's worth recording that the *surfaced* recommendation in round 11 ("batch the inbox drain") was the wrong fix, and only the discipline of measuring the applied fix caught it. A surfaced fix is a hypothesis, not a conclusion.

**What this says about the next kit version:**
- 19. A numeric acceptance threshold (a perf floor, a coverage bar, a latency budget) should carry, in the spec, the *shape of the system it was measured against*. The 100K floor was unfalsifiable-in-practice because nobody recorded that it came from a prototype missing the required encode. A threshold without its measurement provenance is a number waiting to be either fudged or worshipped. Candidate: BOOTSTRAP / the spec template should require a "measured against: {config, hardware-class, what was included}" line next to any normative number.
- 20. "Optimize-first-then-rebaseline" is a reusable ruling shape for any MUST-miss on a tunable metric: the optimization pass either closes the gap or produces the diagnosis that justifies the amendment. Worth naming in AGENTS.md as the expected handling of a `dual_contract_fail` on a numeric threshold, distinct from a functional MUST-miss.

---

### 2026-06-13 (round 13) — the "does it do what it says it does" audit: an honest kernel can ship a dishonest surface

**What happened:** With the runtime functionally complete and conformance honest, an external 24-agent audit asked the one question the internal Rubber Duck Passes structurally couldn't: not "is the kernel correct" (it was) but "does the *presentation* — README, CLI output, docstrings, the reference topologies, the committed artifacts — claim only what the code does?" It found the substance sound and the packaging over-claiming in six specific ways, all closed over reviews #8–#13 (verdict: ship). The fixes: a reference checker that was a fake stand-in named like a type-checker → a real load-bearing `ast.parse`; "recorded runs" referenced but never committed → committed deterministic CI-mode records that replay byte-identically; "proves" → "checks/exercises" throughout; a dead `Decision.LET_FINISH` enum + no-op `let_finish` recipe → removed; the rich CLI eating `[config]`/`[lock]`/`[FAIL]` status text as markup → `Console(markup=False)`; aspirational "enforced by import-linter in CI" claims → made true (round 14).

**What worked:**
- **The audit found the one class of defect the in-loop Rubber Duck Pass is blind to by construction.** The pass checks the *trace* against the *vocabulary* — it verifies the runtime says true things on the log. It has nothing to say about whether the README, a docstring, or a CLI banner over-claims, because those aren't on the log and aren't in the vocabulary. Every wave closed clean on the pass and the presentation layer still drifted into overstatement. The check surfaces the pass is grounded in (vocabulary, dual contract, tone canon) cover trace-truth and player-facing-string tone, but NOT prose claims about capability. That's a real coverage hole.
- **"Fake but honestly-named" vs "fake and deceptively-named" is the line that matters.** The deterministic CI Producers are fine — they're stand-ins, and CI says so. The R-3 checker was not fine: it was a no-op *named and described as if it type-checked*. Replacing it with a real `ast.parse` (which genuinely does something load-bearing) and a docstring that says "deterministic stand-in; swap in a real type/test checker" is the fix — not removing the stand-in, but making the name and the doc match what it does. The audit's value was forcing that distinction everywhere.
- **A dead enum value is a lie the type system happily tells.** `Decision.LET_FINISH` existed, `let_finish()` returned it, and `_consult_termination` had no branch for it — so it was a silent no-op that read, from the API surface, as a supported termination mode. Nothing failed; mypy was green; tests passed. Removing it (rather than shipping a confusingly-named alias for "finalise on quiescence") is the honest move, with the real drain-then-finalise mechanism deferred with its re-visit condition. Dead code that *presents as a feature* is worse than missing code.

**What got in the way:**
- **The internal review apparatus had no "presentation truth" pass, so the drift accumulated silently across nine waves.** Each wave's docstrings and README edits were written to be helpful and rounded up; no single wave's Rubber Duck Pass was scoped to catch "this sentence claims more than the code delivers." It took an external, adversarial, whole-artifact audit to surface it. That's expensive and late.

**What this says about the next kit version:**
- 21. The Rubber Duck Pass needs a seventh observation category: **capability-claim trace** — every player/reader-facing claim of *what the system does* (README, docstrings, CLI banners, example narration) checked against what the code actually does, the way `tone trace` checks strings against the voice canon. The existing six categories all check the trace against a contract; none checks the *prose about the system* against the *system*. The audit proved this is a distinct, recurring drift with its own failure mode (round-up-to-sound-impressive), invisible to trace-grounded checks.
- 22. A "does it do what it says it does" audit — adversarial, whole-artifact, run by agents briefed on the originals — should be a named **phase-close** ceremony, not an external accident. It is the presentation-layer dual to the per-wave Rubber Duck Pass: the pass guards trace-truth wave by wave; the audit guards claim-truth at phase boundaries. Candidate for AGENTS.md as a required step before a milestone tag.
- 23. Three honesty anti-patterns recurred and deserve naming as a checklist: (a) a stand-in named/described as the real thing (vs an honestly-labeled stand-in); (b) a referenced artifact that was never committed (the "recorded runs" that weren't in the repo); (c) a dead code path that presents as a feature (the `LET_FINISH` enum). All three pass type-checks and tests; all three are caught only by reading the claim against the code.

---

### 2026-06-13 (round 14) — re-root + real CI: the dev venv is not a clean room

**What happened:** Packaged the project as a standalone private repo (re-rooted at `substrate/` via subtree split, history preserved, force-pushed to a private GitHub) and stood up real GitHub Actions CI: a matrix of ubuntu+macOS × py3.12/3.13/3.14, each running ruff + format + mypy --strict + pytest + lint-imports + `substrate conformance --no-perf`. On its very first run, CI failed mypy on all six jobs.

**What worked:**
- **CI caught, on its first execution, a real defect that every local gate had been green on for waves.** `reference/_models.py` imports `httpx`; `httpx` was declared only in the `[openai-compat]` extra, never in `[dev]`. Every local `mypy`/`pytest` passed because the dev venv happened to carry httpx (installed transitively at some point). The clean-room matrix — a fresh environment with exactly the declared deps — is an external check surface the developer's accreted venv physically cannot be. This is the same lesson as the Rubber Duck Pass (you need a surface outside your own state) applied to the build environment: "passes on my machine" is intrinsic self-certification; "passes in a fresh matrix install" is the external check.
- **The fix made the dependency declaration honest, not the CI lenient.** The right move was `httpx` → `[dev]` (the dev/CI environment genuinely needs it to type-check the reference adapter), not relaxing mypy or excluding the file. CI failing made a latent under-declaration visible; the fix removed the latency, not the signal.
- **import-linter in CI turned an aspirational claim into a true one.** cli.py's docstring had claimed "enforced by import-linter in CI" before any CI existed (an audit finding, round 13). Adding `lint-imports` to the matrix made the sentence true: the contract (cli imports only `substrate.api`) is now actually enforced on every push, 1 kept / 0 broken, backed by the AST test. A claim about CI is only honest once CI exists and runs it.

**What got in the way:**
- **The under-declared dependency had been invisible for the entire build because no gate ran in a clean room.** This is structurally the same blind spot as round 13's presentation drift and round 9's segment-roll bug: a guarantee asserted but never exercised against the surface that would falsify it. The dev venv accumulates state; only a from-scratch install exercises the dependency manifest. Until CI existed, the manifest was untested.

**What this says about the next kit version:**
- 24. A clean-room dependency install (fresh venv, exactly the declared extras, on a matrix of OSes/runtimes) belongs in the kit's default project scaffold from the *first* wave that authors `pyproject.toml`, not bolted on at packaging time. The dev venv is the one external check surface a developer cannot self-provide; deferring it to the end means every dependency claim is unverified until the end. Pairs with finding 7 (ship a default pytest-timeout): the scaffold's CI is itself an external-check-surface generator, and it should exist early.
- 25. "A claim about a check (CI runs X, the linter enforces Y) is only honest once the check exists and runs." cli.py asserted import-linter-in-CI before CI existed. The capability-claim trace (finding 21) should treat claims-about-enforcement as a special, high-priority case: they're the claims most likely to be written aspirationally and most damaging when false, because they're load-bearing for trust in everything else.

---

### 2026-06-13 (round 15) — the demo, and the same number that passes and fails

**What happened:** Built a legible, runnable demo from the committed reference records (`demo.sh` + an annotated `docs/demo.md`) so the runtime's behavior is readable without running an LLM. Running the conformance suite for the demo surfaced that N-PERF-1 (check 15) *fails* on this laptop — ~26K appends/sec against the 40K floor — the same check that *passes* at ~56K on the build machine. Wrote that into the demo as-is rather than hiding it.

**What worked:**
- **The committed deterministic records made a no-LLM, byte-reproducible demo possible.** The whole walk — R-1/R-2/R-3 tail, replay-with-hash-verification, provenance via `inspect --ancestry`, the conformance gate — runs from committed artifacts with no network and exits 0. The records-as-observation-surface design (H3) is what made the demo a *re-run of committed truth* rather than a fresh, possibly-divergent run. The artifact you ship IS the demo.
- **Reporting the perf failure plainly is the design working, not a wart.** The number that passes on one machine and fails on another is the visible consequence of a deliberate, recorded decision: the per-frame JCS encode is CPU-bound and machine-dependent, so check 15 runs `--no-perf` in CI and the floor is opt-in / controlled-hardware at release. Writing "on this laptop it measures 26K and fails the gate; that's why it isn't a CI gate" into the demo is more credible than a green screenshot — it shows the team knows exactly where the number is soft and has structured around it.

**What got in the way:**
- **A machine-variant gate is a permanent footnote.** N-PERF-1 will always need the "which hardware?" caveat; there is no single true number. That's inherent to a CPU-bound correctness-critical encode, not a defect — but it means every report of the perf result has to carry its measurement context (finding 19, made concrete), or it misleads. The demo had to spend a paragraph on it.

**What this says about the next kit version:**
- 26. The most credible demo of a system with honest gates *includes a failing one, explained*. A demo that only shows green trains the reader to distrust it; a demo that shows the one hardware-variant gate failing on the demo machine, with the reason and the design response, demonstrates that the honesty machinery is real. Candidate: the kit's notion of a release/demo artifact should explicitly permit (even encourage) showing a known-soft gate failing with its rationale, rather than curating an all-green surface.

---

### 2026-06-19 — Hardening + reorg + a new app + CI: what real CI and real models exposed

**What happened:** A long chapter (reviews #44–#48): applied a 78-finding adversarial review of both repos; reorganized `src/substrate/` into subpackages, `topologies/` into co-located code+records packages, and `substrate-ui/` into folders; added LICENSE + a docs index + White/Orwell README fixes; stood up CI on both repos (substrate's matrix + NEW substrate-ui CI with a cross-repo private checkout and a real-Chrome Playwright e2e); and built `coding_flow` — best-of-N over a model ensemble → build-validation → correction loop.

**What worked:**
- **Resolve-in-spec held under load.** Five spec↔code gaps the review surfaced went into product amendment A3 (additive, following the A1/A2 precedent), not into code comments or a side doc. The discipline scaled to a five-item batch without drift.
- **The dual-mode contract carried a brand-new app.** coding_flow shipped CI-deterministic (canned candidates, real gate) AND walkthrough (a real local-coder ensemble) on day one — the wiring proven in CI, the claim proven against real models.

**What got in the way (and the lessons):**
- **Green locally is not green in a clean clone.** Pushing to real CI caught two bugs the local suite hid: `typing_extensions` (python-ulid 3.x imports it but does not declare it, so a base `pip install substrate` broke at import for ANY user — masked locally because a dev dep pulled it transitively) and a server-test that passed only on STALE `runs/` fixtures a clean checkout doesn't have. A suite that has never run from a clean checkout is not verified.
- **A parser tested only on your own canned format breaks on real model output.** coding_flow's deterministic tests (canned candidates) all passed and the demo "worked" — then EVERY real-model candidate parsed to zero files and the flow exhausted, because the model put `# path:` INSIDE the code fence, not as a header before it. The green test said nothing; I only caught it by LOOKING at the raw model output. A model-output-parsing seam must be verified against real output, not just the format your fixtures emit.
- **best-of-N's diversity is the ENSEMBLE, not sampling.** The point of best-of-N is N DIFFERENT models (each family's distinct strengths/failure modes), not N temperature-samples of one — a correctness point the Architect had to make; the topology already supported per-slot models, but the helper hardcoded one.
- **The standing pipe reviewer out-caught a cold agent.** A readability review on the live pipe flagged a duplicated run-block that a freshly-spawned reviewer missed — continuity (it has watched the repo evolve) is worth more than a cold independent read for this kind of pass.

**What this says about the next kit version:**
- 27. **Make "runs green from a clean checkout" an explicit gate, distinct from "runs green here."** The kit's dual contract proves wiring locally; it does not prove the artifact installs and tests from a fresh clone. A base-install / clean-checkout CI run should be a named step — it is where undeclared transitive deps and stale-fixture dependencies surface, and they are invisible to a warm dev tree.
- 28. **For any seam that parses real model (or external) output, the observation contract should require a check against REAL output, not just the canned format the producer emits.** A deterministic stand-in proves the wiring; it actively HIDES format-mismatch bugs, because the stand-in emits exactly the shape the parser expects.

---

## Phase boundary syntheses

*(one per phase close)*

---

### 2026-06-13 — Phase 1 (Implementation) close

**Did the phase deliver its acceptance criteria?** Yes, on the code/spec axis. The v1.0 Substrate runtime is built end-to-end against the four-document spec corpus and verified by an external reviewer running it: 151 tests + 1 opt-in perf skip pass; ruff/format/mypy --strict clean; `substrate conformance` = 16 PASS / 0 FAIL / 1 DEFERRED (check 6, Level-3b, spec-amended A1.1) on representative hardware (15/0/1/1 under CI's `--no-perf`); the three reference topologies run both in CI mode (committed, replayable, hash-verified) and for real against local Ollama; the public API is import-linter-enforced in real CI across a six-job matrix; the repo is a standalone private GitHub repo. Every base-spec functional MUST is shipped or carries an additive spec amendment with rationale. The single non-code blocker to literally cutting `v1.0.0` is §12 gate (g) — external adoption — a process item, and the Architect has parked the tag.

**The through-line of what we learned.** Three distinct kinds of "truth" had to be defended, each by a different surface, because each is blind to the others:

1. **Trace-truth** — does the runtime say true things on the log? Defended wave-by-wave by the Rubber Duck Pass, grounded in the locked vocabulary + the dual contract. This caught the double-finalise, the `$blob` nesting, the D-8 over-strip — bugs the green test suite was silent on. (Rounds 5–11.)
2. **Contract-truth** — does the implementation respect, and the vocabulary sanction, the fields it depends on? Defended by the supervised-grammar-evolution path: carry-ahead-with-proposal → surface → additive bump. The recurring "implementation needs a field the locked contract can't express" pattern fired at least three times (instance/factory; view_at; composition inner provenance) and the methodology absorbed each without silent drift. (Rounds 7–10.)
3. **Claim-truth** — does the *presentation* (README, docstrings, CLI, committed artifacts, dependency manifest) claim only what the code does? This was the gap. Nine waves of clean Rubber Duck Passes still let the presentation layer over-claim, because the pass is grounded in the trace and the vocabulary, neither of which contains prose claims about capability. It took an external whole-artifact audit (round 13) and a clean-room CI (round 14) — two surfaces outside the project's own state — to defend it. (Rounds 13–15.)

The single biggest structural finding of the phase: **the kit's in-loop checks defend trace-truth and contract-truth well, but have no native defense for claim-truth.** An honest kernel shipped a dishonest surface, and nothing internal caught it. Findings 21–26 are the candidate fixes (a capability-claim observation category; a phase-close "does it do what it says" audit; clean-room CI from the first packaging wave; permission to demo a failing gate honestly).

**Hypotheses at phase close:** H1 confirmed (round 0). H2 confirmed (orchestration overlay composed cleanly through the whole build without bypassing the dual contract or vocabulary lock). H3 confirmed (the run record served as the entire view-side/observation surface; the demo made it concrete). H4 still partially (originals-over-summaries held throughout for subagents/reviewers, but no paired control run was ever set up — it remains a strong observation, not a controlled result).

---

## Project-close synthesis

*(top 5–10 structural findings for the next sdd-kit revision, at project close)*

The Substrate build is the first project of its class (a runtime / event-sourcing / orchestration-substrate, where the subject matter IS a typed event vocabulary) to run sdd-kit-2 end to end. The top structural findings for the next kit revision, in priority order:

1. **Add a claim-truth defense to the kit (findings 21, 22, 25).** This is the phase's biggest gap. The Rubber Duck Pass defends trace-truth; nothing defends the truth of *prose claims about the system*. Two concrete additions: (a) a seventh Rubber Duck observation category, **capability-claim trace**, checking every reader/operator-facing claim against what the code does (with claims-about-enforcement — "CI runs X", "the linter enforces Y" — as a high-priority sub-case); (b) a named, adversarial, whole-artifact **"does it do what it says it does" audit as a phase-close / pre-tag ceremony**, the presentation-layer dual of the per-wave pass.

2. **Ship external-check surfaces in the scaffold, early (findings 7, 24).** The two defects that hid longest (an under-declared dependency; presentation drift) hid because no surface outside the project's own state exercised them until the end. Clean-room CI (fresh venv, declared extras only, OS/runtime matrix) and a default `pytest-timeout` belong in the project scaffold from the first wave that writes `pyproject.toml`, not at packaging time. The dev venv and the green local suite are intrinsic self-certification; the kit should generate external checks by default.

3. **Name the "contract-cannot-express" and "unsanctioned-but-expressible" dispositions (findings 9, 15).** The "implementation needs a field the locked contract doesn't have" pattern fired repeatedly with two distinct sub-shapes: the field is expressible but unratified (→ a ratification request) vs the field cannot ride the locked envelope at all (→ a vocab/envelope change). Both deserve named Rubber Duck disposition buckets distinct from resolved-here/surfaced, because both are recurring, specific SDD states with different resolution paths.

4. **Attach measurement provenance to every normative number (finding 19).** The N-PERF-1 saga (a 100K floor derived from a prototype that skipped the required encode) cost a wave. Any normative threshold in a spec should carry "measured against: {config, hardware-class, what was included}". A number without its provenance is destined to be either fudged or worshipped. Pair with the "optimize-first-then-rebaseline" ruling shape (finding 20) for handling a MUST-miss on a tunable metric.

5. **A version bump's dual contract should include a machine-checkable additive-diff assertion (findings 11, 12).** "Additive bump" should be proven, not asserted: old == new outside the declared change set. And "supplementary metadata excluded" in any equivalence relation is a spec smell unless the exclusion set is enumerated — every timing/identity/host-derived field that can reach a compared payload must be named; "etc." is where false divergences hide. (The D-8 exclusion set leaked a run-varying value three times before it was enumerated.)

6. **The between-wave Rubber Duck Pass is highest-power as a separate adversarial agent briefed on the originals (findings 5, 6).** Distinct from the author's own close-out narration. For behavior-touching/architecture sprints it found genuine blockers the author and the green suite missed, by reasoning from the spec mechanism to paths the small test fixtures never reach (segment rolls, application payloads colliding with reserved key names, timing-lucky tests). And it cuts both ways: a review finding that is plausible and well-cited can still be wrong (the "hash the sealed object" note) — a finding is `resolved-here` only after its claim is verified against real API/spec behavior.

7. **Ship class-specific scaffold fixtures for runtime/append-log/event-sourcing projects (findings 1, 2, 3, 13, 14).** This project class recurs and has predictable hazards: the dual contract's view-side is "reconstructable from the record" not a UI (generalize BOOTSTRAP Step 9); a "force a segment roll" test fixture belongs in the kit because the natural fixtures never cross the seal boundary where cursor/dedup/ordering bugs live; security/IO invariants (read-only, no-follow-symlink, no-lock) should be implemented in one shared helper, not restated per call site. Candidate: a `TECHNIQUES.md` Section-2 subsection + an `ORCHESTRATION_OVERLAY.md` template (the CT-1..CT-5 seed) for this class.

8. **The Vocabulary Session needs an explicit anti-fabrication verify pass (finding 4).** The kit folds the Rubber Duck Pass into sprint *close*, but the Sprint-0 synthesis step — where one agent holds the global view under pressure to produce a complete artifact — is exactly where fabrication crept in (a `vocab_version` attribute, an over-claimed dual-contract audit). A spec-fidelity verifier grounded against the source docs caught both; it should be a non-optional part of the session, not a happy accident of how this project ran it.

---

*process/KIT_DIARY.md for Substrate. Rounds 0–15 logged; Phase 1 (Implementation) closed 2026-06-13. H1/H2/H3 confirmed, H4 partially. Eight structural findings filed for upstream propagation by the kit maintainer — the headline being that the kit defends trace-truth and contract-truth but had no native defense for claim-truth (an honest kernel shipped a dishonest surface, caught only by an external audit + clean-room CI).*
