# Applications

The launchable patterns library. Each is a substrate topology on real input, one command away. Every run lands on the record: lifecycle events, application events, one `ModelUsage` per model call. You can inspect, diff, and assay any of them.

Design_spec draft1 / product principle 6 bans "workflow," "step," and "task" as marketing reframes, including in code identifiers. The package was `workflows/` until 2026-07-31; it is `applications/` now.

Three topologies and one tool. `fanout_review` composes `code_review` and feeds it a real git diff. `research_sweep` is authored from the builder primitives, because map-reduce has no whole to compose against. `best_of_n_verified` composes `best_of_n_correction`. None invent kernel machinery. `delegate` is a tool_loop tool, not a topology, but it belongs here — it is the W2.1 deliverable: an agent hands a subtask to a child agent. Authoring pattern for anything new: [adding-a-topology.md](adding-a-topology.md).

## fanout_review — a review panel on a real git diff

N role reviewers (security, performance, style, correctness, clarity) critique the changed files in parallel. A quorum fires a judge. `cancel_all_others` stops the stragglers.

`code_review_topology` fed a real `git diff` instead of a demo blob. Composition, not engine change. The diff covers modified tracked files and any new untracked ones. `quorum` clamps to the number of roles so a narrow panel still adjudicates.

```
uv run python scripts/run_fanout_review.py --repo <path> --ref HEAD~1 --model kimi-k2.6:cloud --quorum 3
```

Home: `src/substrate/topologies/applications/fanout_review.py` — `fanout_review_topology`, `changed_files`. Records: N `CritiquePosted` events, then one `VerdictRendered`. Contract: `tests/test_fanout_review.py`.

## best_of_n_verified — generate N, verify each, select the survivor

A drafter model fans out N candidates. Each is verified. The judge selects the first that passes, or feeds failures into a correction round.

The verifier is caller-supplied. Two shapes: a deterministic `check(response) -> (passed, reason)` where the answer is mechanically checkable (prefer this), or an independent judge Responder — judge family disjoint from the drafter family — where it isn't. Judge replies parse on the first PASS/FAIL token. Neither token means the parse fails closed, so a preambling model does not silently pass a wrong candidate.

Composes `best_of_n_correction`.

One verifier per candidate. The M-verifier adversarial refute panel the parity plan sketched (WORKFLOW-PARITY §W1.2) is a stronger, separate mechanism — deferred, not shipped. Noted here so the divergence from the plan is on the record (review F-20).

```
uv run python scripts/run_best_of_n_verified.py --task "..." --model kimi-k2.6:cloud \
    --verifier-model glm-5.1:cloud --n 3
```

Home: `src/substrate/topologies/applications/best_of_n_verified.py`. Records: N `Candidate`/`Verdict` pairs, then `Solved` or `Exhausted`. Every model call metered as `ModelUsage`. Contract: `tests/test_best_of_n_verified.py`.

## research_sweep — map readers over documents, critique gaps, synthesize

Map-reduce. A seeder emits one request per document. A reader extracts findings from each for the question — that is the map. A completeness critic names what the findings do not cover. A synthesizer writes the answer grounded in findings plus gaps — that is the reduce.

Authored from primitives (seeder-fan plus fan-in quorum). No existing whole has that shape.

A model call that fails on any of the three seams — reader, critic, synthesizer — becomes a recorded failure the sweep works around. The sweep never finalises with no answer.

```
uv run python scripts/run_research_sweep.py --dir docs --glob '*.md' \
    --question "..." --model kimi-k2.6:cloud
```

Home: `src/substrate/topologies/applications/research_sweep.py`. Records: N `ReadRequest`/`Finding` pairs, then `Gaps`, then `Synthesis`. Every model call metered as `ModelUsage`. Contract: `tests/test_research_sweep.py`.

## delegate — an agent hands a subtask to a child agent, folds the answer back (W2.1)

A tool, not a topology. `make_delegate(...)` builds a `delegate` tool a tool_loop agent composes into its suite.

`delegate(task)` runs a child agent on the subtask to a FinalAnswer at its own record root. The result folds back as an ordinary `ToolResult` carrying `{answer, child_root, steps}`. `child_root` is the run-granularity provenance link — the parent record cites the child.

The child runs the real model on the real task. It gets its own `workspace/` subdir; its record lives in a sibling `record/` subdir so it cannot overwrite itself. It inherits the parent's capability set. Depth and fan-out are capped with typed failures.

The tool seam is synchronous: the child runs to completion on a worker thread, blocking like `bash`. `embedded_substrate` is the concurrent-child shape, deferred.

```
uv run python scripts/run_tool_agent.py --delegate --model kimi-k2.6:cloud \
    --task "... a task the agent will split and delegate ..."
```

Home: `src/substrate/topologies/tool_loop/delegate.py`. Records: the child's own `tool_loop` record, cited from `ToolResult.output.child_root` on the parent. Contract: `tests/test_delegate.py`.

## Verifying the library

CI is the regression guard. Deterministic, no network. Each application has a contract test; `tests/test_applications_integration.py` runs all three to their terminals as a set. The contract tests assert model-facing text with spy responders — the diff reaches the panel, the question and document reach the reader, the task reaches the drafter, the candidate reaches the judge — not just event counts. Severing any of those inputs turns a test red (review F-11).

Real-model runs are re-runnable, not committed. Each application was demonstrated once with a live model (sprints 137-141, `process/BLACKBOARD.md`). Real-model records are non-reproducible, so nothing lands in git as proof. Re-run yourself: `scripts/run_fanout_review.py`, `scripts/run_best_of_n_verified.py`, `scripts/run_research_sweep.py`, `scripts/run_tool_agent.py --delegate`. Each takes `--model <ollama-tag>`.

## Assayability

Every application is an assay approach. "Is this multi-agent pattern actually better than the simpler one?" is a board away, with honest statistics, because every model call is on the record as `ModelUsage`. The agency assay already found the top coder is the worst agent — the same machinery judges these. Measure it.
