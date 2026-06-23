# tool_loop: a best-in-class tool suite — RESEARCH NOTE (PARKED)

> **Status: PARKED.** Captured 2026-06-22 at the Architect's request; to be picked up *after* the
> current substrate-ui thread (scene → replay → terminal → interactive model agent). This is a
> research stub, not a design — it records the ask, the plan, and the candidate shape so the thread
> can resume cold.

## The ask

`tool_loop` today ships a deterministic stand-in tool set (a calculator: `add`, `mul`) — enough to
demonstrate the model→tool→model loop, not enough to be a *useful* agent. It should ship with the
**full suite of available tools a real tool-using agent has** — best-in-class, just *available*,
out of the box. The model talks to it (eventually via the terminal, against an open-source model)
and can actually do things.

## The method (Architect's instruction)

Research the **top open-source agent projects** — the same way the tool-loop's error/budget patterns
came from reading opencode's real source — and **learn the patterns, do NOT copy any code**. Survey:

- **opencode** (`anomalyco/opencode`, already read once for the loop): `packages/core/src/tool/` —
  `read` / `write` / `edit` / `apply-patch` / `bash` / `glob` / `grep` / `webfetch` / `websearch` /
  `todowrite` / `question` / `skill`. Note its tool *shape*: typed input + output schema (validated
  both directions), `ToolFailure` as a value, a `toModelOutput` projection (full structured result on
  the record, minimal text to the model), permission decoration.
- **aider**, **Cline / Continue**, **Cursor agent**, **Codex** — for the canonical command surface
  and which tools each treats as core vs optional.
- **Anthropic's own guidance** — "Writing tools for agents" / "Building effective agents": few
  thoughtful high-impact tools beat many narrow ones; consolidate; enrich results with metadata;
  errors as observations; minimal structured output.

Extract: (a) the **canonical tool set** every agent ships, (b) the **interface patterns** (typed
schemas, errors-as-observations — already in tool_loop, parallel calls, permissioning), (c) the
read-only vs side-effecting split.

## Candidate canonical suite (to confirm against the survey)

Group by side-effect, because Substrate cares about determinism + approval:

- **Read-only (safe, deterministic-friendly):** `read_file`, `list_dir` / `glob`, `grep` / search,
  `web_fetch`, `web_search`.
- **Side-effecting (→ `deterministic=False`, human-approval-gated via `pause_await_input`):**
  `write_file`, `edit_file` (surgical), `bash` / shell (sandboxed), network POSTs.
- **Substrate-native:** a `delegate` / `run_topology` tool whose execution is an `embedded_substrate`
  (the "substrate as a tool" doc) — a tool that is itself an agent/ensemble/pipeline.

## How it lands in substrate (sketch, not committed)

Extend `tool_loop`'s `_TOOLS` registry into a real suite: each tool a typed function the `tool`
Producer dispatches; a tool *schema* (name + input/output types) so the model knows the surface;
side-effecting tools marked non-deterministic + gated behind approval; results are typed
`ToolResult`s on the log (full structured result), with a minimal projection fed back to the model.
Composes with: the **CliResponder** (CLI-backed open models — see the CLI-models finding) so the
"model" can be Claude Code / Codex / Gemini / Ollama; the **interactive human-in-the-loop agent**
topology; and the **terminal** as the chat surface.

## Why parked

The current thread (read-commands terminal → interactive open-source-model agent in the terminal,
watched live in the UI) is the on-ramp; the real tool suite is most useful *once the agent loop is
interactive and model-backed*. Build the surface first, then arm it with the full toolset. Resume
here when the interactive-agent increment lands.
