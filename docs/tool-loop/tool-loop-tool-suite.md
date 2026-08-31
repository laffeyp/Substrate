# tool_loop tool suite — design, from the source of three OSS agents

Status: un-parked 2026-06-22 (was a parked research stub). The survey was done by
reading the source of three reference agents through the GitHub API, not blog
summaries — the same way the loop's error/budget design was taken from opencode.
Evidence below. The suite is `topologies/tool_loop/tools.py`.

## What was read (the evidence — actual source)

- **opencode** — `packages/core/src/tool/`, read in full earlier for the loop. Each
  tool is a typed `Tool` with a Zod `parameters` schema, an `execute` returning
  `{ output, metadata }`, a `ToolFailure` value for errors, and `toModelOutput`
  projecting the rich result to a minimal model view. Each tool wears a permission
  decorator. Catalog: read, write, edit, patch, bash, glob, grep, webfetch,
  websearch, todowrite, question, skill.
- **Cline** — `sdk/packages/core/src/extensions/tools/definitions.ts` +
  `schemas.ts`, and `apps/cli/src/runtime/tool-policies.ts`. Catalog: `read_files`,
  `edit_file`, `apply_patch`, `run_commands`, `search_codebase`,
  `fetch_web_content`, `ask_question`, `skills`, `submit`. Each has a Zod schema
  (`validateWithZod` + `zodToJsonSchema`); output is capped (`MAX_READ_LINES`,
  `MAX_*_OUTPUT_CHARS`); exec runs `withTimeout`; errors are typed
  (`CommandExitError`). The decisive file is `tool-policies.ts`: a
  `SAFE_AUTO_APPROVE_TOOL_NAMES` set — `read_files`, `search_codebase`,
  `fetch_web_content`, `ask_question`, `skills`, `submit` — auto-approves;
  everything mutating needs approval.
- **aider** — `aider/coders/editblock_coder.py`, `shell.py`, `base_coder.py`. A
  different paradigm. No discrete tool calls: the model emits SEARCH/REPLACE
  blocks parsed by a `Coder` (`do_replace`), a tree-sitter repo-map supplies
  context, shell commands are *suggested* in ```bash blocks for the human to run
  (not auto-executed), and every edit auto-commits to git.

## The convergent patterns (what all three do)

1. **Partition tools by side-effect → approval policy.** Cline auto-approves a
   safe read-only set and gates the mutating rest; opencode decorates each tool
   with a permission check; aider defaults to "suggest shell, the human runs it."
   Read-only is safe; mutation needs a gate. The central pattern.
2. **Typed I/O schemas**, validated before execute, surfaced to the model as JSON
   schema.
3. **Errors are observations, not crashes** — a typed failure value returned to
   the model.
4. **Output is capped** — every read, search, and exec truncates to protect the
   model's context window.
5. **Exec has a timeout.**
6. **Surgical `edit` over full rewrite** — the primary code-change tool is a
   search/replace `edit` (aider EditBlock, Cline `edit_file`); `write_file` is
   reserved for new files.
7. **"done" and "ask" are tools** — `submit` / `attempt_completion` ends the run;
   `ask_question` / followup pauses for a human.

## Where we diverge — permissions (the deliberate inversion)

All three references gate mutation behind human approval by default (pattern 1
above). This suite does not. The default is no permission gate: full autonomy,
equivalent to a coding agent in auto-accept mode or more permissive. That reflects
the substrate's direction: the end state is the LLM running these topologies
itself (the self-running direction in `process/BACKLOG.md` and the agent-IDE
note), so the default is autonomy, not a human in the loop. Approval-gating is an
opt-in capability — gate any tool behind `pause_await_input` (R-2) when an
operator wants one. Never the default. The side-effect taxonomy below is
therefore about *determinism* — what can go into the byte-reproducible CI record
— not about approval.

## How it maps onto the substrate

| pattern (from source) | substrate mechanism |
|---|---|
| side-effect → DETERMINISM (not approval) | PURE keeps the CI record reproducible; READ-ONLY/WRITE-EXEC are `deterministic=False`. We do NOT gate by default — see "Where we diverge" |
| typed I/O schema | msgspec `Struct` tool I/O (the bus validates at the boundary) |
| errors as observations | `ToolResult(ok=False, error=...)` — already the loop's discipline |
| output caps | truncate in each tool (`[:8000]`, 50 hits) |
| exec timeout | `subprocess.run(timeout=60)` |
| surgical edit > write | `edit_file` (search/replace) primary; `write_file` for new files |
| done / ask are tools | `FinalAnswer` event = submit; `pause_await_input` = ask_question |

## The suite shipped (`tools.py`)

- **PURE** (deterministic, CI): `add`, `mul`.
- **READ-ONLY** (`deterministic=False`): `read_file`, `list_dir`, `grep`,
  `web_fetch`.
- **WRITE/EXEC** (`deterministic=False`, ungated by default): `edit_file`
  (search/replace), `write_file`, `bash`.

The CI demo uses PURE (byte-reproducible record). A real agent passes
`FULL_SUITE` and runs it with full autonomy. The substrate-native `delegate` /
`run_topology` tool — a tool whose execution is an `embedded_substrate`, the
"substrate as a tool" doc — is a future addition.

## Next (not yet built)

- An opt-in `pause_await_input` gate (the human-in-the-loop seam) for operators
  who want one. Not the default — the suite runs ungated (see Permissions above).
- Per-tool input schema as a msgspec `Struct`. Today the args are a positional
  list.
- A `toModelOutput`-style projection (opencode) if raw results get noisy for
  small local models.
- The natural-language tool-calling convention for the full suite (string args,
  variable arity). Belongs with the interactive-agent work, which needs its own
  usage/theory pass first.
- **Read-before-edit precondition** (backlog — from Claude Code's leaked edit
  tool, 2026-07-01). CC fails an `edit_file` on a file not `read` earlier in the
  conversation, forcing the model to ground its `search` in real bytes. We get
  most of this free: a blind edit with the wrong `search` already fails with a
  typed "not found" (the uniqueness guard). The marginal value is low, and it
  needs conversation-scoped read-tracking state our stateless tool closures do
  not carry. Deferred, not rejected. Revisit if arena runs show weak models
  mis-editing files they never read.
