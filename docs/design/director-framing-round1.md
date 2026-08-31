# Working as a director — the framing (round 1)

*Status: framing / philosophy, pre-spec. Not a spec, not a market argument — a way of describing the role a person plays when working over Substrate, written down because it reframes the whole way of working and a later spec/UI should be able to cite it. A living document, maintained by rounds + the revision log. Version 0.1. Terms provisional.*

*Provenance: a design conversation, 2026-07-01, following the M1 theory pass (`interactive-agent.md`) and the Cockpit design (`cockpit-design-round1.md`). This round captures the framing while it is fresh, before it has been proven in a built cockpit. Sibling to those two: they describe the machinery; this describes the person operating it.*

---

## 1. The claim

When you work over Substrate, your role is a **director's**, not an engineer's. You do not operate the camera, act, or cut the film. You hold the intent, make the taste calls, cast the performers, review the takes, and coordinate specialists toward one coherent whole that is yours. Everything below that — writing the lines of source, running the loop, applying the patch — is done by agents. The human moves up a level, from lines of source to the run and whether it was correct.

This is a real change in the kind of work, not a nicer title for the same work. Software engineering used to put you close to the material — hands on the code the way an editor is hands on the footage. Substrate moves you off the material and onto the intent and the judgment. That move is the whole point of the runtime: the record is the only state, the human reads the record and the verdicts rather than the source, and attention lives at the altitude of the run.

## 2. The progression — and where taste goes

A rough history of the altitude a builder works at:

- **Assembly / machine code** — operating the camera by hand, one frame of exposure at a time.
- **High-level languages, IDEs** — the editor: hands on the footage, assembling and cutting the material you were given.
- **Agents over a verified substrate** — the director: you hold the intent, cast, judge the takes, and coordinate; you don't touch the film stock.

The tempting story is "you left taste behind and became a manager." That story is wrong, and the correction matters. Editing was *already* a taste craft — a film is made in the edit. You did not move away from taste; you moved from one taste-craft (assembling the material you were handed) to another (deciding what material to make at all, casting who makes it, and judging whether the result is true). The taste relocated and got larger. What is genuinely *new* — bolted onto the taste — is the forensics (§4).

## 3. Which director

The uncertainty about *which kind* of director is not a loose end; it points at a real structure. Substrate spans two different director's jobs, and which one you are doing depends on what backs the run.

- **Live-action director** — you work with autonomous, stochastic performers you cannot fully specify. You steer and you select takes; you don't dictate the performance. This is the **model-backed** path: non-deterministic agents, several takes (best-of-N), the assay picking the winner in the edit. You cannot write the performance; you can only cast well, give notes, and choose.
- **Animation director** — you author every frame; the output is deterministic and fully specified. This is the **deterministic-topology** path (the simulations, the determinism core): total control, no stochasticity, the diff-to-zero fixture as the ground truth.

The system holds both at once. A run backed by a model is directed like live action; a run backed by a pure function is directed like animation. That is why no single metaphor fits — the medium itself is mixed.

And for the case that started this — the **daily driver**, many projects, several review cycles running at once, a different pipeline per kind of work (an Android app, a research assay, a coding flow) — the closer word is **showrunner**. A showrunner holds the bible (the vocabulary), runs many episodes (runs and topologies), and coordinates rotating writers' rooms and directors (multiple review cycles, multiple coder processes). A director is per-film; a daily driver is per-series. The cockpit is a showrunner's room.

## 4. The disanalogy that makes it real, not hype

Here is the one place the metaphor breaks, and it is the important place. A film director's crew is **reliable** — the focus puller nails focus, the gaffer lights the scene. Your crew lies. LLM agents are brilliant, fast, and sometimes confidently wrong. So the director's genuinely new burden over Substrate is not taste — you had taste as an editor. It is **forensic verification**: you have to review every take because the crew cannot be trusted to tell you whether the take worked.

This is exactly why Substrate's honesty machinery exists and why it is the thing that separates this framing from the romantic version:

- "reached RunFinalised — but 1 thing inside failed. **Finished is not worked.**"
- the claim-truth pass, which checks what the system *says it did* against what it did;
- the assay's paired, matched-compute, **can-it-lose** verdict.

