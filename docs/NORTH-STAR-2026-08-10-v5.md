# NORTH STAR — substrate as the cockpit (2026-08-10, v5)

*Sixth version. Prior five on disk as the audit trail:
`NORTH-STAR-2026-08-09.md` (v1);
`NORTH-STAR-2026-08-10.md` (v2);
`NORTH-STAR-2026-08-10-v2.md` (v3);
`NORTH-STAR-2026-08-10-v3.md` (v4);
`NORTH-STAR-2026-08-10-v4.md` (v5-precursor). This version fixes three residual
comparative negatives the v4 pass carried through.*

Source: `postitdesigns/IMG_0810–0827.HEIC`, sixteen post-its shot 2026-08-08.

---

## The five themes

**T1. Text is the medium of engineering thought and always has been.** Socrates worked
in text. Plato's dialogues worked in text. Code review works in text. Git commits work
in text. Substrate is not inventing the medium; the medium is what engineering has
lived in since engineering existed. The one new thing is that one of the interlocutors
is stochastic. Every design decision in the cockpit reduces to that shift, and the
weight of the shift is enormous — a fluent text partner turns every text-shaped
engineering task into a paired activity, which was possible before only with a real
colleague and only for as many hours as the colleague could give.

**T2. The typed vocabulary is the interpreter under the surface talk.** Chat is what
the user speaks. Events are what the system speaks. The vocabulary translates between
the two. This is the load-bearing piece of substrate — the piece that makes
substrate a machine rather than a friendlier way to reach an LLM. A vocabulary is a
named list of the events a system admits it knows about, the categories those events
belong to, and the payload each carries. The vocabulary is designed before the code;
it is versioned; it is validated at the speaker's mouth (unknown tag = error,
missing required field = error). Once a topology commits to a vocabulary, every
event it emits is a typed record, every state is reconstructable, every claim about
what happened has a citation. The chat surface reads the record when the user asks
what the system did and narrates back in the vocabulary's own terms
(`substrate/api/narrate.py` does this projection today). When the user asks the
chat to compose a topology, the chat composes in the vocabulary. When substrate
replays, it replays against the vocabulary. One artifact, three roles — audit,
composition, replay. Without the vocabulary, chat is a wrapper. With it, chat is the
surface of a real machine.

**T3. Named strategies are factored, ready-to-run topologies.** A strategy is a name
the user says. Behind the name lives a topology with the models placed, the roles
assigned, the context threaded, the prompts pinned. The user says the name and gets
the whole factored setup — models placed, roles filled, context threaded, prompts
ready. This shape is close in spirit to the
Toyota production line: bounded stations, quality at the speaker's mouth, pull
semantics, well-known flows instead of messy chains of small calls with humans
brokering between them. The strategies are software-engineering workflows: code
review, code generation, roadmap breakdown, task estimation, research. Substrate is
the toolbox of these.

**T4. The cockpit feels right for code.** A working environment whose baked-in
worldview is the correct one — text as medium, dialectic as process, vocabulary as
ground. The user sits down and recognizes it. It feels like the chair the user did
not know they loved. Working at a higher level with such a tool extends what the
user can do; the extension is its own reward. There is no lesson layered on top,
no dashboard of confidence, no explainer pane. The tool works well and the user
learns by using it, the way software engineers have always learned — by working at
the edge of what they know, by collating information, by shipping.

**T5. Small-model orchestration is the horizon.** Substrate uses whatever strong
model fits the orchestrator position today and whatever specialized small models fit
the ensemble positions. The shape works with a single strong backbone; the shape
holds when the world moves to orchestrated groups of small specialized models —
what a swarm looks like a couple of years out. Substrate is what the user reaches
for when that world arrives, and it is what the user reaches for now while the
strong-model-plus-verifier shape is the sensible default.

---

## The philosophical layer

Two claims from the post-its sit under the themes and give them weight. Read them
slowly.

