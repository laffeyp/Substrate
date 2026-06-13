# BLACKBOARD.md — Substrate

*Single writer per section. Discipline, not code-enforced. See `sdd-kit-2/AGENTS.md` § The BLACKBOARD protocol. The Architect reads `## Surfaced for review`; the Agent surfaces what matters there plus plain-English summaries in chat.*

---

## Surfaced for review

*Agent + Architect. Halts, partials, comprehension affirmations, Rubber Duck observations marked `surfaced`, proposed decisions awaiting ratification.*

- **2026-06-12 Claude Code (Opus 4.8, 1M)** — COMPREHENSION_AFFIRMATION: This project is **Substrate**, a concurrent streaming dataflow runtime shipped as a Python 3.12+ library plus a CLI. You bring computations (LLMs, ML models, deterministic transforms, subprocesses, simulators, parsers, sensors) as *Producers* that take typed input and emit a stream of typed *Events*; the runtime runs them concurrently and coordinates them through a single totally-ordered append-only *Bus*, creating new Producers dynamically when *Predicates* over *Views* of the bus are satisfied (the *Trigger* mechanism), carrying data into future instantiations via *Routes*, and ending the run via a *TerminationPolicy*. The load-bearing commitment is that **all state lives on the log and nothing consequential is silent** — every runtime decision (trigger firing with resolved input, injection, quarantine, termination, invalid emission) is a sequenced event, and the persisted bus (the *run record*: framed/CRC JSONL segments + manifest + blob store, RFC 8785 canonical bytes) IS the product surface, because the product promises byte-identical replay, content-hash citations, and diffable records. v1.0 is one full build (no thin-slice MVP — half a substrate orchestrates nothing), gated by 17 conformance checks. **What SDD is at root:** it replaces the lossy human-describes-it-in-prose step with a designed, typed signal vocabulary — vocabulary is the contract (designed before code, refactored like a public API, never silently mutated); signals are typed events, not log lines; the runtime trace is what the next session reads directly. **The kit's canonical loop here:** I read the next sprint card, execute via Read/Write/Edit, return a Signal Report per `templates/SIGNAL_REPORT.md`, run the Rubber Duck Pass at sprint close (sequence narration → six-category observation → four-state disposition, grounded against the locked vocabulary + dual contract + tone canon as external check surfaces), and write to BLACKBOARD under single-writer discipline — never to `## Decisions`, which is Architect-only. **For this project specifically:** Substrate is an unusually clean SDD fit because the kernel spec (v15) already defines a typed event vocabulary — 13 `substrate.*` lifecycle kinds, the envelope schema, and per-Producer declared kinds — so Layers 0–2 are largely *pre-specified by the spec* rather than invented; the dominant risk is the inverse of soundfield's — because no thin slice is permitted, the vocabulary must be comprehensive at lock time, which is exactly what the Sprint-0 Vocabulary Session (hard rule 12) is built to force. Project class: backend/library + CLI (+ optional LLM-integration extras). Validator-extras posture: **strict** (matches product principle 4 — validation is mandatory and non-configurable). **The hard rule binding me:** halt-and-articulate — when uncertain about a sprint's scope, a vocabulary need, or what a passing Signal Report should contain, I write a typed halt to this section and stop rather than paper over; I never invent vocabulary (I propose via the eight supervised-evolution types).

- **2026-06-12 Claude Code — PROPOSED_DECISION (awaiting Architect ratification into `## Decisions`):** *Project scope.* Substrate is a concurrent streaming dataflow runtime: an importable Python 3.12+ library plus a `substrate` CLI, Apache-2.0, open source from day one. It runs Producers concurrently, coordinates them through one totally-ordered append-only bus, and creates new Producers dynamically when predicates over the log are satisfied. The deliverable is the full v1.0 runtime per product spec DRAFT 7 §2 (all eight primitives, the v15 append cycle, admission/backpressure, both persistence modes, composition with export maps, replay Levels 1–3(b), the thirteen lifecycle kinds, the CLI, the inspection/provenance API, the test helpers) — verified by the 17 conformance checks (product §7) as the acceptance spine, with reference topologies R-1..R-3 (product §8) as integration proofs. Out of scope for v1.0: a UI (but UI-readiness on public surfaces is a requirement — principle 8 / F-API-6), the demonstration catalogue, schema-migration tooling, distributed execution, Windows persistent-bus support. Canonical specs: kernel **v15**, product **DRAFT 7**, technical **DRAFT 5**, design **DRAFT 1**. Cadence: plan-mode for Sprint 0 and architecture-band sprints; auto-within-phase available for functional sprints against established contracts. Orchestration layered on top of the kit: parallel subagent teams + per-sprint git worktree isolation (see WORKING_AGREEMENT § Custom techniques).

