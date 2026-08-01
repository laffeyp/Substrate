# Sprint 138 — best_of_n_verified: generate N, verify each, select the survivor

---

```yaml
---
id: 138
status: closed
phase: 2
pass_kind: functional
cadence_band: auto-within-phase
---
```

---

> PROCESS NOTE (2026-07-31, review F-25): this card omits an explicit `## signal contract` and
> `## context_files` (sprint 137 had both). It was an `auto-within-phase` card written at close; the
> signal contract (reuses best_of_n's Draft/Candidate/Verdict/Solved/Exhausted + ModelUsage — no new
> vocabulary) and the observation contract lived in the BLACKBOARD Built entry and
> `tests/test_best_of_n_verified.py`. Recorded here so the gap is acknowledged, not hidden. The record
> kinds are now locked in `process/signals/applications-vocabulary.md`.

## why

Application-parity W1.2 (`docs/cockpit/WORKFLOW-PARITY-SPRINTS-2026-07-31.md`). The agent-CLI "best of N with verification" pattern is the existing `best_of_n_correction` loop — a seeder fans out N drafts, each is validated, a judge selects the passing one or feeds failures into a correction round. The only missing piece is a general application surface: a drafter that answers a task and a verifier, on real input. Same move as fanout_review (sprint 137): compose an existing topology, add a run script, no engine change, no new vocabulary.

## scope

`best_of_n_verified_topology(task, *, drafter, verify, n, max_rounds, ...)` composes `best_of_n_correction`: a `_drafter_factory` (call the drafter Responder, emit ModelUsage + Candidate) and a `_validator_factory` (verify each candidate → Verdict). `verify` is caller-supplied — a deterministic `check(response) -> (passed, reason)` (substrate's preferred; no model in the validator slot) OR an independent judge Responder (judge-family disjoint from the drafter, finding #42). Plus `scripts/run_best_of_n_verified.py`, the real-model launch. `best_of_n/` is untouched; the loop, correction, and records are its own.

## artifact contract

### Files created

- `src/substrate/topologies/workflows/best_of_n_verified.py` — `best_of_n_verified_topology` + the drafter/validator factories.
- `scripts/run_best_of_n_verified.py` — argparse (`--task`, `--model`, `--verifier-model`, `--n`, `--max-rounds`); real Ollama drafter + independent judge; runs to a record.
- `tests/test_best_of_n_verified.py` — the observation contract.

### Files modified

- `src/substrate/topologies/workflows/__init__.py` — export `best_of_n_verified_topology`.
- `process/WORKING_AGREEMENT.md` — canonical-home row.

### Content assertions

- `best_of_n_verified_topology(...)` calls `best_of_n_correction(b, ...)` — composes, does not reimplement.
- `verify` accepts a callable check OR a Responder; the Responder branch parses a `PASS`-leading reply.
- ruff + mypy clean on the package + script.

### Command exit codes

- `uv run python -m pytest tests/test_best_of_n_verified.py -q` returns 0
- `PATH="$PWD/.venv/bin:$PATH" uv run python -m pytest -q` returns 0 (full suite, mypy on PATH — the gotcha)

## observation contract

`pass_kind: functional` — required. Three CI paths (DeterministicResponder + deterministic check, no network):

- **Solved:** N candidates drafted round 1, all verified pass, judge selects one → Solved, RunFinalised; no invented vocabulary.
- **Exhausted after correction:** nothing passes → a correction round 2 (n candidates per round, rounds {1,2}) → Exhausted, RunFinalised.
- **Independent-judge-model branch:** `verify` is a Responder (menu PASS reply) → the model-verify parse produces passing Verdicts → Solved.

### Walkthrough (real models — named, human-run)

`run_best_of_n_verified.py --task "..." --model kimi-k2.6:cloud --verifier-model glm-5.1:cloud --n 3` — kimi drafts, glm (independent judge) verifies, the survivor is selected; kept as the W1.2 walkthrough record. Cross-family judge (finding #42). Honesty split: CI proves the wiring; the human judges whether the answers/verification are good.

## done criteria

best_of_n_verified generates N candidates for a real task, verifies each (deterministic check or independent judge), and selects the survivor via the existing best_of_n loop, on a replayable record. CI green (three paths); full suite green with mypy on PATH; the real-model walkthrough demonstrated once. best_of_n untouched.

## notes

- Auto-within-phase: 137 set the W1 pattern (gather/compose real input → an existing topology → a run script); this follows it. The card documents the contract that was met.
- One drafter Responder serves all slots (diversity comes from model temperature on the real path; deterministic → identical candidates, honest for CI). Per-slot drafters are a later option if wanted.
- The full-suite gotcha (2026-07-31): the coding-gate tests shell out to `mypy`; run the suite with `.venv/bin` on PATH or see 77 spurious returncode-127 failures.
