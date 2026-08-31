# REVIEW — SDD conformance of the SWE-bench additions

**Reviewer:** external (Claude Opus 4.7 session)
**Date:** 2026-08-09
**Question posed:** do the SWE-bench additions to substrate follow `sdd-kit-2/AGENTS.md` in full?
**Scope of read:** `sdd-kit-2/` in full (17 markdown files, `lib/sdd.py`, all templates); `substrate/process/BLACKBOARD.md`; `substrate/scripts/assay_swebench_confirmatory.py`; `substrate/src/substrate/assay/swebench*.py`; `substrate/src/substrate/topologies/swebench_solver/*`; the Aug-08 review `docs/review/REVIEW-2026-08-08-swebench-solver.md`; the Sprint tail from Sprint 000 (2026-06-12) through 2026-08-09.

---

## Verdict

Not in full. The additions honour the majority of the twelve hard rules and land the load-bearing pieces the manifesto names: the adapter-only door, the firewall, the bridge mapping, halt-and-articulate, the Rubber Duck Pass, the pre-registration gate, and the sprint sweet spot. Seven concrete gaps stand against `AGENTS.md`. Two of them are the same anti-patterns the kit exists to prevent — vocabulary materialising after implementation, and deletions of superseded artefacts — carried into the SWE-bench sub-topology as documented deviations.

Overall conformance, weighted by load-bearing rule: about 85%.

---

## The seven gaps against AGENTS.md

### 1. Rule 12 — no SWE-bench Sprint-0 Vocabulary Session (LOAD-BEARING)

Substrate's Sprint 000 on 2026-06-12 locked `process/signals/0.1.json` and its rationale via the twelve-step `grammar/BOOTSTRAP.md` procedure. That founding act covered the runtime kernel's vocabulary.

The SWE-bench-solver sub-topology grew its own tag set — `SuspectFiles`, `SuspectElements`, `EditLocations`, `ReproductionTest`, `TestResults`, `AppliedPatch`, `SelectedPatch`, `RepairSummary`, `Reproduction` — sprint-by-sprint from sprint 133 onward. No Sprint 0 opened the sub-topology. Three vocab halts landed in Phase B (sprints 147-149) *after* the 108/291 exploratory run had already reported a number: `RepairSummary.repro_agreed_with_grade`, `Result.grader_error_band`, `ArmReport.model_ensemble_id/split_id`.

This is the exact shape of the soundfield failure mode `AGENTS.md` hard rule 12 cites: "soundfield's vocabulary materialised at sprint 60 of 67; the prior 59 sprints inherited the gap." The Aug-08 fold pass (F2 on `recall_at_k` / `full_recall_at_k`) is Phase B repair for gaps a Sprint 0 for the sub-topology would have surfaced up front.

**Remedy:** run a small Vocabulary Session for the SWE-bench sub-topology now, retrofit as `signals/0.2.json` with a rationale doc that names every tag added between sprint 133 and today.

### 2. Rule 12 — deletions (DEVIATION, DOCUMENTED)

`AGENTS.md` hard rule 12: "Delete files. New thinking goes into new files / folders / round-N versions. The audit trail is the work."

Sprint 146 deleted four files: `scripts/assay_full_run.py`, `scripts/swebench_smoke.py`, `scripts/assay_swebench_smoke.py`, `scripts/assay_agent_debug.py`. The Sprint tail entry cites `git grep` returning zero live callers for each and writes a project-side carve-out:

> "The deletion policy for this chain (roadmap §Deletion policy): superseded tooling gets deleted, run artifacts stay — hard rule 12's 'audit trail is the work' applies to design decisions and captured outcomes, not to leaving two live scripts that do the same thing."

Git preserves the deleted code, so the audit trail survives as history. `AGENTS.md`'s prohibition is stricter than that; it names round-N versioning as the additive path. The carve-out has not been promoted to a kit-level ADDENDUM.

**Remedy:** file the deletion policy as a candidate ADDENDUM under `sdd-kit-2/ADDENDUMS.md`, sourced from the substrate roadmap, dated 2026-08-08. Either the kit adopts it as a rule 12 clarification, or the project reverses the deletion policy for the next sprint chain.

### 3. Rule 7 — canonical home registry missed string-literal contracts

F10 in the Aug-08 fold pass caught sixteen bare view-name string literals across `topologies/swebench_solver/assemble.py`. The fix hoisted them into six module-level constants (`_VIEW_APPLIED`, `_VIEW_EDIT_LOCATIONS`, `_VIEW_REPRODUCTION`, `_VIEW_SOLVED`, `_VIEW_TEST_RESULTS`, `_VIEW_VERDICTS`) so a typo becomes a `NameError` at import.

