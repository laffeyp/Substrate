# process/RESEARCH.md — Substrate research log

*The long-form record of what we are learning by running real models through substrate's topologies.
This is not state and not methodology. `BLACKBOARD.md` holds current state (what is built, what is
next); `KIT_DIARY.md` holds findings about the SDD kit itself. This holds the **empirical findings
about agent behaviour on substrate** — the questions, the setup, what we actually observed (with the
data), what we think it means, and what is still open. Findings here get distilled outward: a
current-state line into the BLACKBOARD, a methodology lesson into the KIT_DIARY. The full account,
including the dead ends and the refuted hypotheses, stays here.*

*Register: plain and concrete. Every claim carries its evidence and its caveats. An n=1 run is
labelled n=1. A refuted hypothesis is kept, not deleted — the refutation is the finding.*

---

## Thread 1 — What breaks when a real model drives the tool loop

**The question.** The `tool_loop` topology is the model→tool→model agent loop. It passes its
deterministic CI test and simple scripted tasks. But does it hold when a *real, stochastic* model
drives it against *open-ended* tasks — the way a user actually uses it? And where, exactly, does it
stop being a loop problem and start being a model problem?

**The method — the container arena as a discovery harness.** Scripted tests can only check failures
you already know to write. To find the unknown ones we run the agent WILD: a real model (Ollama,
local or cloud) drives the real `FULL_SUITE` against a throwaway `/arena` filesystem inside a
disposable container (`Dockerfile.arena` + `scripts/agent_arena.py`), free to do anything, and we
read the record afterward. The container is a test arena, never the product — the product is
host-native by design (direct filesystem, real autonomy, like Claude Code). Destructive tool use in
the arena costs nothing: `docker rm` and it is gone. Models tested: `llama3.2:1b` (weak),
`qwen2.5-coder:7b` (moderate), `qwen3-coder:480b-cloud` (the capable one).

---

### R-1 — A stochastic driver finds bugs no fixture author would write

The first real-model demo wedged the loop. The model called `glob('**/*.py')` on a large tree; the
~340 KB result crossed the 16 KiB blob-offload threshold, which stripped the loop-control fields
(`step`) off the frame; the continue predicate then raised `KeyError('step')` and quarantined. No
one writes the unit test "glob returns 340 KB" — it surfaced only because a real model did what a
fixture never would.

**Fix (general, not spot):** the root cause was "any tool result crossing the offload threshold
strips control fields," so the fix is a byte-cap in the tool runner — *any* oversized output becomes
a typed "too large to inline" notice before it can strip the frame — plus a defensive `.get("step")`.
Capping `glob` alone would have left `read_file`/`grep`/`bash`/`web_fetch` wedge-able.

**Status:** fixed, reproduce-then-kill test (250-file glob). **Interpretation:** the discovery harness
earns its keep on turn one — it is the front end that *feeds* reproduce-then-kill, which can only
*kill* a failure you already know.

---

### R-2 — Real models batch tool calls; our parser degraded that to a no-op

`qwen2.5-coder:7b` emits several tool calls concatenated in one message: `{..}\n{..}\n{..}`. Our
parser grabbed the greedy span from the first `{` to the last `}` — invalid JSON for multiple
objects — so it fell through to "this is a final answer" and ran **zero tools**. The run "finalised
OK" while doing nothing. It hit 2 of 12 tasks, the two most multi-step ones.

**Fix:** parse the *first balanced* `{...}` object (brace-depth scan respecting string literals), so a
batched message yields the first call and the loop runs it; the model continues sequentially.

**Status:** fixed, reproduce-then-kill test. **Interpretation:** confirms the kit's finding-28 ("parse
*real* model output, not the canned single-object shape") one level up. Also exposed R-3.

---

### R-3 — "Green" is blind to soft failure; the discovery signal needed the same skepticism

