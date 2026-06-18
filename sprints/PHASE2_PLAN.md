# Phase 2 — Applications + visibility roadmap (PROPOSED)

*Build-organizer planning artifact. Status: PROPOSED, pending Architect go. Not a dispatch.*

*Phase 1 produced the runtime. Phase 2 produces the surface most users actually touch: the topologies that demonstrate what the runtime can do, and the TUI that lets a human watch it happen. The conformance gate and replay correctness are already shipping; Phase 2 makes them visible.*

*Grounded in: kernel v15 §What this enables + §Where this points; product spec draft7 §8 (R-1..R-3 already shipped); design spec draft1 §8 (future UI sketches now in scope).*

---

## What this phase delivers

1. **A bundled topology catalogue.** Six new topologies, each shipping with: a Python module under `substrate.topologies.<name>`, a deterministic CI-mode record, an annotated walkthrough doc, and a captured walkthrough-mode record (run against a real local LLM, committed for replay).

2. **A terminal UI** (`substrate tui`). Live-attached view of a running or recorded topology — Producer state column, semantically-colored event stream, topology graph overlay, status bar with writer-stats, replay scrubbing. Built only on public substrate surfaces (F-API-6 second existence proof).

3. **A topology gallery** — `substrate topology list`, `substrate demo <name>`, `substrate demo replay <name>`, with bundled and pip-installable community topologies discovered via setuptools entry points.

4. **An interactive tutorial.** `substrate tutorial step<N>` walks through writing a topology with live feedback, using the runtime to teach the runtime.

---

## Sequencing principle

The TUI design depends on knowing what topologies it has to visualize. The topologies depend on the runtime (Phase 1 — done). The gallery depends on having topologies AND the TUI. The tutorial depends on all of it.

So the order is: survey → TUI design → TUI build (in parallel with) priority topologies → gallery + tutorial integration.

Sweet spot honored: **≤2 files / one concept per sprint** (hard rule 6). Wave-0-carry contracts at start. **N.INT** integration sprint per wave.

---

## Wave 10 — Survey + design  *(architecture/research)*

Pre-fills the catalogue and the TUI design before any building begins.

- **S-10.1** Application catalogue survey. Read every §What this enables and §Where this points across the spec corpus. For each candidate: implementation cost (afternoon / day / week), substrate-coverage value (which primitives it stresses), shock-and-awe value (does a non-expert immediately understand the value over LangGraph / Claude Code / Aider). Produce a sorted list with the top 6 marked "build now," the rest deferred with reasons. *(research)*
- **S-10.2** TUI design specification. Pane layout, color scheme, keybinds, modes (live/replay/focused/tree), latency display, narration overlay surface, and the public-surfaces-only contract. Includes a Textual-vs-alternatives comparison and the decision. *(architecture)*
- **S-10.bridge** SDK bridge mapping for **Textual** — reverse-engineer the real API surface for app shape, reactive state, async event handling, key binding dispatch. *(bridge)* — MUST land before S-12.1.
- **S-10.INT** Catalogue ratified by Architect; TUI design spec ratified; bridge mapping committed; next-wave dependencies confirmed.

---

## Wave 11 — First three priority topologies  *(functional)*  →  exercises every primitive in walkthrough mode

The topologies the user explicitly named, plus the recursive-decomposition demo because it's the substrate's most visible departure from LangGraph.

- **S-11.1** `topologies/code_review.py` — N-LLM code review (default N=5) with role-distinct system prompts (security, performance, style, correctness, clarity). Reviewer Producers stream critiques in parallel; a judge Producer fires on fan-in and emits a verdict; cancel-all-others on adjudication. CI mode uses deterministic canned critiques; walkthrough mode uses local LLMs via the `[openai-compat]` extra. Committed records for both modes. *(functional)*
- **S-11.2** `topologies/pair_coding.py` — driver Producer streams code; navigator Producer subscribed to a View of the driver's buffer emits typed suggestions; a Route stages suggestions for the driver's next chunked instantiation. Committed records for both modes. *(functional)*
- **S-11.3** `topologies/recursive_decomposition.py` — planner Producer emits N subtask events; a Trigger with PerEvent firing fires N solver Producers; each solver may itself emit further subtask events that the same Trigger matches at any depth. Bounded by a budget predicate counting depth. CI mode uses a deterministic planner with a fixed-depth tree; walkthrough mode uses local LLMs producing a real-shape tree. *(functional)*
- **S-11.INT** All three topologies' CI records replay at Level 2 (every recorded decision reconstructed + hash-verified) and committed under `topologies/<name>/records/`; walkthrough records exist and replay at Level 2. (Level-3(b) byte-identity is the deferred A1.1 item — `replay --level 3b` raises NotImplementedError and conformance check 6 stays DEFERRED — NOT a Phase-2 gate.) Each topology's docstring honestly describes what it demonstrates.

---

## Wave 12 — TUI build  *(functional)*

Built only on public substrate surfaces. Verified by import-linter.

- **S-12.1** `cli/tui/app.py` — Textual app shell with the panel layout from S-10.2; attaches to a record via `substrate.api.attach()`; renders the live event stream with semantic coloring; status bar reads writer-stats sidecar. *(functional)*
- **S-12.2** Topology graph overlay — reads the `RunStarted` event's topology manifest and renders Producer kinds + Triggers + Routes as ASCII or Unicode box-drawing; flashes Triggers as they fire; reads producer state to render running/completed/cancelled. *(functional)*
- **S-12.3** Replay scrubber + focused mode + tree mode — keybinds for navigation; current state of every named View shown at the selected sequence; `f` to focus one Producer (main pane filters to its emissions); `t` to render Producer ancestry as a live tree (for recursive-decomposition demos). *(functional)*
- **S-12.4** Per-Producer latency display — for each Producer with `running` status, show recent emission rate and current streaming-state indicator. For LLM Producers, surface token-rate and progress if the adapter exposes them. *(functional)*
- **S-12.INT** TUI imports `substrate.api` and `textual` only (verified by import-linter rule); attaches to all three Wave-11 records and renders them correctly in live and replay mode; F-API-6 second existence proof.

