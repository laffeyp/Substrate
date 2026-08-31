# Substrate — UI Design Handoff

**For:** the designer building Substrate's UI.
**Assumes:** no prior knowledge of Substrate. You may also receive images for visual
direction; this document is the *substance* — what the thing is, who uses it, what it
shows, and the rules a correct design must respect. The images decide how it looks; this
decides what it has to mean.

Read it once top to bottom. It is ordered so each idea has what it needs before it arrives.
There is a worked example near the end (§9) — if you learn better from a concrete case, read
that first, then come back to the top.

A note on the form factor: the visual form (web, desktop, terminal) is deliberately left
open. Design for the *content and the jobs* described here; the medium follows from the
images and the product owner's call, not from this document.

---

## 1. The one-paragraph mental model

Substrate runs many independent computations at once — language models, scripts, parsers,
simulators — and coordinates them through a single shared timeline. You don't write a
flowchart that calls them in order. Instead, each computation reacts to what has already
happened: when the timeline contains the right things, a new computation starts
automatically. Every step — every start, every result, every decision to spawn something
new, every failure — is written down as a typed entry on that one timeline, in order,
permanently. **That written-down timeline is the product.** You watch it happen, you read it
back afterward, you replay it, you compare two of them. The UI is the window onto that
timeline.

If you take one thing from this document: **Substrate does not have a UI that controls a
hidden process. It has a UI that reads a permanent record.** The record is the truth. The
design's central job is to make a fast, concurrent, typed stream of events *legible* to a
human — live as it happens, and later as a finished artifact.

---

## 2. Five things that make this unlike what you might expect

These are the conceptual jumps. A design that misses them will feel wrong to the people who
use this.

**2.1 There is no central plan being executed.** Most "workflow" tools show a diagram that
runs top to bottom. Substrate is the opposite: behavior *emerges* from independent
computations reacting to the shared timeline. Nobody scripted "now run the judge" — the judge
started because the timeline came to hold three critiques, which satisfied a standing
condition. The structure is reactive and grows as the run proceeds. So a static diagram is
only half the story; the other half is the timeline filling in and new things appearing in
response.

**2.2 One ordered timeline, many things happening at once.** Everything that happens gets a
position number (a sequence number, "seq") on a single ordered list. But the things being
recorded are running *concurrently* — five computations can be working simultaneously, their
results landing interleaved on the list. The design lives in this tension: the data is one
strictly-ordered list, but the reality it describes is parallel. Both readings matter — the
ordered story (what happened, in order) and the concurrent picture (what was running at
once). Don't flatten the parallelism away, and don't lose the order.

**2.3 The product is an artifact, not a session.** When a run ends, you have a *record* — a
file you can reopen, re-read, replay step by step, and compare against another run. It is not
a log that scrolls away. It can be cited: every claim the UI makes points back to a specific
numbered entry. Think "a document you can inspect and diff," not "a console that streams and
is gone."

**2.4 Everything is typed, and nothing important is silent.** Every entry is a structured,
named event — not a line of free text. Crucially, *failures are events too*: a computation
that crashed, a result that was rejected as malformed, a computation that got cancelled — all
of these are recorded as first-class, named entries. There is no hidden failure. A core
product value: a run that finished but did something broken must *look* broken in the UI, not
read as a clean success. (More in §7.)

**2.5 It is deterministic and replayable.** The same record always reads the same way. The UI
itself is a pure lens — it shows what the record says and never invents, guesses, or hides.
Two people opening the same record see the same thing.

---

## 3. The vocabulary (the nouns you will render)

Substrate is built from exactly eight words. They are a fixed contract: the UI should use
*these* words, not invented synonyms. Do **not** introduce "agent," "workflow," "step,"
"node," "task," or "job" — those carry the wrong mental model and the project deliberately
avoids them. Here is each word in plain terms, with the running example of an automated
code review.

- **Producer** — a computation that takes an input and emits a stream of results. (e.g. one
  reviewer, or the judge.) It's the active thing. It has no memory or goals of its own; it
  runs, emits, and ends.
- **Bus** — the single ordered timeline every result is written to. The one source of truth.
  (Also called the *run record* once persisted to disk.)
