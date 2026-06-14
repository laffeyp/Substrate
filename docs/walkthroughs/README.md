# Reference-topology walkthroughs (R-1 / R-2 / R-3)

Each reference topology (product §8) is **dual-mode**:

- **CI mode** — deterministic stand-in Producers. Exercises the *wiring*; runs on every commit
  (`tests/test_reference.py`). It does NOT stand in for the demonstration: the spec is explicit
  that CI mode alone "sanitizes away the thing each topology exists to demonstrate."
- **Walkthrough mode** — REAL local LLMs via the openai-compat adapter. Shows the *claim*: real
  adjudication (R-1), a real model's structured-error behavior (R-2), real code streaming with
  cross-chunk overlap (R-3). Run on demand; transcripts below.

## Committed records you can read back

The deterministic **CI-mode** records for all three topologies are committed under
`docs/walkthroughs/records/` — they are small, reproducible, and ARE the durable replayable
artifact the product is about. From a fresh checkout you can read one back directly:

```
uv run substrate tail    docs/walkthroughs/records/r1
uv run substrate inspect docs/walkthroughs/records/r1 --seq 14   # the adjudicate firing + its inputs
uv run substrate replay  docs/walkthroughs/records/r2 --level 2
uv run substrate tail    docs/walkthroughs/records/r3
```

`r1` is the ensemble→adjudicator run; `r2` is the error-cascade run paused on `RetryExhausted`
then resumed (one continuous record across the pause); `r3` is the composed code-synth outer run
(`r3-inner` is its embedded inner record). Regenerate them with
`uv run python scripts/gen_walkthrough_records.py`. (Each record's wall-clock `t` field varies
per generation — it is excluded from D-8 log-equivalence; the event SEQUENCE is what is stable.)

## Running the real-LLM walkthroughs

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

Each prints what it showed and the record root; inspect the record it writes with
`uv run substrate tail ./walkthrough/r1`.

## Illustrative transcripts (local Ollama)

The blocks below are transcripts from a local Ollama run — illustrative of what the real-LLM
mode produces, not the committed artifact (those are the CI-mode records above). Reproduce them
with the `openai-compat` extra and the commands above; exact model text will vary run to run.

### R-1 Ensemble + adjudicator — *real adjudication, disagreement, AND cancellation*

3 fast + 2 lingering weak `llama3.2:1b` members (temperature 0.9) answer an OPEN judgment
question — "In one word, what is the most important quality in a leader?" — chosen because weak
models genuinely DISAGREE on it (unlike "2+2", where every model says "4" and the ensemble is
pointless). A Bus-view predicate ("≥3 answers") fires the `qwen2.5-coder` adjudicator (Once)
once the 3 fast members answer; the 2 lingering members are still running, so cancel-all-others
cancels them on the adjudicator's completion — `substrate.ProducerCancelled` lands on R-1's OWN
record.

```
R-1 status: finalised
  Candidate m0: 'Charisma'
  Candidate m1: 'Vision'
  Candidate m2: 'Integrity'
  VERDICT: m2 -> 'Integrity'
  CANCELLED (lingering loser): member-slowA
  CANCELLED (lingering loser): member-slowB
  distinct answers among candidates: 3 of 3
```

What it shows: the weak members genuinely disagreed (3 distinct answers of 3 — Charisma / Vision
/ Integrity); the Bus-view "≥quorum" predicate fired the adjudicator exactly once after the
quorum accumulated; the real adjudicator model judged the candidates and chose one (Integrity);
and because the 2 slow members were still running at adjudication, cancel-all-others cancelled
them — two real `substrate.ProducerCancelled` events on this run's own log. The marquee R-1
behavior (adjudication + disagreement + live cancellation) on R-1's own record.

### R-2 Pipeline: structured error cascade + halt-with-resume — *a real model's error behavior end to end*

