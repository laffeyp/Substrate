# NORTH STAR — substrate as the cockpit (2026-08-10, v3)

*Fourth version of this doc. The prior three (`NORTH-STAR-2026-08-09.md`,
`NORTH-STAR-2026-08-10.md`, `NORTH-STAR-2026-08-10-v2.md`) stay on disk as the audit
trail. This version drops two lingering comparative negatives that the v2 pass
missed. The five themes are unchanged; only the writing register moves.*

Source: `postitdesigns/IMG_0810–0827.HEIC`, sixteen post-its shot 2026-08-08.

---

## The five themes

**T1. Text is the medium of engineering thought and always has been.** Socrates worked
in text. Plato's dialogues worked in text. Code review works in text. Git commits work
in text. The one new thing is that one of the interlocutors is stochastic. Every
design decision in the cockpit reduces to that shift.

**T2. The typed vocabulary is the interpreter under the surface talk.** Chat is what
the user speaks. Events are what the system speaks. The vocabulary translates. The
typed layer under the chat is what lets substrate be verifiable, replayable,
composable, and legible. Substrate is a machine because of it.

**T3. Named strategies are factored, ready-to-run topologies.** A strategy is a name
the user says. Behind the name lives a topology with the models placed, the roles
assigned, the context threaded, the prompts pinned. The user says the name and gets
the whole factored setup. The strategies are software-engineering workflows: code
review, code generation, roadmap, task breakdown, research. Substrate is the toolbox
of these.

**T4. The cockpit feels right for code.** A working environment whose baked-in
worldview is the correct one — text as medium, dialectic as process, vocabulary as
ground. The user sits down and recognizes it. Working at a higher level with such a
tool extends what the user can do; the extension is its own reward.

**T5. Small-model orchestration is the horizon.** Substrate uses whatever strong
model is available today at the orchestrator position and whatever specialized small
models fit at the ensemble positions. The shape works today with a single strong
backbone; the shape holds when the world moves to orchestrated groups of small
models. Substrate is what you reach for when that world arrives.

---

## How the post-its map to the themes

The reading is thematic; several post-its feed each theme.

T1 draws on post-its 4, 4a, and 14. Chat replaces the API menu and the raw REPL
because the LLM is the interlocutor and text is the exchange. The dialectic (thought
→ dialogue → action) is Socrates's process with a stochastic second party. The
`language = thought?` question sits under all of it: text carries meaning, so a
fluent text interface reaches meaning directly.

T2 draws on post-its 14 and 10. The typed vocabulary answers `what is under
language?`. The wired-models sketch in post-it 10 shows the machinery: producers
connected by triggers, each emission a typed event on a locked record. When the user
asks the chat what happened, the chat narrates in the vocabulary's own terms. When
the user asks the chat to compose, the chat composes in the vocabulary. When
substrate replays, it replays against the vocabulary. The vocabulary is one artifact
serving three roles.

T3 draws on post-its 13, 6, and 12. Drag-and-drop common topologies and `say review
strategy N` are the same request: strategies are user-facing objects, addressable by
name, invocable without re-authoring. Post-it 6 (verifiable, composable, multiplied
output, all SWE workflows made to work with agents) is why the toolbox has to be
complete enough that the user's output multiplies. Post-it 12 (small in cohesion
under orchestration) names the substrate under each strategy: several models
factored into their places, cohering because the topology puts them there.

T4 draws on post-its 5, 7, 8, 9, and the unnumbered `IMG_0819`. `Substrate as default
even for…` says the tool is the one the user reaches for because it fits. `I want to
push my own limits` and `build things I barely understand` say the tool extends the
user. The unnumbered card names three properties together — verifiable, auditable,
editable — and the cockpit honors all three. `Interior vs exterior` (post-it 9) is a
UI rhythm: things unfold within the window like a painting reveal from the middle;
the OS is where the user goes when the cockpit does not host the artifact.

T5 draws on post-its 11 and 12. A strong model orchestrates smaller ones; correction
rounds raise the ceiling; small in cohesion beats one large one under orchestration.
Substrate's shape is already right for this. The current SWE-bench Verified run
measures whether the mechanism holds on the standard benchmark. What matters for the
horizon is that substrate is built for orchestrated groups without pinning any
specific model at the top.

---

## What substrate has that fits the themes

The runtime carries most of what the themes demand.

**Typed vocabulary and the record.** `substrate/kernel/` implements the primitives and
the append-only cycle. Every event lands on the record with a stable schema.
`substrate/api/narrate.py` renders the record as prose in the vocabulary's own terms.
This is T2 in code today.

**Nine bundled topologies.** `coding_flow`, `swebench_solver`, `best_of_n`,
`tool_loop`, `code_review`, `code_evolution`, `debate`, `pair_coding`,
`natural_conversation`. Each is a candidate strategy. The substrate for T3 exists;
the naming and the cockpit surface are what remain.

**Assay layer.** Suite, Arm, Case, Oracle, control plane, report, stats,
preregistration. Pre-registered comparators, paired McNemar, two-level bootstrap,
Tango/Nam score-TOST, Benjamini-Hochberg FDR. This is the verifiable half of the
unnumbered card's trio. The record is the auditable half. Editable — live topology
swap while a run is in flight — comes later.

