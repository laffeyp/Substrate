# NORTH STAR — substrate as the cockpit (2026-08-10)

*Second version. `NORTH-STAR-2026-08-09.md` is the first; kept on disk as the audit
trail. This one grows from five themes the user named directly, not from a checklist of
post-it features. The post-its are still the source
(`postitdesigns/IMG_0810–0827.HEIC`); the reading is different.*

---

## The five themes

**T1. Text is the medium of engineering thought and always has been.** Socrates worked
in text. Plato's dialogues worked in text. Code review works in text. Git commits work
in text. The claim substrate makes is not that text is a new interface — text was
always the interface. The one new thing is that one of the interlocutors is now
stochastic. Every design decision in the cockpit reduces to that one shift.

**T2. The typed vocabulary is the interpreter under the surface talk.** Chat is what
the user speaks. Events are what the system speaks. The vocabulary translates. This is
the load-bearing piece of substrate — the reason substrate is not a chat wrapper. The
typed layer under the chat lets substrate be verifiable, replayable, composable,
teachable. Without the interpreter, chat is a friendlier way to hit an LLM; with it,
chat is the surface of a real machine.

**T3. Named strategies are factored, ready-to-run topologies.** A strategy is a name
the user says. Behind the name lives a topology with the models placed, the roles
assigned, the context threaded, the prompts pinned. The user says the name and gets
the whole factored setup — not a fresh best-effort interpretation the model has to
guess at. The strategies are software-engineering workflows: code review, code
generation, roadmap, task breakdown, research. Substrate is not a general
orchestration framework; it is the toolbox of these named workflows.

**T4. The cockpit feels right for code.** Not a schoolroom. Not a confidence
dashboard. Not a market-share pitch. A working environment whose baked-in worldview
is the correct one — text as medium, dialectic as process, vocabulary as ground —
so the user sits down and recognizes it. Working at a higher level with such a tool
extends what the user can do. The extension is the reward; nothing pedagogical needs
to be added on top.

**T5. Small-model orchestration is the horizon.** Not today's default. The world two
years out has interesting engineering happening on orchestrated groups of small
specialized models. Substrate is what you use when that world arrives. Today's
substrate uses whatever strong model is available; tomorrow's uses the swarm.
Substrate's shape is right for both.

---

## What the post-its say, read through these themes

Each theme absorbs several post-its. The reading is thematic, not
one-to-one.

**T1 is post-its 4, 4a, 14.** The chat replaces the API menu and the raw REPL because
the LLM is the interlocutor and text is the exchange. The dialectic (thought →
dialogue → action) is the process; it is Socrates's process, unchanged in kind, with a
new second party. The "language = thought?" question is the anchor: text carries
meaning, so a fluent text interface is not a friendly wrapper — it is the direct
surface.

**T2 is post-its 14 and 10.** "What is under language?" — the typed vocabulary. The
substrate box in post-it 10 with input/output condition and wired models: the wiring
is typed. The types are the interpreter. When the user asks the chat what happened,
the chat narrates in the vocabulary's own terms; when the user asks the chat to
compose, the chat composes in the vocabulary; when substrate replays, it replays
against the vocabulary. The vocabulary is one artifact serving three roles.

**T3 is post-its 13 and (indirectly) 6 + 12.** Drag-and-drop common topologies and
"say review strategy N" are the same request: the strategies are user-facing objects,
addressable by name, invocable without re-authoring. Post-it 6 (verifiable,
composable, multiplied output, all SWE workflows made to work with agents) is why:
the toolbox has to cover the workflows so the user's output multiplies. Post-it 12
(small in cohesion vs one paid model) names the substrate under a named strategy:
several models, factored into their places, cohering under orchestration. The
factoring is the point. A named strategy replaces the messy chain of small model
calls with a bounded, well-known one that runs to a known shape. This is close in
spirit to the Toyota production line — quality at the speaker's mouth (SDD's
poka-yoke), bounded stations, pull semantics — but the comparison is a passing one;
substrate is not modeling itself on TPS.

