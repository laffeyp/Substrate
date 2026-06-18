# Demo — what Substrate does, on real runs

This is a guided read of Substrate working. Every block below is genuine output
from the committed reference records, reproducible with `bash demo.sh` (or the
individual commands shown). The Producers in these records are deterministic
stand-ins — no LLM, no network. Every block here is the committed record read back,
so it is identical for everyone; and re-running the topology produces the same events
in the same order on any machine — equivalent modulo run ids and timestamps (the D-8
relation), not byte-for-byte. That is the point: the record *is* the run, and you can
read it back.

A reminder of the vocabulary, since every line of output uses it:

- **Producer** — a callable that takes typed input and emits typed **Events**. An
  LLM, a parser, a transform; here, deterministic stand-ins.
- **Event** — one numbered fact on the log (e.g. `Candidate`, `Row`).
- **Trigger** — starts a new Producer when a condition over the log holds. The
  `substrate.TriggerFired` line records *what input it saw* when it fired.
- **Route** — carries data from past events into a future Producer's input.
- **TerminationPolicy** — decides when the run ends or pauses for outside input.
- Every line prefixed `substrate.*` is a **decision the runtime made**, written
  onto the same log as the data. Nothing is stranded in memory.

Each record is read with four commands: `tail` (the whole log in order),
`replay` (reconstruct state + re-verify every decision), `inspect` (provenance
queries), and `conformance` (the release gate). All cite sequence numbers.

---

## 1. Ensemble + adjudicator (R-1)

**What it shows:** several Producers running concurrently on the same question, a
Trigger that fires once enough answers are in, and structured termination that
cancels the losers.

```
$ substrate tail docs/walkthroughs/records/r1
seq=0   substrate.RunStarted        config={...vocab_version: 0.2}  run_id=01KV1VGAQQ...
seq=1   substrate.TriggerFired      factory=member-m0  firing_key=__initial__  ...
seq=2   substrate.TriggerFired      factory=member-m1  ...
seq=3   substrate.TriggerFired      factory=member-m2  ...
seq=4   substrate.TriggerFired      factory=member-m3  ...
seq=5   substrate.TriggerFired      factory=member-m4  ...        # five members start
seq=6   substrate.ProducerStarted   producer={kind: member-m0 ...}
seq=7   Candidate                   answer=Paris  member=m0
seq=8   substrate.ProducerCompleted producer={kind: member-m0 ...}
seq=10  Candidate                   answer=Nice   member=m1
seq=13  Candidate                   answer=Nice   member=m2
seq=14  substrate.TriggerFired      factory=adjudicator  trigger_id=adjudicate
                                    resolved_input={candidates: [Paris/m0, Nice/m1, Nice/m2]}
seq=17  Candidate                   answer=Paris  member=m3        # m3, m4 still running
seq=20  Candidate                   answer=Lyon   member=m4        #   concurrently with adjudicator
seq=23  Verdict                     answer=Paris  chosen=m0
seq=25  substrate.TerminationMatched decision=finalise-run  policy=any_of(cancel_all_others,all_completed)
seq=26  substrate.RunFinalised
```

The thing to notice is **seq=14**: the adjudicator's Trigger fired the moment
three candidates were on the log, and its `resolved_input` records *exactly* the
three it saw (`Paris/m0, Nice/m1, Nice/m2`) — while members m3 and m4 were still
running (their candidates land at seq 17 and 20). Concurrency and the
"once-enough-are-in" condition are both visible in the log, not inferred. The
adjudicator (a deterministic stand-in here) emits its `Verdict` at seq=23, and
the run finalises under a composed policy.

Replaying it reconstructs every intermediate state and re-checks every decision's
input against its recorded hash:

```
$ substrate replay docs/walkthroughs/records/r1 --level 2
[OK] Level 2 replay successful.
Frames replayed: 27
Decisions verified: 6 (all inputs verified by hash)
```

---

## 2. Retry / escalate / pause-for-operator (R-2)

**What it shows:** a malformed input that can't even be built, an invalid emission
that gets quarantined, the failure reason routed back into a retry, a bounded
retry that escalates, and a run that *pauses* to wait for an operator and then
resumes — all on one log.