`WORKING_AGREEMENT.md`'s canonical home registry covers file-level type ownership. It has no section for string-literal contracts on the wire (view names, event kinds, decision enum values). KIT_DIARY finding 33 already named the class; the registry section that would enforce it did not exist. F10 is repair at review time, not prevention at authorship time.

**Remedy:** add a "String-literal contracts" subsection to `WORKING_AGREEMENT.md`'s canonical home registry naming, per contract, the module that owns the constant and the sites that reference it. A `SignalTag`-style enum would suffice for view names and event kinds.

### 4. Rule 2 — dead vocabulary carried for seven weeks

`records.py:51-55` defined `SuspectElements` from sprint 138. The `swebench_solver_topology` at `assemble.py:398` wired `localizer_factory` (file-level) instead of `element_localizer_factory` (element-level) until F9 in the Aug-08 fold pass. For roughly seven weeks the sub-topology's schema declared a tag no producer emitted and no consumer read.

`grammar/PRINCIPLES.md` commitment 2 is speaker-side validation. The runtime enforced the schema at emit — it correctly refused unknown tags. It has no symmetric check for a declared tag with no emitter. `AGENTS.md`'s "Rubber Duck Pass" step 2 lists "vocabulary gap" as an observation category but names the reverse — a real event with no tag. A declared tag with no event is uncovered.

**Remedy:** add "tag with no emitter" as a seventh Rubber Duck observation category, or as a boot-time assertion the topology builder runs against its declared `schemas=[...]` list.

### 5. Rule 9 — observation contract used inconsistently

Sprints 155 and 158b write formal `## observation contract` sections with named 2×2 shapes and grep-able expected substrings. Earlier SWE-bench sprints substitute prose narratives: "smoked on the LIVE flask-4045 container," "ran the record and read it — the three Generation grids show the blinker oscillating," "every phase ran with a real model and a real container."

Prose is not grep-able at report time. A grader — human or agent — cannot mechanically confirm the observation held. The kit's rule 9 exists because "content assertions don't cover product behavior" (soundfield round 23); the same logic makes prose narratives an unreliable observation channel.

**Remedy:** every SWE-bench sprint that touches Docker, models, or the grader carries a `## observation contract` with UI-driving-equivalent steps (the `run_arm_on_case` invocation), expected log substrings, and expected runtime signals. The observation runs against the committed record.

### 6. Stringly-typed cell dispositions in the confirmatory runner

`scripts/assay_swebench_confirmatory.py:186` sets `source == "run"` on a live cell, `"salvage"` on a regrade, and (implicitly, per the halt-on-error rewrite) `"error"` never — because errors halt the sweep now. The report layer at `assay/cells.py` set-differences on these strings.

This is the same class as the F10 view-name literals — a public contract encoded as a bare string with no import-time check. A typo would surface as an empty aggregation, not a `NameError`.

**Remedy:** an enum `CellSource` in `assay/run.py` alongside `Result`. Every write site references the enum; every read site set-differences the enum values.

### 7. Substrate-gap discipline missed external model tags

The bridge-mapping discipline `AGENTS.md` inherits from soundfield rounds 13/20-26 is executable: `verify_constants` (`assay/swebench.py:219-239`) asserts our `KEY_INSTANCE_ID` / `KEY_MODEL` / `KEY_PREDICTION` literals against the installed swebench package, and raises on drift.

External model tags in the pre-registration and sprint cards have no such gate. `qwen3-coder:480b-cloud` was retired by Ollama Cloud on 2026-07-15. The Sprint 160 pass-2 fold on 2026-08-09 discovered the retirement live, replaced it with `deepseek-v4-pro:cloud`, and swapped the ensemble triplet. The gap between "external substrate names" (SDK constants) and "external substrate identities" (model tags) is real; the kit's rule covers the first, not the second.

**Remedy:** a `verify_model_tags` shell check (or a five-line script) that resolves every model id named in `signals/0.1.json`, `WORKING_AGREEMENT.md`, and any `.preg.json` against a live Ollama endpoint, run at the top of any sprint that names a model. Halt on drift.

---

## Where the additions honour the kit cleanly

