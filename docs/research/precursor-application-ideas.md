# Ideas lifted from `recursive_strategy_refinment` (precursor extraction)

*Input to the Phase-2 application catalogue (sprint-100). The precursor at
`/Users/peterlaffey/recursive_strategy_refinment` ran multi-LLM applications — debate,
prisoner's dilemma, intel asymmetry, natural conversation, recursive document refinement —
by HAND-ROLLING the orchestration: a "chunked half-sync cascade" scheduler (speaker k+1
fires when speaker k crosses a chunk boundary; all N stream concurrently), cancel-on-converge,
an `events.jsonl` + replay plane, a side-LLM lane. That is substrate, reimplemented per app.
So the precursor is "substrate's applications, built before the substrate existed." What's
worth taking is the application layer, not the runtime — substrate does the runtime better.*

*Direct mapping: the precursor's cascade IS substrate's Trigger-on-chunk-boundary (exactly the
pair_coding topology already built); its "any speaker emits `<verdict>CONVERGED</verdict>` →
scheduler cancels in-flight peers" IS code_review's cancel_all_others on adjudication; its
`events.jsonl` + replay IS the run record + `replay`. The precursor wanted these; substrate
has them natively. Porting these apps onto substrate is the precursor's natural completion.*

---

## 1. Five ready-to-port topologies (each isolates a different structural driver)

Each ships with the precursor's tested system prompts in `demos/`. They are more vivid
than abstract population/adversarial demos, and each isolates a different *structural* driver.

| Topology | Structural driver | Substrate shape |
|---|---|---|
| **Debate** | *positional* asymmetry (same info, opposite stipulated sides; steelman-first) | 2 Producers, opposing system prompts, chunk-boundary Trigger cascade, optional judge Producer (Once) |
| **Prisoner's dilemma** | *payoff* asymmetry, sequential (BRAVO sees ALPHA's reasoning) | 2 Producers; Trigger fires BRAVO on ALPHA's first chunk; one-shot; scheduler ends the run |
| **Intel asymmetry** | *information* asymmetry (each holds private intel; must reach a joint, calibrated assessment) | 2 Producers with private-knowledge inputs; cross-questioning; `CONVERGED` verdict on joint assessment |
| **Natural conversation + ABLATION** | the headline emergence demo — same prompts WITH vs WITHOUT the instruments below | thin Producers + the common-ground/repair instruments toggled; the **delta** is the demo |
| **Recursive refinement** (the namesake) | iterated revisor↔critiquer with convergence detection | 2 Producers alternating over a shared View; converge on `<verdict>CONVERGED</verdict>` |

The natural-conversation **ablation** is the single best emergence demo: identical prompts
produce two parallel monologues bare, but coupled conversation with the instruments on — and
the comparison, not either run alone, is what shows the substrate earns its keep.

## 2. Three reusable INSTRUMENTS (composable across conversation topologies)

