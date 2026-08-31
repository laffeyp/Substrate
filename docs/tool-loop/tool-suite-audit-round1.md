# Tool suite audit — is `FULL_SUITE` best-in-class? (round 1)

*2026-07-01. Reviewer pass. Audits `topologies/tool_loop/tools.py` (`FULL_SUITE`) against the canonical agent tool definitions — Anthropic's `agent_toolset_20260401` (bash / read / write / edit / glob / grep / web_fetch / web_search) and the schema-less client tools `text_editor_20250728` (`str_replace_based_edit_tool`) + `bash_20250124` — sourced from the claude-api reference, not memory. Extends `tool-loop-tool-suite.md`. Register: plain, skeptical. "Simple" is not a licence for weak or unsafe tools.*

---

## Verdict

**The suite has the right SHAPE and thin, in places UNSAFE, IMPLEMENTATIONS. Grade: C+.** It is a faithful minimal skeleton — errors-as-observations, capped output, surgical-edit-as-primary — but not best-in-class, and one tool (`edit_file`) has a correctness/safety gap that substrate has *already fixed elsewhere in this very repo*. It is not yet the tool suite you'd want driving a real daily-driver agent.

The good news is small and specific: the fixes are known, several are cheap, and the strategic answer to "best-in-class open-source tool imports" is a mechanism substrate is already heading toward — **MCP**.

---

## The gap, tool by tool (vs canonical)