Strip that machinery out and "director" degrades into "a person who approves plausible-looking garbage." The seductive version of this framing — *everything below is automated, you just give notes* — is the hype version, and it is false. The real version is: **you give notes, and you review every take, because the crew cannot be trusted — and the tooling makes that review fast enough that you can stay at director altitude instead of dropping back down to inspect the source by hand.** The director framing is only true welded to the verification substrate. That weld is what most "AI agent" tools do not have and Substrate does.

## 5. What the framing changes in the build

This is not only a way of talking; it has consequences for what the cockpit *is*.

A director works off a **monitor** — the video village, the playback everyone gathers around to watch the take. The cockpit is the video village, not an IDE. That reframes substrate-ui away from "a code editor with AI bolted on" and toward "a director's monitor plus a dailies-review room plus a call sheet." You do not read the raw camera sensor; you watch the monitor at the right zoom.

That gives a concrete handle on the open **altitude question** in the Cockpit design (`cockpit-design-round1.md` §6.4): the question is literally *what monitor does the director watch, and at what zoom* — the event stream when debugging, the topology when composing, the verdicts when judging, likely zoomable across those, with a default and a way to move between them without losing your place in the record. Designing the cockpit as a monitor rather than an editor is the design decision this framing forces.

## 6. The mapping

| Directing | Substrate |
|---|---|
| The intent / what the film is | The task; the Decision on the record |
| The script / the bible | The typed vocabulary (validated at `build()`) |
| Casting a performer | Choosing the model / agent Responder (Ollama, a CLI agent, a specialist) |
| The performance you can't fully specify | A model-backed Producer (stochastic) |
| A fully-authored animation frame | A deterministic Producer (the determinism core) |
| Multiple takes | Best-of-N |
| The dailies | The run record |
| Reviewing the take frame-by-frame | Reading the record; the claim-truth pass |
| "Does the take work?" | The assay's can-it-lose verdict |
| The video village / monitor | The cockpit (substrate-ui) |
| Giving notes / steering | Live steering; injecting a human event mid-run |
| Lifting a good sequence into a repeatable setup | Promotion (a real run → a reusable topology) |
| The render farm / the crew | The agents — tools, not authors |

## 7. Authorship

The framing settles the authorship question cleanly. Nobody credits the render farm, and nobody lists the focus puller as the film's author. The director is the author; the crew and the equipment are how the film got made. An agent is a tool the way a camera or a compiler is a tool — it does not earn a credit. This is consistent with the standing rule that the model gets no attribution in any artifact.

## 8. What this is not

- **Not a market or positioning claim.** Nothing here rests on a competitor or adoption. It is a description of a way of working, offered because it is a *true and useful* description, not because it sells.
- **Not a spec.** It is framing; a spec or a UI decision may cite it, but it defines no vocabulary to build against.
- **Not the whole truth if taken romantically.** §4 is the guard: the framing is only correct paired with the verification substrate. Repeat it whenever the framing is invoked, or it becomes an excuse to stop checking the work.
- **Not naming-final.** "Director", "showrunner", "video village", and the §6 terms are provisional.

## 9. Vocabulary (provisional)

- **director** — the person's role over Substrate: holds intent, casts, judges takes, coordinates; does not execute.
- **showrunner** — the director's role scaled across many concurrent runs/topologies/projects; the daily-driver case.
- **casting** — choosing which model/agent backs a Producer.
- **take** — one run (or one best-of-N candidate) produced against an intent.
- **dailies** — the record, read as the reviewable account of what the takes did.
- **the monitor / video village** — the cockpit as the surface the director watches, at a chosen altitude.
- **forensic verification** — the director's new burden: reviewing every take because the crew cannot be trusted; the reason the honesty machinery exists.

---

## Revision log

- **0.1 — 2026-07-01.** Initial capture of the director framing from the design conversation: the role is a director's not an engineer's (§1); the assembly→editor→director progression, taste relocated not lost (§2); which director — live-action for model-backed, animation for deterministic, showrunner for the daily driver (§3); the crew-lies disanalogy and why the honesty machinery makes the framing real rather than hype (§4); the build consequence — the cockpit is a monitor/video-village, answering the altitude question (§5); the mapping table (§6); authorship (§7).