R-2 runs on a PERSISTENT bus. parser → (real `llama3.2:1b` transform), PerEvent per row, with
three seeded conditions: row 1 a RECOVERABLE fault (first transform attempt emits an undeclared
kind → `ProducerEmittedInvalidEvent`, then a retry-with-enrichment re-fire succeeds); row 2 an
UNRECOVERABLE fault (every attempt invalid → retry budget exhausted → `RetryExhausted`); row 3 a
malformed row whose input_builder raises → `InputBuildFailed`. `RetryExhausted` trips a
`pause_await_input` policy, so the run PAUSES; a `substrate resume` (here `Runtime.resume`)
injects an `OperatorOverride` that fires a recovery Producer and the run finalises — on the SAME
seq sequence, across a process boundary.

```
R-2 (run-to-pause) status: paused
  INPUT-BUILD-FAILED trigger=to-transform: ValueError('malformed row 3: cannot build transform input')
  Transformed row=0 attempt=1: 'TRANSFORM'
  INVALID-EMISSION row=1 reason=unknown_kind
  INVALID-EMISSION row=2 reason=unknown_kind
  Transformed row=1 attempt=2: 'TRANSFORM'
  INVALID-EMISSION row=2 reason=unknown_kind
  RETRY-EXHAUSTED row=2 after 2 attempt(s)
  TERMINATION: pause-await-input (resume_condition=OperatorOverride)
R-2 (resume) status: finalised | run_id continuous: True
  RECOVERED row=2 by=operator
  continuous seq across pause: True (len 43)
```

What it shows, every mechanism on R-2's own log: (1) a REAL invalid emission (an undeclared
kind) became `substrate.ProducerEmittedInvalidEvent` — no fabricated event reached the bus;
(2) the retry Trigger, enriched via a Route carrying the failure reason, re-fired the transform
and row 1 recovered on attempt 2; (3) row 2's repeated invalidity exhausted the retry budget and
escalated to `RetryExhausted`; (4) row 3's input_builder raised and the kernel recorded
`InputBuildFailed` instead of crashing; (5) `RetryExhausted` paused the run, and a fresh
`Runtime.resume` injected the operator override, ran the recovery, and finalised with a single
unbroken seq sequence across the pause boundary — the persistent-bus halt-with-resume. (The
model uppercasing — `'TRANSFORM'` — is authentic small-model behavior, faithfully recorded.)

### R-3 Code synthesis with overlap, composed — *a checker firing per declaration as the writer streams*

A real `qwen2.5-coder` writer emits two functions; the output is chunked so declarations span
chunk boundaries (overlap). The inner pipeline (writer → buffer-View chunk-boundary predicate →
checker → typecheck → ArtifactReady) runs as an EMBEDDED SUBSTRATE exporting only `ArtifactReady`
onto the outer run.

```
R-3 status: finalised | chunks: 3 | complete defs: 2
  inner Declarations: 2
  crossed to outer (OuterArtifact): 1
  inner kinds leaked to outer: False
```

Code the writer streamed (real model output):

```python
def add(a, b):
    return a + b

def mul(a, b):
    return a * b
```

What it shows: the chunk-boundary predicate fired the checker Producer once per COMPLETE
declaration (2) **while the writer was still streaming** — even though `add()` spanned multiple
chunks (overlap), it fired exactly once; the composition boundary exported ONLY the mapped
`ArtifactReady` (→ `OuterArtifact`) — no inner `CodeChunk` / `Declaration` / `TypecheckOk` /
`substrate.*` kind crossed to the outer bus; the inner record is complete and independent at its
own root.

The checker and typecheck stages are **deterministic stand-ins**, not a real toolchain: the
"AST" detector is a `def`-block splitter, and the typecheck stage runs a cheap, deterministic
`ast.parse()` (emitting `ok=False` on a SyntaxError) — it does NOT run mypy/pytest/a subprocess.
R-3 demonstrates the *wiring* (a checker firing per complete declaration as the writer streams);
swap a real type/test checker into the typecheck Producer in your own topology.

## Honesty note

Real small local models are imperfect (see R-2's uppercasing). That is the point: the
walkthrough shows the substrate faithfully recording what real models actually did, including
their mistakes — every answer, every transform, every declaration is on the log, citable. CI
mode exercises the wiring deterministically; the walkthrough shows the substrate orchestrating
and recording *real* model behavior.
