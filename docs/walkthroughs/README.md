# Reference-topology walkthroughs (R-1 / R-2 / R-3)

Each reference topology (product §8) is **dual-mode, and both modes are required**:

- **CI mode** — deterministic stand-in Producers. Proves the *wiring*; runs on every commit
  (`tests/test_reference.py`). It does NOT stand in for the demonstration: the spec is
  explicit that CI mode alone "sanitizes away the thing each topology exists to demonstrate."
- **Walkthrough mode** — REAL local LLMs via the openai-compat adapter. Proves the *claim*:
  real adjudication (R-1), a real model's structured-error behavior (R-2), real code synthesis
  with cross-chunk overlap (R-3). Run before each release; documented here.

## Running the walkthroughs

Prereqs: the `openai-compat` extra (`uv sync --extra openai-compat`) and a local
[Ollama](https://ollama.com) at `http://localhost:11434` with these LOCAL models pulled
(cloud models are deliberately avoided — this runs on your machine):

```
ollama pull llama3.2:1b
ollama pull huihui_ai/qwen2.5-coder-abliterate:7b
```

Then:

```
uv run python -m substrate.reference.walkthrough r1 ./walkthrough/r1
uv run python -m substrate.reference.walkthrough r2 ./walkthrough/r2
uv run python -m substrate.reference.walkthrough r3 ./walkthrough/r3 ./walkthrough/r3-inner
```

Each prints what it demonstrated and the record root; inspect the record with
`uv run substrate tail ./walkthrough/r1` or `uv run substrate inspect ./walkthrough/r1 --why ...`.

## Recorded runs (2026-06-13, local Ollama)

These are ACTUAL outputs from real model runs on the development machine — not stubs, not
edited. Small inputs (a demonstration, not a benchmark).

### R-1 Ensemble + adjudicator — *demonstrates real adjudication*

4 weak `llama3.2:1b` members answer "What is 2+2?"; a Bus-view predicate ("≥3 answers") fires
the `qwen2.5-coder` adjudicator (Once), which judges the candidate answers and picks one.

```
R-1 status: finalised
  Candidate m0: '4'
  Candidate m1: '4'
  Candidate m2: '4'
  Candidate m3: '4'
  VERDICT: m0 -> '4'
```

What it proves: the Bus-view "≥quorum" predicate fired the adjudicator exactly once after the
quorum of real candidate answers accumulated; the real adjudicator model judged them and
emitted a Verdict; the run finalised. (On this fast question all four members completed before
adjudication, so cancel-all-others had no live candidates to cancel — the cancellation wiring
is exercised separately in `tests/test_cancel_others.py`; a slower/larger ensemble would show
live cancellations on the log as `substrate.ProducerCancelled`.)

### R-2 Pipeline with structured error cascade — *demonstrates a real model's error behavior*

parser → (real `llama3.2:1b` transform) → validator, PerEvent per row; row 1 is the seeded
fault (empty transform output → validation failure).

```
R-2 status: finalised
  Parsed: {'row': 0, 'value': 'alpha'}
  Parsed: {'row': 1, 'value': 'beta'}
  Parsed: {'row': 2, 'value': 'gamma'}
  Transformed: {'out': 'TRANSFORM', 'row': 0}
  Transformed: {'out': '', 'row': 1}
  Transformed: {'out': 'GAMMA', 'row': 2}
  Validated: {'ok': True, 'row': 0}
  Validated: {'ok': False, 'row': 1}
  Validated: {'ok': True, 'row': 2}
```

What it proves: the parser→transform→validator chain ran per row through PerEvent Triggers; the
seeded fault row (1) produced an empty transform output and failed validation while the others
passed — the structured outcome is entirely on the log, row by row. (Note row 0's `TRANSFORM`:
the small model misread the instruction and uppercased a word from the prompt — authentic
real-model behavior, exactly the kind of thing CI's clean stub hides and the walkthrough
surfaces. The record captures what the model actually did, faithfully.)

### R-3 Code synthesis with overlap, composed — *demonstrates real synthesis + overlap + composition*

A real `qwen2.5-coder` writer emits two functions; the output is chunked into ~30-char pieces
so declarations span chunk boundaries (overlap). The inner pipeline (writer → buffer-View
chunk-boundary predicate → AST → typecheck → ArtifactReady) runs as an EMBEDDED SUBSTRATE
exporting only `ArtifactReady` onto the outer run.

```
R-3 status: finalised | chunks: 3 | complete defs: 2
  inner Declarations: 2
  crossed to outer (OuterArtifact): 1
  inner kinds leaked to outer: False
```

Generated code (real model output):

```python
def add(a, b):
    return a + b

def mul(a, b):
    return a * b
```

What it proves: the chunk-boundary predicate fired the AST producer once per COMPLETE
declaration (2) even though `add()` spanned multiple 30-char chunks (overlap); the composition
boundary exported ONLY the mapped `ArtifactReady` (→ `OuterArtifact`) — no inner `CodeChunk` /
`Declaration` / `TypecheckOk` / `substrate.*` kind crossed to the outer bus; the inner record
is complete and independent at its own root.

## Honesty note

Real small local models are imperfect (see R-2 row 0). That is the point: the walkthrough
shows the substrate faithfully recording what real models actually did, including their
mistakes — every answer, every transform, every declaration is on the log, citable. CI mode
proves the wiring deterministically; the walkthrough proves the substrate orchestrates and
records *real* model behavior.
