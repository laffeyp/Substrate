# NORTH STAR — substrate as the cockpit (2026-08-09)

*Sixteen post-its from the bench, read four times: forward, back, at random, and slowly for
the drawings. What emerges is a product larger than substrate today. The runtime is the
engine; the cockpit is the machine. This is a full statement of the vision, the pieces
that match, the pieces that don't, and the sequence of moves that gets us there.*

Sources: `postitdesigns/IMG_0810–0827.HEIC`, transcribed inline.
Companion: `substrate/docs/vision-postit-alignment-2026-08-09.md` (the first-pass
alignment doc; superseded by this one but kept in place as the audit trail).

---

## Twelve claims the post-its make

Each claim is one sentence in the user's voice, with the file that carries it. The
philosophical anchors sit at the bottom; the product features sit at the top.

**C1. `I want to use LLMs to code in a verifiable, composable way that lets me multiply
my output by giving me all SWE workflows made to work with agents.`** (`IMG_0817`, post
6.) The single sentence that defines the product. Every other claim serves it.

**C2. `Start as terminal using LLM.`** (`IMG_0810`, post 1.) The daily-driver surface is
a terminal, and the terminal is driven by a language model. Not a menu, not a form, not
a REPL — a chat window with a running command line under it.

**C3. `"Display this on Chrome" ⇒ embedded browser.`** (`IMG_0811`, post 2.) When the
LLM produces a web artifact, it renders inside the cockpit as a pane. Chrome does not
open. The pane is the substrate's own view.

**C4. `"I need to see the code" ⇒ embedded editor.`** (`IMG_0812`, post 3.) Same
treatment as the browser. A code view is a pane, not a jump to VSCode. The pane is
scrollable, editable, syntax-highlighted, and connected to the same event bus every
other pane reads.

**C5. `I want to work by driving an LLM. Terminal ⇒ chat. Direct interface to
machine is LLM.`** (`IMG_0813`, post 4.) The alternatives sketched on the same card —
an API list and a "type it yourself" console — are shown as INFERIOR to chat. Chat
subsumes both: the LLM asks you what you want, translates to the API call. The verdict
is not "add chat alongside menus"; it is "chat replaces menus."

**C6. `I want to use models to code ⇒ substrate ⇒ default even for [...]`** (`IMG_0816`,
post 5.) The word that matters is **default**. Substrate is the everyday tool, not the
research niche. It competes for the seat Cursor and Claude Code occupy today.

**C7. `I want to define an input & output condition and wire models to complete some
goal in a verifiable way.`** (`IMG_0822`, post 10.) The sketch shows an ensemble
topology: fan-in of parallel producers, a central merge/transform, fan-out to
candidates, a final selector marked `→O`. This is what the user means by "topology" —
not a general DAG, but specifically the best-of-N + selector shape substrate already
implements.

**C8. `I want to drag & drop common topologies.` `I want to say review strategy N and
it reviews with that strategy.`** (`IMG_0826`.) Two related demands: a spatial canvas
for composition, and a named-strategy registry addressable from chat. `Strategy N` is a
number — the strategies are enumerated, versioned, and referenced by identifier, not
by re-authored prompt.

**C9. `Small is "good enough" — free models working in cohesion under orchestration vs
one paid model.`** (`IMG_0825`.) The engineering claim under substrate's ensemble arm:
several small free models, made to cohere by an orchestrator, outperform one big paid
one. Cohesion is not parallelism; it is a topology-level property.

**C10. `Claude` (solid OS model) `+ orchestrate small model, raise the bar via error
correction.`** (`IMG_0823`.) A finer version of C9. Claude is the OS-level backbone;
small models are the specialized userspace. Error-correction rounds — draft, critique,
correct, re-select — are the mechanism that raises the ceiling above what any single
model produces in one shot.