The arena's OK/CRASH signal caught wedges and tracebacks but not "finalised with a tool-call JSON
blob as the answer" (R-2's no-op). We added a SOFT signal — a `FinalAnswer` that looks like an
unparsed tool call. The *first* version matched any leading code fence, and immediately produced
**false positives**: `build-app` and `rename-all` both *completed* (the file was written / renamed
correctly) and then legitimately showed the file in a ```` ```python ```` fence. Reading the logs
caught it. Tightened to require the tool-call shape (`"name"` *and* `"arguments"`); validated against
all 12 real captured logs (0 false positives, still catches the genuine no-op).

**Interpretation:** be-your-own-skeptic applies to the *instrument*, not just the code under test. A
discovery harness's own success signal can lie, and only reading the raw output catches it.

---

### R-4 — Adversarial review as advice: three real hardening findings, cleanly bounded

An independent adversarial review of the workspace + hardening changes, treated as advice not verdict,
surfaced three real defects (all fixed, all reproduce-then-kill tested):
- `replace_all = bool(arg)` — `bool("false")` is `True`, so a model stringifying a falsey value would
  silently *enable* the destructive replace-all and disable the unique-or-error mis-splice guard.
  Fixed with a value-preserving `_as_bool` (treats `"false"/"0"/"no"/"off"/""` as false).
- `read_file` with an out-of-range `offset` returned a bare `""` — the exact ambiguity the empty-file
  marker was added to kill. Now an empty window says so.
- Empty `?workspace=` resolved to `Path(".")` not the cwd default. Fixed.

The review's *dropped* items were correctly dropped (the workspace-autonomy "footgun" is deliberate
posture, not a bug). **Interpretation:** an adversarial pass that cuts both ways — real findings kept,
non-findings released — is worth its cost, and treating it as advice (we adjudicate) is the right
stance.

---

### R-5 — The write-spin: a capable model rewrites and never verifies

The headline. On an open-ended "build a Hangman game and PROVE it runs" task, `qwen3-coder:480b`
wrote `hangman.py` **16 times and ran it zero times** — no `bash`, no `read_file`, no `edit_file`. It
was not re-emitting an identical call; the byte counts varied (2923, 3621, 3795, …) — it kept
*rewriting* the file with cosmetic variations and never committed to running it. Classic no-commit
perfectionism.

**What it is not (hypotheses raised and refuted by observation):**
- **Not token starvation.** Re-ran at 8× the token budget (`max_tokens` 1024 → 8192): identical
  16-write spin. Falsified.
- **Not a history-threading bug.** Confirmed the full results transcript threads into every model
  prompt (the `results` View is a `KindBuffer("ToolResult")` that accumulates; the prompt carries
  "Tool results so far, in order: …"). The model *sees* its 15 prior writes and rewrites anyway.
- **Not a prompt problem — for this model.** We adapted best-in-class agent-loop discipline into the
  prompt (act when ready; do not redo a succeeded action; verify by running; report truthfully) and
  sharpened it on substrate's spine (decide from the observed record; a failed result is information
  not a wall; "written" is not "working"). The thin prompt spun; the disciplined prompt spun
  *identically*. A prompt is a request this model does not honour here.

**Interpretation:** the load-bearing lesson — *a prompt is a request; substrate can enforce.* Best-in-
class harnesses work partly because their model obeys the prompt. We cannot assume that across
arbitrary models, but we can enforce discipline structurally on the record. See R-6.

**Caveat:** every 480b run is n=1; the behaviour was consistent across five runs but this is a
demonstrated pattern, not a measured rate.

---

### R-6 — Structural enforcement: the anti-spin guard, and the errors-as-observations tension

**The fix (SDD-sound):** the loop now treats a *second consecutive* `write_file` to the same file,
with no run/read between, as a redundant action — it returns a typed `ToolResult(ok=False)` telling
the model to run or read the file to verify before rewriting. Errors-as-observations, on the record,
consistent with the existing unknown-tool and missing-arg guards. State (`prev_write`) persists across
firings in the closure; the CI calculator never writes, so committed records stay byte-identical.

**Effect at the loop level:** the spin's *waste* is gone — 16 real writes collapse to 1 (the rest
refused). Confirmed live.

**The tension it exposed.** The model factory halted the loop on *any* `ok=False` — which contradicts
the discipline ("a failed result is not a wall") and neuters the guard into a halt. We worked through
three positions:
1. **Halt on first failure** (original): the anti-spin corrective halts cleanly with a truthful
   message at 2 writes. But a capable model that hits one transient tool error can never self-correct.
2. **Never halt** (relaxed for walkthrough): SDD-correct in principle, but the *observation refuted
   the theory* for this model — it flailed to the step budget on 15 refused writes and answered "no
   result." Strictly worse.
3. **Recover, but bail when stuck** (final): a real model gets room to react (up to
   `_MAX_CONSECUTIVE_FAILS = 3` consecutive failures), then the loop bails with a truthful report
   rather than flailing. The deterministic/default path still halts on the first failure (its tests
   rely on it; it has no model to reason). Confirmed live: 4 writes (1 real + 3 refused) → "stopped
   after 3 failed tool call(s): you already wrote hangman.py … run or read it to verify."

**Interpretation:** position 2 is a clean example of preferring a principle over an observation and
being wrong for it. Recover-then-bail is the honest resolution: room to self-correct, bounded, never
"no result."

---

### R-7 — The model ceiling: where enforcement ends

With the anti-spin guard *and* recovery both live, `qwen3-coder:480b` still would not verify. Fed the
typed corrective ("run it to verify before rewriting") **15 times in a row**, it kept trying to write
and never ran `bash`. No prompt, no sharpened discipline, no repeated typed observation moved it.

**Interpretation:** this is a **model** ceiling, not a loop bug. `qwen3-coder:480b` via Ollama, on
this open-ended build-and-verify task, does not run its own code. The loop is now as good as the loop
can be here; making the model behave agentically is not a loop fix. This is exactly the boundary the
liveness test exists to locate: where a better harness stops helping and model capability takes over.

**Open questions:**
- Is the ceiling model-specific? **ANSWERED by R-9 (2026-07-02): yes.** `kimi-k2.6:cloud` (thinking+tools)
  ran its own code on the same task — write→read→run→verify. The ceiling is agentic reasoning, not a
  wall. Still untested: `deepseek-v4-pro:cloud`, `glm-5.1:cloud`, `deepseek-r1:8b` (local reasoning).
- Does the ceiling depend on task framing? The task says "PROVE it works by running it" — an even more
  explicit "your FIRST action after writing must be a bash run" might move a borderline model.
- Is there a substrate-native lever short of hard-coding the sequence — e.g. surfacing the file's
  existence/content in the write result so the model stops re-deriving it?

---

### R-8 — Tool coverage: what we have, what is untested, what is missing

- `web_fetch` (URL → page text, 20 KB cap) exists but was **untested** — live network I/O with zero
  coverage. Closing that with a local `http.server` fixture test (fetch, decode, cap, error) is
  queued.
- `web_search` (query → results) does **not** exist. It is buildable free with no API key via
  DuckDuckGo's HTML/lite endpoint (the same `urllib` as `web_fetch`) — real markup captured; the
  result links come back as `//duckduckgo.com/l/?uddg=<encoded-url>` redirects to decode. (Google
  specifically blocks scrapers; DDG is the standard free route.) Not yet built.
