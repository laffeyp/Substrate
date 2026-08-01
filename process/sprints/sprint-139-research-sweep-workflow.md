# Sprint 139 — research_sweep: fan out readers, critique gaps, synthesize

---

```yaml
---
id: 139
status: closed
phase: 2
pass_kind: functional
cadence_band: auto-within-phase
---
```

---

> PROCESS NOTE (2026-07-31, review F-25): this card omits an explicit `## signal contract` and
> `## context_files` (sprint 137 had both). It was an `auto-within-phase` card written at close; the
> signal contract (the four topology-local Structs) and observation contract lived in the BLACKBOARD
> Built entry and `tests/test_research_sweep.py`. The four record kinds are now locked in
> `process/signals/applications-vocabulary.md` (review F-17) — the before-code lock the card should have
> carried. Acknowledged, not hidden.

## why

Application-parity W1.3 (`docs/cockpit/WORKFLOW-PARITY-SPRINTS-2026-07-31.md`), the third and last W1 application, and the one distinct from the first two: fanout_review and best_of_n_verified both fan out over ONE input and SELECT/judge; research_sweep fans out over DIFFERENT inputs (a document set) and SYNTHESIZES — map then reduce. No existing whole topology composes cleanly for map-reduce (code_review's reviewers all take the same `code`; best_of_n's slots all attempt one task), so this is a NEW topology authored from the standard builder primitives — the same way code_review and best_of_n were authored. In-pattern (producer_kind / trigger / view / termination, topology-local frozen Structs), not novel machinery; reuses the seeder-fan-out shape (best_of_n) and the fan-in-quorum trigger (code_review).

## scope

`research_sweep_topology(question, documents, *, reader, critic, synthesizer, deterministic)` and a `gather(paths) -> list[(source, content)]` file reader (read-only, bounded, like fanout_review's `changed_files`). The topology: a seeder emits one ReadRequest per document; a `read` trigger fires a `reader` per request (a model extracts findings for the question from that document → Finding); when all N findings are in, a `critic` names what is still missing across them (→ Gaps); the `synthesizer` then writes the answer grounded in findings + gaps (→ Synthesis). Termination on the Synthesis. `scripts/run_research_sweep.py` is the real-model launch. Four topology-local Structs (ReadRequest, Finding, Gaps, Synthesis) declared here — application event kinds, per-topology, exactly as code_review declares CritiquePosted/VerdictRendered (NOT the locked lifecycle vocabulary).

## artifact contract

### Files created

- `src/substrate/topologies/workflows/research_sweep.py` — `research_sweep_topology` + `gather` + the four Structs + the seeder/reader/critic/synthesizer factories.
- `scripts/run_research_sweep.py` — argparse (`--question`, `--paths`/`--dir`, `--model`); real Ollama reader/critic/synthesizer; runs to a record.
- `tests/test_research_sweep.py` — the observation contract.

### Files modified

- `src/substrate/topologies/workflows/__init__.py` — export `research_sweep_topology`.
- `process/WORKING_AGREEMENT.md` — canonical-home row.

### Content assertions

- `gather(paths)` reads the files read-only, bounded per file; a missing path is a clear error, not a crash.
- The topology fans one reader per document, fires the critic once all N findings land, then the synthesizer once — map → critique → reduce.
- ruff + mypy clean.

### Command exit codes

- `uv run python -m pytest tests/test_research_sweep.py -q` returns 0
- `PATH="$PWD/.venv/bin:$PATH" uv run python -m pytest -q` returns 0 (full suite, mypy on PATH)

## observation contract

`pass_kind: functional` — required. CI (DeterministicResponder, no network):

- N documents → N Finding (one per reader, each over its own document).
- The critic fires ONCE after all N findings → Gaps.
- The synthesizer fires ONCE after Gaps → Synthesis.
- `result.status == "finalised"`; the record ends on RunFinalised; no lifecycle-kind collisions.
- `gather` is read-only (the files/dir are unchanged after a run).

### Walkthrough (real models — named, human-run)

`run_research_sweep.py --dir <a docs folder> --question "..." --model kimi-k2.6:cloud` — reads each document, extracts findings, names gaps, synthesizes an answer; kept as the W1.3 walkthrough record. Honesty split: CI proves the wiring; the human judges whether the synthesis is good.

## done criteria

research_sweep gathers a real document set, fans a reader over each, runs a completeness critic, and synthesizes an answer through a topology authored from primitives, on a replayable record. CI green; full suite green with mypy on PATH; the real-model walkthrough demonstrated once.

## notes

- Auto-within-phase; follows the W1 pattern (gather real input → a topology → a run script) — the third instance, this one authored fresh because map-reduce has no existing whole to compose.
- Keep `gather` bounded per file (the byte-cap lesson) so a big corpus doesn't blow the reader prompt.
- Completeness critic is technique "completeness critic" (the what-did-we-miss pass) made a real producer, not folded into the synthesis prompt — the gap pass is visible on the record.
- W1 closes after this; sprint 140 is W1.INT (the three demonstrated end-to-end, kept walkthroughs, a docs page) then phase W2 (delegate).