```
$ substrate tail docs/walkthroughs/records/r2
seq=3   Row                              raw=alpha  row=0
seq=7   Row                              raw=gamma  row=2
seq=9   Row                              raw=delta  row=3
seq=10  substrate.InputBuildFailed       error=ValueError('malformed row 3...')  trigger_id=to-transform
seq=13  Transformed                      attempt=1  row=0                         # row 0: clean
seq=16  substrate.ProducerEmittedInvalidEvent  raw_payload={junk: <<invalid>>, row: 1}  reason=unknown_kind
seq=17  substrate.InjectionApplied       route_id=failure-context  target_input_slot=failure
seq=18  substrate.TriggerFired           trigger_id=retry  resolved_input={attempt: 2, prior_reason: unknown_kind, row: 1}
seq=26  Transformed                      attempt=2  row=1                         # row 1: recovered on retry
seq=29  substrate.ProducerEmittedInvalidEvent  raw_payload={<<persistently-invalid>>, row: 2}  reason=unknown_kind
seq=31  substrate.TriggerFired           trigger_id=escalate  resolved_input={attempts: 2, reason: unknown_kind, row: 2}
seq=34  RetryExhausted                   attempts=2  reason=unknown_kind  row=2
seq=35  substrate.TerminationMatched     decision=pause-await-input  resume_condition=OperatorOverride
seq=36  OperatorOverride                 note=operator approved manual recovery  row=2
seq=37  substrate.TriggerFired           trigger_id=on-override  resolved_input={by: operator, row: 2}
seq=39  Recovered                        by=operator  row=2
seq=41  substrate.TerminationMatched     decision=finalise-run
seq=42  substrate.RunFinalised
```

Four distinct failure handlings, each legible:

- **seq=10 `InputBuildFailed`** — row 3 was so malformed the transform's input
  couldn't be constructed. Recorded, not crashed.
- **seq=16–26** — row 1's Producer emitted an event of unknown kind. The runtime
  quarantines it (`ProducerEmittedInvalidEvent`), a **Route** injects the failure
  reason back as input (`InjectionApplied` → `target_input_slot=failure`), and the
  `retry` Trigger fires *carrying that reason* (`prior_reason: unknown_kind`). The
  retry succeeds at seq=26.
- **seq=29–34** — row 2 fails again on retry; the bounded policy gives up and the
  `escalate` Trigger fires, producing `RetryExhausted`.
- **seq=35–41** — the run **pauses** (`pause-await-input`) with a named resume
  condition. Once an `OperatorOverride` event arrives (seq=36), the `on-override`
  Trigger spawns a recovery Producer, and the run finalises.

```
$ substrate replay docs/walkthroughs/records/r2 --level 2
[OK] Level 2 replay successful.
Frames replayed: 43
Decisions verified: 8 (all inputs verified by hash)
```

---

## 3. Streaming synthesis + concurrent checking (R-3 inner)

**What it shows:** one Producer streaming output while another fires per completed
unit *as it arrives*, running alongside the still-streaming first one. (R-3's
outer run wraps this as an embedded sub-run — composition — and emits a single
`OuterArtifact`; the interesting part is the inner run.)

```
$ substrate tail docs/walkthroughs/records/r3-inner
seq=3   CodeChunk      text="def add(a, b):"
seq=4   CodeChunk      text="    return a + b"
seq=5   substrate.TriggerFired  factory=ast  firing_key=0  trigger_id=on-declaration
                       resolved_input={index: 0, source: "def add(a, b):\n    return a + b"}
seq=6   CodeChunk      text="def mul(a, b): ..."         # writer keeps streaming
seq=7   substrate.TriggerFired  factory=ast  firing_key=1  trigger_id=on-declaration
seq=10  Declaration    index=0  source="def add..."
seq=11  substrate.TriggerFired  trigger_id=to-typecheck
seq=18  TypecheckOk    index=0  ok=True
seq=22  TypecheckOk    index=1  ok=True
seq=25  ArtifactReady  declarations=1
seq=28  substrate.RunFinalised
```

At **seq=5** the `on-declaration` Trigger fired for the first complete
declaration (`firing_key=0`) — and then at **seq=6** the writer emitted its next
chunk. The checker started working on declaration 0 *while* the writer was still
producing declaration 1. Each declaration flows independently through
`ast → typecheck → artifact`. The per-declaration keys (`firing_key=0`, then `1`)
are how the Trigger fires once per unit rather than once per event.