- Hardening lifted from Claude Code's leaked *tool* descriptions (adapted, not copied): the empty-file
  marker, the `edit_file` line-number-prefix warning, `replace_all`, the minimal-`old_string`
  guidance. The deliberate divergences we keep (workspace-relative paths not absolute-required; glob
  sorted alphabetically for replay-determinism not by mtime; no read-before-overwrite guard because
  autonomy is the point) are cases where their choice is wrong *for us*.

---

### R-9 — A thinking model breaks the R-7 ceiling: write → read → run → verify

Same hangman task, `kimi-k2.6:cloud` (thinking+tools, `--think` on). Tool mix: **`write_file`(1),
`read_file`(1), `bash`(1)** — it wrote the file, read it back, and RAN it (`bash`, `exit: 0`, stdout
began `=== HANGMAN ===` with the gallows). No spin, no anti-spin refusals needed; the task completed
with the model verifying its own work. Confirmed from the record (the bash exit code + stdout), not
the model's say-so.

**Interpretation:** R-7's ceiling was **model-specific** — "a coder without agentic reasoning," not
"models can't do this." A thinking+tools model plans the verify step the pure coder
(`qwen3-coder:480b`) skipped. This simultaneously:
- validates the roster's central hypothesis — thinking-vs-non-thinking is the axis that matters for the
  agentic verify-loop, not raw code quality (`qwen3-coder:480b` is the better *coder* on benchmarks and
  the worse *agent* here);