**Language and thought.** Post-it 14 asks `Language = thought? What is under
language?`. Substrate's answer is the typed vocabulary. Text carries meaning; a
fluent text interface reaches meaning directly; the vocabulary is what meaning looks
like when it is grounded, verifiable, replayable. The chat is the surface the user
speaks. Events are the surface the system speaks. The vocabulary translates. If
language is thought, then substrate's vocabulary is the model of thought that sits
under the surface talk. This is the answer to the post-it's question and it is
already in code (`sdd-kit-2/grammar/PRINCIPLES.md` for the discipline;
`substrate/kernel/topology.py` for how it lands in a run).

**The extension of the user.** Post-its 7 and 8 together say: I want to push my
own limits, work at the limits of my own understanding, build things I barely
understand, learn by doing, and still trust the output. The right frame is not
protection from an LLM's stochasticity; the right frame is that a good tool
extends what the user can do, and by having such a tool, the user works higher and
naturally learns the shape of the higher work. Software engineering has always
worked this way — engineers collate information they did not previously have, ship
past the edge of what they understood yesterday, and know more by tomorrow.
Substrate makes the collation faster and the extension larger.

---

## What the post-its say, read through the themes

The reading is thematic. Several post-its feed each theme.

**T1 draws on post-its 4, 4a, and 14.** Chat replaces the API menu and the raw REPL
because the LLM is the interlocutor and text is the exchange. Post-it 4 places chat
against those two older shapes and lands on chat: the LLM asks the user what they
want; the machine interface IS the LLM. Post-it 4a inserts DIALOGUE between THOUGHT
and ACTION — the dialectic is the engineering process, unchanged in kind since
Socrates. Post-it 14 anchors the whole thing: text carries meaning, so a fluent
text interface reaches meaning directly.

**T2 draws on post-its 14 and 10.** The typed vocabulary answers `what is under
language?`. The wired-models sketch in post-it 10 shows the machinery: producers
connected by triggers, each emission a typed event on a locked record. The
vocabulary discipline (design before code, validate at the mouth, evolve through
supervised proposals) lives in `sdd-kit-2/grammar/PRINCIPLES.md`. The runtime
enforcement lives in `substrate/kernel/topology.py`. Together they give substrate
its three roles for one artifact: audit (narrate the record back to the user),
composition (build new topologies in the vocabulary's shape), replay (reconstruct
any state from the record).

**T3 draws on post-its 13, 6, and 12.** Drag-and-drop common topologies and `say
review strategy N` are the same request: strategies are user-facing objects,
addressable by name, invocable without re-authoring. Post-it 6 says why the toolbox
matters: a verifiable, composable, agent-multiplied output requires that all the
SWE workflows are made to work with agents — a strategy for each. Post-it 12 names
what a single strategy is under the surface: several small models factored into
their places, cohering because the topology puts them there. Cohesion is a
topology-level property; a fresh chain of LLM calls without a topology does not
cohere.

**T4 draws on post-its 5, 7, 8, 9, and the unnumbered `IMG_0819`.** `Substrate as
default even for…` says the tool is the one the user reaches for because it fits.
`Push my own limits` and `build things I barely understand` say the tool extends
the user, and the extension itself is the point. The unnumbered card demands three
properties together — verifiable, auditable, editable — and the cockpit honors all
three. Post-it 9 `interior vs exterior` is a UI rhythm the cockpit adopts: things
unfold within the window like a painting reveal from the middle, opening from the
center rather than sliding off the edge. The OS is where the user goes when the
cockpit does not host the artifact.

**T5 draws on post-its 11 and 12.** A strong model orchestrates smaller ones;
correction rounds raise the ceiling; small in cohesion beats one large one under
orchestration. Substrate's shape is already right for this. The SWE-bench Verified
run in flight measures whether the mechanism holds on the standard benchmark. The
horizon claim survives either way: substrate is built for orchestrated groups
without pinning any specific model at the top.