```
$ substrate replay docs/walkthroughs/records/r3-inner --level 2
[OK] Level 2 replay successful.
Frames replayed: 29
```

---

## 4. Provenance — reading causality back off the log

Because every decision is on the log, you can ask *why* any Producer exists and
get the full causal chain back to the start of the run — no tracing, no guessing:

```
$ substrate inspect docs/walkthroughs/records/r3-inner \
    --producer "artifact[01KV1VGAYWVBTJ35V5Q54W7A72]" --ancestry
artifact[01KV1VGAYWVBTJ...]   caused_by TriggerFired at seq=19 (trigger=to-artifact)
typecheck[01KV1VGAYNJN...]    caused_by TriggerFired at seq=11 (trigger=to-typecheck)
ast[01KV1VGAYK13...B]         caused_by TriggerFired at seq=5  (trigger=on-declaration)
writer[01KV1VGAYK13...A]      caused_by RunStarted    at seq=1  (trigger=__initial__)
```

`inspect --why` gives the single proximate cause; `--ancestry` (above) walks it
all the way to `RunStarted`. Both cite sequence numbers, so every claim is
checkable against `tail`.

---

## 5. The release gate — conformance suite

The reference runs above show the runtime doing things. The conformance suite is
the standing check that it does the *required* things: one canonical topology per
spec property, run as the v1.0 release gate.

```
$ substrate conformance --no-perf
Running 17 conformance checks (product §7)...
  [01/17] Retry enrichment            ... PASS
  [02/17] Single legal cascade        ... PASS
  [03/17] Backpressure liveness       ... PASS
  [04/17] Invalid-emission cascade    ... PASS
  [05/17] Quiescence                  ... PASS
  [06/17] Replay round-trip           ... DEFERRED (spec-amended A1.1)
  [07/17] Export boundary             ... PASS
  [08/17] Quarantine visibility       ... PASS
  [09/17] Determinism                 ... PASS
  [10/17] Persistent-bus locking      ... PASS
  [11/17] Provenance closure          ... PASS
  [12/17] View-at fidelity            ... PASS
  [13/17] Divergence localization     ... PASS
  [14/17] Diagnostic invariance       ... PASS
  [15/17] Performance floor (N-PERF-1)... SKIPPED (--no-perf)
  [16/17] Torn-tail recovery          ... PASS
  [17/17] InputBuildFailed visibility ... PASS

15 passed, 0 failed, 1 deferred, 1 skipped. No check FAILED.
```

Two honest notes, both deliberate:

- **Check 6 (replay round-trip) is DEFERRED, not passed.** Level 2 replay (state +
  decision reconstruction, verified by hash) ships and passes; full byte-for-byte
  re-execution (Level 3b) is post-1.0 under spec amendment A1.1. The suite reports
  it as deferred rather than quietly counting it green.
- **Check 15 (performance floor) is hardware-dependent**, so it's excluded from CI
  (`--no-perf`) and run on controlled hardware. The floor is 40,000 appends/sec; the
  shipping implementation measures ~56,000 on commodity hardware and **passes**. The
  dominant per-append cost is the RFC-8785 canonical-JSON encode, which is
  correctness-critical — the 100k floor in earlier drafts predated that encode and
  was revised down to 40k with a recorded reason (product amendment A2). The number
  moves with the host, which is exactly why it isn't a CI gate; the correctness
  checks (1–14, 16–17) are hardware-independent and pass everywhere.

Backing all of this: the full test suite passes (`uv run python -m pytest` — note
the `python -m`, so the project's pinned pytest is used rather than whatever
`pytest` resolves on PATH), and the public-API import boundary is enforced by
`import-linter` in CI on every push.

---

## Run it yourself

```
uv venv --python 3.12 && uv pip install -e ".[dev]"
bash demo.sh                       # the whole walk, against committed records
uv run python -m pytest            # the full suite (~300 tests)
uv run substrate conformance       # the release gate (includes the perf floor)
```

The committed records are deterministic CI-mode artifacts (stand-in Producers).
To see the same topologies driven by a real local LLM, see
`docs/walkthroughs/README.md`.