- **2026-06-12 Architect (verbal, via chat)** — Direction: proceed; the project keeps the working name **Substrate** for now (official package/import name deferred — not pushing any packages yet, so B-Q-1 does not block). "Keep going." Treating the proposed scope above as effectively endorsed for working purposes; the formal `## Decisions` entry remains the Architect's to write/edit when convenient.

- **2026-06-12 Claude Code — SPRINT-0 CANDIDATE READY + `spec_ambiguity` halt (awaiting Architect ratification).** The Vocabulary Session ran as a 15-agent parallel team (research → per-subsystem drafting → synthesis → adversarial verification; first run aborted, resumed from journal cache). Candidate written to `signals/0.1.json` (`locked:false`), `signals/0.1-rationale.md`, `signals/proposals.json` (27 typed proposals), `signals/research-pass.md`. Contents: 38 Layer-0 entities, 14 categories, the 12 reserved `substrate.*` lifecycle tags (spec-grounded payloads only), 1 session (the Run), 6 temporal invariants, 5 transition rules, 9 operators, 12 evidence constraints, an 11-row dual-contract audit (record-as-view-side). **Verifier-driven fixes applied:** removed a fabricated `vocab_version` session attribute (in no spec); demoted an asserted-as-fact `ProducerEmittedInvalidEvent` producer-field claim to `P-INVALID-PRODUCER-FIELD`; filed the kernel-vs-tech `TriggerFired.factory` drift as `P-TRIGGERFIRED-FACTORY`. **The halt — `spec_ambiguity`:** the runtime-emitted lifecycle events (`ProducerStarted/Completed/Cancelled/Failed`, `InjectionApplied`) carry `producer:null` (tech §3.4) and spec-empty payloads, so the SUBJECT Producer / route-slot-message is NOT on the frame — but conformance checks 1 & 11 and reference topology R-1 require it. `F-PROD-4` types `ProducerId` but never says it rides the lifecycle payload. This is a genuine spec gap (filed `P-SUBJECT-ID`, `P-INJECTION-FIELDS`), recommended for ratification into v0.1 and likely warranting a kernel **v16** reconciliation. **Architect actions to lock v0.1:** (1) rule on the load-bearing proposals (≥ `P-SUBJECT-ID`, `P-INJECTION-FIELDS`, `P-INVALID-PRODUCER-FIELD`); (2) decide whether to cut a kernel v16 / tech-spec revision first (product principle 1: spec-disagreement resolved in the spec first) or carry them as ratified-ahead-of-spec; (3) sign `0.1-rationale.md`, which flips `0.1.json` `locked:true`. No implementation sprint dispatches until then (hard rule 12). Rubber Duck Pass (content sprint, no runtime trace): narrated self-review against the locked vocabulary + the 17 conformance checks as external check surface; the four verifier dimensions (conformance-coverage, dual-contract, principle-compliance, spec-fidelity) ARE the pass; dispositions — 2 blockers resolved-here (fabrication removed, audit made conditional), 3 majors surfaced (the proposals above), 0 halted-unresolved beyond the single `spec_ambiguity` awaiting your ruling.

---

## Decisions

*Architect-only. Append-only. The Agent never writes here. If the Agent thinks a decision is needed, surface to `## Surfaced for review` and ask.*

- *(awaiting first Architect ratification — see the PROPOSED_DECISION in `## Surfaced for review`. Once ratified, the project-scope Decision lands here and Sprint 0 vocabulary work is grounded against it.)*

---

## Built

*Agent appends one entry per sprint close. Append-only.*

- **Sprint 000 (2026-06-12)** — Vocabulary Session (founding act). Files authored: `signals/0.1.json` (locked v0.1 — 38 entities, 14 categories, 12 reserved `substrate.*` lifecycle tags, layers 3–10), `signals/0.1-rationale.md` (signed), `signals/proposals.json` (27 proposals; 3 ratified into v0.1), `signals/research-pass.md`, `kernel_spec/v16_reconciliation_note.md`. Dual contract: signal (vacuous — content sprint) + artifact (all files exist; `0.1.json`/`proposals.json` validate as JSON — pass). Produced via a 15-agent parallel workflow with adversarial verification. Architect ratified `P-SUBJECT-ID`/`P-INJECTION-FIELDS`/`P-INVALID-PRODUCER-FIELD` into v0.1 and flagged kernel v16. `spec_ambiguity` halt resolved. v0.1 LOCKED. Phase 1 (implementation) unblocked.