**C11. `Interior vs exterior.`** (`IMG_0821`, post 9.) The cockpit chooses per-artifact
whether to render it interior (a pane) or to punt to the OS (open the real browser). The
sketch shows the interior as the featured region and the exterior as a small hyperlink
at the bottom. Default is interior; exterior is the exception.

**C12. `Engineering via dialogue (Socratic method / dialectic / thought → dialogue →
action) vs engineering by thought → action.`** (`IMG_0815`, post 4a.) The load-bearing
philosophical claim. The dialogue inserts a step between thought and action, and that
inserted step is the engineering paradigm. The LLM is the second party in the dialectic.

## Three deeper anchors

Three cards sit under the product features and hold up the whole. Read them slowly.

**A1. `Language = thought? What is under language?`** (`IMG_0827`.) The deep question.
If language IS thought, then a chat with a fluent language model is not "a friendlier
interface" — it is the direct thought-to-machine surface. The question the post-it
poses — *what is under language?* — is the question SDD-kit-2's typed vocabulary
answers. The vocabulary is the model of meaning under the surface talk. The tag names
are the concepts. Chat is the layer the user speaks; typed events are the layer the
system speaks; the vocabulary translates.

**A2. `I want to push my own limits. Work at the limits of my own understanding. That
can be dangerous if using LLMs due to stochastic nature.`** (`IMG_0818`, post 7.) The
user names the risk. Stochasticity means an LLM's answer today is not its answer
tomorrow. If you build past your own understanding on top of unstable answers, you
build on sand. The substrate's job is to convert stochastic outputs into a verifiable
ledger, so the user can push past their understanding without paying stochastic tax.

**A3. `I want to build things I barely understand, learn by doing, and still trust the
output.`** (`IMG_0820`, post 8.) The sharper form of A2. The user demands three
properties at once: **build past understanding**, **learn by doing**, **trust the
output**. The middle demand (learn by doing) means the cockpit is a schoolroom as much
as a workshop. Every action is legible enough to teach.

## The unnumbered card: framework at the highest level

`IMG_0819` has no visible number. It reads:

> `I need a thing that gives me the framework to work at the highest level but remain
> verifiable, auditable, editable, etc. Tame the errors.`

Three properties are named where one usually is: **verifiable**, **auditable**,
**editable**. Verifiable means the answer can be checked. Auditable means the process
that produced it can be inspected. Editable means the process can be changed. All three
apply — a solve that's verifiable but not auditable is a black box; auditable but not
editable is a museum. The cockpit's promise is all three, together, at the highest
level of user ambition.

---

## What substrate has today

Substrate carries most of the engine. The runtime is production-grade; the discipline
is codified; the assay layer is built. What is missing sits above.

**The runtime.** `src/substrate/kernel/` implements the eight primitives (Producer,
Trigger, Route, View, TerminationPolicy, FiringPolicy, Subscription, BlobRef). The
single-writer append cycle is at `kernel/sequencer.py`. Records are content-hashed
JSONL frames with CRC + torn-tail recovery (`record/framing.py`, `record/record.py`).
753 tests green as of the current run. Replay ships at levels 1, 2, 3(a); level 3(b)
is deferred pending a t-replay decision.