---

## Wave 13 — Three more topologies  *(functional)*

The shock-and-awe set plus the research workflow.

- **S-13.1** `topologies/population_simulation.py` — N agent Producers (default N=50) emitting typed action events each tick; a world-state Producer subscribed to all actions emits typed world-state events; agents' next-step inputs routed from world-state updates; the bus is the simulation log. Walkthrough mode runs all agents through one batched local model (e.g. Qwen 2.5 1B via Ollama with `OLLAMA_NUM_PARALLEL=50`). *(functional)*
- **S-13.2** `topologies/adversarial_pair.py` — writer Producer streams an artifact; vulnerability-finder Producer subscribed to a View of the writer's buffer emits typed challenge events; a Trigger with predicate on challenge events fires a refinement Producer. Both stream concurrently from t=0; the refinement loop bounded by attempt-count predicate. *(functional)*
- **S-13.3** `topologies/research_workflow.py` — M retrievers stream candidates; a synthesizer Producer fires at the first relevance-predicate cross; a fact-checker Producer subscribed to the synthesizer's View routes corrections into the synthesizer's next instantiation; a citation-extractor Producer fires on `SynthesisComplete` and emits citation events; an optional `pause-await-input` policy allows human review before finalisation. Combines several primitives in one topology — the "you can compose all this?" demo. *(functional)*
- **S-13.INT** All three topologies' CI records replay at Level 2 (decisions reconstructed; Level-3(b) deferred, A1.1); walkthrough records committed; TUI tree mode renders the population simulation legibly; adversarial pair clearly shows two streams running concurrently in the TUI.

---

## Wave 14 — Gallery + records + tutorial  *(functional)*

The discovery surface and the on-ramp.

- **S-14.1** Bundled topology registry — `substrate.topologies.bundled` package with entry-point discovery; `substrate topology list` enumerates installed topologies (bundled + community-installed via setuptools entry points); each topology declares a one-line description, a `walkthrough_kwargs` factory, and a `ci_kwargs` factory. *(functional)*
- **S-14.2** Bundled demo records — every Wave-11 and Wave-13 topology's committed records vendored under `substrate/topologies/<name>/records/`; `substrate demo replay <name>` opens the canned record in the TUI; `substrate demo run <name>` runs the walkthrough mode live. *(functional)*
- **S-14.3** Narration overlay schema — per-event annotations as a typed sidecar stream (NOT bus events; same discipline as diagnostic sidecar); each bundled topology ships an optional `narration.jsonl` for its canned record; TUI renders the annotation when a viewer reaches the annotated sequence. *(functional)*
- **S-14.4** Interactive tutorial — `substrate tutorial step<N>` walks through writing a topology incrementally, with live feedback (validates declared types, runs the partial topology, shows the resulting record in the TUI). The tutorial topology is itself bundled, exercising the gallery surface. *(functional)*
- **S-14.INT** A fresh checkout reproduces: `substrate topology list` shows 6 bundled topologies; `substrate demo replay code-review` plays the canned record with narration overlays; `substrate demo run pair-coding` runs live against Ollama and matches the committed walkthrough record's shape; `substrate tutorial step1` walks through the first lesson without errors.

---

## Deferred to a later phase

- **Speculative execution + rollback** — needs a fork tool that doesn't exist yet (design spec §8).
- **Federation** — needs transport + signing (out of scope for v1.x).
- **Self-modifying topologies** — needs the topology-mutation primitive that v1.0 doesn't have.
- **Cross-run delta predicates** — needs the persistent bus opt-in surfaces; design pass first.
- **Steganographic capture** — niche; needs a topology-author with a specific use case to drive it.
- **Meta-orchestration (topology-as-output)** — needs sandboxed topology execution; design pass first.

These are not closed; they're parked. Each deserves its own Phase-N when the dependencies land.

---

## Open questions for Architect ratification

- **Q-2.1** Does the topology gallery support remote installation (e.g. `substrate topology install <pkg>` calling `pip install` in the venv)? Or only support locally-installed topologies discovered via entry points? Latter is simpler.
- **Q-2.2** Does `substrate tutorial` ship in v1.1 or v1.2? Tutorial is more work than the rest of Wave 14; could defer to keep this phase tight.
- **Q-2.3** Should the population simulation default to 50 agents or 25? 50 looks more impressive; 25 fits in less VRAM on consumer hardware. Possibly: parameterize and document the tradeoff.
- **Q-2.4** Does the TUI ship `replay --diff` (two records side-by-side) in v1.1 or v1.2? Useful but not a blocker.
- **Q-2.5** What's the bundled-topology naming convention? `substrate.topologies.bundled.code_review` vs `substrate.topologies.code_review` (no `bundled` subpackage)? Affects discovery code.

---

*Phase 2 ships v1.1: the runtime made visible. After Phase 2, the substrate has both the kernel-level rigor (Phase 1) and the application-level surface (Phase 2). v1.2 would be the deferred list + 0.x feedback from external adopters.*