- validates the recover-then-bail design (R-6) by exhibiting a model that actually recovers/verifies,
  running cleanly through the loop;
- validates the whole stack end-to-end: a capable agentic model drives write→read→run→verify through
  substrate on a real open-ended build, every step a typed event on the record.

**Caveat:** n=1. One clean run; the *behaviour* (write→read→run) and the verified execution are the
finding, not a success rate. The confound is controlled — `--think` was on (a flag added to
`run_tool_agent` for this), where the earlier failing runs used a non-thinking coder.

**Through-line of Thread 1 so far:** the arena found the ceiling; the loop was hardened as far as a loop
can be (anti-spin, recover-then-bail, errors-as-observations); and the ceiling turned out to be a
*model-capability* axis (agentic reasoning), locatable precisely because every step is on the record.
**Best coder ≠ best agent.**

---

### R-10 — The discipline PROMPT is inert; the levers are the guard and the model (A/B, under challenge)

Claim under test (mine): "the SDD-sharpened discipline prompt helps compliant models." It was built to
NOT fail — I added the prompt, saw kimi succeed *with* it (R-9), and asserted the prompt helped. That
green never isolated the prompt's contribution. Under an SDD skeptic challenge I built the check that
*could* fail: A/B, `kimi-k2.6 --think`, same hangman task, anti-spin guard still active, the discipline
text swapped for the thin "tools are optional" prompt.

**Reading (thin prompt):** tool mix `write_file(1), read_file(1), bash(2)`; the two bash runs read
`exit: 1` then `exit: 0`, stdout `=== HANGMAN ===`. kimi wrote the file, read it, ran it, hit an error
(exit 1), FIXED it, and re-ran to a clean exit 0 — the full agentic recover loop — **without** the
discipline prose.

**Verdict — claim RETRACTED.** The discipline PROMPT is inert as an agentic lever: kimi verified with
or without it (n=1 each arm), and it did nothing for qwen either (R-5). kimi's verify-and-recover
behaviour is the MODEL. The *verified* levers are (a) the structural anti-spin guard (R-6) and (b) model
choice (R-9); the prompt stays only as the cheap generative-escape carrier (the poem fix), not as a
proven lever. n=1 both arms is not enough to rip it out (that would be the same over-correction), but
it is enough to stop claiming it works.

**Bonus (independent confirmation):** the `exit 1 → fix → exit 0` recovery is a real capable model
recovering from a tool failure unprompted — direct evidence that recover-then-bail (R-6) is the right
shape, not just my design preference.

**Method note:** this is what the challenge is for. The green that lied was "kimi succeeded, and I had
just added the discipline prompt, therefore the prompt helped." The could-fail check separated the two.

---

## Model roster — what we test against, and why

The tool loop is written against a `Responder`, so any model is a candidate. But suitability for the
AGENTIC task (drive tools → read results → verify → stop) is not raw capability, and the capability
tag is **necessary but not sufficient**: `qwen3-coder:480b` advertises `tools` and still will not
verify its own code (R-7). So we grade on our own axis: (1) does Ollama declare a `tools` capability
(the native tool-calling path needs it); (2) is it code-tuned or agentic; (3) does it have a
`thinking` mode — the live R-7 hypothesis, that a reasoning model plans the verify step a pure coder
skips. Capabilities below are from `curl /api/show` — Ollama's own declaration for the installed
manifest, verified 2026-07-02. Benchmark numbers are **vendor/aggregator claims** (sources at the
end), not our measurements; the arena is the only test that counts for our task.

### Suitable — LOCAL (on-machine, fast iteration)

| Tier | Model | Caps (verified) | Why | Our data |
|---|---|---|---|---|
| Workhorse | `qwen2.5-coder:7b` | tools, insert | code-tuned, ~5 GB | moderate; over-calls on multi-step; emits calls as JSON-in-content (parser handles) |
| Reasoning | `deepseek-r1:8b` | tools, thinking | a LOCAL thinking+tools model — tests the R-7 verify hypothesis cheaply | untested on the loop; R1 `<think>` blocks may interfere — to measure |
| Stronger coder (to pull) | `qwen2.5-coder:32b` (or `:14b`) | tools | bigger local coder for a higher local ceiling | not pulled; hardware-dependent |

