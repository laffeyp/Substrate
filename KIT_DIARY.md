# KIT_DIARY.md — Substrate

*Per-sprint or per-phase: what worked, what got in the way, what this says about the next kit version. The diary is this project's accumulating memory about how sdd-kit-2 serves the work. Maintained with the discipline that produced soundfield's ~130 numbered findings.*

---

## Hypothesis tracking

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | A project whose subject matter IS a typed event vocabulary (Substrate's kernel) makes the Vocabulary Session unusually high-fidelity, because Layers 0–2 are transcribed from the spec rather than inferred. | **confirmed** | Layers 0–2 transcribed near-verbatim from kernel v15 / tech §3.4; authoring effort went to Layers 4–7 + gap-surfacing (round-0 Sprint-0 entry). |
| H2 | The kit's Section-3 deferral of orchestration (teams, worktrees, best-of-N) composes cleanly: layering it as project techniques (CT-1..CT-5) preserves the dual contract + Rubber Duck Pass while adding parallelism. | _pending_ | — |
| H3 | The dual contract's "view-side counterpart" generalizes from UI view-tags to "reconstructable from the run record" (replay Level 1/2) for a runtime project with no UI. | _pending_ | — |
| H4 | "Originals over summaries" (hard rule 11) is mechanically load-bearing for *subagents*: agents briefed with file paths to read outperform agents briefed with the Supervisor's summary. Worth a paired comparison. | **partially** | Drafters read originals; verifiers cited exact spec lines, enabling precise gap-detection. No paired control run yet. |

---

## Entries

---

### 2026-06-12 (round 0) — Project bootstrap + Sprint 0 framing

**What happened:** First session on a greenfield Substrate project that already had a mature four-document spec corpus (kernel v15, product DRAFT 7, technical DRAFT 5, design DRAFT 1) but zero kit scaffolding. Read the full sdd-kit-2 (AGENTS/CLAUDE, foundations 01–04, grammar PRINCIPLES + BOOTSTRAP, TECHNIQUES, all six templates, lib/sdd.py, process-not-prompt research, the full `example/`) and the four canonical specs in full. Bootstrapped BLACKBOARD (with COMPREHENSION_AFFIRMATION + proposed scope Decision), WORKING_AGREEMENT, this diary, and the Sprint-0 card. Architect directed: bootstrap + start the session; maximize parallel agent teams + worktrees; brief every agent on the actual techniques (originals, not summaries); do a real academic/best-practices research pass and re-ground in the originals before settling the grammar; strict validator-extras.

**What worked:**
- The kit's first-session ritual (read AGENTS → read BLACKBOARD → foundations → vocabulary → working agreement → sprint card) mapped cleanly onto a fresh project: the absence of `signals/0.1.json` plus the absence of a `COMPREHENSION_AFFIRMATION` bullet correctly identified this as a first session and routed straight to hard rule 12 (Sprint-0 gates implementation).
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

**What happened:** Ran the Vocabulary Session as a 15-agent parallel workflow (CT-1): 4 research strands → 6 per-subsystem drafters (each reading originals, CT-2) → 1 synthesizer → 4 adversarial verifiers. First launch aborted mid-synthesis; resumed from the journal (9 cached agents replayed instantly, tail re-ran). Produced the candidate `signals/0.1.json` + rationale + proposals + research-pass.

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

**What happened:** The Architect ratified the three carry-ahead TriggerFired proposals and ruled the bump be ADDITIVE: new `signals/0.2.json` (`prior_version:"0.1"`), v0.1 retained as audit trail, `0.2-rationale.md` recording the changes, proposals marked ratified. Built it by copying v0.1 → mutating exactly the metadata + the TriggerFired tag, and diff-verified nothing else changed. Folded external-review #1's D-8 honesty findings in at the same time (equivalence-relation concerns = vocabulary territory).

**What worked:**
- **The carry-ahead → ratify → additive-bump loop closed exactly as the methodology predicts.** Fields were implemented-ahead-of-ratification with typed proposals (Waves 5–6), surfaced for a ruling, and the ruling produced a real version bump with a rationale — not a silent edit to a locked file. v0.1 is untouched; a future session can diff 0.1→0.2 and read the why. The compounding-stability claim made concrete.
- **Diff-verifying the additive bump caught nothing — which is the point.** Asserting `0.1 == 0.2` everywhere except {metadata, TriggerFired} is a cheap mechanical guard against an "additive" edit that silently perturbs an unrelated tag.
- **The D-8 `measured_us` leak is the THIRD instance of one pattern:** a run-varying value leaking into an identity/comparison that should be stable (run_id at frame 0 → the global-key-strip over-reach → a wall-clock measurement). The equivalence relation's exclusion set is load-bearing and under-specified by the spec; enumerating it (rationale + amendment) is what makes check 13 honest.

**What this says about the next kit version:**
- 11. A version bump should ship with a machine-checkable "additive diff" assertion (old == new outside the declared change set) as part of its dual contract — the rationale says *what* changed; the diff proves *nothing else* did.
- 12. "Supplementary metadata excluded" in an equivalence relation is a spec smell unless the exclusion set is enumerated. Every timing/identity/host-derived field that can reach a compared payload must be named; "etc." in an equivalence definition is where false-positives/negatives hide.

---

## Phase boundary syntheses

*(one per phase close)*

---

## Project-close synthesis

*(top 5–10 structural findings for the next sdd-kit revision, at project close)*

---

*KIT_DIARY.md for Substrate. Round 0 logged at bootstrap. Four hypotheses pending. Three kit-suggestion candidates filed for upstream propagation by the maintainer.*
