# Sprint 224 — four application manifests + BUNDLED registration

```yaml
---
id: 224
status: closed
phase: daily-driver-piece-E
pass_kind: functional
---
```

Round-5 mislabel: `pass_kind: docs` was wrong — this sprint modifies `topologies/bundled.py` (four new entries), runs `substrate topology list`, `demo replay`, `demo run` assertions, and renames the existing `pair_coding` BUNDLED entry. That is behavior-touching code. `pass_kind: functional` per SDD template. Post-review 2026-08-25.

## scope

Write four `manifest.toml` files under `substrate/src/substrate/topologies/applications/`:

- `code_review.manifest.toml` — wraps `fanout_review_topology(repo, ref, ...)`; inputs schema encodes reviewer_model + judge_model roles.
- `best_of_n_verified.manifest.toml` — wraps `best_of_n_verified_topology(task, drafter, verify, n=3, max_rounds=2)`.
- `research_sweep.manifest.toml` — wraps `research_sweep_topology(question, documents, reader, critic, synthesizer)`.
- `daily.manifest.toml` — wraps `session_topology(...)` from piece A with `runs = "session"`.

Register the three real applications + `daily` in `substrate/src/substrate/topologies/bundled.py:BUNDLED` under CI-mode factories.

**pair_coding name collision — post-review 2026-08-25.** `topologies/pair_coding/__init__.py:87` is the existing chunked-writer topology; `BUNDLED` at `bundled.py:65` binds `"pair_coding"` to it. Sprint 225's application at `applications/pair_coding_composite.py` uses the same name for a session-composite. Two catalogs, one name — `substrate topology list` walks BUNDLED; `substrate run <name>` per §7.6 hits the application registry first, falling back to BUNDLED. Round-6 resolution: rename the existing BUNDLED entry to `"pair_coding_chunked"` in this sprint. The Python function `pair_coding_topology` keeps its name at `topologies/pair_coding/__init__.py:87` (source-compat); only the BUNDLED key changes. Update the CI-mode record path (`topologies/pair_coding/records/ci_mode.record/`) rename note in the sprint-close entry. The application at `applications/pair_coding_composite.py` (sprint 225) then owns the `"pair_coding"` name unambiguously.

## prerequisites

- Sprint 223 closed.
- Sprint 210 closed (piece A landed, `daily` maps to session_topology).

## context_files

- Sprint 223 output.
- Sprint 209 output: `topologies/session/` in BUNDLED.
- `substrate/src/substrate/topologies/applications/{fanout_review,best_of_n_verified,research_sweep}.py` — the real topology signatures.
- `substrate/src/substrate/topologies/bundled.py:65-86` — existing BUNDLED dict pattern.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §7.1, §7.2, §7.4, §7.5 (per-app manifest shapes).

## artifact contract

### Files

- `substrate/src/substrate/topologies/applications/code_review.manifest.toml`
- `substrate/src/substrate/topologies/applications/best_of_n_verified.manifest.toml`
- `substrate/src/substrate/topologies/applications/research_sweep.manifest.toml`
- `substrate/src/substrate/topologies/applications/daily.manifest.toml`
- `substrate/src/substrate/topologies/bundled.py` — four new entries.

### Assertions

- Every manifest parses; `load_manifests()` from sprint 223 returns four entries.
- Each manifest's `[inputs]` schema matches the topology's actual signature (per-role model fields spelled out).
- Every application's CI-mode factory in BUNDLED uses `DeterministicResponder` seeded distinctly.
- `substrate topology list` shows all four names.
- `substrate demo replay <app>` walks each application's CI record; `substrate demo run <app>` reproduces byte-for-byte.

### Tests

- `test_code_review_manifest_parses.py`, `test_best_of_n_verified_manifest_parses.py`, `test_research_sweep_manifest_parses.py`, `test_daily_manifest_parses.py`.
- `test_bundled_four_apps_registered.py`.

## observation contract

`substrate run code_review --repo <fixture-repo> --ref HEAD~1` produces a Verdict on the record. `substrate run best_of_n_verified --task "sum 2 and 3"` produces a Solved. `substrate run research_sweep --question "..." --documents <fixture>` produces a Synthesis. `substrate run daily` opens a session.

## halt conditions

- `dual_contract_fail` if any manifest's `[inputs]` schema drifts from its topology signature.

## definition of done

Four manifests parse and dispatch. Sprint 225 (pair_coding session-composite) can dispatch.
