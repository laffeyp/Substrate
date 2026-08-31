# Application catalogue (Phase 2, sprint-100)

*The runnable application library is [applications.md](applications.md). This file
is the strategic catalogue behind it.*

What the substrate is for, in two lists: the 12 topologies shipped in the `BUNDLED`
registry (code_review, pair_coding, recursive_decomposition, debate,
prisoners_dilemma, intel_asymmetry, natural_conversation,
natural_conversation_bare, adversarial_pair, game_of_life, game_of_life_glider,
tool_loop), and the candidates the precursor pulled out
(`docs/precursor-application-ideas.md`) worth building next.

## The organizing axis: instrument emergence, don't fake it

Two ways to make a dynamic show up in the output. Only one of them lives in the
substrate.

Instrumenting the dynamic means setting up structural conditions — asymmetric
information, payoffs, tighter coupling, a side instrument feeding the next step —
so the behaviour arises as the best response to that setup. Pull the structure and
the behaviour changes. The dynamic lives in the topology, not the prompt.

Faking the dynamic means constraining the input space until only the wanted shape
comes out: bake "short turns, acknowledge the other speaker" into the system
prompt, or post-hoc stitch two monologues together. The shape arrives because the
prompt wrote it. Pull the prompt and it disappears.

The natural-conversation ablation makes the distinction runnable:
`substrate demo replay natural_conversation` (instruments on) versus
`natural_conversation_bare` (off). Same prompts, different dynamics. The delta is
the substrate.

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
| `adversarial_pair` | writer vs vulnerability-finder, attempt-count-bounded refinement loop (GAN/red-team) | View-of-buffer + predicate-bounded loop |

## Built (application library) — launched via `scripts/run_*.py`, documented in [applications.md](applications.md)

A separate track from the table above. These are not in the `substrate run --topology`
registry (`BUNDLED`). They compose the primitives on real input, launch from a script,
and each run lands as a replayable record.

| Application | Structural driver | Composition |
|---|---|---|
| `fanout_review` | quorum review panel over a real git diff | composes `code_review` |
| `best_of_n_verified` | generate N → verify each → select the survivor | composes `best_of_n_correction` |
| `research_sweep` | map readers over a document set → critique gaps → synthesize | authored from primitives |
| `delegate` (tool) | an agent hands a subtask to a child agent, folds the answer back | tool_loop tool + child run |

Four instruments compose across the conversation topologies: **scoring** (proper
rules — Brier, log-loss, spherical — close the cheap-talk loop), **common-ground**
(Clark's shared state accretes per turn), **repair** (Schegloff's other-initiated
repair fires and discriminates), and **grader** (scores prior confidence claims
into a payoff).

## Candidates worth building next (ranked by coverage × emergence, deferred)

| Candidate | Driver | New primitive stress | Cost | Note |
|---|---|---|---|---|
| `research_workflow` | M retrievers → synthesizer → fact-checker route → citation-extractor; optional pause-await-input | composition of ~all primitives | week | **partly shipped** as `research_sweep` (map→critique→synthesize); the fact-checker route + citation-extractor legs remain |
| `population_simulation` | N agents + world-state Producer; the bus IS the simulation log | N-way concurrency, batched local model | day | watch VRAM (50× 1B); validate batching before flagship default |
| `socratic` | questioner with no thesis — only sharper questions | output-type asymmetry (questions, not claims) | afternoon | conversation config + prompt |
| `adversarial_collaboration` | opposite-prior collaborators jointly author one endorsed doc | convergence-by-mutual-endorsement | day | drop the editor/author split |
| `murder_board` / `jury` | N differentiated critics / deliberation-then-verdict | role-differentiated fan-in, deliberation phase | day | peer-review / committee shapes; the fan-in-then-verdict half now exists in `fanout_review` (differentiated-critic panel + judge) |
| `red_blue_team` | two internally-cooperative coalitions | coalitional structure | day | scales the ensemble pattern |
| `self_refine` (N=1 baseline) | one Producer generates + critiques in alternation | measurement floor | afternoon | the control: if a two-Producer pair-loop doesn't beat it, the second isn't earning its cost; `best_of_n_verified` is the N>1 verified-selection sibling to measure against it |

The candidate map came from the precursor's `notes/recursive_questioning.md` (~25
dialogue patterns), `notes/orchestrating_conversation.md` (the gaps each instrument
closes), and the PHASE2_PLAN Wave-13 originals. Build order favours structural
drivers first. `population_simulation` needs a batching-feasibility receipt before
it can default to flagship.

## What the catalogue deliberately excludes

The faking moves. Named here so the decision survives.

Post-hoc synthesis of two monologues into chat shape. Pragmatic-marker injection as
the primary mechanism (allowed as an ablation baseline — "here is how it looks when
we just tell it to behave"). TTS-coupled timing illusions. Each produces a shape
without instrumenting a dynamic. The substrate is for the other kind.
