# Sprint 000 — Vocabulary Session (the founding act)

---

```yaml
---
id: 000
status: closed
phase: 0
pass_kind: architecture
---
```

---

## scope

Run the 12-step Vocabulary Session (`sdd-kit-2/grammar/BOOTSTRAP.md`) for Substrate and produce the locked vocabulary `signals/0.1.json` (eleven layers populated to the extent the specs support) plus the rationale document `signals/0.1-rationale.md` (per-layer decisions, dual-contract audit table, open proposals for v0.2, Architect signature). Open proposals that the specs force but v0.1 does not adopt land in `signals/proposals.json`. No implementation sprint dispatches until both core files exist and the Architect signs off (hard rule 12).

This sprint is preceded by a **research + re-grounding pass** (Architect directive): an academic/best-practices literature pass on signal/event vocabulary and grammar design, plus a faithful re-read of the canonical specs and the kit grammar, so the eleven layers are grounded in the originals and in current best practice rather than first-pass intuition. Drafting mode: **draft-all-then-review** (all eleven layers in one candidate, ratified in a single Architect pass), with the research pass front-loaded.

---

## prerequisites

- Bootstrap complete: `BLACKBOARD.md`, `WORKING_AGREEMENT.md`, `KIT_DIARY.md`, `signals/`, `sprints/`. (done)
- Architect ratifies the proposed scope Decision (`BLACKBOARD.md ## Surfaced for review` → `## Decisions`).

---

## context_files

*Every spawned agent reads the originals for its slice (CT-2 / hard rule 11) — never the Supervisor's summary.*

- `sdd-kit-2/AGENTS.md`
- `sdd-kit-2/foundations/01-signal-driven-development.md`
- `sdd-kit-2/grammar/PRINCIPLES.md` (the 11-layer stack + non-negotiables + eight proposal types)
- `sdd-kit-2/grammar/BOOTSTRAP.md` (the 12-step procedure)
- `sdd-kit-2/templates/VOCABULARY.json` (the layer scaffold)
- `sdd-kit-2/example/signals/0.1.json` (a worked, locked vocabulary to pattern-match against)
- `docs/specs/kernel_spec/v15.md` (the eight primitives, 13 lifecycle kinds, envelope, append cycle, replay)
- `docs/specs/product_spec/draft7.md` (F-* / N-* requirements, §7 conformance, §8 reference topologies, D-1..D-9)
- `docs/specs/technical_spec/draft5.md` (§3 envelope/record, §4 encoding, §6 writer cycle, §16 public API)
- `docs/specs/design_spec/draft1.md` (vocabulary discipline, error UX, CLI output shapes)
- `WORKING_AGREEMENT.md` (strict posture; record-as-view-side override; tone canon; CT-1..CT-5)

---

## signal contract

### Emits

None at runtime — this is a content/architecture sprint (the founding act). The Signal Report narrates the layer-build as `signal_trace` in the report's own terms; no code emits signals this sprint.

### Consumes

- The canonical specs + kit grammar (above), read directly by each agent for its slice.

### Invariants

- `signals/0.1.json` validates as JSON.
- Every tag references a declared category; every category aligns with an architectural boundary, not a class/file name.
- No vocabulary is invented beyond what the specs support; gaps are surfaced as typed proposals in `signals/proposals.json`, not silently filled (BOOTSTRAP anti-pattern: fabricating to avoid halting).
- Lifecycle/control-plane kinds use the reserved `substrate.` prefix and match the spec names exactly (e.g., `ProducerEmittedInvalidEvent`, not a paraphrase).
- Strict validator-extras posture recorded in the rationale doc.

---

## artifact contract

### Files created

- `signals/0.1.json` — the locked vocabulary (Layers 0–10).
- `signals/0.1-rationale.md` — per-layer rationale, dual-contract audit table, open proposals, signatures.
- `signals/proposals.json` — typed open proposals for v0.2 (eight evolution kinds).
- `signals/research-pass.md` — the academic/best-practices + prior-art findings with citations that informed the grammar (Architect directive).

### Files modified

- `BLACKBOARD.md` — append the Sprint-0 close to `## Built` + `## Sprint tail`; resolve/append open questions.
- `KIT_DIARY.md` — Sprint-0 / Phase-0 synthesis entry.

### Content assertions

