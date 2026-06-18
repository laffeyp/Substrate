# Application catalogue (Phase 2, sprint-100)

What the substrate is for, as a ranked, structured list of applications — the ones built, and
the candidates worth building next. Grounded in the 8 topologies shipped in `topologies/` and
the precursor extraction (`docs/precursor-application-ideas.md`).

## The organizing axis: instrument emergence, don't fake it

The catalogue is sorted by one principled question, lifted from the recursive_strategy_refinment
precursor — NOT by "shock-and-awe vs LangGraph" (a marketing frame):

- **Instrumenting for emergence** — create structural conditions (asymmetric
  information, payoffs, tighter coupling, a side instrument that feeds the next step) so the
  wanted dynamic arises as a *best-response* to the setup. Pull the structure and the behaviour
  changes. This is what the substrate is good for: the dynamic lives in the topology, not the
  prompt.
- **Faking** — constrain the input space to force the output shape (bake "use
  short turns, acknowledge the other speaker" into a system prompt; post-hoc stitch monologues).
  The shape arrives because it was written on the prompt; pull the prompt and it disappears.

A topology earns its place by what it *instruments*. The natural-conversation ablation makes the
distinction runnable: `substrate demo replay natural_conversation` (instruments on) vs
`natural_conversation_bare` (off) — same prompts, different dynamics; the delta is the substrate.

## The axes a topology varies (the design space)

Every application is a point in this space (the precursor's "axes that vary"):

role symmetry · goal alignment · participant count (N) · memory across rounds · information
asymmetry · round cadence · output type per role.

## Built (Phase 2) — runnable via `substrate run --topology <name>`

| Topology | Structural driver (what it instruments) | Primitives exercised |
|---|---|---|
| `code_review` | quorum fan-in → adjudication → cancel-others | Producer, View, Predicate, Trigger(Once), Termination(any_of/cancel) |
| `pair_coding` | route-context-into-the-next-instantiation | Producer, View, Trigger, **Route** |
| `recursive_decomposition` | one recursive Trigger spawns at any depth; depth budget bounds it | Trigger(PerEvent, recursive), depth-budget predicate |
| `debate` | positional asymmetry (opposite stipulated sides) | the conversation substrate (round-robin Turn cascade) |
| `prisoners_dilemma` | payoff asymmetry, sequential reveal | conversation substrate, 1 round |
| `intel_asymmetry` | information asymmetry (private intel → forced cross-questioning) | conversation substrate |
| `natural_conversation` (+`_bare`) | the emergence ablation: common-ground + repair + scoring instruments toggled | conversation + 3 instruments (Producer+View+Route), the cheap-talk scoring loop |

Instruments (composable, reusable across conversation topologies): **scoring** (proper rules —
Brier/log-loss/spherical — close the cheap-talk loop), **common-ground** (Clark's shared state
accretes per turn), **repair** (Schegloff's other-initiated repair fires + discriminates),
**grader** (scores prior confidence claims → payoff).

## Candidates worth building next (ranked by coverage × emergence, deferred)

| Candidate | Driver | New primitive stress | Cost | Note |
|---|---|---|---|---|
| `adversarial_pair` | writer vs vulnerability-finder, refinement loop bounded by attempt-count | View-of-buffer + predicate-bounded loop | day | precursor's GAN/red-team shape; strong emergence |
| `research_workflow` | M retrievers → synthesizer → fact-checker route → citation-extractor; optional pause-await-input | composition of ~all primitives | week | the "compose all this?" demo (plan S-13.3) |
| `population_simulation` | N agents + world-state Producer; the bus IS the simulation log | N-way concurrency, batched local model | day | watch VRAM (50× 1B); validate batching before flagship default |
| `socratic` | questioner with no thesis — only sharper questions | output-type asymmetry (questions, not claims) | afternoon | conversation config + prompt |
| `adversarial_collaboration` | opposite-prior collaborators jointly author one endorsed doc | convergence-by-mutual-endorsement | day | drop the editor/author split |
| `murder_board` / `jury` | N differentiated critics / deliberation-then-verdict | role-differentiated fan-in, deliberation phase | day | peer-review / committee shapes |
| `red_blue_team` | two internally-cooperative coalitions | coalitional structure | day | scales the ensemble pattern |
| `self_refine` (N=1 baseline) | one Producer generates + critiques in alternation | measurement floor | afternoon | the control: if a two-Producer pair-loop doesn't beat it, the second isn't earning its cost |

Source for the candidate map: the precursor's `notes/recursive_questioning.md` (~25 dialogue
patterns) + `notes/orchestrating_conversation.md` (the gaps each instrument closes) +
PHASE2_PLAN Wave-13 originals. Build order favours STRUCTURAL drivers first; `population_simulation`
needs its batching-feasibility receipt before it is a flagship default.

## What the catalogue deliberately excludes

Faking moves named so the decision survives: post-hoc synthesis of two monologues into chat
shape; pragmatic-marker injection as the *primary* mechanism (useful only as an ablation
baseline — "here's how it looks when we just tell it to behave"); TTS-coupled timing illusions.
These produce a shape without instrumenting a dynamic; the substrate's value is the opposite.
