# Sprint 065 — delete dead prompt-composition code

```yaml
---
id: 065
status: open
phase: 8
pass_kind: cleanup
---
```

## Product-spec conformance

**Fulfills:** the third state closes. After sprints 060-064, every real prompt-composition path runs through the composer + fragment producers. The pre-migration scaffolding — `assemble_seed`, `assemble_seed_from_chain`, `bind_slots`, `_validate_slot_kind`, the sprint-230 slot machinery, `_prefix_context_slice` (already deleted in sprint 063), the inline f-string composition in `_model_factory` (already deleted in sprint 064) — all becomes dead code. This sprint deletes it. No third state per the "when work is done, say it is done" discipline (KIT_DIARY finding 73): the code either serves the new path or leaves the tree.

**Consumes:** every sprint 058-064 landed and green.

## Motivation

Dead code around a working system reads like optionality but functions as trap. A future contributor greps for `assemble_seed`, sees the function, reads the docstring citing a spec section that does not exist, and concludes that seed assembly is a thing the system does. The 2026-09-01 audit only surfaced the dead-code state because a live-model observation was absent. This sprint removes the trap.

## Scope

Four deletions, one comment audit, one test-suite prune.

**Delete from `src/substrate/bundles.py`:**
- `assemble_seed` (~L324-345)
- `assemble_seed_from_chain` (~L348-381)
- `bind_slots` (~L440-483)
- `_validate_slot_kind` (~L405-437)
- `SlotUnfilledError` (~L384-395)
- `SlotKindMismatchError` (~L398-403)
- `__all__` entries for the above.

`Bundle`, `BundleError`, `BundleNotFoundError`, `BundleShapeError`, `BundleCycleError`, `BundleChainTooDeepError`, `load_bundle`, `resolve_extends`, `list_bundles` stay — they have live callers (the bundle producers from sprint 062 and the UI bundle picker at `server.py:770`).

**Delete tests:**
- `tests/test_bundles_229.py::test_assemble_seed_*` — every test of `assemble_seed` / `assemble_seed_from_chain`. Keep tests of `load_bundle` and `resolve_extends`.
- `tests/test_bundle_slot_binding_230.py` — the whole file. Nine tests of `bind_slots` machinery that no longer exists.
- `tests/test_mad_lib_wizard_232.py` and `tests/test_all_wizard_templates_232b.py` — if they exercise `bind_slots`, delete or refactor to exercise `load_bundle` only.

**Comment audit on remaining code:**
- `src/substrate/bundles.py` docstrings — remove references to `bind_slots`, `assemble_seed`, "Sprint 230 will wire slot binding on top", "Sprint 232 ships the Mad Lib wizard". Replace with pointers to the producer-based composition (sprint 062 for bundle slots).
- `substrate/process/signals/session-vocabulary.md` — no change needed; the vocabulary rulings are the source of truth.

**Comment audit on session-topology code:**
- `src/substrate/topologies/session/__init__.py` — every docstring mention of "assemble the seed" or "the seed the daemon composes" is stale post-sprint-060 (per_turn migrated) and post-sprint-062 (bundle wired). Update wording so the docstring reflects the fragment/composer shape.

**Manifest `seed` field decision.** `SessionManifest.seed` today is a client-supplied string that flows through as `session_topology(seed=…)`. Post-sprints 060-064 it has no consumer inside the topology (every fragment source overrides it). Two options: (a) keep the field, deprecate it with a warning at construct time if non-empty, delete in a future sprint; (b) delete now. Prefer (a) — the field on disk is real state, and clients may be writing to it; a deprecation window is honest. Halt-and-articulate if the field turns out to have a use the audit missed.

## Prerequisites

- Sprint 058, 059, 060, 061, 062, 063, 064 all closed and green on live-model tests.
- Full substrate suite green with the fragment/composer path.

## Context files

- `src/substrate/bundles.py` — 501 lines today; probably ~350 after this sprint.
- `tests/test_bundles_229.py`, `tests/test_bundle_slot_binding_230.py`, `tests/test_mad_lib_wizard_232.py`, `tests/test_all_wizard_templates_232b.py` — the test files touching deleted code.
- `src/substrate/topologies/session/__init__.py` — docstring audit.
- `src/substrate/session_registry.py` — the `seed` and `role` field on `SessionManifest`; audit deprecation shape.

## Artifact contract → Files modified

- `src/substrate/bundles.py` — deletions listed above; `__all__` shrinks; docstrings updated.
- `tests/test_bundles_229.py` — pruned to `load_bundle` + `resolve_extends` coverage.
- `tests/test_bundle_slot_binding_230.py` — file deleted.
- `tests/test_mad_lib_wizard_232.py`, `tests/test_all_wizard_templates_232b.py` — deleted or reduced per audit.
- `src/substrate/topologies/session/__init__.py` — docstring language updates.
- `src/substrate/session_registry.py` — deprecation warning on `SessionManifest.seed` if the field is populated post-migration.

## Signal contract → Emits

None. Cleanup sprint, no new vocabulary, no new emit sites.

## Observation contract

- `grep -rn "assemble_seed\|bind_slots\|_validate_slot_kind\|SlotUnfilledError\|SlotKindMismatchError" src/ tests/ substrate-ui/` returns zero code hits (docstring or historical sprint-card mentions in `process/` do not count — those stay per rule 12).
- Full substrate test suite green (`uv run python -m pytest tests/`).
- Full substrate-ui test suite green (`uv run python -m pytest ../substrate-ui/tests/`).
- Live-model tests from sprints 060-064 all still green — the deletions cannot have broken the real paths because the deletions target code that had no callers on the real paths to begin with.
- Deprecation warning fires exactly once per session-open when `manifest.seed` is non-empty. Manual verification.

## Halt conditions

- `bridge_mapping_required` if any deletion breaks a test that the sprint 058-064 arc did not migrate. Halt, name the test, decide: was that test exercising a real path the migration missed, or is it a stale test of deleted machinery?
- `dual_contract_fail` if a live-model test from sprints 060-064 fails after this sprint. Never possible under clean deletion; if it happens, the deletion caught a dependency the audit missed. Revert the specific deletion; open a mini-card to migrate the dependency.

## Definition of done

`bundles.py` is ~150 lines shorter and contains only functions with real callers. `bind_slots` and its supporting code no longer exists. `_model_factory` docstrings match the fragment/composer shape they now implement. `SessionManifest.seed` warns on populated use. `grep` returns zero hits for the deleted names in code.