**The nine bundled topologies.** `coding_flow`, `swebench_solver`, `best_of_n`,
`tool_loop`, `code_review`, `code_evolution`, `debate`, `pair_coding`,
`natural_conversation`. Each declares its schemas as frozen `msgspec.Struct`s — a
per-topology locked vocabulary. This is the substrate for C7's `wire models to
complete some goal in a verifiable way`. It is also the substrate for C8's `common
topologies`; they already exist as named factories, just not yet as drag-drop objects.

**The assay layer.** `substrate/assay/` — Suite, Arm, Case, Oracle, control plane,
report, stats, preregistration, conformance. Pre-registered comparators, paired
McNemar, two-level bootstrap on Δ-pass^k, Tango/Nam score-TOST equivalence,
Benjamini-Hochberg FDR across the arm matrix. The pass 1 SWE-bench run in progress
(`process/assay_confirmatory_swebench_verified_2026-08/pass1/`) is exercising the
whole surface end-to-end.

**The model seam.** `substrate/adapters/` — `OllamaResponder` for local + `:cloud`
tags, `DeterministicResponder` for CI, `CliResponder` for any command-line agent
(Claude Code, Gemini, Aider), `EnsembleResponder` for round-robin across N backends.
Any model that speaks HTTP or a CLI drops in.

**SDD kit-2.** The discipline: vocabulary-as-contract, dual + observation contract,
Rubber Duck Pass, halt-and-articulate. `sdd-kit-2/AGENTS.md` is the working agreement;
`sdd-kit-2/TECHNIQUES.md` is the ~53-entry catalogue. This is the answer to A1:
vocabulary is what sits under language.

**substrate-ui.** A read-only console projecting a runtime's signal log into a browser
UI. Playwright-driven visual harness (see `sdd-kit-2/ADDENDUMS.md` Addendum A). This is
the raw material for the cockpit, but not the cockpit itself — the console reads; the
cockpit must also drive.

## What is missing

The runtime is the foundation. The vision demands a house on top of it. Almost none
of that house is built.

**M1. A cockpit process the user opens as their daily tool.** The `.app` or the `docker
run` line that launches the day. Movable panes, a title bar, standard OS
integration. Nothing on disk does this today. Memory pointer:
`project-cockpit-redesign-rulings.md` says the direction is to evolve substrate-ui
into this shape, not to rewrite; the canonical plan is `COCKPIT-DIRECTION-round2` in
the substrate-ui repo. Round-1 is a dead branch.

**M2. The chat pane (C2 + C5).** The primary surface. A `tool_loop`-shaped topology
that runs continuously, holds the cockpit's own event bus in context, and translates
the user's natural language into calls: `open_pane(url)`, `load_file(path)`,
`dispatch("review_strategy_3", target=<current file>)`, `spawn(topology, args)`. This
is not a new topology — `tool_loop` at `src/substrate/topologies/tool_loop/` already
has the shape. What is missing is the binding to a cockpit action-set and the
persistent chat scrollback.

**M3. The embedded browser pane (C3 + C11).** A Chromium view (via `pywebview`,
`WebKit.WKWebView`, or Tauri) that renders any URL a topology or the user hands it.
First use: viewing the SWE-bench report; substrate-ui's own signal graph; markdown
docs; the generated HTML the assay report emits. A pane, not `open -a Chrome`.

**M4. The embedded editor pane (C4).** A Monaco or CodeMirror view driven by file
paths on disk. Read + edit + a language server. Same event bus. First use: opening
whatever file a topology's `SuspectFiles` names, inline in the cockpit. On save, the
edit lands on disk and any topology watching the file re-runs.

**M5. Named-strategy dispatch (C8).** Every registered topology needs a
natural-language alias. The registry exists (`kernel/topology.py:_REGISTRY`); the
translation layer does not. The chat pane speaks NL; the dispatcher turns `"review this
with strategy 3"` into `dispatch("review_strategy_3", target=<current file>)`. The
strategies themselves are already just topologies; naming them is a policy.

**M6. Drag-drop topology composer (C8).** A spatial canvas where topologies are
draggable objects, and where composing them emits real `TopologyBuilder` calls (not a
parallel serialization format). Because the typed vocabulary is already the contract,
the canvas can emit type-safe wiring — it doesn't invent a new DSL. This is the
biggest single piece of new work, and it comes AFTER the chat + browser + editor panes.
Ship after the cockpit shell has real users.

**M7. Default coding surface (C6).** Once M1–M5 exist, the invitation to "code with
substrate by default" is a shell-level choice: launch the cockpit, tell the chat what
you want, watch the panes update. Nothing new to design here; only to wire.

