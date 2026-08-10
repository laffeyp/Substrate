# Post-it vision → substrate alignment (2026-08-09)

*Sixteen post-its shot at a workbench. What the vision says, what substrate has today,
what is missing, and which move to make next. Source: `postitdesigns/IMG_0810–0827.HEIC`.*

---

## What the post-its say

Read in order 1–14 (some post-its share a number as a → b annex).

**1. `start as terminal using LLM`.** A signal-log rectangle. The everyday surface is a
terminal-style pane where an LLM is the driver, not a submenu.

**2. `"Display this on Chrome" ⇒ embedded browser`.** A window with two panes; the right
one is a page. The cockpit renders web content inline; the browser is a pane, not another app.

**3. `"I need to see the code" ⇒ embedded editor`.** File tree, source, output. The editor
is a pane too. Same treatment as the browser.

**4. `"I want to work by driving an LLM"`, `terminal ⇒ chat`, `direct interface to machine
is LLM`.** Two sketches: `API` list vs `type it yourself` box. The verdict is chat. The LLM
is the one machine interface.

**4a. `engineering via dialogue` (Socratic method / dialectic / thought → dialogue → action)
vs `engineering by thought → action`.** The dialectic loop is what makes the cockpit useful;
the LLM is the interlocutor.

**5. `"I want to use models to code" ⇒ substrate ⇒ default even for…`.** A `substrate`
outer box with an inner signal-log pane. Substrate is the default coding engine, not a
niche tool.

**6. `"I want to use LLMs to code in a verifiable, composable way that lets me multiply my
output by giving me all SWE workflows made to work with agents"`.** The one-sentence
product claim: verifiability + composition + agentic SWE workflows, all at once.

**7. `"I want to push my own limits. Work at the limits of my own understanding. That can
be dangerous if using LLMs due to stochastic nature."`.** The user pushes beyond what they
themselves can verify by hand. Stochasticity is the risk that must be engineered against.

**8. `"I want to build things I barely understand, learn by doing, and still trust the
output."`.** Same claim, sharper: trust must be delivered by the substrate, not by the
user's own review.

**9. `"interior vs exterior"`.** A window with a Google-like sub-frame and an
`open browser` link. Every external tool becomes an interior pane; leaving the cockpit
is the exception.

**10. `"I want to be able to define an input & output condition and wire models to
complete some goal in a verifiable way."`.** A `substrate` box with nodes + arrows + an
output. The topology — producers wired by triggers into a verifiable end state — IS the
composition unit.

**11. `"Claude"`, solid as model → `+ orchestrate` with a small model, `raise the bar via
error correction`.** A strong model orchestrates a smaller one; correction rounds are the
mechanism that raises the ceiling above the strong model's single-shot ceiling.

**12. `"Small is good enough" free models working in cohesion under orchestration vs one
paid model.`** The thesis: an ensemble of small free models beats one big paid model, given
the orchestration.

**13. `"I want to drag & drop common topologies."` `"I want to say review strategy N and it
reviews with that strategy."`.** Topologies are user-facing objects, addressable by name
and by drag.

**14. `Language = thought?` `What is under Language?`.** The philosophical anchor. If
language is thought, an LLM interface is the direct thought-to-machine surface. The whole
cockpit follows.

## What lines up

Substrate today already carries most of the load-bearing pieces the post-its describe.

**The runtime.** `src/substrate/kernel/` is the substrate box in post-its 5, 10, 11.
Producers, triggers, views, termination, records, replay — all implemented, all tested,
739+ tests green. Nine bundled topologies live under `src/substrate/topologies/`:
`coding_flow`, `swebench_solver`, `best_of_n`, `tool_loop`, `code_review`,
`code_evolution`, `debate`, `pair_coding`, `natural_conversation`. Post-it 10's
`define input & output, wire models` is `TopologyBuilder` at `kernel/topology.py:79`.

**Ensemble beats mono (post-it 11–12).** `EnsembleResponder` at `adapters/ensemble.py` and
the `n_drafts_repair_ensemble_arm` at `assay/swebench_matrix.py:171` are the coded form of
the claim. Whether the claim holds on SWE-bench is what the run in progress
(`process/assay_confirmatory_swebench_verified_2026-08/pass1/`) is measuring.

**Verifiability (post-its 6, 7, 8).** The `substrate.assay` layer (oracle, suite, run,
report, stats, preregistration) is the verification engine — pre-registered comparators,
paired McNemar, two-level bootstrap, TOST equivalence, Benjamini-Hochberg FDR. Every
Producer emits an event that lands on the append-only record; replay reconstructs any
state. The runtime enforces halt-on-error at the ProducerFailed boundary. What the user
"barely understands" can still be graded.

**Composition + typed vocabulary (post-it 10).** Each topology declares its schemas as
frozen `msgspec.Struct`s (a locked vocabulary per topology). Composition of topologies is
built-in: `embedded_substrate` at `kernel/composition.py:84` lets a substrate be a
Producer inside another substrate.

**SDD methodology (post-it 14, the language anchor).** `sdd-kit-2/` at the workspace root
is the discipline that makes the typed vocabulary real. Vocabulary-as-contract is the
mechanism by which "language = thought" becomes engineering, not slogan. The kit is a
process, not a prompt (see `sdd-kit-2/process-not-prompt-summary.md`).

## What is missing

The gap between substrate and the vision is almost entirely at the cockpit surface. The
runtime is there; the daily-driver UI around it is not.

