# The interactive agent — M1 theory pass (design, round 1)

*Status: vision / pre-spec. This is the theory pass ROADMAP §1 requires **before any code or sprint card** — the design conversation written down so a later vocabulary session and sprint card transcribe from it. A living document, maintained by rounds + the revision log at the end. Version 0.1. Names are provisional and not locked.*

*Provenance: written 2026-07-01 as the reviewer/architect-partner output of a consolidation pass (`../../CONSOLIDATION-AND-ROADMAP-2026-07-01.md`). Sibling to `cockpit-design-round1.md` — this is the first concrete milestone (M1) on the way to the Cockpit; the Cockpit doc is the destination, this is the first step. Nothing here rests on a market or a competitor; the goal is a correct artifact.*

*Architect decision folded (2026-07-01): **the first build leads with an Ollama open-source model as the driver.** The CLI-agent path (`CliResponder`) comes second, onto the same seam. Both end up selectable; this is only which one proves the tool-calling seam first.*

---

## 1. What M1 is

The read console becomes the place you actually work. substrate-ui opens as the terminal, foregrounded. You pick a driver — an open-source model on Ollama — type a task, and watch the model drive a real, recorded run: it reads the task, calls tools, and the run grows **live** across the graph / stream / scene as it works. You read the conversation in the terminal and the run in the console; both are two views of one record.

This is the smallest honest increment from the current state (a *lens* over finished records) to an interactive *product* (talk to it, watch everything grow). It is deliberately **not** the whole Cockpit — no human-as-Producer event model, no promotion, no live-steering, no MCP. Those are later. M1 is: one driver, one live loop, watched.

## 2. Why this is the right first step, and why Ollama leads

The console's read surfaces (graph, stream, scene, terminal, replay, diff) and the real tool suite (`FULL_SUITE`) are built. Live-attach (`followLive`) is built. The pause-await-input seam (R-2) and `/api/resume` are built. The one thing missing between "the loop runs on canned input" and "a model drives it" is a **model seam that does natural-language tool-calling** (§6). M1 is the minimum that turns the existing pieces into a driver.

**Ollama leads** because it proves the substrate's founding promise directly — you bring arbitrary compute (here, a free local open-source model) as a Producer, and it drives a recorded topology. It is the north-star framing ("the interactive open-source-model agent"). The engineering cost of leading with a weaker/higher-variance model is real (the tool-calling seam is harder to stabilize against a small model), and that cost is *the point of doing it first*: if the seam is honest against a flaky 7–8B local model, it is honest against a strong one. The CLI-agent path (Claude Code / Codex / Gemini via `CliResponder`) is the second Responder onto the identical seam.

## 3. The five theory-pass questions (ROADMAP §1), answered

These are the questions the ROADMAP said to answer before a sprint card. Answers are proposals for the vocabulary session to ratify, not locked.

### 3.1 Interaction model — **both, turn-by-turn as default**

Turn-by-turn chat is the default: you type a task/message, the model answers and may call tools, the tool results re-fire the model, and it either continues or emits a final answer; then it waits for you. An **autonomous "let it run and watch"** mode is the same loop without the per-turn wait — you drop into it and out of it. The human injects mid-run through the existing **`pause_await_input` (R-2) + `/api/resume`** seam: a paused run parks waiting on a human event and continues when you feed it one. No new termination machinery is needed for M1 — R-2 already parks-and-resumes.

### 3.2 Topology shape — **`tool_loop` with a real Ollama Responder + `FULL_SUITE`**

The existing `tool_loop` topology is the shape: a `model` Producer reads the task + tool results so far and emits **either** a `ToolCall` **or** a `FinalAnswer`; a `tool` Producer runs on each `ToolCall`; the `ToolResult` re-fires the model with the result appended. Parallel tool calls already work (a turn emitting N `ToolCall`s starts N tool Producers concurrently). For M1: swap the calculator stub for the real `FULL_SUITE` (read_file / list_dir / grep / web_fetch / edit_file / write_file / bash) and back the `model` Producer with a real `OllamaResponder`. **No-permissions-by-default stands** (the philosophy already in `tool-loop-tool-suite.md`): tool calls do not gate for approval by default. Approval-gating is opt-in via the `pause_await_input` seam, for operators who want it — not the M1 default.

The human's role each turn is therefore **watching and steering**, not approving. Steering = injecting a message (a new instruction, a correction) via resume; approving = the opt-in gate only.

### 3.3 Terminal commands — **`chat` / `run`, streaming into the dock**

