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

## Phase boundary syntheses

*(one per phase close)*

---

## Project-close synthesis

*(top 5–10 structural findings for the next sdd-kit revision, at project close)*

---

*KIT_DIARY.md for Substrate. Round 0 logged at bootstrap. Four hypotheses pending. Three kit-suggestion candidates filed for upstream propagation by the maintainer.*