The precursor factored out side-LLM "instruments" that are general across topologies. In
substrate each is a small composition of primitives — a Producer subscribed to a View, often
feeding a Route into the next speaker's instantiation. Building these once makes every
conversation topology richer and demonstrates composition (the plan's "you can compose all
this?" demo, S-13.3).

- **Confidence-claim grader + proper scoring rules** (`instruments/grader.py`, `scoring.py`).
  Participants attach calibrated probabilities to claims; a grader Producer reads the prior
  claims against the new turn and emits typed `Grade{claim, prior_confidence, observed_outcome}`
  rows; a *proper scoring rule* (Brier / log-loss / spherical — a clean registry of three, each
  a pure function) converts them to per-claim losses. This closes the **cheap-talk** loop: with
  no payoff tied to calibration, stated probabilities are decorative (Crawford-Sobel) and a
  rational reader ignores them; the scoring rule makes calibration pay. Substrate: a side
  Producer + a pure scoring module; the grades are typed bus events, replayable.
- **Repair detector** (`instruments/repair.py`). Other-initiated repair (Schegloff): a side
  Producer scans the just-landed turn for misalignment (reference drift, contradiction) and
  emits `Repair{status: ok|misaligned|contradiction, note}`; on non-ok, a **Route** prepends a
  `<requires_repair>` cue to the next speaker's input. Repair dynamics *emerge* from the
  detector firing, not from a prescription in the system prompt. Substrate: Producer + Route —
  the exact pattern pair_coding already uses for suggestions.
- **Common-ground extractor** (`instruments/common_ground.py`). A side Producer maintains a
  structured "what speakers already share" document (established facts / open claims /
  agreements / disagreements / ambiguous references), updated each turn from a View and Routed
  into every speaker's next prompt. Closes Clark's common-ground gap (stateless LLMs must
  hand-rebuild shared state every turn). Substrate: Producer + View + Route.

All three are explicitly **soft-fail / non-load-bearing** in the precursor ("a failure must
not abort the conversation"). Substrate already gives this for free: a failed side Producer
emits `ProducerFailed` and the run's termination doesn't depend on it (confirmed by the
Wave-11 pressure tests). Worth preserving as the discipline for "instrument" Producers.

## 3. Framing assets (re-shape the catalogue, sprint-100)

- **Emergence vs. faking** — the precursor's load-bearing distinction. *Faking* = constrain the
  input space to force the output shape (bake "use short turns, acknowledge the other speaker"
  into the system prompt; post-hoc stitch two monologues). *Instrumenting for emergence* =
  create structural conditions (asymmetric info, payoffs, tighter coupling, strip the prompt)
  under which the wanted dynamics arise as best-responses. **Recommendation: replace the
  catalogue's "shock-and-awe value vs LangGraph" axis (review #14 flagged it as marketing) with
  this principled criterion — does the topology INSTRUMENT a dynamic or PRESCRIBE it?** It is a
  gradable, honest axis and it is the substrate's actual value proposition.
- **The "axes that vary"** taxonomy for organizing the catalogue: role symmetry, goal
  alignment, participant count, memory across rounds, information asymmetry, round cadence,
  output type per role. Every conversation topology is a point in this space; structure the
  catalogue along these axes rather than an ad-hoc list.
- **The recursive-questioning pattern map** (`notes/recursive_questioning.md`) — ~25 dialogue
  patterns already mapped (Socratic, adversarial collaboration, steelman, GAN, open peer
  review, dialectical synthesis, murder board, Quaker-consensus-by-silence, jury deliberation,
  red/blue team, self-refine, reflexion, RED/GREEN/REFACTOR, Talmudic chevruta, …). This is a
  ready-made candidate-application source for sprint-100 — each is a substrate topology defined
  by its point in the axes above.
- **The gaps catalogue** (`notes/orchestrating_conversation.md`): what stateless LLMs natively
  miss — common-ground, repair, listening-mode, reference-equality, persistent identity. Each
  gap is a target for one instrument; the mapping "gap → which Producer/View/Route closes it"
  is the design rationale for the instruments above.

## 4. Conventions worth porting as event/payload patterns

- **`<verdict>CONVERGED</verdict>` early-stop → cancel in-flight peers** = `cancel_all_others`
  on an adjudication. Adopt `Converged` as a standard application event a conversation topology
  can emit to trigger termination.
- **Structured output contract** — `<scratchpad>` (discarded reasoning), `<artifact>` (the
  payload), `<log_entry>` (meta-cognition), `<claims>` (calibrated bullets, lead with NN%).
  Substrate replaces the tag-parsing with msgspec schemas, but the *shape* — a discarded
  reasoning surface, a payload, a calibrated-claims block — is a good Producer-output convention.
- **Predict-then-grade / rubric pre-commitment** (Bayesian persuasion) — a Producer commits a
  rubric/prediction event *before* reading, gradable later; makes the signal credible.

---

## Recommendation for Phase 2

1. **Re-shape the Wave-13 topology set** to: debate, prisoner's dilemma, intel asymmetry,
   natural-conversation-with-ablation (plus keep recursive_decomposition; recursive_refinement
   overlaps code_review). These are stronger, prompt-complete demos with a clear structural
   point each.
2. **Build the three instruments** (grader+scoring, repair, common-ground) as composable
   substrate components, and make natural-conversation's WITH/WITHOUT ablation the flagship
   composition demo.
3. **Adopt emergence-vs-faking + the axes taxonomy as the catalogue's organizing frame**
   (sprint-100), sourcing candidates from the recursive-questioning pattern map.
4. The precursor's `notes/substrate/` (where the substrate specs originated) and its prompts
   are the canonical reference when porting — transmit those, not summaries (hard rule 11).