The terminal already parses commands (`runTerm` / `termSubmit`) and reads the record. M1 adds the drive commands:
- `run <topology>` — launch a bundled topology live (the thin control `/api/launch` already does this; M1 makes the terminal a first-class caller of it and follows the result live).
- `chat <message>` (or bare text at the prompt) — the human turn: POST the message as the driving input to a live `tool_loop` run (a fresh run, or a resume of a parked one), then stream the model output + tool results back into the terminal dock as they land on the record.

The terminal reads the live record the same way the GUI does (one cursor); it POSTs to the live run and reads it back. The dock streams model content + `ToolResult` payloads as they are written.

### 3.4 UI live-watch — **confirm the one-cursor carries a live run**

The one-seq-cursor drives graph + stream + scene in lock-step; the e2e proves it carries replay (scrub, play, rewind) and proves `followLive` renders a live launch (LIVE → FINALISED). M1's job is to confirm the cursor tracks the *growing tail* of a live run as the model works — the conversation shows in the terminal, the scene/graph animate as tools fire. This is close to done (live launch already animates); the specific new thing is a long-lived, human-paced run (§6, the slow-Producer problem in miniature).

### 3.5 Natural-language tool-calling — **the crux; see §6**

The walkthrough convention is calculator-only and cannot carry a real agent. This is the one genuine build in M1 and gets its own section.

## 4. The read/drive boundary (a usability requirement, not polish)

Today the terminal is a read interface wearing a prompt (`… type a command — help`), which is honest because it only reads. The moment it drives, the user must be able to tell at a glance whether they are **observing a finished record**, **watching a live run**, or **steering it** — or they will mistake one for another (this is `cockpit-design-round1.md` §6.2, the replay-vs-live boundary, surfacing at the UI). M1 must make the mode legible: a live/driving run reads visibly differently from a replayed one, and the prompt states which it is. This is a first-class M1 deliverable, not a follow-up.

## 5. What is already built vs what M1 builds

**Built (reuse, do not rebuild):** `OllamaResponder` (native `/api/chat`, `think=False`, retry, now reports `ModelUsage` accounting — prompt/eval tokens + wall_ms); the `tool_loop` topology (`model` → `ToolCall`/`FinalAnswer` → `tool` → `ToolResult` → re-fire; parallel calls); `FULL_SUITE` tools; `pause_await_input` (R-2) + `/api/resume`; live-attach (`followLive`) + the thin control (`/api/launch`); the terminal (`runTerm`/`termSubmit`, read-only); the one-cursor render.

**M1 builds:**
1. The natural-language tool-calling seam (§6) — the hard dependency.
2. Per-tool input schemas as msgspec `Struct`s (`tool-loop-tool-suite.md` §2) — today tool args are a positional list; typed+validated is the prerequisite for a real model emitting varied calls.
3. The terminal drive commands (`run`/`chat`) + the dock streaming (§3.3).
4. The read/drive legibility (§4).

**M0 pre-work this depends on** (from the consolidation): give the model/adapter seam a canonical home — `OllamaResponder` lives under `reference/_models` (an "acceptance-tests" package) with 21 dependents; the driving loop, the future `CliResponder`, and the eventual MCP surface all need a peer-of-`api` `adapters/` home. Do M0 first or M1's model code accretes into the wrong place.

## 6. The natural-language tool-calling seam — the crux, designed

Today (grounded in `topologies/tool_loop/__init__.py`): the `model` Producer prompts the Responder to "Reply with exactly one line: `TOOL <name> <a> <b>` or `ANSWER <value>`", parses `reply.strip().splitlines()[0].split()`, and builds a `ToolCall` with **two integer args** (`args=[int(head[2]), int(head[3])]`); a weak model emitting non-integer args falls through to an answer. `ToolCall.args` is already `list[Any]`, so the *type* allows strings — the **parse** is the constraint.

A real agent needs **string args, variable arity, and a real model deciding**. Two mechanisms, and the design uses both:

- **Primary — Ollama native tool-calling.** Ollama's `/api/chat` accepts a `tools=[…]` field (JSON-schema function definitions) and returns `message.tool_calls` for models that support it. This is the typed, clean path: `OllamaResponder` gains a tool-aware call (pass the `FULL_SUITE` schemas as `tools`, read structured `tool_calls`), which is exactly why per-tool msgspec schemas (deliverable #2) come first. This is model-dependent — not every OSS model emits `tool_calls` reliably.
- **Fallback — a tolerant text convention** for models that don't do native tool_calls: the model emits a fenced JSON object (`{"tool": "...", "args": {...}}`) or a `TOOL <name> <json-args>` line; a tolerant parser extracts it. String args and variable arity by construction. Weak-model failures become a **typed observation** (a `ToolResult(ok=False)` or a re-prompt), never a crash — matching the errors-as-observations discipline the tool suite already holds.