**M8. Persistent cockpit memory.** The chat's scrollback, the pane layout, the open
files, the dispatched topologies — all of this needs to survive a cockpit restart.
The runtime already knows how to persist an append-only log; the cockpit reuses that.

## Fresh ideas from the second pass

The first read caught the shape. The second read (backwards, random, slow) caught
these.

**F1. Chat subsumes menus AND type-it-yourself; it does not coexist.** Post 4's sketch
puts the API list and the terminal-console side by side as `VS`; the arrow lands on
chat. Substrate today has neither an API menu surface nor a native REPL — the runtime
is a library. When the cockpit ships, it needs to ship chat as the ONLY driving
surface, not chat plus menus. Menus optimize for the case where the user knows what
they want. Chat optimizes for the case where the LLM knows what the user wants BETTER
than the user does. The vision is the second case.

**F2. Cohesion is a topology-level property, not a compute-level one.** Post 12 says
`working in cohesion under orchestration`. Random parallel samples do not cohere. The
orchestration is what makes cohesion. This puts substrate on the right side of the
`n_drafts_repair_ensemble` result. If pass 1 shows the ensemble beats the strong single
model on resolve@k while spending less compute, cohesion is the mechanism. If it
doesn't, the claim collapses to "small models are cheap" — a compute-purchased win, not
a mechanism-driven one.

**F3. Claude-as-OS inverts the usual framing.** Post 11 does not say "we use Claude."
It says "Claude" and puts the whole substrate stack under it, with small models
orchestrated as userspace processes. This has two implications. First, the cockpit's
default backbone is Claude (via the API or via the Claude Code CLI through
`CliResponder`), not a swarm of small models. Second, small models are the specialty
compute — they run inside the orchestrated topologies. Substrate does not choose
between big and small; it uses big to orchestrate small.

**F4. Interior/exterior is a policy the cockpit makes per-artifact.** Post 9 sketches
both — an interior pane at the top and an "open browser" link at the bottom. The
implication is a decision rule: substrate decides, per artifact, whether to render
interior or hand off exterior. Default = interior. Exterior is the escape hatch. The
decision rule is a first-class part of the cockpit spec, not an afterthought.

**F5. Language = thought is a design constraint, not a slogan.** Post 14 asks `what is
under language?` — and the whole cockpit's answer is: the typed vocabulary. Chat is
the surface the user speaks. Events are the surface the system speaks. The vocabulary
translates. Which means the vocabulary must be **legible from chat** — the user can ask
"what events did the last run emit?" and the chat produces a narration in the
vocabulary's own terms. `substrate/api/narrate.py` already does this projection; the
cockpit surfaces it directly.

**F6. `Strategy N` implies a registry with cardinal identity.** Post 13 says
"strategy N" — N is a number. Strategies are enumerated, versioned, and referenced by
number. This is a stronger claim than "named strategies"; a NUMBERED registry is
stable across time. `Strategy 3` today is `Strategy 3` tomorrow, even if the
implementation changes. That is a pre-registration discipline: change the number when
the behavior changes materially.

**F7. Drag & drop is a canvas, not a form.** Post 13's `drag & drop common topologies`
means a spatial editor. This is the largest single UX chunk in the vision. It is also
the only place the vision explicitly names a graphical composition surface;
everywhere else the composition is via chat. The canvas is for the case where the user
needs to see the wiring — the audit form of C7.

**F8. Verifiable + auditable + editable are three, not one.** `IMG_0819`'s trio
enforces separate properties. Substrate today has verifiable (assay), and auditable
(the record). Editable means the topology itself can be changed AT RUNTIME — a
running arm swapped for a different arm, a Producer's factory replaced. Substrate
does not do this today. Post-run editing is: kill the run, edit the topology, re-fire.
The vision asks for live edit.

