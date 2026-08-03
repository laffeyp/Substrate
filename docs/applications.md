# Applications

The application library: the orchestration patterns the agent-CLI products ship as features
(subagent fan-out, verify panels, research sweeps), expressed as substrate topologies on real input.
Each is one launch away, each run is a replayable record, and — the difference from those products —
every step is on that record: the lifecycle events, the application events, and a `ModelUsage` entry
per model call, so a run is inspectable, diffable, and assayable.

("application", not "workflow": the lexicon bans "workflow"/"step"/"task" as marketing reframes,
scope including code identifiers — design_spec draft1 / product principle 6. This package was renamed
from `workflows/` per that rule on 2026-07-31.)

The library is three TOPOLOGIES plus one TOOL. Of the topologies, two COMPOSE an existing whole (the
way `fanout_review` is `code_review` fed a real diff) and one (`research_sweep`) is AUTHORED from the
standard builder primitives because map-reduce has no existing whole to compose; none invents kernel
machinery. The fourth, `delegate`, is a tool_loop TOOL, not a topology — it belongs to the library
because it is the W2.1 deliverable (an agent hands a subtask to a child agent), and it is documented
below. See [adding-a-topology.md](adding-a-topology.md) for the authoring pattern the topologies follow.

## fanout_review — a review panel on a real git diff

N role reviewers (security, performance, style, correctness, clarity) critique the changed files in
parallel; a quorum fires a judge; cancel-all-others stops the stragglers. This is
`code_review_topology` fed a real `git diff` instead of a demo blob — composition, no engine change.
The gathered diff covers both modified tracked files and new untracked files (a new file is the most
review-worthy change there is); `quorum` is clamped to the number of roles so a narrow panel still
adjudicates.

```
uv run python scripts/run_fanout_review.py --repo <path> --ref HEAD~1 --model kimi-k2.6:cloud --quorum 3
```

Home: `src/substrate/topologies/applications/fanout_review.py` (`fanout_review_topology`, `changed_files`).
Records: `CritiquePosted` ×N → `VerdictRendered`. Contract: `tests/test_fanout_review.py`.

## best_of_n_verified — generate N, verify each, select the survivor

A drafter model fans out N candidates; each is verified; the built-in judge selects the first that
passes or feeds failures into a correction round. The verifier is caller-supplied — a deterministic
`check(response) -> (passed, reason)` where the answer is mechanically checkable (preferred), or an
INDEPENDENT judge Responder (judge-family disjoint from the drafter) where it is not. The judge reply
is parsed by first PASS/FAIL token and fails closed on neither, so a preambling model does not silently
fail a correct candidate. Composes `best_of_n_correction`.

This ships ONE verifier per candidate, not the M-verifier adversarial refute panel the parity plan
sketched (WORKFLOW-PARITY §W1.2); an M-way panel prompted to refute is a stronger, separate mechanism,
left as a follow-up. Stated so the divergence from the plan is on the record (review F-20).

```
uv run python scripts/run_best_of_n_verified.py --task "..." --model kimi-k2.6:cloud \
    --verifier-model glm-5.1:cloud --n 3
```

Home: `src/substrate/topologies/applications/best_of_n_verified.py`. Records: `Candidate`/`Verdict` ×N →
`Solved` | `Exhausted`, each model call metered as `ModelUsage`. Contract: `tests/test_best_of_n_verified.py`.

## research_sweep — fan readers over a document set, critique gaps, synthesize

Map-reduce: a seeder emits one request per document; a reader extracts findings from each for the
question (map); a completeness critic names what the findings do not yet cover; a synthesizer writes
the answer grounded in findings + gaps (reduce). Authored from primitives (seeder-fan + fan-in
quorum), the shape no existing whole provides. A model call that fails on any of the three seams
(reader, critic, synthesizer) becomes a recorded failure the sweep works around — it never finalises
with no answer.

```
uv run python scripts/run_research_sweep.py --dir docs --glob '*.md' \
    --question "..." --model kimi-k2.6:cloud
```

Home: `src/substrate/topologies/applications/research_sweep.py`. Records: `ReadRequest`/`Finding` ×N →
`Gaps` → `Synthesis`, each model call metered as `ModelUsage`. Contract: `tests/test_research_sweep.py`.

## delegate — an agent hands a subtask to a child agent, folds the answer back (W2.1)

A tool, not a topology: `make_delegate(...)` builds a `delegate` tool a tool_loop agent composes into
its suite. Calling `delegate(task)` runs a CHILD agent on the subtask to a FinalAnswer at its own record
root and folds `{answer, child_root, steps}` back as an ordinary `ToolResult`; `child_root` on that
result is the run-granularity provenance link, so the parent record cites the child. The child runs the
real model on the real task, in its own `workspace/` subdir with its record in a sibling `record/` subdir
(so it cannot write over its own record); it inherits the parent's capability set, and depth + fan-out
are capped with typed failures. The tool seam is synchronous, so the child runs to completion in a worker
thread (blocking like `bash`); `embedded_substrate` is the concurrent-child shape, a later option.

```
uv run python scripts/run_tool_agent.py --delegate --model kimi-k2.6:cloud \
    --task "... a task the agent will split and delegate ..."
```

Home: `src/substrate/topologies/tool_loop/delegate.py`. Records: the child run's own `tool_loop` record
(cited from the parent's `ToolResult.output.child_root`). Contract: `tests/test_delegate.py`.

## Verifying the library

- CI (deterministic, no network) — the durable proof: each app's contract test, plus
  `tests/test_applications_integration.py` which runs all three to their terminals as a set. The
  contract tests assert the model-FACING text with spy responders (the diff reaches the panel, the
  question and document reach the reader, the task reaches the drafter and the candidate reaches the
  judge), not just event counts — severing any of those inputs turns a test red (review F-11).
- Real models — re-runnable, not a committed artifact: each app was demonstrated once with a live
  model (sprints 137-141, logged in `process/BLACKBOARD.md`). Real-model records are non-reproducible,
  so they are not committed as proof; re-run them yourself:
  `scripts/run_fanout_review.py`, `scripts/run_best_of_n_verified.py`, `scripts/run_research_sweep.py`,
  `scripts/run_tool_agent.py --delegate` (each `--model <ollama-tag>`). The CI tests above are what
  guards against regression.

## Assayability

An application is an assay approach — so "is this multi-agent pattern actually better than the simpler
one?" is a board away, with honest statistics, because every model call is on the record as
`ModelUsage`. The agency assay already found the top coder is the worst agent; the same machinery
judges these. Do not assume a fancier pattern wins; measure it.