| Ours (`FULL_SUITE`) | Canonical (`agent_toolset_20260401` / client tools) | Gap that matters |
|---|---|---|
| `read_file(path)` → `text[:8000]` | `read` — text, **images, PDFs, notebooks**; **line-numbered**; offset/limit | No line numbers (and `edit` needs line context to be safe), **silent 8000-char truncation** with no pagination, text-only. A model can't reliably edit a file it can only half-see. |
| `edit_file(path, search, replace)` → `text.replace(search, replace, **1**)`, error only if `search` absent | `str_replace` — **replace exactly one occurrence; error if 0 OR >1 matches**; `create` makes a **backup** if the file exists | **This is the headline.** `.replace(…, 1)` silently edits the *first* occurrence with **no uniqueness guard** — the exact silent-wrong-region splice class (`y = 1` corrupting `y = 1234`). No backup, no read-before-edit staleness check, **no path confinement**. |
| `write_file(path, text)` | `write`; `text_editor create` backs up an existing file | No backup, no read-before-overwrite guard, no path confinement. |
| `grep(pattern, path)` — Python **substring**, hard cap 50, `rglob("*")` | `grep` — **regex** (ripgrep-class) | Substring only (can't express a real pattern), slow whole-tree `rglob`, arbitrary 50-hit cap with no "more" signal. |
| `list_dir(path)` | `glob` — fast **pattern** file matching | No pattern/recursive find. **`glob` is missing entirely** — a real agent leans on it constantly. |
| `web_fetch(url)` → raw bytes `[:20000]` | `web_fetch` — content extraction | Raw HTML (not markdown/text), hard 20000-byte cut. |
| *(none)* | `web_search` | Missing. Defensible for a local agent, but name the absence. |
| `bash(cmd)` — 60s, capped, one-shot | `bash` — **persistent shell session** + `restart` | No session state across calls, no restart, fixed timeout. |
| `args: list[Any]`, `describe`: a one-line string | typed **JSON `input_schema`** per tool (name, description, properties, required) | **No per-tool schema.** This blocks native tool-calling (Ollama's `tools` field / any function-calling model needs JSON schemas) and is already the #2 item on the tool-suite NEXT list. M1 needs this regardless. |

## The two safety gaps, stated plainly

The suite is "no-permissions-by-default, autonomous," which is a defensible philosophy — but it makes tool *correctness and containment* matter **more**, not less, because nothing gates a bad call.

1. **No path confinement on `edit_file` / `write_file` / `bash`.** The canonical text-editor contract treats `path` as untrusted model output and confines every op to a project root (realpath + containment check). Ours writes wherever the model says. Substrate's own SWE-bench applier learned this the hard way and added a realpath containment guard (KIT_DIARY finding #15). The tool_loop suite never got it.
2. **`edit_file`'s missing uniqueness invariant is a correctness bug, not just a safety one.** A first-occurrence replace reports a clean success while splicing the wrong region — the silent-wrong-but-applied class the substrate diary calls out repeatedly (#11, #15). For a driver you're about to trust with your codebase, this is the one to fix first.

The docstring's "sandbox the run if that autonomy is unwanted" punts containment to the operator. That's an honest stance, but it should be written as a real limitation of the suite, not a design flourish — and it does not excuse the uniqueness bug, which corrupts files *inside* any sandbox.

## The thing that makes this easy to fix: substrate already built the good version

The repair topology's SEARCH/REPLACE applier (`topologies/swebench_solver/applier.py`, hardened through gate-#2 to a tiered exact → whitespace-flexible-if-unique → reject match with a uniqueness invariant at every tier, line-anchoring, empty-diff reject, and a realpath containment guard) **is** a best-in-class `edit_file`. The tool_loop suite reimplemented a weaker one beside it. So the first fix is not "write a good applier" — it's **reuse the one you have**. This is the same "reuse, don't re-roll" the diary already booked for the best-of-N loop (finding #12); it applies here one level down.

---

## Recommendation — both tracks, together and permanently (decided 2026-07-01)

Not either/or, and not a fallback relationship. Owned built-ins and imported MCP tools solve **two different problems**, so keeping both is coverage, not redundancy:

- **Owned built-ins solve customization** — bend a tool however you want, and have tools no external server can provide (see below).
- **Imported MCP tools solve not-having-to-think** — the standard, maintained by the ecosystem, drop in and it works.

The built-ins are the **customization substrate**, first-class forever — *not* a fallback. MCP is the zero-thought breadth layer. You reach for the import when you don't want to think about it, and for the owned one when you need to bend it.

**The unifying constraint — one tool interface, two backends.** A topology must not care whether a `ToolCall` is served by an owned built-in or an imported MCP server: same `ToolCall`/`ToolResult` contract, same schema shape, chosen per tool. This is the second reason Track 1 matters beyond quality — matching the canonical `agent_toolset_20260401` contract is what makes an owned built-in and its MCP equivalent **drop-in interchangeable**. Skip it and you fork into two tool worlds; match it and they're the same shape with a different implementation behind them.

**Why owning them is load-bearing, not vanity.** Owning the built-ins is the *only* way to have **substrate-native tools** an MCP server structurally cannot provide, because they only make sense inside substrate:
- a `delegate` / `run_topology` tool whose execution *is* an embedded topology ("substrate as a tool") — the compounding one;
- signal-instrumented tools that emit onto the record;
- deterministic/pure tools that keep the committed CI record byte-replayable.

Import-only would forfeit all three. That is why "always keep our own best-in-class rolled" is the correct standing posture, not just a customization nicety.

### Track 1 (do inside M1): match the canonical semantics, reusing your own code

Not "add tools" — make the eight you have honest:
- **`edit_file` → reuse `swebench_solver`'s applier**: uniqueness-guarded (error on 0 or >1 match), line-anchored, backup-on-overwrite, realpath-confined. Kills the headline bug by deletion, not addition.
- **`read_file`**: line numbers + offset/limit, drop the silent truncation (paginate).
- **`grep`**: real regex (shell out to ripgrep if present, else `re`), report when capped.
- **add `glob`**: pattern file-find — the missing staple.
- **per-tool msgspec `Struct` schemas** (tool-suite NEXT #2) — required anyway for M1's native tool-calling; adopt the canonical `name`/`description`/`input_schema` shape and write **prescriptive descriptions** ("call this when…"), which measurably raise a model's should-call rate.
- **path confinement** on all three mutating tools; state the no-permissions posture as a named limitation.

Target the published `agent_toolset_20260401` semantics as the spec to match — it's the reference definition of each tool, so you're matching best-in-class by copying a contract, not guessing.

### Track 2 (the real answer to "best-in-class open-source tool imports"): MCP

The mechanism for *importing* proven tools is **MCP**, the ecosystem's tool-import standard (filesystem, fetch, git, and dozens more as reference servers). This composes exactly with the M2 roadmap step: the same MCP surface that lets an agent *author* a topology also lets substrate *consume* best-in-class tool servers as Producers. Behind the one tool interface above, `FULL_SUITE` resolves each tool to either the owned built-in **or** an imported MCP toolset — the operator's choice per tool. You stop owning the maintenance of the file/edit/bash tools the ecosystem already maintains, without giving up the owned layer where customization and substrate-native tools live.

---

## Bottom line

"Simple" was never the problem — the suite is *too* simple in the two places where simplicity costs correctness (`edit_file` uniqueness) and safety (path confinement), and it's missing the typed schemas M1 needs anyway. The decision: **do both tracks, together and permanently, behind one tool interface.** Fix the owned built-ins to canonical semantics by reusing substrate's own applier (Track 1, cheap, inside M1) — that both makes them best-in-class *and* makes them interchangeable with their MCP equivalents — and support importing MCP toolsets for breadth (Track 2, composes with M2). Owned layer for customization and substrate-native tools; imported layer for zero-thought breadth; same contract behind both. Mostly deletion and reuse, not new code.

*Cross-ref: `tool-loop-tool-suite.md` (design + NEXT), `interactive-agent.md` (M1, the tool-calling seam), `../process/KIT_DIARY.md` findings #11/#12/#15 (silent-wrong applier class + reuse-don't-re-roll + the hardened applier). Canonical tool contracts: `agent_toolset_20260401`, `text_editor_20250728`, `bash_20250124`.*