---

## Second-pass insights

Four cycles of re-reading the post-its surfaced these. Each holds up under the five
themes; each carries its own weight.

**Chat replaces the API menu and the raw REPL.** Post-it 4 shows both older shapes
side by side with an arrow to chat. The chat is the surface; the older shapes are
what the chat replaces. Cursor and Claude Code already show this — the productive
loop is chat, and menus have moved into the chat as tool-calls the model resolves.
Substrate's cockpit is the same shape with a factored substrate underneath.

**Cohesion is a topology-level property, not a compute-level one.** Post-it 12 says
`working in cohesion under orchestration`. Random parallel calls do not cohere; a
topology makes them cohere. This is what substrate's ensemble arm brings that a
plain N-shot dispatch does not — the topology places each model into a role, and
the roles carry the coherence.

**Strategies are factored, invocable by name.** The named strategy is a topology
with its inputs pinned, its roles filled, its context threaded. The user says the
name and gets the whole setup — every model in its role, every context slot filled
in advance. This is where the toolbox becomes usable. It is where substrate stops
being a kit and starts being a tool.

**Interior unfolding is the UI rhythm.** Panes reveal from within the window like a
painting reveal from the middle. Cosmetic on the surface, load-bearing for T4 — the
geometry is part of the fit. The OS is where the user goes when the cockpit
declines to host the artifact; the cockpit's default is to host.