- **Event** — one typed entry on the Bus: it has a position (seq), a kind (its type, e.g.
  `CritiquePosted`), the Producer that emitted it, and a structured payload. The atom of
  everything.
- **View** — a running summary of the timeline that conditions can read. (e.g. "how many
  critiques have been posted so far.") It updates as events land.
- **Predicate** — a condition over Views. (e.g. "at least three critiques exist.")
- **Trigger** — a standing rule: *when* a matching event lands *and* a Predicate holds, start
  a named Producer with a computed input. (e.g. "when critiques reach three, start the
  judge.") This is the mechanism by which the run grows itself.
- **Route** — carries data from one event forward into the input of a Producer that a Trigger
  later starts. (e.g. stage a failure reason so the retry can see it.)
- **TerminationPolicy** — the rule that decides when the whole run ends. (e.g. "stop once the
  judge renders a verdict, and cancel any reviewers still running.")
- **Topology** — the whole assembled design: which Producers exist, the Triggers, Routes,
  Views, and TerminationPolicy. The thing an author writes; the thing a run is an instance of.

Two more terms you'll see constantly:

- **Run record** — the persisted Bus for one run: the ordered list of events, plus a
  manifest describing the topology and a store for any large payloads. This is the file the
  UI opens.
- **Lifecycle events** — the runtime's own bookkeeping entries, all prefixed `substrate.`
  (e.g. `substrate.RunStarted`, `substrate.TriggerFired`, `substrate.ProducerCompleted`,
  `substrate.ProducerFailed`, `substrate.TerminationMatched`, `substrate.RunFinalised`).
  Distinct from the *application events* a topology defines (`CritiquePosted`,
  `VerdictRendered`, etc.). The catalogue is in the appendix.

---

## 4. What the user is actually looking at

The raw material is a run record: an ordered list of typed events. Here is a real one,
rendered as prose (Substrate already ships a "narration" view that turns the record into a
readable account — this is a good seed for the UI's "read it as a story" surface, though the
UI can do far more than linear prose, see §6). Payload detail is lightly trimmed here for
readability; the seqs and beats are exact:

```
seq  0  Run started.
seq  1  Initial trigger starts reviewer-security.
seq  2  Initial trigger starts reviewer-performance.
seq  3  Initial trigger starts reviewer-style.
seq  4  Initial trigger starts reviewer-correctness.
seq  5  Initial trigger starts reviewer-clarity.
seq  7  reviewer-security    -> CritiquePosted (role=security, severity=4)
seq 10  reviewer-performance -> CritiquePosted (role=performance, severity=2)
seq 13  reviewer-style       -> CritiquePosted (role=style, severity=1)
seq 14  Trigger adjudicate fired -> starts judge
seq 19  judge -> VerdictRendered (decision=block, n_critiques=3)
seq 21  Termination matched: cancel-others
seq 22  reviewer-correctness cancelled
seq 23  reviewer-clarity cancelled
seq 24  Termination matched: finalise-run
seq 25  Run finalised.
```

Read that and you can see the whole shape: five reviewers start at once; three finish and
post critiques; the third critique satisfies the "at least three" condition, so the judge
starts; the judge blocks; the run cancels the two reviewers still working and ends. **That
legibility — making this graspable at a glance — is the design problem.**

Each event also carries machine detail the UI can surface on demand: the exact input a
Producer ran on (by content hash), the precise condition that fired a Trigger, the parent
Producer that led to this one. This is what powers provenance ("why did the judge exist?" —
answer: the `adjudicate` Trigger fired at seq 14 because the critique count reached three).

A run record can be **short** (a dozen events) or **long** (many hundreds). The design must
scale: filtering, summarizing, and the distinction between "the plot" (the load-bearing
beats) and "every single frame" are essential, not optional.

---

## 5. Who uses this, and what they are trying to do

Three people, often the same person at different moments:

**The Observer** — watching a run happen, or reading a finished one, to understand *what it
did*. Their questions: What's happening right now? What did each Producer produce? Did it
work? What was the outcome? They want the story, legibly, with the concurrency visible.

**The Debugger** — something went wrong, or surprising, and they need to know *why*. Their
questions: Why did this Producer start? What input did it run on? Where did it fail? What was
different between this run and the one that worked? They live in provenance and comparison.

**The Author** — designing or adjusting a Topology. Their questions: What Producers, Triggers,
Routes, and Views make up this design? If I change a condition, what happens? (Authoring today
happens in code; bringing it into the UI is the ambitious end of the scope — see §10.)

Their jobs, concretely:

1. **Watch a run unfold live** — the stream of events as they land, with what's currently
   running made obvious. (The runtime supports attaching to a run *as it is being written*.)
2. **Read a finished run as a story** — the legible account of what happened, start to end.
3. **See the structure** — the Topology as a graph: Producers as nodes, the Triggers and
   Routes that connect them as edges.
4. **See the run as it grew** — the dynamic counterpart: Producers appearing over time,
   running concurrently, ending. A timeline or an animated graph, not a static diagram.
5. **Answer "did it work?"** at a glance — outcome and health, with failures impossible to
   miss (a finished-but-broken run must look broken — see §7).
6. **Inspect one thing** — pick a Producer or event and trace its provenance: why it exists,
   what it ran on, the causal chain back to the start of the run.
7. **Compare two runs** — what diverged, and where (by seq).
8. **Light control** — launch one of the bundled topologies; pause a run that's waiting on
   external input and feed it that input; resume.
9. **Author (full vision)** — assemble and wire a Topology in the UI.

---

## 6. The probable surfaces (form-agnostic)

Roughly one surface per job in §5. These are *what each surface must accomplish*, not a
prescription of layout — the images and the medium decide the visual form.

One thing the UI does **not** render directly: **Views and Predicates are internal.** A View is
a running summary of the timeline; a Predicate is a condition over Views that decides whether a
Trigger fires. You render their *effect*, not the things themselves — "a condition held, so a
Trigger started this Producer" appears in the live stream and the provenance surface, not as a
separate "View" screen.

- **The live run / event stream.** Events arriving in order as the run proceeds. The hard part
  is conveying concurrency: several Producers running at once, their outputs interleaving. The
  user needs to feel "five things are working" without losing the ordered thread. Suppress
  routine bookkeeping by default; surface the plot; make every failure jump out. **Pace:** events
  arrive at *human* speed. Substrate is bound by the latency of the computations it runs —
  typically language models — so a live run produces a few events per second, with short bursts
  when several Producers land at once. Design the live view for watchability and legible bursts,
  not for a high-rate firehose.

- **The story view (finished run).** The same content at rest, readable end to end — the
  narration. Expandable from "the plot" to "every frame." Every line is anchored to a seq the
  user can pivot from into detail.

- **The structure graph (the Topology).** The static design: Producer kinds as nodes; Triggers
  ("on this event, when this holds, start that") and Routes ("carry this forward") as the
  edges. This is how someone understands *what a topology can do* before or without running it.

- **The run-as-graph / timeline (the dynamic).** The structure coming alive: instances of
  Producers appearing as Triggers fire, running in parallel, completing, being cancelled. This
  is where concurrency and causality become visible — arguably the signature view, and the one
  a plain list or plain diagram can't deliver.

- **The provenance / "why" detail.** For a selected Producer or event: its cause (the exact
  Trigger firing and condition), the input it ran on, its parent, the chain back to the run's
  start. Reads like a focused inspector.

- **The outcome / health summary.** "Did it work?" answered honestly and immediately:
  finished vs. finished-with-failures vs. paused-waiting; counts of what ran, succeeded,
  failed, was cancelled; what the run actually produced. (See §7 — this surface is where the
  "finished isn't the same as worked" rule is won or lost.)

- **The diff.** Two runs side by side, the first point of divergence located by seq.

- **Run controls.** Launch a bundled topology; for a paused run, see what input it's waiting
  for and provide it; resume.

- **The authoring surface (full vision).** Place Producers, wire Triggers/Routes, define
  Views and the TerminationPolicy. The largest and least-settled surface; treat as the
  horizon, not the first deliverable.

---

## 7. Non-negotiable constraints (what backs every pixel)

These are not style preferences. They come from what Substrate *is*, and a design that breaks
them is wrong regardless of how it looks.

1. **Everything shown is backed by a real event with a seq.** The UI reads the record; it does
   not invent, infer, or smooth over. If the UI shows it, the user can ask "which event?" and
   get a number. This is the project's first principle: *read the record, never the runtime's
   mind.* Citations (seq numbers) are load-bearing, not decoration.

2. **Nothing consequential is silent — least of all failure.** Failures, rejected outputs, and
   cancellations are events, and the UI must *show* them, never swallow them. The sharpest
   version of this: **a run that finished while something inside it failed must look broken at
   first glance, not green.** A summary whose headline says "finished" and buries the failure
   three lines down is a bug, not a nuance. "Finished" and "worked" are different facts; the UI
   must distinguish them everywhere it reports outcome.

3. **Honor the concurrency.** Many Producers run at once. Don't force the run into a false
   single-file narrative where the ordering implies causation that isn't there. The seq order
   is real, but so is the parallelism; the design has to hold both.

4. **Use the eight words.** Producer, Bus, View, Predicate, Trigger, Route, TerminationPolicy,
   Topology — plus Event, run record. No "agent / workflow / step / node / task / job." The
   vocabulary is a contract with the rest of the system; the UI's labels are part of it.

5. **No anthropomorphism.** A Producer is a computation that emits events. It does not "think,"
   "decide," "want," or "try." Even when a Producer *is* a language model, the UI describes
   what it emitted, not what it "meant." Keep the register plain and mechanical.

6. **Scale to volume.** Runs can be long. Filtering, summarizing, and the plot-vs-every-frame
   distinction are core, not afterthoughts. The default view should be the legible plot; the
   full frame-by-frame is one step away.

7. **The UI is a lens, not a controller.** Its reason to exist is comprehension. Control
   (launch, pause/resume, feed input) is a thin, explicit layer on top — never the center, and
   never something that hides what it did (every control action is itself recorded as events).

---

## 8. What already exists to build on

The UI does not need a new backend. Substrate already exposes everything above through a
public read interface and a command-line reader (the UI is "the same data, made visual"):

- **Read a record** — the full ordered list of events, or filtered by kind / Producer / seq.
- **Attach to a live run** — follow a run's events *as they are being written*, for the live
  surface. (Read-only; the UI observes the record, never the runtime's internals.)
- **Narrate** — the legible story (the §4 example), with a one-glance summary that already
  surfaces failure counts honestly (the §7.2 rule is implemented here; mirror it visually).
- **The topology structure, as a graph** — Producer kinds (with what they emit and which are
  entry points), the Trigger spawn-edges (`on` a subscription, with a firing policy, `starts` a
  Producer), the Routes, and the TerminationPolicy. Ready-made for the structure-graph surface.
- **The run-as-graph** — every Producer *instance* with its spawn link (parent + the Trigger
  that started it), its lifecycle span (start..end seq) and end status, what it emitted, and the
  run-level status (running / paused-awaiting-input / finalised). The parent links are the spawn
  forest. Ready-made for the run-as-graph / timeline surface. **Rendering concurrency — important:**
  derive "ran concurrently" from the *spawn structure* (Producers spawned by one firing, or at
  adjacent seqs, are concurrent siblings), **not** from span-overlap alone. The spans are honest,
  but in fast or deterministic runs the single writer serializes near-instant Producers so their
  spans can look sequential — render concurrency from the spawn structure and you won't flatten
  the parallelism §7.3 forbids.
- **Explain a Producer / trace its ancestry** — the provenance chain for the "why" surface.
- **View state at a point** — what a running summary held as of seq N.
- **Diff two records** — the first divergence, by seq.
- **Replay** — re-run a record and verify it reproduces, for the "trust this record" story.

Treat these as the data contract. Anything the UI shows, there is already a way to get. The
design's job is comprehension and interaction, not new computation.

---

## 9. A worked example, end to end

The automated code review, the run from §4, is the best single anchor. Here is the whole
thing in both readings the UI must support.

**As structure (the Topology, before it runs):**
- Five Producer kinds: `reviewer-security`, `reviewer-performance`, `reviewer-style`,
  `reviewer-correctness`, `reviewer-clarity`, plus `judge`.
- A View counting `CritiquePosted` events.
- One Trigger, `adjudicate`: *when* a critique lands *and* the count is at least three, start
  `judge`.
- A TerminationPolicy: when the judge renders a verdict, cancel any reviewers still running and
  end; otherwise end when everything has finished.

**As a run (what actually happened):**
- All five reviewers start at once (seq 1–5) — concurrent.
- Three of them finish and post critiques (seq 7, 10, 13) — the other two are slower.
- The third critique pushes the count to three, satisfying `adjudicate`'s condition; the judge
  starts (seq 14) — caused, traceably, by that firing.
- The judge emits a verdict of `block` (seq 19).
- The TerminationPolicy matches: cancel the two reviewers still running (seq 21–23); the policy
  then matches `finalise-run` (seq 24); the run finalises (seq 25).

A designer should be able to point at the dynamic view and see: five things start in parallel,
a sixth appears partway *because* a threshold was crossed, and two of the original five are
cut off when the outcome arrives. That causal, concurrent, emergent shape — not a left-to-right
pipeline — is what the UI exists to make obvious. Now imagine the same machinery with a
hundred Producers and several hundred events: that's the scale the design must still keep
legible.

(There are several other bundled topologies the designer can run for variety: a turn-taking
debate, a driver/navigator pair writing code, a writer/critic refinement loop, a recursive
task decomposition, an instrumented conversation. Each has the same underlying shape — Producers
reacting to a shared timeline — but a different silhouette, which is useful for pressure-testing
that a design generalizes.)

---

## 10. Scope, phasing, and division of labor

- **Scope is intentionally open here and is the product owner's call, not settled by this
  document.** The solid core is *observe + read records + light run control*. Authoring
  topologies in the UI is the ambitious full extent — design toward it as the horizon, but do
  not assume it is the first thing built. A natural progression: (1) read a finished record
  legibly; (2) watch a run live; (3) provenance and diff; (4) light control; (5) authoring.
- **This document is substance; the images are form.** Where they seem to disagree, the images
  govern look-and-feel and this governs meaning, data, and the §7 rules. If an image implies
  hiding failures or renaming the vocabulary, that's the one place to push back — those are
  load-bearing.
- **When in doubt, optimize for comprehension.** The entire reason this UI exists is that a
  fast, concurrent, typed event stream is hard for a human to hold in their head. Every design
  decision serves making it graspable — live, at rest, and under scale.

---

## Appendix A — the lifecycle event catalogue

The runtime's own events (prefixed `substrate.`), which the UI renders as the "plot beats":

- `RunStarted` — the run opens (carries the topology manifest).
- `TriggerFired` — a Trigger's condition held; names the Producer it starts and the input.
- `ProducerStarted` / `ProducerCompleted` — a Producer began / finished normally.
- `ProducerCancelled` — a Producer was stopped before finishing (e.g. by cancel-others).
- `ProducerFailed` — a Producer raised; carries the error. **A failure — surface it.**
- `InputBuildFailed` — building a Producer's input failed; it never started. **A failure.**
- `PredicateQuarantined` — a condition misbehaved and was isolated. **A failure.**
- `ProducerEmittedInvalidEvent` — a Producer emitted something malformed; rejected. **A failure.**
- `InjectionApplied` — a Route staged data forward into a slot (bookkeeping).
- `TerminationMatched` — the TerminationPolicy decided the run should end (or pause); carries
  the decision (e.g. `cancel-others`, `finalise-run`, `pause-await-input` with what it awaits).
- `RunFinalised` — the run ended. Reaching this is **not** the same as succeeding (§7.2).

Application events (e.g. `CritiquePosted`, `VerdictRendered`, `Turn`, `CodeChunk`,
`SubtaskProposed`) are defined per topology and carry that topology's domain payload.

## Appendix B — the reader surface (what the UI consumes)

Command-line reader (each has a programmatic equivalent the UI would call directly):

- `run` / `demo run` — execute a topology to a record (optionally streaming live).
- `tail` — the raw ordered events, filterable by kind / Producer / seq; can follow a live run.
- `narrate` — the legible story; `--summary` for the one-glance honest digest.
- `inspect` — provenance ("why did this Producer exist," the ancestry chain), a single event,
  the decisions in a seq range, or a diff against another record.
- `replay` — re-execute a record and verify it reproduces.
- `topology list` / `demo replay` — discover and replay the bundled topologies.
- `score` — score a run's calibration-style outputs (topology-specific).

Everything the UI needs to show is reachable through this surface. The design problem is
comprehension and interaction, not computation.
```
