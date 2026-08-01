# Workflow applications

The workflow-application library: the patterns the agent-CLI products ship as "workflow features"
(subagent fan-out, verify panels, research sweeps), expressed as substrate topologies on real input.
Each is one launch away, each run is a replayable record, and — the difference from those products —
every step is on that record: inspectable, diffable, provenance-complete, and assayable.

Two of the three COMPOSE an existing topology (the way `fanout_review` is `code_review` fed a real
diff); the third is AUTHORED from the standard builder primitives because map-reduce has no existing
whole to compose. None invents kernel machinery or new lifecycle vocabulary. See
[adding-a-topology.md](adding-a-topology.md) for the authoring pattern they follow.

## fanout_review — a review panel on a real git diff

N role reviewers (security, performance, style, correctness, clarity) critique the changed files in
parallel; a quorum fires a judge; cancel-all-others stops the stragglers. This is
`code_review_topology` fed a real `git diff` instead of a demo blob — composition, no engine change.

```
uv run python scripts/run_fanout_review.py --repo <path> --ref HEAD~1 --model kimi-k2.6:cloud --quorum 3
```

Home: `src/substrate/topologies/workflows/fanout_review.py` (`fanout_review_topology`, `changed_files`).
Records: `CritiquePosted` ×N → `VerdictRendered`. Contract: `tests/test_fanout_review.py`.

## best_of_n_verified — generate N, verify each, select the survivor

A drafter model fans out N candidates; each is verified; the built-in judge selects the first that
passes or feeds failures into a correction round. The verifier is caller-supplied — a deterministic
`check(response) -> (passed, reason)` where the answer is mechanically checkable (preferred), or an
INDEPENDENT judge Responder (judge-family disjoint from the drafter) where it is not. Composes
`best_of_n_correction`.

```
uv run python scripts/run_best_of_n_verified.py --task "..." --model kimi-k2.6:cloud \
    --verifier-model glm-5.1:cloud --n 3
```

Home: `src/substrate/topologies/workflows/best_of_n_verified.py`. Records: `Candidate`/`Verdict` ×N →
`Solved` | `Exhausted`. Contract: `tests/test_best_of_n_verified.py`.

## research_sweep — fan readers over a document set, critique gaps, synthesize

Map-reduce: a seeder emits one request per document; a reader extracts findings from each for the
question (map); a completeness critic names what the findings do not yet cover; a synthesizer writes
the answer grounded in findings + gaps (reduce). Authored from primitives (seeder-fan + fan-in
quorum), the shape no existing whole provides.

```
uv run python scripts/run_research_sweep.py --dir <folder> --glob '*.md' \
    --question "..." --model kimi-k2.6:cloud
```

Home: `src/substrate/topologies/workflows/research_sweep.py`. Records: `ReadRequest`/`Finding` ×N →
`Gaps` → `Synthesis`. Contract: `tests/test_research_sweep.py`.

## Verifying the library

- CI (deterministic, no network): each app's contract test, plus `tests/test_workflows_integration.py`
  which runs all three to their terminals as a set.
- Real models (walkthroughs demonstrated in sprints 137-139): fanout_review reviewed substrate-ui's
  last commit (kimi); best_of_n_verified drafted with kimi and verified cross-family with glm;
  research_sweep swept these very docs and synthesized the UI-next + workflow-parity plan.

## Assayability

A workflow is an application, and an application is an assay approach — so "is this multi-agent
pattern actually better than the simpler one?" is a board away, with honest statistics. The agency
assay already found the top coder is the worst agent; the same machinery judges workflows. Do not
assume a fancier workflow wins; measure it.
