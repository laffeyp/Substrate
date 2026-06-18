# Sprint 100 — Application catalogue survey

---

```yaml
---
id: 100
status: pending
phase: 2
pass_kind: research
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Read every §What this enables and §Where this points section across the spec corpus. For each candidate application: assess implementation cost (afternoon / day / week), substrate-coverage value (which primitives it exercises), and shock-and-awe value (does a non-expert immediately see what this does that LangGraph / Aider / Claude Code can't). Produce a sorted list with the top 6 candidates marked "build now in Phase 2," the rest deferred with explicit reasons. This sprint is plan-mode-per-sprint — Architect reviews the prioritization before any topology builds dispatch.

---

## prerequisites

- Phase 1 closed (runtime ships v1.0; conformance gate green).
- Architect ratifies the Phase 2 scope Decision (PHASE2_PLAN.md → process/BLACKBOARD.md `## Surfaced for review` → `## Decisions`).

---

## context_files

- `docs/specs/kernel_spec/v15.md` — §What this enables (13 worked topology examples) and §Where this points (8 experimental directions).
- `docs/specs/product_spec/draft7.md` §8 — the three reference topologies already shipped (R-1 ensemble, R-2 error cascade, R-3 code synthesis).
- `docs/specs/design_spec/draft1.md` §7 (user journeys) and §8 (future UI sketches that name what topologies would benefit from each visualization).
- `precursors/horizon_multi_agent.md`, `horizon_compositional_grammar.md`, `orchestrating_conversation.md` — the precursor thinking that fed into the substrate.
- `process/WORKING_AGREEMENT.md` — tone canon for the survey doc (concise, honest, no overclaim).
- `process/BLACKBOARD.md` — current `## Open questions` and `## Drift watchlist` for any topology candidates surfaced previously.

---

## signal contract

### Emits

None at runtime — this is a research/architecture sprint. The Signal Report narrates the survey as `signal_trace` in the report's own terms; no code emits signals this sprint.

### Consumes

- The canonical specs (above), read directly by each agent for its slice.

### Invariants

- Every candidate is sourced from the spec corpus, not invented. New ideas (not in the specs) are surfaced as proposals in `process/signals/proposals.json` per the vocabulary-evolution discipline.
- Each candidate has all three scores (cost / coverage / shock-and-awe) with one-paragraph rationale, not a hand-wave.
- Local-model feasibility is assessed honestly — claims like "50 agents at 1B model concurrent" must reference batching (Ollama `OLLAMA_NUM_PARALLEL` or vLLM continuous batching) explicitly.
- "Shock-and-awe" is judged against a non-expert who has used LangChain or LangGraph but not the substrate. Score the moment they see it, not the value after they've used it for a month.

---

## artifact contract

### Files created

- `docs/application-catalogue.md` — the sorted candidate list with per-candidate scoring + rationale + deferral reasons; top 6 marked for Phase 2 build with proposed sprint-card numbers (130/131/132/150/151/152 or similar).
- `docs/catalogue-research-pass.md` — research-pass findings: small-local-model feasibility study (Ollama / llama.cpp / vLLM batching for consumer hardware), Producer-adapter latency expectations, demo-record sizing.

### Files modified

- `process/BLACKBOARD.md` — append survey close to `## Built` + `## Sprint tail`; resolve/append `## Open questions` related to the catalogue.

### Content assertions

- `docs/application-catalogue.md` lists at least 12 candidates (13 from §What this enables + 8 from §Where this points minus the 3 already shipped = 18; expect cutting some as duplicates).
- Each candidate row has: name, source-spec-section, implementation-cost (afternoon/day/week), primitives-exercised (subset of {Producer, View, Predicate, Trigger, Route, TerminationPolicy, Composition}), shock-and-awe-score (1–5), Phase-2-build-decision (build / defer / discard), rationale.
- Top 6 are explicitly named with proposed sprint IDs.
- Deferred items each have a one-line reason for deferral.

### Command exit codes

None — this is a content sprint with no runtime emission and no build target. The Signal Report stands as the artifact alongside the doc.

---

## done criteria

- `docs/application-catalogue.md` exists and validates against the content assertions above.
- `docs/catalogue-research-pass.md` exists with citations to actual Ollama / llama.cpp / vLLM docs (or measured numbers from a local benchmark if performed).
- BLACKBOARD updated.
- Architect ratifies the top-6 list in BLACKBOARD `## Decisions` before Sprint 130+ dispatches.
- Rubber Duck Pass clean (no surfaced contradictions; deferral reasons hold up under independent reading).