### Suitable — CLOUD (via `ollama signin`, big models)

| Tier | Model | Caps (verified) | Why | Our data / source |
|---|---|---|---|---|
| Top coder | `qwen3-coder:480b-cloud` | tools | best raw code (~69.6% SWE-bench Verified) | **GREAT coder, WEAK agent** — fails the verify loop (R-7); NO thinking mode |
| Reasoning | `deepseek-v4-pro:cloud` (or `glm-5.1:cloud`) | tools, thinking | thinking+tools; DeepSeek V4 ~70–73% — the direct R-7 ceiling test | untested on the loop |
| Agentic specialist | `kimi-k2.6:cloud` | tools, thinking, vision | Kimi K2 family leads agentic multi-attempt (~71.6%) — strongest verify-loop candidate | untested on the loop |

(`nemotron-3-super:cloud` is an alternate thinking+tools cloud model, already pulled.)

### Unsuitable — negative controls (run these to confirm WHAT breaks and WHY)

| Model | Caps (verified) | Why unsuitable | Use as |
|---|---|---|---|
| `llama3:8b` | completion ONLY | NO `tools` — can't native tool-call (forced onto the text/JSON fallback); not code-tuned | control for the fallback path + "no tool support" |
| `llama3.2:1b` | tools | too weak: over-calls, doesn't recognize "done", needs the max_steps backstop | fast PLUMBING smoke only; weak-capacity baseline |
| `qwen2.5:7b-instruct` | tools | has tools but general, not code-tuned | control for "tools ≠ coding suitability" |

### The experiment this roster sets up

R-7's ceiling was a *non-thinking* coder. The roster deliberately pairs a thinking model against a
non-thinking one at the cloud tier (`kimi-k2.6` / `deepseek-v4-pro` vs `qwen3-coder:480b`) and gives a
local reasoning model (`deepseek-r1:8b`) for cheap iteration. **Next experiment:** run a thinking+tools
model on the hangman build task. If it write→run→verifies where `qwen3-coder:480b` would not, the
ceiling is "coder without agentic reasoning," not "models can't do this" — and it validates the
recover-then-bail design by showing a model that actually recovers.

*Sources for the benchmark claims (aggregators/press, treat as claims not measurements): kilo.ai and
morphllm.com open-source coding roundups (2026); turingpost.com Chinese-models guide; deeplearning.ai
The Batch on Kimi K2.6; akitaonrails.com LLM benchmarks (May 2026).*

### Backlog — a broader command-line-model catalogue

Beyond Ollama: any command-line model drives the loop via `CliResponder` (Substrate owns the tools,
so even a plain prompt→text CLI becomes tool-using). We want a standing catalogue so we never
re-research it — the commercial agent CLIs (Claude `claude -p`, proven live; Gemini `gemini -p`,
wired, needs auth; Grok and others as they ship CLIs) and open models we run or port to run locally.
**Deferred** — current focus is the Ollama/local path (llama + the coder models above). Filed here so
the shape is captured; build the catalogue once the model path is settled.

---

## Distillation targets (what leaves this doc)

- **BLACKBOARD:** current state — the tool loop now has an anti-spin guard + recover-then-bail; the
  arena is a working discovery harness; the model ceiling (R-7) is the current frontier.
- **KIT_DIARY / ADDENDUMS:** the methodology findings — the discovery harness (Addendum D, filed);
  "a prompt is a request, substrate can enforce" and "prefer the observation over the principle when
  they conflict" (R-5/R-6) are diary candidates not yet filed.

---

## Claim ledger — verified vs unverified (2026-07-02)

A standing honest audit, run under the SDD skeptic challenge. **Verified** = a reading *outside my
control* would differ if the claim were false (a live run's real fs/bash/oracle output, an independent
tool, rendered pixels, a diff vs source-of-truth). Everything else is named plainly. Kept current;
this is the list to attack, not trust.

