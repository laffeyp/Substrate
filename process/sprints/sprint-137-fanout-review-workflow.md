# Sprint 137 — fanout_review: the review panel on a real diff

---

```yaml
---
id: 137
status: closed
phase: 2
pass_kind: functional
cadence_band: plan-mode-per-sprint
---
```

---

## why

The first workflow-parity application (`docs/cockpit/WORKFLOW-PARITY-SPRINTS-2026-07-31.md` W1.1). The agent-CLI products' "fan out a review over the changed files" is exactly `code_review_topology` — five role reviewers in parallel, a quorum-gated judge, cancel-all-others — which already exists and is tested. The only missing piece is feeding it a REAL git diff instead of the hardcoded buggy blob the bundled demo uses. No engine change; a gatherer + a launchable surface. It is the cheapest demonstration that substrate already is the orchestration engine these features are built on, and its output is a replayable record, which theirs is not.

## scope

Author `fanout_review` as (1) a topology-builder function that gathers a repo's changed files and calls the existing `code_review_topology`, and (2) a thin run script (mirroring `scripts/run_tool_agent.py`) that wires real Ollama reviewers/judge and runs it. The engine's deterministic CI registry stays untouched (CI-default topologies only); the real-model launch lives in the script, the walkthrough path. `code_review/__init__.py` is NOT modified — `code_review_topology(code, ...)` is called as-is.

## prerequisites

- 130 (code_review_topology exists) — closed.
- The uncapped responder defaults (2026-07-30) — landed.

## context_files

- `sdd-kit-2/AGENTS.md`
- `src/substrate/topologies/code_review/__init__.py` (the topology this wraps — `code_review_topology(code, *, responders, judge, roles, quorum, deterministic, slow_roles, ...)`)
- `src/substrate/adapters/models.py` (`OllamaResponder`, `DeterministicResponder`)
- `scripts/run_tool_agent.py` (the run-script pattern: argparse → responders → Runtime → record → tail)
- `src/substrate/topologies/bundled.py` (`_code_review` — the CI-default config to mirror)
- `process/WORKING_AGREEMENT.md` (canonical home registry)

## signal contract

### Emits

Reuses code_review's locked kinds — no new vocabulary:
- `CritiquePosted` (role, severity, summary, line_refs) — one per role reviewer
- `VerdictRendered` (decision, cited_roles, n_critiques) — the judge
- the lifecycle kinds (TriggerFired `adjudicate`, ProducerCancelled for lingering reviewers, TerminationMatched cancel-others + all-completed, RunFinalised)

### Invariants

- No new event kind is invented (halt with `vocabulary_change_required` if one seems needed — it should not). **AMENDED (2026-08-07, review S-1): this invariant was later FALSIFIED — commit `56a0d79` (review C-2) added `ReviewSubject` to `fanout_review` so the reviewed diff lands on the record, and this open card's invariant went unamended. `ReviewSubject` is a real emitted kind here, locked in `process/signals/applications-vocabulary.md`. The set-difference a Rubber Duck Pass runs against this card must include it.**
- `code_review/__init__.py` is not modified.
- The diff-gathering shells to git read-only (`git diff`), never mutates the repo.

## artifact contract

### Files created

- `src/substrate/topologies/applications/__init__.py` + `src/substrate/topologies/applications/fanout_review.py` — `fanout_review_topology(repo, *, ref="HEAD~1", roles=DEFAULT_ROLES, quorum, responders, judge, deterministic)` and a `changed_files(repo, ref) -> str` gatherer (git diff → a formatted review input). (One concept, ≤2 files.)
- `scripts/run_fanout_review.py` — argparse (`--repo`, `--ref`, `--n`/roles, `--model`, `--quorum`); wires OllamaResponder per role + judge; runs to a record; prints the verdict + record path (mirrors `run_tool_agent.py`).
- `tests/test_fanout_review.py` — the observation contract.

### Files modified

- `process/WORKING_AGREEMENT.md` — canonical-home row for `fanout_review_topology` / `changed_files`.

### Content assertions

- `changed_files(repo, ref)` returns the changed files' content (or unified diff) as one string; an empty diff yields an honest empty/no-op marker, not a crash.
- `fanout_review_topology(...)` calls `code_review_topology(gathered_code, responders=..., judge=..., ...)` — it composes, does not reimplement.
- `scripts/run_fanout_review.py` defines `main()` and the `if __name__ == "__main__"` idiom.

### Command exit codes

- `uv run python -m pytest tests/test_fanout_review.py -q` returns 0
- `uv run ruff check src/substrate/topologies/applications/ scripts/run_fanout_review.py` returns 0
- `uv run mypy src/substrate/topologies/applications/` returns 0

## observation contract

`pass_kind: functional` — required (technique #24). Behavior: a real review over a real diff produces the expected record shape.

### Input fixture

- A tiny throwaway git repo created in the test (`git init`, commit a file, edit it) so `changed_files` has a real diff to gather — deterministic, no network for the CI path.

### Expected runtime signals (CI path, DeterministicResponder)

- N `CritiquePosted` (one per role) with the gathered diff reflected in the reviewer input.
- `TriggerFired` `adjudicate` once the quorum of `CritiquePosted` is on the bus.
- `VerdictRendered` from the judge with `n_critiques >= quorum`.
- `RunFinalised` — the run reaches a terminal.

### Expected walkthrough (real model — named, human-run, not in CI)

- `run_fanout_review.py --repo <a real repo> --model <ollama tag> --n 5` reviews the actual diff; the record shows role-distinct critiques carrying real model prose; kept as the W1.1 walkthrough record. (Honesty split, Cascade E2: the CI path proves the wiring; only the human on a real repo judges whether the review is *good*.)

## done criteria

`fanout_review` reviews the changed files of a real git diff through the existing code_review panel and produces a replayable record; the CI path is green on a throwaway-repo fixture; the real-model walkthrough is demonstrated once and kept. The engine's deterministic registry is unchanged.

## notes

- The gatherer's default `ref` is `HEAD~1` (review the last commit's changes); `--ref` overrides (e.g. `main` to review a branch). `git diff <ref>` for content; `git diff --name-only <ref>` if per-file reviewers are wanted later (not this sprint — one blob to the panel, as code_review takes today).
- Keep `changed_files` output bounded — a huge diff would blow the reviewer prompt; cap and note the truncation (the tool-result byte-cap lesson), do not silently send megabytes.
- This is the pattern the other two W1 apps follow: gather real input → compose an existing topology → a run script. Keep it that clean.

## plan-mode review checklist

- [ ] Scope is one concept (gather a diff, feed the existing panel); ≤2 topology files + a script + a test.
- [ ] No new vocabulary; `code_review/__init__.py` untouched.
- [ ] The CI path is deterministic (throwaway repo + DeterministicResponder); the real-model path is the named walkthrough.
- [ ] Diff-gathering is read-only and bounded.