**F9. Stochastic risk is a first-class UI problem, not just a backend one.** Post 7 says
stochasticity is DANGEROUS at the user's ambition ceiling. This means the cockpit
must SHOW uncertainty. When a topology produces an answer, the cockpit must convey how
sure it is. Substrate's assay layer already computes CIs and equivalence verdicts;
the cockpit's job is to render them so the user reads confidence at a glance.

**F10. Learn by doing means the cockpit is a schoolroom.** Post 8's middle demand.
Every dispatched topology should be inspectable in ways that teach: "here is what the
first draft looked like, here is why the validator rejected it, here is what the
correction round changed, here is what the selector chose." Substrate has the events
on the record; the cockpit turns them into a teaching narrative. `narrate.py` is the
half of this already built. The teaching half is the second half.

**F11. Engineering via dialogue is not brainstorming; it is the process itself.** Post
4a inserts DIALOGUE between THOUGHT and ACTION. The dialogue is not a preliminary chat
before you go do the work — the dialogue IS the work. Every code change goes through
the dialectic: the user proposes, the LLM critiques or completes, the user accepts or
counters, action follows. This is what Cursor Agent / Claude Code already approximate.
Substrate's cockpit needs the same feel, but the underlying substrate is a running
topology (not a single LLM call), and the record is the audit trail (not a chat
history).

**F12. "Default even for..." names the market claim.** Post 5's cut-off phrase is the
positioning statement. Substrate should be the default coding tool the user reaches
for even for small tasks that a plain Cursor session would handle. This is a much
higher bar than "substrate wins on hard problems"; it is "substrate wins on the mean
problem." The engineering implication: cockpit startup latency matters. A tool that
takes 10 seconds to spawn a topology loses to Cursor's inline autocomplete. The
default-tool claim forces low-latency paths for the small case.

---

## The cockpit north star

Read the twelve claims and twelve fresh ideas together and one product falls out. The
cockpit is:

**A single-window desktop application.** Standalone, launchable from the OS. Not a
browser tab. Reason: the browser tab framing loses focus, cannot host a real PTY, and
undersells the substrate as a daily tool.

**Four panes, movable, resizable.** (1) Chat, the primary. (2) Terminal PTY, running
the shell the LLM drives. (3) Editor, showing the code the LLM edits. (4) Browser,
showing web artifacts the LLM produces. Post 2's browser is a pane, not a link; post 3
is the same. Post 9 says interior by default; the panes are interior; exterior is the
escape hatch.

**One LLM as the driver, always on.** Post 4 + post 11 together: Claude is the
OS-level model driving the chat pane. The chat pane's `tool_loop` topology is bound to
a cockpit action set: `open_pane(url)`, `load_file(path)`, `run_shell(cmd)`,
`dispatch(strategy_name, args)`, `spawn_arm(arm_name, args)`, `read_events(filter)`,
`show_state()`. Chat is the machine interface; every menu the user would have used
becomes a natural-language sentence.

**A named-strategy registry.** Post 13. Every topology has a stable name + number.
Chat dispatches by name; the drag-drop canvas (later) composes new ones. The registry
is a first-class artifact under `substrate/strategies/` or similar.

