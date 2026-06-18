# Sprint 110 — TUI design specification

---

```yaml
---
id: 110
status: pending
phase: 2
pass_kind: architecture
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Produce the full design spec for `rostrum tui` — a terminal UI for watching a topology run, replaying a record, and inspecting state at any point in the run. The TUI is built only on public substrate surfaces (F-API-6 second existence proof: the first is the CLI; the second is this TUI). Pane layout, color scheme, keybinds, modes (live / replay / focused / tree), latency display, narration-overlay surface, and the public-surfaces-only contract are all pinned in this sprint before any code is written. Includes a Textual-vs-alternatives comparison and the framework decision.

---

## prerequisites

- Sprint 100 closed; application catalogue ratified (the TUI must serve the topologies it'll visualize).
- Architect ratifies the proposed scope Decision for Phase 2 (PHASE2_PLAN.md).

---

## context_files

- `docs/specs/design_spec/draft1.md` §8 — the future-UI sketches: trace UI, topology visualizer, diff viewer, operator dashboard. Each names the public surfaces it builds on.
- `docs/specs/design_spec/draft1.md` §6 — error-and-observability UX (what the user sees when things fail).
- `docs/specs/technical_spec/draft5.md` §6.4 — writer-stats sidecar (what the status bar reads from).
- `docs/specs/technical_spec/draft5.md` §13 — live attach contract (the read path the TUI uses).
- `docs/specs/technical_spec/draft5.md` §14 — inspection / provenance / divergence API surface.
- `docs/specs/product_spec/draft7.md` §4 principle 8 — "No UI, UI-ready" and F-API-6.
- `docs/specs/product_spec/draft7.md` F-API-6 — UI buildability requirement (the contract this TUI lives under).
- `docs/application-catalogue.md` (output of Sprint 100) — the topology surface the TUI must visualize well.

---

## signal contract

### Emits

None at runtime — this is an architecture/design sprint. The Signal Report narrates design decisions as `signal_trace`.

### Consumes

- The canonical specs (above).
- Public Textual documentation (current stable release).

### Invariants

- Every design choice cites the substrate's public surface that backs it. No private hooks. F-API-6 is normative.
- The pane layout, keybinds, and color scheme are pinned to specific values — not "TBD" or "designer's choice." Phase 2 builders implement these literally.
- Modes are enumerated with precise transitions (live → replay → focused → tree and back). State diagram included.
- Narration-overlay surface is an off-bus sidecar (NOT bus events) per the same discipline as the diagnostic sidecar (technical spec §3.8, §6.4) — annotations MUST NOT perturb bus log determinism (conformance check 14).
- Local-model latency considerations (Sprint 100 research-pass output) are addressed: per-Producer streaming indicator design that works at the actual token rates of Qwen 2.5 1B / Llama 3.2 1B / Phi-3 mini.

---

## artifact contract

### Files created

- `docs/tui-design-spec.md` — the full design:
  - §1 Goals (live attach, replay scrub, F-API-6 proof, demo-watching ergonomics)
  - §2 Pane layout (top header, left producer column, center event stream, right topology graph, bottom status bar — with exact widths/heights for an 80x24 baseline)
  - §3 Modes (live / replay / focused / tree) + state-transition diagram
  - §4 Keybinds (full list, with rationale where non-obvious; conflict-free)
  - §5 Color scheme (semantic categories: control-plane recedes, application events stand out, firings flash, failures red, resume conditions blue; full palette for both 16-color and 256-color terminals; respects NO_COLOR env var)
  - §6 Per-Producer latency display (streaming state indicator, recent emission rate, token-rate surfacing for LLM Producers via the openai-compat adapter's progress reporting)
  - §7 Narration-overlay surface (sidecar schema, when overlays render, how a topology author authors a `narration.jsonl`)
  - §8 Public surfaces used (explicit list: `attach()`, `load_record()`, `replay()`, `view_at()`, `decisions_between()`, `explain_producer()`, `trace_ancestry()`, and which lifecycle events drive each pane)
  - §9 Framework decision: Textual vs alternatives (Rich-live, Prompt Toolkit, blessed, urwid, custom curses). Decision recorded with the rejected alternatives' rationales.
  - §10 Open questions for Architect ratification
- `docs/tui-framework-decision.md` — the framework comparison long-form (Textual wins on the technical merits; this doc shows the work).

### Files modified

- `process/BLACKBOARD.md` — append the Sprint-110 close; surface Q-2.4 (replay --diff in v1.1 or v1.2?) for ratification.

### Content assertions

- Every keybind appears in §4 with an explicit mode (works in live / replay / both).
- Every color in §5 maps to a semantic category, not a producer name (color-by-kind, not rainbow-by-instance).
- §8 enumerates exactly the public-surface functions used; if the TUI needs something not on the list, that's a v1.0 API bug surfaced now, not papered over.
- §9 names at least four rejected alternatives with one-line reasons.

### Command exit codes

None — design sprint, no runtime emission.

---

## done criteria

- `docs/tui-design-spec.md` exists and validates against the content assertions.
- `docs/tui-framework-decision.md` exists with the comparison matrix.
- BLACKBOARD updated with Q-2.4 surfaced.
- Architect ratifies the design spec in BLACKBOARD `## Decisions` before Sprint 120 dispatches.
- A bridge sprint (S-10.bridge) follows: SDK bridge mapping for Textual (reverse-engineer the real API surface for App, Widget, reactive state, async events, key bindings) — REQUIRED before Sprint 120 ships any line of TUI code.