### Verified — outside-my-control evidence (this session)
- Byte-cap kills the glob-wedge (arena live + reproduce-then-kill). · Parser batched-call fix (live
  flip 0-tools→executing + test). · Anti-spin guard (live `16→2` writes). · Recover-then-bail (live
  `4`+truthful bail + tests). · Workspace rooting: rel→root / absolute passthrough / bash cwd (real fs
  smoke). · **Server→workspace→file** (live, counter-checked: file in `/tmp/ws-verify`, none leaked to
  server cwd). · **`/cwd` terminal** (structural E2E + perceptual screenshot showing `workspace =
  /tmp/agent-e2e`). · Empty-file marker (arena live). · R-9 kimi write→read→run→verify (n=1, real
  `exit: 0` + `=== HANGMAN ===`). · R-10 discipline prompt inert (n=1 A/B). · SOFT regex (12 real
  logs, 0 false positives). · Container arena reaches host Ollama (live). · 17 tool_loop + 6 reference
  + 28 server tests (independent pytest, run this session). · ruff+mypy over `src/substrate` (95 files).

### Unverified / weaker (this session)
- **`replace_all` coercion, out-of-range read marker:** could-fail UNIT TEST only — adequate for a pure
  function, but no independent/live channel.
- **`edit_file` line-prefix warning:** prompt text; no behavioral test that a model heeds it —
  UNVERIFIED as an effect.
- **"CI is green":** FALSE, and pre-existing. CI has been red since before this session (the
  2026-06-27 commit too), for TWO repo-wide reasons, both surfaced only by running the CI-equivalent
  gates locally (bare `ruff check` / `ruff format --check`, whole repo — my session gates were scoped
  to `src/substrate`): (1) two `F401` unused imports in assay scripts — **fixed**; (2) **`ruff format
  --check` drift across 61 files** (assay/, swebench tests, scripts), NOT a version skew (reproduces
  locally, ruff 0.15.17, no pinned version). I formatted the 2 files in my own changeset; the
  remaining **59 are pre-existing and not mine to reformat unasked**. So CI stays red until a repo-wide
  `ruff format` + a pinned ruff version — an Architect decision, not a fix I should bundle into this
  branch. My contribution is CI-clean; the repo is not.
- **"Nothing else regressed" after the ~40-file adapter-move refactor:** now VERIFIED — full local
  suite **565 passed, 1 skipped** (2026-07-02, 4m43s), whole-repo `ruff check` clean, `mypy --strict`
  clean over 95 files. (Moved to verified; kept here as the record of the gap that was open.)

### Inherited / not re-verified this session
- **CliResponder:** the mechanism is verified (stub test); "Claude drives FULL_SUITE live" is inherited
  from the pre-compaction summary, NOT re-observed this session. Gemini never worked (auth).
- **Capability eval** (poem/doc/software × tiers): from a prior run, not re-run.
- **Model roster suitability:** only `qwen3-coder:480b` (fails, R-7) and `kimi-k2.6` (verifies, R-9) are
  actually tested on the agentic loop. `deepseek-v4-pro` / `glm-5.1` / `deepseek-r1:8b` / `nemotron` /
  `qwen2.5-coder:7b` verify-behaviour is UNVERIFIED — the roster is a plan, not a result.
- **Benchmark numbers** in the roster: vendor/aggregator claims, not our measurements.

### Project-level standing caveats (flagged, not re-audited here)
- SWE-bench 36% on Lite-300 is real (official-oracle graded), but the split is public+contaminated —
  the contamination-CLEAN rate is unverified (dating deferred).
- N-PERF-1 is machine-dependent; there is no single true number.
- Every n=1 / n=5 model run is exploratory, not a rate — the power floor gates any reported number.
- The "cockpit / daily-driver" vision is aspirational, not a verified capability.

**The process finding under it all:** my local gates were scoped narrower than CI (src-only ruff vs
whole-repo), and I ran targeted test subsets rather than the full suite after a broad refactor. The
green I read was real but *narrower than the claim*. The fix is a habit: run the CI-equivalent gate
(bare `ruff check`, full `pytest`) and observe CI, before saying "clean."

---

*process/RESEARCH.md — started 2026-07-02. Append; never delete a refuted hypothesis (the refutation
is the finding). Thread 1 open: the model ceiling (R-7) is the live frontier.*