**T4 is post-its 5, 7, 8, 9, and the unnumbered `IMG_0819`.** "Substrate as default
even for..." — the tool is the one you reach for because it fits, not because it
markets. "I want to push my own limits" and "build things I barely understand" — the
tool extends the user; the extension is what learning-by-doing looks like without a
schoolroom around it. The unnumbered card names three properties together —
verifiable, auditable, editable — and the cockpit honors all three. Interior/exterior
(post-it 9) is a UI rhythm the cockpit adopts: things unfold within the window like a
painting reveal from the middle, not by sliding off to the edge; the OS is where the
user goes when the cockpit does not host the artifact.

**T5 is post-its 11, 12.** Strong model orchestrates smaller ones; correction rounds
raise the ceiling; small in cohesion beats one large one under orchestration. This is
substrate's shape already. The current SWE-bench run measures whether the mechanism
holds on the standard benchmark. What matters for the horizon is that substrate is
built for orchestrated groups; it does not force any specific model at the top.

---

## What substrate has that fits

The engine matches most of what the themes demand.

**The typed vocabulary and the record.** `substrate/kernel/` implements the primitives
and the append-only append-cycle. Every event lands on the record with a stable schema.
`substrate/api/narrate.py` renders the record as prose in the vocabulary's own terms.
This is T2 in code today.

**The nine bundled topologies.** `coding_flow`, `swebench_solver`, `best_of_n`,
`tool_loop`, `code_review`, `code_evolution`, `debate`, `pair_coding`,
`natural_conversation`. Each is a candidate strategy — needs a name, needs a home in a
registry, needs a place in the cockpit. The substrate for T3 exists; the naming and
surfacing do not.

**The assay layer.** Suite, Arm, Case, Oracle, control plane, report, stats,
preregistration. Pre-registered comparators, paired McNemar, two-level bootstrap,
Tango/Nam score-TOST, Benjamini-Hochberg FDR. This is the verifiable half of T4's
verifiable/auditable/editable trio. The record is the auditable half. Editable — live
topology swap while a run is in flight — does not exist yet.

**The model seam.** `substrate/adapters/`. `OllamaResponder` for local + `:cloud`
tags, `CliResponder` for any command-line agent, `EnsembleResponder` for round-robin.
Whatever model is strong today drops in as the orchestrator; whatever small ones show
up drop in as the ensemble members. T5 is not blocked on model support.

**SDD kit-2.** `sdd-kit-2/AGENTS.md` is the working agreement; `TECHNIQUES.md` is the
catalogue; `PRINCIPLES.md` is the vocabulary discipline. This is where T2's discipline
comes from — vocabulary designed before code, validated at the speaker's mouth,
evolved through supervised proposals.

**substrate-ui.** Read-only console projecting a runtime's signal log into a browser
UI. The raw material for the cockpit shell. Not the cockpit yet — reads without
driving.

## What is missing

Short list. The vision is not a list of features and the doc must not become one.

**A cockpit process the user opens.** The window, the panes, the launch. The
substrate-ui evolution path (memory: `project-cockpit-redesign-rulings.md`,
`COCKPIT-DIRECTION-round2`) is the direction.

**The chat as the primary driver.** A `tool_loop`-shaped topology bound to a cockpit
action set. This is the surface T1 demands. Chat dispatches strategies by name,
opens files, opens URLs, runs shell.

**A named-strategy registry.** T3 has no home today. Every bundled topology gets a
name, a description, a pinned set of inputs. The chat resolves the user's ask to a
name. Naming is a design pass — the names carry meaning; identifiers are
mechanically trivial and beside the point.

**Panes for what the strategies produce.** Code the strategy edits; web pages the
strategy shows; a real terminal available beside the chat (the user already has
GhosttyTerm or iTerm open every morning with several columns — the chat pane does
not replace those, it lives beside them). The exact number of panes is not decided.
Whether one composite editor or a separate pane per file is not decided either. The
themes commit; the count does not.

**Live editability of a running topology.** The third property of the unnumbered
card. Substrate's Registration freezes at build. A strategy swap mid-run needs a new
event kind and a hot-reload path. Deferred until the cockpit shell exists.