**Working at a higher level extends what the user can do.** Post-it 8's `learn by
doing` describes the natural extension the tool creates. A good text-processing
system makes the user better at text. A good code-solving system makes the user
better at code. There is no lesson pane, no confidence dashboard, no explainer
overlay. The tool is legible enough that a competent user reads it and gets
better.

**The dialectic is the engineering process, unchanged in kind.** Post-it 4a
inserts DIALOGUE between THOUGHT and ACTION and puts the dialectic there. This is
Socrates's method with a stochastic second party. Text carries meaning, and
substrate turns each exchange into a typed record — the dialectic gets an audit
trail it did not have before.

**The tool feels right for code.** Post-it 5's `default even for…` is a felt-right
claim. The tool is the one the user reaches for because the worldview under it
matches how the user thinks about their work. The competition is not other
orchestration frameworks; the competition is the terminal the user opens every
morning.

**Small-model orchestration is where the interesting engineering will be.** Post-it
12 names the shape. Two years from now the interesting engineering happens on
orchestrated groups of small specialized models — something in the neighborhood of
a small swarm of narrow specialists, none of them frontier-scale, all of them
cheap. Substrate today is a strong-model-plus-verifier arrangement; the same shape
tomorrow is a specialist ensemble under a coordinator. The runtime is model-agnostic;
strategy definitions name the role, and any model that satisfies the role drops in.

---

## What a named-strategy toolbox looks like

Every named strategy is a factored topology addressable from chat by name. The
name carries meaning. A first sketch of the toolbox:

- `code_review.adversarial` — three critics attack the diff from distinct
  perspectives (correctness, security, complexity), one synthesizer merges. Best-of-N
  produces alternatives; the synthesizer picks or composes.
- `code_review.pass_over` — a single reviewer walks the diff sequentially, flagging
  concerns with citations to the file, ending in a summary.
- `code_generation.spec_first` — user gives a spec; substrate drafts tests from the
  spec; a repair loop iterates the implementation against the tests.
- `code_generation.example_first` — user gives an example input/output pair;
  substrate writes the function to satisfy it, tests it against additional inputs,
  iterates.
- `roadmap.sprint_breakdown` — a goal in prose; substrate produces sprint-sized
  chunks with acceptance criteria and dependencies.
- `task_breakdown.estimation` — a task in prose; substrate produces an estimate,
  the risks, and the sub-tasks.
- `task_breakdown.spike` — a rough problem; substrate produces a two-day timeboxed
  spike plan with success criteria and abort conditions.
- `research.narrow_survey` — a question; three sources; a paragraph-sized summary
  and citations.
- `research.deep_dive` — a question; broad search; deep read; a structured report
  with sections for what is known, what is contested, what is open.
- `refactor.mechanical` — the diff is small and known-shape (rename, extract
  function, inline variable); substrate applies it across the codebase.
- `debug.reproduce_first` — a bug report; substrate produces a failing test that
  reproduces it, then the fix.

Names carry meaning. `code_review.adversarial` tells the user what happens.
`roadmap.sprint_breakdown` tells the user what happens. Naming is a design pass
worth doing well; the toolbox is only as usable as its names.

---

## What substrate has that fits

**Typed vocabulary and the record.** `substrate/kernel/` implements the primitives
and the append-only cycle. Every event lands on the record with a stable schema
(`msgspec.Struct` frozen; validated at the speaker's mouth per SDD kit-2's
poka-yoke). `substrate/api/narrate.py` renders the record as prose in the
vocabulary's own terms. This is T2 in code today.

**Nine bundled topologies.** `coding_flow`, `swebench_solver`, `best_of_n`,
`tool_loop`, `code_review`, `code_evolution`, `debate`, `pair_coding`,
`natural_conversation`. Each is a candidate strategy — needs a name, a home in a
registry, a place in the cockpit. The substrate for T3 exists; the naming and the
surface remain.

**Assay layer.** Suite, Arm, Case, Oracle, control plane, report, stats,
preregistration. Pre-registered comparators, paired McNemar, two-level bootstrap
on Δ-pass^k, Tango/Nam score-TOST for equivalence, Benjamini-Hochberg FDR across
the arm matrix. The verifiable half of the trio in the unnumbered card. The
record is the auditable half. Editable — live topology swap while a run is in
flight — comes later.

**Model seam.** `substrate/adapters/` — `OllamaResponder` for local + `:cloud`,
`CliResponder` for any command-line agent (Claude Code, Gemini, Aider), `EnsembleResponder`
for round-robin across N backends. Whatever strong model fits at the orchestrator
position drops in; whatever small models arrive drop in as ensemble members.

**SDD kit-2.** `sdd-kit-2/AGENTS.md` is the working agreement.
`TECHNIQUES.md` is the catalogue of ~53 universal + ~30 per-class techniques.
`grammar/PRINCIPLES.md` is the eleven-layer vocabulary discipline. The kit is
where T2's discipline comes from — vocabulary designed before code, validated at
the mouth, evolved through supervised proposals.

**substrate-ui.** A read-only console projecting a runtime's signal log into a
browser UI. The raw material for the cockpit shell; today it reads without
driving.

## What remains to build

**The cockpit process the user opens.** A standalone window with movable panes,
launched from the OS. The direction is to evolve `substrate-ui` (memory:
`project-cockpit-redesign-rulings.md`, canonical `COCKPIT-DIRECTION-round2` in the
substrate-ui repo).

**The chat pane as primary driver.** A `tool_loop`-shaped topology bound to a
cockpit action set. Chat opens files, opens URLs, dispatches strategies by name,
runs shell, shows state. A real terminal (Ghostty, iTerm) stays available beside
the chat; the chat sits alongside the shell the user already keeps open every
morning.

**The named-strategy registry.** Every bundled topology gets a name and a
one-sentence description. Chat resolves the user's phrasing to a name; the name
resolves to a factored topology. Registry is a first-class artifact.

**Panes for what the strategies produce.** Code the strategy edits; web pages the
strategy shows; the record the strategy writes. The exact number of panes is not
fixed yet; the themes commit and the count follows the strategies.

**Interior unfolding as a UI rhythm.** Panes open from the center, revealing like a
painting; the geometry matters for T4.

**Live editability of a running topology.** The third property from `IMG_0819`.
Substrate's `Registration` freezes at build; live edit needs a new event kind
(`substrate.RegistrationAmended`) and a hot-reload path. Ships after the cockpit
shell has real users.

---

## The next moves

Ordered by dependency. Sizing is rough but honest.

**1. Finish the SWE-bench Verified confirmatory (running).** Pass 1 measures
whether the ensemble mechanism holds. Pass 2 puts it in equivalence form. The
number decides only T5's timing; the shape holds either way. Small window (days).

**2. Evolve substrate-ui into the cockpit shell.** Standalone window, movable panes,
a real PTY somewhere, the interior-unfold rhythm. Direction fixed by memory
`COCKPIT-DIRECTION-round2`. Medium window (a month).

**3. Ship the chat pane bound to a cockpit action set.** `tool_loop` with the
initial tools: `open_pane(url)`, `load_file(path)`, `run_shell(cmd)`,
`dispatch(strategy_name, args)`, `show_state()`. Medium (two-three weeks after
step 2).

**4. Name the strategies and land the registry.** Every bundled topology gets a
name and a one-sentence description; chat resolves phrasing to name; registry as
a first-class artifact. Small-medium (a week or two).

**5. Add code and web panes as the strategies need them.** A strategy that emits
a patch wants the file open. A strategy that emits a chart wants a web view.
Panes arrive on demand. Medium (per pane, a week).

**6. Persistent cockpit memory.** The cockpit is itself a substrate run at a
well-known root; its own event log is its memory. Chat scrollback, pane layout,
open files — persistent by construction. Medium (a week).

**7. Live topology edit.** Third property from the unnumbered card. New event
kind, hot-reload path. Larger (a month), ships after real users exist.

**8. Drag-and-drop canvas.** The primitives to compose are few — producers
foremost, the rest inferable — so the canvas surfaces a small vocabulary. Ships
after the toolbox is full enough that users want to build new strategies. Large
(a month or more).

## Where the runtime and the cockpit want to diverge

The runtime is done in its important pieces. Each divergence below adds one thing to
the shell around it.

**A standalone desktop wrapper.** Launchable from the OS as a `.app` (macOS first;
Linux and Windows follow when someone asks). Tauri (small bundle, Rust backend,
WKWebView) is the right long bet; Electron is the fast first bet. A week of
prototyping settles the pick.

**A chat pane bound to a cockpit action set.** `tool_loop` at
`src/substrate/topologies/tool_loop/` is the shape today. The change is binding its
tool set to the cockpit's action set and running it continuously with a persistent
scrollback.

**An embedded web view for artifacts substrate produces.** Not a general browser
(the OS handles that when the cockpit hands off exterior). A pane that renders the
assay report, the substrate-ui signal graph, markdown docs. Shares the desktop
wrapper's built-in webview.

**An editor pane for the file the topology touches.** Monaco or CodeMirror driven
by file paths on disk. LSP for at least Python and TypeScript. Read + edit + save;
saves propagate back to any topology watching the file.

**Named-strategy dispatch from natural language.** The registry exists in code
(`kernel/topology.py:_REGISTRY`). What is missing is the naming pass on the
bundled topologies and the chat's tool for translating the user's phrasing into a
name.

**Persistent cockpit memory.** The cockpit runs as its own substrate at
`~/.substrate/cockpit/`; its event log carries the chat scrollback, pane layout,
open files. `LiveRecord` in `substrate/projections/attach.py` already handles the
follower half of the loop.

**Live topology edit.** New event kind `substrate.RegistrationAmended`; runtime
accepts it as a hot-reload signal for a subset of factories. Non-trivial — the
Registration is frozen at build for good reasons — but the third property of
`IMG_0819` demands it eventually.

**A causal-chain projection on click.** Walk the record backwards from a chosen
event, threading Trigger → PredicateEvaluated → View state at that seq. The
runtime carries the raw material; the cockpit renders it when the user clicks a
step and asks why.

**A drag-and-drop canvas.** A spatial editor that emits real `TopologyBuilder`
calls. The typed vocabulary is already the contract, so the canvas can emit
type-safe wiring without inventing a parallel DSL.

---

## The SWE-bench measurement in flight

The confirmatory sweep at
`process/assay_confirmatory_swebench_verified_2026-08/pass1/` is running as this
doc is written. It measures whether the ensemble mechanism claim in post-it 12
(small in cohesion beats one large model under orchestration) holds on SWE-bench
Verified. The ensemble arm is three free cloud-tag models (`glm-5.2:cloud`,
`kimi-k2.7-code:cloud`, `nemotron-3-super:cloud`); the control comparator (from
the pre-registration file at
`docs/preregistrations/2026-08-swebench-lite.preg.json`, updated for Verified) is
Agentless + GPT-4o at 27.8%.

If the ensemble arm beats the compute-matched single-model baseline, T5's timing
moves forward — the horizon claim is data today. If the ensemble is a
compute-purchased win rather than a mechanism-driven one, T5 defers to the horizon;
the substrate's shape still fits, but today's default topology moves to
strong-model-plus-verifier instead of ensemble. Either way T1–T4 hold; only the
default topology inside the cockpit changes.

The full matrix (pass 2, five arms, ~4,500 cells) is the equivalence-form claim
substrate goes public with. It runs after pass 1 lands and the observed K =
median-model-calls-per-case sets the matched-compute baseline's K.

---

## Risks and open questions

**Startup latency of the cockpit.** For the tool to be the one the user reaches
for, it opens fast. Ghostty opens instantly; the cockpit needs to feel the same.
Measure launch time from day one; treat regressions as blocking.

**Desktop tech.** Tauri vs Electron. Tauri is the long bet; Electron the fast
first. A week of prototyping decides. LSP integration is where the tech choice
bites hardest.

**Editor tech.** Monaco (VSCode's engine, richer) vs CodeMirror 6 (smaller,
faster). Pick with a working prototype, not in a doc.

**Chat pane cost.** A strong model at every user keystroke is expensive. Cache
against the substrate record so caching is a runtime concern; the LLM sees only
cache misses. The strong model sits at the orchestrator position; small models
handle the in-topology work.

**Trust in the output.** The runtime proves replay-equivalence and content-hash
identity. It cannot prove semantic correctness of an LLM answer. Trust in T4's
sense is the user's, not the runtime's. The cockpit shows enough of the process
that the user can decide they trust it — the narration view is the load-bearing
piece.

**Strategy name stability.** A named strategy today should be the same named
strategy tomorrow, even as the implementation improves. Discipline: version
strategies (`code_review.adversarial@1`, `code_review.adversarial@2`); users pin
when they want stable behavior; the registry surfaces the current version by
default.

**Which OS first.** macOS is where the developer lives. Linux and Windows
follow when someone asks.

**What if the SWE-bench number is disappointing.** T1–T4 hold. T5 defers. The
cockpit still wants chat + editor + web pane + strategy registry. The default
topology inside the cockpit becomes a Claude-shaped single-model-plus-verifier
arm; small-model orchestration ships as the arm the user selects when their task
fits it.

---

## The one-line summary

Text has always been how engineering happens; the new thing is a stochastic
interlocutor; substrate turns the exchange into a verifiable, composable, named
toolbox of software-engineering workflows; the cockpit is where the user sits
down and recognizes it.

*Companions on disk: `docs/NORTH-STAR-2026-08-09.md` (v1),
`docs/NORTH-STAR-2026-08-10.md` (v2),
`docs/NORTH-STAR-2026-08-10-v2.md` (v3.1), `docs/NORTH-STAR-2026-08-10-v3.md`
(v3.2), `docs/vision-postit-alignment-2026-08-09.md` (first-pass alignment).*