---

## Deferred

*Anyone may append. Re-visit conditions noted.*

- **2026-06-12 (Architect direction)** — **B-Q-1 package/import name deferred.** Working name "Substrate" used throughout for now; no packages published. Re-visit before the first sprint that authors `pyproject.toml` or fixed import paths (Wave 0 of Phase 1). Until then, the canonical home registry uses placeholder import root `substrate`. Shortlist + brainstorm preserved in `## Open questions` B-Q-1. The kernel spec's *concept* word "the substrate" is unaffected regardless of the eventual package name.

---

## Open questions

*Anyone may append.*

- **B-Q-1.** Package/import name — **DEFERRED** 2026-06-12 (see `## Deferred`). Working name "Substrate" stands; official name picked later. Was: product D-2 shortlist (`substrate-kernel`, `substrate-bus`, `pysubstrate`, `substrated`, `horizon-substrate`, `buskernel`); design-spec placeholder `rostrum`; brainstorm added Strata / Keel / Chronicle / Cradle.

---

## Drift watchlist

*Agent maintains. Patterns to monitor across sprints. When the same observation surfaces in three consecutive sprints, escalate to `## Surfaced for review`.*

- **Vocabulary-already-in-spec.** The kernel spec pre-names lifecycle kinds and the envelope. Watch that Sprint-0 layers 0–2 transcribe the spec faithfully rather than re-inventing or silently renaming (e.g., spec says `ProducerEmittedInvalidEvent`, not `InvalidEmission`).
- **Orchestration vs. kit purity.** We are layering teams + worktrees + best-of-N on top of a kit that defers these to Section 3. Watch that the orchestration never bypasses the dual contract, the Rubber Duck Pass, or the vocabulary lock (hard rule 10 — no silent hand-author).

---

## Sprint tail

*Agent maintains. Last 10 sprint summaries; older entries roll into `## Built` as compressed paragraphs.*

### Sprint 000 (2026-06-12, closed) — Vocabulary Session
- **Scope:** lock `signals/0.1.json` + rationale via the 12-step BOOTSTRAP procedure, preceded by a research pass; draft-all-then-review cadence; strict validator-extras.
- **Dual contract:** signal vacuous (content sprint, no runtime emission); artifact pass (4 signals files + v16 note authored; JSON validates).
- **Method:** 15-agent parallel workflow (4 research → 6 subsystem drafters reading originals → 1 synthesizer → 4 adversarial verifiers); first run aborted, resumed from journal cache losslessly.
- **Rubber Duck Pass (narrated self-review; no runtime trace):** external check surfaces = the locked vocabulary, the 17 conformance checks, the canonical specs. Observations: (payload anomaly) synthesizer fabricated `vocab_version` → *resolved-here* (removed); (vocabulary gap) lifecycle/injection subject-identity not spec-named but required by checks 1/11/R-1 → *surfaced* → Architect ratified into v0.1 + flagged kernel v16; (payload anomaly) asserted-as-fact `ProducerEmittedInvalidEvent` producer claim → *resolved-here* (demoted to ratified proposal); (vocabulary gap) `TriggerFired.factory` kernel-vs-tech drift → *deferred* (P-TRIGGERFIRED-FACTORY / v16 R-4).
- **Outcome:** v0.1 LOCKED, signed. 3 proposals ratified into v0.1; kernel v16 reconciliation note filed. Closed clean (no unresolved halts).

---

## Single-writer-per-section discipline

| Section | Who writes | What they write |
|---|---|---|
| `## Surfaced for review` | Agent + Architect | Halts (Agent), comprehension affirmations (Agent), partial verdicts (Agent), proposed decisions (Agent), specific feedback (Architect) |
| `## Decisions` | Architect ONLY (append-only) | Project scope; binding decisions; resolutions of halts |
| `## Built` | Agent (append-only) | One paragraph per sprint close |
| `## Deferred` | Anyone | Items deferred with re-visit condition |
| `## Open questions` | Anyone | Questions not yet answered |
| `## Drift watchlist` | Agent maintains | Observations to track across sprints |
| `## Sprint tail` | Agent maintains | Last 10 sprint closes |

---

*BLACKBOARD.md for Substrate. First session 2026-06-12. One COMPREHENSION_AFFIRMATION on file. One proposed scope Decision awaiting Architect ratification. Sprint 0 (Vocabulary Session) is the founding act per hard rule 12; no implementation sprint dispatches until `signals/0.1.json` + `signals/0.1-rationale.md` are locked and signed.*