- `signals/0.1.json` validates as JSON; contains an `ontology.entities` array, a `categories` array, a `tags` array, and the Layer 3–10 sections per `templates/VOCABULARY.json`.
- `signals/0.1.json` contains all thirteen `substrate.` lifecycle kinds from kernel v15 / product F-LIFE-1 (`RunStarted`, `TriggerFired`, `InputBuildFailed`, `ProducerStarted`, `ProducerEmittedInvalidEvent`, `ProducerCompleted`, `ProducerFailed`, `ProducerCancelled`, `InjectionApplied`, `PredicateQuarantined`, `TerminationMatched`, `RunFinalised`).
- Layer 0 entities include at least: Producer, Event, Bus, View, Predicate, Trigger, Route, TerminationPolicy, Topology, RunRecord, Segment, Blob, AdmissionQueue, ControlQueue (the spec's nouns).
- `signals/0.1-rationale.md` contains a "Dual-contract audit" section pairing every behavior tag with a record-observable counterpart (replay Level 1/2 reconstruction), per the WORKING_AGREEMENT override.
- `signals/0.1-rationale.md` ends with an Architect signature line.

### Command exit codes

- `python -c "import json; json.load(open('substrate/signals/0.1.json'))"` returns 0
- `python -c "import json; json.load(open('substrate/signals/proposals.json'))"` returns 0

---

## observation contract

Not applicable — content/architecture sprint, no runtime behavior. The verification is the artifact contract + the Architect's read of the rationale doc (BOOTSTRAP Step 11: "the rationale should answer why X is separate from Y six months from now").

---

## done criteria

`signals/0.1.json` is locked at v0.1 and signed off by the Architect; the rationale doc is defensible; open proposals are filed. The eight primitives, thirteen lifecycle kinds, append-cycle decision points, and replay/record vocabulary are all named with typed payloads, categories aligned to architectural boundaries, strata assigned, and the conformance checks (§7) cross-checked for vocabulary coverage. Phase 1 (implementation) may then begin.

---

## notes

- **Substrate's gift:** Layers 1–2 are substantially pre-specified by kernel v15 (lifecycle kinds + envelope) and technical §3.4/§16. The session's real work is (a) faithful transcription of the spec's kinds, (b) Layer 0 ontology (the spec's nouns), (c) Layer 4–7 (temporal/transition/operator/evidence — the append-cycle ordering invariants, the `substrate.`-namespace transition rules, the writer as the single operator, the canonical-encoding/sequence-density evidence constraints), and (d) the dual-contract audit mapping behavior tags to record-observability.
- **Categories** should align with architectural boundaries (technique 5 / 52): e.g., `lifecycle` (control-plane), `bus`/`append-cycle`, `producer`, `predicate-trigger`, `route`, `termination`, `record`/`persistence`, `replay`, `composition`, `cli`/`inspection`. Final set decided in the session.
- **Strata** (event / ambient / summary / incident): e.g., `ProducerEmittedInvalidEvent`/`ProducerFailed`/`PredicateQuarantined`/`InputBuildFailed` are incident; `RunFinalised`/`TerminationMatched` are summary; writer-stats are ambient (and off-bus per tech §6.4 — a candidate Layer-7/observability note, not a bus tag); `RowTranslated`-style application kinds are event.
- **Cross-check every conformance check (§7) for vocabulary coverage** (technique: the spec ENUMERATES state transitions, #53) — each check names events it depends on; all must have tags.
- Orchestration: the research pass + per-subsystem layer drafting + adversarial verification run as a parallel subagent workflow (CT-1), each agent reading originals (CT-2). No worktrees this sprint (agents return structured proposals; the Supervisor writes the files — CT-3 applies to parallel *implementation*, not Sprint 0).

---

## plan-mode review checklist

- [ ] Scope concrete and bounded (produce + lock `signals/0.1.json` + rationale; research pass front-loaded).
- [ ] `context_files` covers the kit grammar + all four canonical specs + the worked example.
- [ ] Signal contract: vacuous-at-runtime acknowledged (content sprint).
- [ ] Artifact contract gradable: JSON validates; thirteen lifecycle kinds present; dual-contract audit present; signature present.
- [ ] Strict validator-extras recorded in rationale.
- [ ] Within sweet spot: the deliverable is the vocabulary + rationale (one concept: the founding grammar), not implementation.