**The discipline this seam must follow (non-negotiable, from the substrate diary):** finding-28 / finding-20 — *green-on-canned hides crash-on-real*. The current walkthrough parser is proven only against its own two-int format; against real model output it will meet fenced code, prose preamble, multi-line JSON, `tool_calls` in the structured field, and refusals. **The observation contract for M1 grades this seam against REAL Ollama output, not a canned fixture** — the deterministic stand-in proves the wiring and actively hides the format-mismatch bug. Concretely: an M1 acceptance run drives `tool_loop` with a real local model against the real `FULL_SUITE` and asserts the model actually called a tool with string args and the run reached a terminal — the "prove against a real model, then generalize" pattern the diary earned on the SWE-bench work.

## 7. The observation contract for M1 (how we verify, since it's behavior-touching)

Per hard rule 9, this is a behavior-touching milestone and the sprint card must declare an observation contract. Sketch:
- **Driving steps:** start a live `tool_loop` run backed by a real `OllamaResponder` + `FULL_SUITE`; feed a task that requires at least one string-arg tool call (e.g. "read file X and tell me the first function"); optionally inject a mid-run steering message via resume.
- **Expected record:** a `ToolCall` with **string** args (not the calculator's ints), a matching `ToolResult`, a re-fire, and a `FinalAnswer`; the run reaches `RunFinalised`.
- **Expected UI:** the terminal dock streams the model turns + tool results; the graph/scene animate live; the mode reads visibly as *driving*, not *replay* (§4).
- **Both tracks** (structural DOM e2e + perceptual screenshot, per substrate-ui's two-track contract), plus the model-output-parsing check against real Ollama output (§6).
- **Honesty split** (Cascade Addendum E2 pattern): what is sim/CI-verifiable (the seam, the record shape, the parse against real output) vs what only the human judges on a real machine (whether the local model is actually *good enough* to be a daily driver — a model-quality question, not a plumbing one). Name the boundary; don't claim the model is good because the plumbing is.

## 8. What the vocabulary session must lock (before any sprint card)

M1 mostly reuses existing vocabulary (`ToolCall`, `ToolResult`, `FinalAnswer`, the lifecycle kinds, `pause_await_input`). Candidates the session should examine — as supervised-grammar-evolution proposals, not unilateral edits:
- Whether a **human message injected into a live run** needs its own typed event (it prefigures the Cockpit's human-as-Producer; for M1 it can ride the existing resume-input seam, but name the question).
- The **per-tool input schema** representation (msgspec `Struct` per tool) and whether `ToolCall.args` moves from `list[Any]` to a typed per-tool payload.
- Any new field the tool-aware `OllamaResponder` needs on the record (it already emits `ModelUsage`; confirm nothing else is discarded).

## 9. What this is NOT (M1 scope fence)

- **Not the Cockpit.** No human-as-Producer event model, no promotion (run → topology), no live-steering (attach/detach triggers mid-run), no ambient assay. Those are post-M1 (`cockpit-design-round1.md` §5–6).
- **Not MCP.** M2 is the MCP surface (agents author/join topologies); M1 is a human driving one agent. M1's `adapters/` home (M0) is what M2 builds on.
- **Not a benchmark claim.** M1 is about being a usable driver, not a resolve-rate. The assay stays separate and stays honest (power floor + pre-registration before any number).
- **Not naming-final.** "Interactive agent", the command names, and any new terms defer to the vocabulary session.

## 10. Open decisions for the Architect

1. **Native-tools vs text-convention as the M1 default.** Recommendation: implement both, default to native `tool_calls` where the chosen model supports it, fall back to the text convention — but the *first* proven model (which OSS model on Ollama) determines which path is exercised first. Which model? (A capable-but-local one — e.g. a recent qwen/llama coder — proves native tool_calls; a small one proves the fallback + the errors-as-observations path. Pick the first target.)
2. **Where the M1 build's spec lives** — this doc is the theory pass; the spec/sprint card transcribes from it after the vocabulary session.
3. **The `adapters/` home (M0)** — confirm the refactor lands before M1 model code, so the driving loop isn't built under `reference/`.

---

## Revision log

- **0.1 — 2026-07-01.** Initial theory pass for M1 (ROADMAP §1), written as the consolidation pass's forward-design output. Leads with Ollama OSS per the Architect's 2026-07-01 decision. Answers the five theory-pass questions (§3); designs the natural-language tool-calling seam grounded in the real `tool_loop` + `OllamaResponder` code (§6); declares the observation contract (§7) and the M0/M2 fences (§5, §9). Sibling to `cockpit-design-round1.md`; no code, no sprint card yet.
