# Sprint 231 — five default bundles for the shipped apps

```yaml
---
id: 231
status: closed
phase: daily-driver-piece-H
pass_kind: functional
---
```

## scope

Populate five default-bundle directories, one per shipped application:

- `substrate/src/substrate/topologies/session/bundle/` — `default`: methodology.md ("general-assistant behavior"), empty personality.md, empty per-turn.md, bundle.toml.
- `substrate/src/substrate/topologies/applications/code_review.bundle/` — methodology.md (reviewer rubric), personality.md ("blunt, specific"), per-turn.md ("flag any unsafe pattern").
- `substrate/src/substrate/topologies/applications/pair_coding.bundle/` — methodology.md (pair-coding roles), personality.md ("collaborative"), per-turn empty.
- `substrate/src/substrate/topologies/applications/best_of_n_verified.bundle/` — methodology.md (solver + verifier), personality.md ("rigorous"), per-turn empty.
- `substrate/src/substrate/topologies/applications/research_sweep.bundle/` — methodology.md (multi-angle-reader), personality.md ("thorough"), per-turn empty.

Every `bundle.toml` in these directories references the correct slot files and declares `schema_version = 1`.

## prerequisites

- Sprint 230 closed.
- Sprint 224 closed (four manifests exist).

## context_files

- Sprint 229 output: `bundles.py` loader.
- Sprint 224 output: four manifests.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §9 default-bundle table.
- Author prose per product spec voice (concise, plain, no LLM tells).

## artifact contract

### Files

- Five bundle directories with methodology.md + personality.md + per-turn.md + bundle.toml each.

### Assertions

- `bundles.load_bundle("session")` returns a parsed Bundle (loaded from `topologies/session/bundle/`).
- `bundles.load_bundle("code_review")` loads from `topologies/applications/code_review.bundle/`.
- Each `manifest.toml`'s `[bundle] default = "<name>"` field points at the right bundle.
- Prose passes the eight-word-tone-canon grep (existing `substrate-ui` grader pattern).

### Tests

- `test_default_bundle_session_loads.py`
- `test_default_bundle_code_review_loads.py`
- `test_default_bundle_pair_coding_loads.py`
- `test_default_bundle_best_of_n_verified_loads.py`
- `test_default_bundle_research_sweep_loads.py`

## observation contract

`substrate run code_review --repo .` opens a session whose seed includes the code_review methodology, the "blunt, specific" personality, and the security-flag per-turn prefix. Every UserMessage on the record's `assembled_prompt` starts with the per-turn line.

## halt conditions

- `vocabulary_change_required` if a bundle prose file needs a slot shape not covered by §9.


## signal contract

Emits: (none — shipped default-bundle prose files — no runtime emit sites).

## definition of done

Five default bundles ship. Every shipped application has its default. Sprint 232 (Mad Lib wizard) can dispatch.