**Model seam.** `substrate/adapters/` — `OllamaResponder` for local + `:cloud`,
`CliResponder` for any command-line agent, `EnsembleResponder` for round-robin
across N backends. Whatever model is strong today sits at the orchestrator
position; whatever specialized small ones arrive drop in as ensemble members.

**SDD kit-2.** `sdd-kit-2/AGENTS.md` is the working agreement; `TECHNIQUES.md` is the
catalogue; `PRINCIPLES.md` is the vocabulary discipline. The vocabulary is designed
before code, validated at the speaker's mouth, evolved through supervised proposals.
This is where T2's discipline comes from.

**substrate-ui.** A read-only console projecting a runtime's signal log into a
browser UI. The raw material for the cockpit shell.

## What remains to build

**A cockpit process the user opens.** Standalone window, movable panes, launch from
the OS. The direction is to evolve `substrate-ui` into this shape (memory pointer:
`project-cockpit-redesign-rulings.md`, canonical `COCKPIT-DIRECTION-round2`).

**Chat as the primary driver.** A `tool_loop`-shaped topology bound to a cockpit
action set. The chat dispatches strategies by name, opens files, opens URLs, runs
shell. A real terminal (Ghostty, iTerm) stays available beside the chat; the chat
does not replace it, it lives beside it.

**A named-strategy registry.** Every bundled topology gets a name and a one-sentence
description of what it does — for instance `code_review.adversarial`,
`roadmap.sprint_breakdown`, `research.narrow_survey`. The names carry meaning. The
chat resolves the user's phrasing to a name; the name resolves to a factored
topology. The registry is a first-class artifact.

**Panes for what the strategies produce.** Code the strategy edits; web pages the
strategy shows; the record the strategy writes. The exact number of panes is not
fixed yet. Whether the editor is one composite view or a pane per file is not fixed
either. The themes commit; the count does not.

**Interior unfolding as a UI rhythm.** Panes reveal from within the window rather
than sliding off the edge. Cosmetic at the surface, load-bearing for T4 — the
geometry is part of the fit.

**Live editability of a running topology.** The third property from the unnumbered
card. Substrate's `Registration` freezes at build; live edit needs a new event kind
and a hot-reload path. Ships after the cockpit shell has real users.

---

## The next moves

**1. Finish the SWE-bench Verified confirmatory.** The sweep is running. Pass 1
measures whether the ensemble mechanism holds; pass 2 puts it in equivalence form.
The number affects only T5's timing.

**2. Evolve substrate-ui into the cockpit shell.** Standalone window, movable panes,
real PTY somewhere, the interior-unfold rhythm.

**3. Ship the chat pane bound to a cockpit action set.** `tool_loop` with tools that
open panes, load files, dispatch strategies, run shell, show state.

**4. Name the strategies.** Every bundled topology gets a name and a
one-sentence description. The registry is a first-class artifact. Chat resolves the
user's phrasing to a name; the name resolves to a factored topology.

**5. Add code and web panes as the strategies need them.** A strategy that emits a
patch wants the file open. A strategy that emits a chart wants a web view. The
cockpit adds each pane its strategies demand.

**6. Persistent cockpit memory.** The cockpit is itself a substrate run at a
well-known root; its own event log is its memory. Chat scrollback, open files, pane
layout — all persistent by construction.

**7. Live topology edit.** The third property from the unnumbered card. Ships after
the cockpit shell has real users and a reason to swap strategies mid-run.

**8. Drag-and-drop canvas.** Ships after the strategy toolbox is full enough that
users want to compose new strategies rather than pick from the shelf. The
primitives are few — producers foremost, the rest inferable — so the canvas
surfaces a small vocabulary.

---

## The scope

Substrate's cockpit and its strategy toolbox focus on software engineering. The
runtime is domain-agnostic; the same primitives support topologies for biology,
trading, classic ML with no LLMs at all. Those are legitimate uses of the runtime.
The named-strategy toolbox and the cockpit surface are for code.

The strategy names carry meaning. `code_review.adversarial` tells the user what it
does. `roadmap.sprint_breakdown` tells the user what it does. Naming is a design
pass on its own — the toolbox is only as usable as the names are clear.

Substrate uses whatever strong model fits the orchestrator position and whatever
small models fit the ensemble positions. The strategy definitions name the role, not
the model. When a new strong model arrives, the strategies keep working. When a
small model beats yesterday's small model, the ensemble picks it up.

---

## The one-line summary

Text has always been how engineering happens; the new thing is a stochastic
interlocutor; substrate turns the exchange into a verifiable, composable, named
toolbox of software-engineering workflows; the cockpit is where the user sits down
and recognizes it.

*Companions on disk: `docs/NORTH-STAR-2026-08-09.md` (v1), `docs/NORTH-STAR-2026-08-10.md`
(v2, this replaces it), `docs/vision-postit-alignment-2026-08-09.md` (first-pass
alignment).*