**A record backbone.** Every action — every chat message, every dispatch, every
edit, every pane open — lands on the substrate record. Reason: post 8's `trust the
output` demands the trail exists. Post 7's `dangerous stochastic nature` demands the
trail is complete. `narrate.py` renders the record as the cockpit's history view.

**Small-model orchestration by default.** Post 9 + 10. The cockpit's default dispatch
for coding tasks is the `swebench_solver`-shaped topology: ensemble of small models,
correction rounds, verifier-based selection. Claude sits above as the reviewer and the
orchestrator; small models drive the fan-out. This is the substrate's mechanism claim
made real on every task.

**The typed vocabulary as the interpreter.** Post 14's philosophical anchor. Chat is
the surface the user speaks; events are the surface the system speaks; the typed
vocabulary translates. When the user asks the chat what happened, the chat narrates
in the vocabulary's terms. When the user asks the chat to compose a topology, the
chat writes it in the vocabulary. The vocabulary is the schema of everything.

**A learning surface (post 8).** Every dispatched topology is inspectable in a way
that teaches. The cockpit has a "why did this decision get made?" affordance —
click a step, see the events that led there, see the alternatives that were
considered. The runtime already carries the raw material; the cockpit renders it.

**A verifiable, auditable, editable substrate (`IMG_0819`).** The three properties are
each their own surface. Verifiable is the assay report. Auditable is the narration
view. Editable — the missing third — is live topology swap: change the strategy while
a run is in flight and see the difference land in the next cell.

## Where the cockpit and the runtime diverge from substrate today

Nine deltas. Each names one thing substrate would gain, one thing substrate would
NOT gain, and the shape of the work.

**D1. Standalone desktop wrapper.** GAIN: launchable process, native window, OS
integration. NOT GAIN: cross-platform mobile. Shape: Tauri or Electron shell around
the substrate-ui web view + a native menu bar. Small — a week if we pick the tech
right. Anchor: memory `project-cockpit-redesign-rulings.md`.

**D2. Chat pane bound to a cockpit action set.** GAIN: primary user surface. NOT
GAIN: a new LLM abstraction. Shape: a `tool_loop` topology whose tool set is the
cockpit's action set, streamed live to the chat pane. The tools call into the same
substrate runtime everything else calls into. Medium — two weeks.

**D3. Embedded browser pane.** GAIN: interior rendering of web artifacts. NOT GAIN: a
general-purpose browser (that is post 9's escape hatch). Shape: pick pywebview /
WKWebView / Tauri's built-in webview at the same time as D1 and share the wrapper.
Small — a few days after D1.

**D4. Embedded editor pane.** GAIN: interior code view. NOT GAIN: Cursor's every
feature. Shape: Monaco or CodeMirror in a pane, backed by a Language Server Protocol
adapter for at least Python + TypeScript. Medium — a week or two.

**D5. Named-strategy registry with NL dispatch.** GAIN: `dispatch("review_strategy_3",
...)` from chat. NOT GAIN: LLM-authored new strategies at runtime. Shape: add
`strategy_name` + `strategy_number` to every registered topology, wire the chat's
tool set to translate NL to a name. Small — a few days.

**D6. Persistent cockpit memory.** GAIN: chat scrollback + pane layout + open files
survive restart. NOT GAIN: a new database. Shape: the cockpit itself is a persistent
substrate run at a well-known root; its own event log is its memory. `LiveRecord`
already does the follower half. Medium — a week.

**D7. Live topology edit (F8's third property).** GAIN: change the strategy mid-run
without killing it. NOT GAIN: mutable topology declarations (the current
Registration is frozen at build). Shape: introduce a new event kind
`substrate.RegistrationAmended`, let the runtime accept it as a hot-reload signal for
a subset of factories. Big — a month. Deferred until D1–D6 land.

**D8. Learning surface (F10).** GAIN: click a step, see why it decided that. NOT
GAIN: a plain event viewer (the substrate-ui console already does that). Shape: a
`whys` projection that walks the record backwards from a chosen event, threading
Trigger → PredicateEvaluated → View state at that seq → the causal chain. Medium — a
week or two.

**D9. Drag-drop topology canvas.** GAIN: spatial composition surface. NOT GAIN: a
replacement for the Python DSL. Shape: web canvas library (React Flow, Rete) plus
codegen that emits real `TopologyBuilder` calls. Big — a month or more. Ship LAST,
after the cockpit shell has real users.

---

## The pass-1 result is the wedge

The SWE-bench Verified pass 1 currently running
(`process/assay_confirmatory_swebench_verified_2026-08/pass1/`) is the single
measurement that decides whether the substrate is the cockpit's engine or a
research toy. If the ensemble arm (`glm-5.2:cloud + kimi-k2.7-code:cloud +
nemotron-3-super:cloud`, all free tier) beats the compute-matched single-model
baseline (`deepseek-v4-pro:cloud` at K=median-of-ensemble calls), post 9's `small in
cohesion beats one paid model` claim is DATA. That number sells the cockpit — every
other feature is built on the mechanism claim.

If it doesn't, the honest thing is: substrate's ensemble is a compute-purchased win,
not mechanism-driven. The cockpit still wants a chat pane and an editor pane; the
default topology in M7 changes. Maybe it's a single-Claude topology + a verifier
loop, not an ensemble. The vision survives; the specific mechanism doesn't.

Pass 2 (the five-arm matrix) puts the number in equivalence form and grades it under
FDR. That is the resolve-rate claim substrate goes public with.

## Roadmap, dependency order

Numbered. Each numbered step ships a testable increment.

**1. Finish the SWE-bench Verified confirmatory (running now).** Blocking gate on
everything below. Pass 1 completes; pass 2 (matrix) fires next.

**2. Ship the cockpit shell (M1 + D1).** Standalone desktop wrapper, four empty panes,
title bar. Launches from the OS. The proof point: the tool exists as an app you can
open.

**3. Ship the chat pane (M2 + D2).** `tool_loop` bound to the cockpit action set.
First action set: `open_pane(url)`, `load_file(path)`, `run_shell(cmd)`,
`show_state()`. Proof: type "open google.com" in chat, browser pane loads
google.com.

**4. Ship the browser pane (M3 + D3).** Rendering only; the chat drives it. Proof:
same demo as step 3, but the browser is a real Chromium view, not a link.

**5. Ship the editor pane (M4 + D4).** Read + write + syntax + LSP for Python.
Proof: `load_file substrate/kernel/runtime.py` in chat, code appears in the editor
pane with hover-doc from the LSP.

**6. Ship the strategy registry + NL dispatch (M5 + D5).** Rename the bundled
topologies with `strategy_number`s. Proof: `dispatch strategy 1 on current file` in
chat runs `swebench_solver` on the file in the editor pane.

**7. Ship persistent cockpit memory (D6).** The cockpit's own event log at
`~/.substrate/cockpit/`. Proof: quit cockpit, relaunch, chat scrollback and pane
layout restore.

**8. Ship the learning surface (D8).** `whys` projection + click-to-explain UI. Proof:
click a step in the assay report, see the causal chain in a side pane.

**9. Announce substrate as a coding tool (M7 + F12).** Public post, landing page,
`brew install substrate`. Proof: metric = daily active users of the cockpit; target =
100 within a month of launch.

**10. Ship live topology edit (D7).** The third property from `IMG_0819` (editable).
`substrate.RegistrationAmended` event. Proof: swap a solver arm mid-run, next cell
uses the new arm.

**11. Ship the drag-drop composer (M6 + D9).** Spatial canvas emitting real
TopologyBuilder calls. Proof: assemble a new topology on the canvas, save, dispatch
by number.

Steps 2–5 are the cockpit MVP; ship them together, sequenced, in a single 2–3 month
push. Steps 6–8 are the professional-tool follow-up. Steps 9–11 are the growth push.

---

## Non-goals

The post-its say five things by omission. Honor them.

**Not a new orchestration framework.** Posts 10 + 11 describe substrate as it is
today. Do not build a second orchestrator (a LangChain, an AutoGen). Compose new
topologies inside substrate. The vocabulary and the record are the mechanism advantage;
throwing them away throws the mechanism away.

**Not a full replacement for Chrome.** Post 9 is precise. The interior browser
renders substrate's own artifacts; the exterior browser is where the user goes when
they want to actually browse. The cockpit does not host tabs, bookmarks, or
navigation controls. It hosts substrate's outputs.

**Not Cursor.** Post 3 says `see the code`, not `replace Cursor`. The editor pane is
for reading and light editing of the file the topology is working on. If the user
wants Cursor's full experience, they open Cursor. The cockpit's editor is a pane, not
a workshop.

**Not a chat product.** Post 4 makes chat the driver, but chat is not the DELIVERABLE.
The deliverable is the finished code, the finished analysis, the finished substrate
run. Chat is the wheel; the car goes places.

**Not a plain LLM UI.** Post 12 requires the dialectic — thought → dialogue → action.
A chat with a model that only speaks (never acts) fails the dialectic. The cockpit's
chat must dispatch, edit, run, verify. Otherwise it's a browser tab pointing at
claude.ai.

---

## Risks and open questions

**R1. Cockpit startup latency (F12).** If the cockpit takes more than 3 seconds to
launch and show the chat, the default-tool claim fails. The daily driver is the tool
that opens FAST. Design decision: measure launch time from day one; treat any
regression as a P0.

**R2. Which desktop tech.** Tauri (small bundle, Rust backend, WKWebView) vs Electron
(fat bundle, Chromium, mature). Tauri is the right long bet; Electron is the fast
first bet. Prototype both in a week, pick.

**R3. Which editor tech.** Monaco is VSCode's engine; CodeMirror 6 is smaller. Monaco
if we want LSP-parity with VSCode. CodeMirror if we want a lighter footprint.
Decide with a working prototype, not in a doc.

**R4. LLM cost for the chat pane.** Claude at every user keystroke is expensive.
Cache aggressively; make chat state a substrate record so caching is a runtime concern
not a LLM concern. Pair with F3: Claude-as-OS drives the chat; small models handle the
in-topology work.

**R5. What does "trust the output" mean operationally?** (Post 8.) The runtime can
prove replay-equivalence and content-hash identity. It cannot prove semantic
correctness of an LLM answer. Trust in the vision is DIFFERENT from trust in a proof;
the cockpit must show enough of the process that the user can decide they trust it.
This is a UX problem as much as a runtime one.

**R6. Named-strategy stability across time.** (F6.) `Strategy 3` today must be
`Strategy 3` tomorrow, even if the implementation improves. Discipline: version
strategies (`Strategy 3.1`, `Strategy 3.2`); the user can pin. The runtime's
manifest can carry a `strategy_version` field.

**R7. Which OS first.** macOS is where the current developer lives. Linux and
Windows are follow-ons. Ship macOS first; do not build for Linux/Windows until
someone asks.

**R8. What if the SWE-bench number is disappointing.** The vision does not fall.
The cockpit still wants chat + editor + browser + strategy registry. The default
topology in step 6 changes: a Claude-first single-model-plus-verifier arm rather
than the ensemble. F3's Claude-as-OS still holds; the small-models-in-cohesion claim
gets deferred to a specific class of task where it demonstrably wins.

---

## One-paragraph summary

Substrate is the engine; the cockpit is the machine the user opens. The post-its
describe a single-window desktop tool with a chat pane, a terminal pane, an editor
pane, and a browser pane, all driven by a Claude-shaped LLM that dispatches typed
topologies from a named registry. The typed vocabulary answers the philosophical
anchor (`Language = thought? What is under language?`) — the vocabulary is what sits
under language. The mechanism claim (`small in cohesion beats one paid model`) is
what the SWE-bench pass currently underway measures. Everything else — the panes,
the registry, the composer, the persistent memory — is engineering on top of the
runtime that already exists. Twelve months of work, sequenced. The pass-1 number
decides the pitch.

*Sources: `postitdesigns/IMG_0810–0827.HEIC` (16 post-its, 2026-08-08). Companion:
`docs/vision-postit-alignment-2026-08-09.md` (first-pass alignment). Anchors:
`sdd-kit-2/ADDENDUMS.md` (Addendum A, substrate-ui harness), `MEMORY.md` pointers
`project-cockpit-redesign-rulings.md`, `project-product-vision-cockpit.md`.*