**Interior unfolding as a UI motif.** Panes reveal from within the window rather than
sliding off the edge. Cosmetic on the surface, load-bearing for T4 — the tool feels
right in part because the geometry feels right. The specific implementation waits
for the shell.

---

## The next moves

Order matters; sizing does not (yet).

**1. Finish the SWE-bench Verified confirmatory.** The sweep is running. Pass 1
measures whether the ensemble mechanism holds; pass 2 puts it in equivalence form.
The number affects nothing about T1–T4, and only affects T5's timing (if today's
substrate already shows the mechanism, the horizon arrives sooner; if not, substrate
still fits the horizon when it arrives).

**2. Evolve substrate-ui into the cockpit shell.** Standalone window, movable panes,
real PTY somewhere, the interior-unfold motif. Direction: `COCKPIT-DIRECTION-round2`.

**3. Ship the chat pane bound to a cockpit action set.** `tool_loop` with the tools
that open panes, load files, dispatch strategies, run shell, show state. This is the
surface T1 asks for.

**4. Name the strategies.** Every bundled topology gets a name and a
one-sentence description of what it does. The registry is a first-class artifact.
Chat resolves the user's phrasing to a name; the name resolves to a factored
topology. This is where the toolbox becomes usable.

**5. Add code and web panes as the strategies need them.** A strategy that emits a
patch wants the file open. A strategy that emits a chart wants a web view. The
cockpit adds the panes each strategy demands, not a fixed set of panes chosen up
front.

**6. Persistent cockpit memory.** The cockpit is itself a substrate run at a
well-known root; its own event log is its memory. Chat scrollback, open files, pane
layout — all persistent by construction.

**7. Live topology edit.** The editable third property from `IMG_0819`. Deferred
until the cockpit shell has real users and a real reason to swap strategies mid-run.

**8. Drag-and-drop canvas.** Later. The primitives to compose are few — producers
foremost, the rest inferable — so the canvas surfaces a small vocabulary. This is
the case where a graphical composer earns its cost, but only after the toolbox is
full enough that users want to build new strategies rather than pick from the shelf.

---

## What NOT to do

Five commitments in the negative.

**Do not build a schoolroom.** The tool teaches by being usable at the user's edge,
not by explaining itself. No confidence dashboards, no "why did this decide that"
side panels unless the user asks for one specifically. `substrate/api/narrate.py`
already puts the record into prose; that is enough for the audit view.

**Do not sell substrate as a market claim.** The tool wins because it fits the
worldview, not because it out-features a competitor. The doc should not describe
substrate in terms of "the seat Cursor and Claude Code occupy." Substrate is
substrate; if it fits, the user picks it up.

**Do not overindex on any one strong model.** Substrate uses whatever model is
strong today at the orchestrator position. Claude is one, GPT-5 is another,
DeepSeek-V4 is another. The strategy definitions do not name the model; they name
the role.

**Do not build a general-purpose orchestration framework.** Substrate is the toolbox
of software-engineering workflows. Topologies for other domains (biology, trading,
classic ML with no LLMs) are possible on the same runtime — the runtime does not
care — but the cockpit and the strategy toolbox are focused on code.

**Do not name strategies by number.** Names carry meaning; identifiers are trivial.
A strategy is `code_review.adversarial`, `roadmap.sprint_breakdown`,
`research.narrow_survey` — not `strategy_3`. The user recognizes the name; the
number tells them nothing.

---

## The one-line summary

Text has always been how engineering happens; the new thing is a stochastic
interlocutor; substrate turns the exchange into a verifiable, composable, named
toolbox of software-engineering workflows; the cockpit is where the user sits down
and recognizes it.

*Companions: `docs/NORTH-STAR-2026-08-09.md` (v1, superseded but on disk);
`docs/vision-postit-alignment-2026-08-09.md` (the first-pass alignment). Source
images: `postitdesigns/IMG_0810–0827.HEIC`, sixteen post-its shot 2026-08-08.*