- **Adapter-is-the-only-door.** `prepare_swebench_case` (`swebench_suite.py:85-128`) is the single admission path. `PreparedPayload` (`swebench_suite.py:44-63`) is a `TypedDict`; a raw dict fails mypy at `solver_topology_from_payload`. F1 in the Aug-08 fold rewired every matrix arm through this door and pinned the shape.
- **Firewall.** Reviews #53-#67 caught leaks pre-code. F7 in the Aug-08 fold closed the unittest-id substring leak with a file-equality parser and a fail-closed regression pin at `tests/test_swebench_firewall_parser.py::test_unittest_id_substring_leak_fails_closed_post_F7`. F8 closed the mixed-quote `diff --git` header leak with a regex covering three shapes.
- **Bridge mapping.** `docs/swebench/swebench-bridge-mapping.md` is reverse-engineered from swebench 4.1.0. `verify_constants` runs against the installed package; a version bump that renames a key raises `AssertionError`. The gold-differential smoke on the Architect's box pins `read_resolved`'s path-search order.
- **Halt-and-articulate.** F4 (K>1 repro), F5 (Django adapter), F11 (model verification), F12 (SoTA anchor) each surfaced to `## Surfaced for review` with a typed reason and waited for Architect resolution. None was silently decided.
- **Rubber Duck Pass.** Sprint closes narrate the trace and disposition observations into the four states. F2 in the Sprint 158 fold caught `case-insensitivity was HIDING drift` — an out-of-band verdict value silently accepted by a `.lower()` normalisation. That is a textbook use of an external check surface (the enum's `.value`).
- **Pre-registration.** `assay/preregistration.py` runs before any disk write (`confirmatory.py:353-379`, per finding F151-#3). `arms_fingerprint` hashes per-arm `{models, n, max_rounds}` after F151-#1 caught the fingerprint scoping only `{name, role}`. `_canonical_bytes` was consolidated onto one implementation after F151-#2 caught three parallel `_fingerprint` helpers with divergent bytes.
- **Sprint sweet spot ≤2 files.** Sprints 157 and 158 split into 157a/157b and 158-schema/158a/158b. Sprint 151 ran three files with a documented "splitting would land dead code" rationale — the "why (revised)" note hard rule 12 asks for.
- **Reviewer cadence.** The Architect runs an independent adversarial reviewer every four to five sprints. The Aug-08 review (`REVIEW-2026-08-08-swebench-solver.md`) landed twelve findings ranked by material impact. Pass 1 closed seven; pass 2 closed the remaining five. F1 (matrix wired through the wrong topology) would have made Sprints 155 and 158 dead code in Pass 2. That is the review earning its keep in the shape KIT_DIARY finding 5 predicts.

---

## Discipline in the review passes themselves

The two Aug-08 fold passes exhibit strong SDD discipline in their own right:

- Every finding is verified against the code by `grep` before touching. F1's "matrix wired through the wrong topology" cites `swebench_matrix._build_repair_arm_from_models` calling `swebench_repair_topology`, not the solver.
- Every fix carries a regression pin. F7's leak-fails-closed test is named after the finding. F8's mixed-quote header parse is pinned at `test_assay_swebench_workspace.py::test_section_b_path_parses_mixed_quote_headers_post_F8`.
- The `## Deferred` list carries every finding not landed in the current fold with the re-visit condition. F5 (Django adapter), F11 (model verification), F12 (SoTA anchor) were deferred in Pass 1 and closed in Pass 2 — the audit trail names both.
- Fold pass 2's cost reframing on F4 ("triple Docker cost" hedge) is a KIT_DIARY-worthy Rubber Duck observation on the reviewer's own hedging. Architect pushback caught a framing that dressed laziness as design.

That posture is exemplary. The gaps above are structural, not behavioural.

---

## Priority stack for closing the gaps

1. Vocabulary Session for the SWE-bench sub-topology; retrofit as `signals/0.2.json`. Highest load; addresses the largest anti-pattern (Gap 1).
2. String-literal-contracts subsection of the canonical home registry, with a `CellSource` enum as the first entry. Addresses Gaps 3 and 6 together.
3. `verify_model_tags` gate at sprint-card-composition time. Addresses Gap 7.
4. `## observation contract` section required for every SWE-bench sprint that touches Docker, models, or the grader. Addresses Gap 5.
5. "Tag with no emitter" as a Rubber Duck category. Addresses Gap 4.
6. ADDENDUM candidate for the deletion policy filed against `sdd-kit-2/ADDENDUMS.md`. Addresses Gap 2 procedurally.

---

## Bottom line

The additions do not follow SDD in full. They follow SDD substantively — every load-bearing piece the manifesto names is present and working — and they document their deviations. Two gaps repeat the exact anti-patterns the kit exists to prevent (Gaps 1 and 2). Four gaps are the kit's own discipline extended one step further than the current text (Gaps 3, 4, 5, 6). One gap identifies a class the kit does not yet cover at all (Gap 7).

The right posture is not to relax the standard. The right posture is to close the six remedy items and, for Gap 2, either promote the deletion carve-out to ADDENDUMS or revert it. The SWE-bench work is otherwise the strongest SDD application in this project's history — F2's case-insensitivity catch and F1's dead-code prevention are exactly what the methodology is for.