**A cockpit process the user opens as their daily tool.** Post-its 1–3, 9, 13 all point
to one binary: a terminal-first window with an embedded PTY, an embedded browser pane,
an embedded editor pane, and drag-drop topology composition. `substrate-ui` (Addendum A
in `sdd-kit-2/ADDENDUMS.md`) is a read-only console projecting a runtime's log — the
right substrate for the cockpit, not the cockpit itself. Memory pointer:
`project-cockpit-redesign-rulings.md` says the direction is to EVOLVE `substrate-ui` into
this shape, not rewrite. Round-1 is dead; round-2 is the canonical plan.

**An LLM chat as the primary machine interface (post-it 4).** No such surface exists.
`tool_loop` is a topology (a bundled agent); it is not the always-on cockpit chat that
authors + edits + inspects a running substrate. This is the biggest UX gap.

**Embedded browser + embedded editor (post-its 2, 3, 9).** Nothing. `substrate-ui` renders
signal graphs; it does not host a browser view or an editor view. `interior vs exterior`
is the whole framing and it is not implemented.

**Named-strategy invocation (post-it 13).** Topologies are Python code today. There is no
name-based dispatch surface a user can say to. The pieces exist —
`api.register_topology(name, factory)` at `kernel/topology.py:326` — but no user surface
resolves natural language to a registered name.

**Drag-drop topology composer (post-it 13).** `TopologyBuilder` is a Python DSL. A GUI
that assembles the same registration graphically does not exist.

**Default coding surface (post-it 5).** No entrypoint invites the user to "code with
substrate by default." The daily-driver is a terminal running Claude Code or a browser
running Cursor. Substrate is a library today, not the surface.

**Small-model-orchestra demo (post-its 11, 12).** The claim needs a first-class,
demoable arm. `n_drafts_repair_ensemble` is the code; it lives inside the assay matrix,
not on a page the user shows a colleague.

## Path forward

The order below is by dependency, not by size. Each step lands a testable increment.

**1. Finish the SWE-bench Verified confirmatory (running now).** The claim in post-its
11–12 — small models in orchestration beat one paid model — needs the number to be a
number. Pass 1 completes on this run; pass 2 is the five-arm matrix that puts the claim
in `resolve@k` form against `Agentless + GPT-4o` (the pre-registered comparator, sha1
`3cc742abe707`). Without this, everything else is engineering ahead of a claim.

**2. Evolve `substrate-ui` into the cockpit shell (round-2).** Movable panes, a real
PTY pane, a standalone wrapper (a `.app` on macOS), a language pass on the running
console. Memory: `project-cockpit-redesign-rulings.md`, canonical
`COCKPIT-DIRECTION-round2` (in the `substrate-ui` repo). No new architecture — evolve
the console that already renders the signal log.

**3. Add the LLM chat pane (post-it 4).** The pane is a `tool_loop`-shaped topology that
runs continuously and speaks to the same cockpit event bus every other pane reads.
Whatever the user types is the driver; the LLM's tool calls open the browser pane, load
a file in the editor pane, or dispatch a topology by name. The chat is not a new backend
— it is `tool_loop` bound to the cockpit's local action set (`open_pane`, `load_file`,
`dispatch("review_strategy_N")`, ...). Its record IS the cockpit's memory.

**4. Add the embedded browser pane (post-it 2, 9).** A Chromium view (via
`pywebview` / `WebKit` / `Tauri`, pick after prototype) that renders any URL a topology
or a user sends it. First use: viewing the SWE-bench report; substrate-ui's own signal
graph; markdown docs. Explicitly a pane, not a spawned `open -a Chrome`.

**5. Add the embedded editor pane (post-it 3).** A Monaco or CodeMirror view driven by
file paths on disk. Read + edit + a language server. Same event bus. First use: opening
whatever file a topology's `SuspectFiles` names, inline in the cockpit.

**6. Named-strategy dispatcher (post-it 13).** Every registered topology gets a natural-
language alias (`review_strategy_thorough`, `review_strategy_fast`,
`swebench_solver_ensemble`, ...). The chat pane translates `"review this with strategy 3"`
to `dispatch("review_strategy_3", target=<current file>)`. The registry already exists
at `kernel/topology.py:_REGISTRY`; the natural-language surface does not.

**7. Drag-drop topology composer (post-it 13).** Deferred. The typed-vocabulary spine
means the composer can emit real `TopologyBuilder` calls, not a parallel format — that
is the correct order (spec then GUI), but the GUI is a large chunk of work. Ship after
the cockpit shell has real users.

**8. Default coding surface (post-it 5).** Once the cockpit shell + chat + editor + a
`swebench_solver`-shaped default topology exist, the invitation to "use substrate to
code" is a shell-level choice: launch the cockpit, tell the chat what you want, watch
the panes update. This is the payoff of steps 2–6; nothing new to design, only to wire.

## What NOT to do

The post-its make three claims by omission. Honor them.

**No `.app` in-app browser that navigates the whole web.** Post-it 9's `interior vs
exterior` is a distinction, not a mandate for a full browser. The embedded browser is
for displaying results the substrate produces, not for browsing.

**No new orchestration framework.** Post-its 10 + 11 describe the substrate we have.
Building a second (a LangChain-alike, an AutoGen-alike) throws away the typed
vocabulary + the record + the assay. Compose new topologies inside substrate.

**No cockpit-as-IDE.** The editor pane is not the point (post-it 3 asks for "see the
code," not "replace Cursor"). The point is a shared surface where the chat, the editor,
the browser, and the topology tree read the same event bus.

## One-sentence summary

The runtime lines up with the vision; the daily-driver surface does not; the SWE-bench
result underway is the single measurement that makes the small-models-in-cohesion claim
in post-its 11–12 either the wedge for the cockpit or a wound the cockpit has to hide.

*Source images: `postitdesigns/IMG_0810–0827.HEIC`, 16 post-its shot 2026-08-08.*
