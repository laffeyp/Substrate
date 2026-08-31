# The Cockpit — design, round 1

*Status: vision / pre-spec. NOT yet a vocabulary session — this is the design conversation written down so a later spec can transcribe from it (per BOOTSTRAP: a session needs source docs to cite, not a pre-decided term list). A living document: maintained by rounds and the revision log at the end. Version 0.1. Working name "Cockpit" is provisional and not locked.*

*Provenance: distilled from a design conversation, 2026-06-25. This round records what is committed, what is open, and what is explicitly out of scope, so the next round can be diffed against it. Nothing here is a market or product-positioning argument; the goal is a correct artifact (§7).*

---

## 1. What the Cockpit is

The Cockpit is the place a person and a set of agents do work together over one shared, append-only record. It replaces the loop of opening several terminal panes and talking to several agents at once. In one place you can:

- run a single agent loop;
- compose a topology (declare which computations run, what conditions start them, how data flows);
- replay, fork, and diff past runs;
- ask whether what was built actually works, against a baseline (the assay).

The person reads the record, the topology, and the verdicts — not source. This is post-*writing*-code, not post-*reading-the-record*: something still has to be ground truth, and it is the record plus the tests plus the assay's verdicts. The human's attention moves up a level, from lines of source to the run and whether it was correct.

The Cockpit spans the whole system: the runtime (which produces the record), the studio/viewer (which reads it), and the assay (which judges it). They are three views of one asset — the record.

## 2. Why the terminal loop is incorrect, and the Cockpit is the correct form

The many-panes loop is not merely inconvenient; it is incorrect, in the same sense Substrate already rejected for producers. It:

- **loses state** — the human's half of every exchange evaporates into scrollback and is not data;
- **coordinates through something unreplayable** — a human eyeball moving between panes, copy-pasting, which cannot be reconstructed or checked afterward;
- **silos context** — each agent's history is trapped in its own session;
- **produces nothing verifiable** — when the session ends there is no account of what happened or whether it worked.

That is the multi-agent equivalent of mutable global state with no logging. Substrate already refused that architecture for computations: everything goes through one totally-ordered, append-only log; no producer talks to another directly; every runtime decision is recorded. The Cockpit is that same decision carried all the way up to where the human sits. The human stops being an operator outside the system and becomes part of it.

## 3. The root commitment: the record is the only state; the human is a Producer

The person's inputs are typed events on the log, exactly like an agent's outputs and the runtime's own decisions. There is no privileged state outside the record. Three properties follow, and they are already true of everything else on the log, so they cost nothing new:

1. **A working session is completely replayable, including the human's interventions.** The session is a record in the same sense a run is, with the person's decisions as first-class events that can be scrubbed, forked, and diffed. A terminal cannot do this even in principle, because the human's inputs there are not data.
2. **There is no hidden state.** The Cockpit is a projection of the record, never a second source of truth that can drift from it — the same property the off-bus sidecars must hold (they leave the log bit-identical). What you see is the log, read a particular way.
3. **Everything is addressable.** Every event, output, and decision has a stable content-addressed id, so the person and the agents share one way to refer to the work: "explain event 4f3a," not "the thing in pane three that scrolled off." Reference is exact.

## 4. Vocabulary as the error-checking mechanism

Topologies — whether written by a person or proposed by an agent — are expressed in the typed vocabulary (producers, triggers, predicates, routes, termination) and validated at `build()`, where malformed coordination does not typecheck: an unknown producer kind, an empty subscription, a reserved-namespace name, both `start=` and `factory=` given, are all rejected before anything runs.

This is the reason an agent may author a topology over an MCP surface and it is correct rather than chaos: the agent *declares* a topology in the vocabulary, the runtime validates it, and the proposal is itself an event on the record — auditable and replayable like everything else. An agent may not write arbitrary code to be executed. The constraint is not a safety feature bolted on; it is the correctness mechanism, the same principle the SDD kit already rests on — a constrained vocabulary that catches whole classes of error before they can occur. Flexibility and rigor are the same constraint seen from two sides.

## 5. Committed design decisions

Each is a correctness property, not a feature. These are taken as settled for this round.

1. **Human-as-Producer; the record is the only state.** The root commitment (§3); everything else derives from it.
2. **The Cockpit is synchronized projections of the record, never its own state.** Graph (which producers and triggers exist, which fired), timeline (the event and decision stream), content (the outputs and artifacts), verdict (the assay's read). Scrubbing the timeline moves the others to match; they are one record seen four ways. The graph is what happened, in time, not a diagram someone drew.
3. **Promotion: a real run is the spec for a topology.** An ad-hoc sequence — talk to one agent, fan out two more, judge them — is already a record. The person selects that span and lifts it into a reusable topology, with the conditions and routes derived from what actually occurred. The structure is induced from a run that happened, not guessed.
4. **Live steering by changing rules, not restarting.** Because a topology is triggers and predicates over an append-only log, a new trigger can be attached mid-run and fires on subsequent matching events; one can be detached and stops. The person steers a running ensemble by editing the rules over the continuous record, never by killing it and losing the history.
5. **The assay is ambient, not a mode.** Wherever two arms exist in the record — two ways a person or an agent did a thing — the Cockpit can ask the paired, matched-compute, can-it-lose question inline. Correctness is a gesture available at any time against one's own work, including against structure an agent authored: did this elaborate thing beat the simple thing, or is it ceremony?

## 6. Open correctness problems

Unsolved. These are the round's real work, not polish.

1. **The human is a slow, asynchronous Producer in a fast asynchronous ensemble.** What happens to quiescence and termination when one producer — the person — takes minutes to emit? The seam exists: pause-await-input termination parks the run waiting on a human event rather than finalizing or spinning. The open question is representation: how does the Cockpit show that an ensemble is parked, waiting specifically on the person, and exactly what it needs — and how can several runs be parked on the person at once without re-creating the pane-juggling the Cockpit exists to end?
2. **Replay with a human in the loop.** Replaying a recorded session replays the person's recorded inputs, since they are events. But forking from a point and going differently means re-entering live at the fork, because the person cannot be re-run. A session record is therefore part replayable, part live-resumable, and the boundary between the two must be exact and legible, or a re-execution will be mistaken for a replay. The runtime already draws this line (replay is reconstruction and log-equivalence, not re-execution); the Cockpit must make it visible.
3. **Bounds and a permission grammar for agent-authored structure.** An agent that authors topologies which author topologies needs hard rails: recursion depth, producer count, fan-out. The admission bound and termination policies are the rails; what is missing is the grammar for what an agent is permitted to author — e.g. "a topology of depth ≤ N, ≤ M producers, terminating on condition C." That grammar is itself a thing to design, and it is what makes self-organization correct rather than unbounded.
4. **The altitude question.** When the person is not reading source, what are they reading, and at what zoom? Events when debugging, the topology when composing, verdicts when judging — likely zoomable across those. The default altitude, and how the person moves between altitudes without losing their place in the record, is unsolved, and it is the core of what the Cockpit is to someone sitting in it.

## 7. What this is not

- **Not a product-positioning document.** No claim here rests on a market, a competitor, or adoption. The aim is an artifact that is correct in a rigorous sense — more rigorous than a casual user would require — because correctness is the end, not a means to reach anyone.
- **Not a spec.** This is pre-vocabulary-session source material; a later spec transcribes from it.
- **Not naming-final.** "Cockpit" and the terms in §8 are provisional pending the vocabulary session.

## 8. Vocabulary (provisional)

Defined against the existing Substrate vocabulary (see `../README.md`, `adding-a-topology.md`); these terms are this document's additions and are not locked.

- **Cockpit** — the interface where a person and agents work over one shared record; the subject of this document.
- **human-as-Producer** — the commitment that a person's inputs are typed events on the log, making the person a participant in the topology rather than an outside operator.
- **projection** — a view the Cockpit derives from the record (graph, timeline, content, verdict); never a second source of truth.
- **promotion** — lifting a span of a real run into a reusable topology, the conditions derived from what occurred.
- **live steering** — attaching or detaching triggers over a running record to change its rules without restarting.
- **arm** — (from the assay) one configured way of doing a thing, compared against another.
- **verdict** — (from the assay) the rigorous, paired, can-it-lose read on whether one arm beat another.

## 9. Open decisions

1. **Which open problem (§6) to attack first.** §6.1 (the human as a parked Producer) and §6.3 (the permission grammar for agent-authored structure) are the two structural ones; the other two depend on choices made there.
2. **Name** — defer "Cockpit" and the §8 terms to the vocabulary session; do not lock now.
3. **Home** — this document lives at `substrate/docs/` for version control and proximity to the design corpus, though the Cockpit spans `substrate` + `substrate-ui` + the assay. Reconsider if the Cockpit becomes its own workspace.

---

## Revision log

- **0.1 — 2026-06-25.** Initial capture from the design conversation: the Cockpit as the correct form of the multi-agent loop (§1–2); the record-as-only-state and human-as-Producer commitment (§3); vocabulary-as-error-checking as the rationale for in-vocabulary agent authorship (§4); five committed decisions (§5); four open correctness problems (§6).
