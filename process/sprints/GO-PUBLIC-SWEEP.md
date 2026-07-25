# GO-PUBLIC-SWEEP — the readiness work, scoped

*The work that gates the repo-public + `1.0.0` moment. Reference: **laffeyp/cascade-img** — a WRITING example only (register, cadence, how comments
state constraints), per Architect ruling 2026-07-24. Nothing structural is copied from it; the
file set this repo ships is decided by what THIS repo needs, each file ruled on its own merit.
Its bar, in one line: every human-facing surface has a named audience and plain register; every
machine-facing surface has a stable typed contract; comments state a constraint and cite its
source; no LLM lexicon, no AI attribution (enforced even in the shipped onboarding prompt);
complete community/CI scaffolding; the README leads with a demo and states its own limits.*

*Substrate's measured state against that bar (greps 2026-07-24 @ `1d2301d`): lexicon already
clean (2 "robust", 1 "powerful", nothing else); 35 source files carry process references
(73 total — heaviest: `swebench_solver/select_regression.py` 7, `tool_loop/agency.py` 5,
`topologies/bundled.py` 4; the kernel nearly clean at 1–2); community files LICENSE +
CONTRIBUTING only. Em-dash density is NOT a work item — the exemplar runs the same density
(38/206 README); the standard is cadence and lexicon, not punctuation.*

Order is by leverage; waves are independent except W6 last. Every wave has a runnable check.

---

## W1 — Community scaffolding

Files, modeled directly on the exemplar's set:

- **SECURITY.md** — names the real trust boundary, not boilerplate (exemplar names its Discord
  token; ours is the record): *records are shareable data by design* — the hardened,
  PoC-tested boundary (a crafted record's blob ref once path-traversed to arbitrary file read;
  fixed); opening a stranger's record is safe, running a stranger's topology module is code
  execution and always was; the tool suite is library functions like `subprocess` — nothing
  runs until composed and invoked. Plus where to report.
- **CHANGELOG.md** — starts at `1.0.0`; Keep-a-Changelog shape; the BLACKBOARD is history,
  not a changelog an outsider can read.
- **CODE_OF_CONDUCT.md**, **SUPPORT.md** (what's welcome now: issues, topologies, ports;
  what's explicitly not yet: large kernel PRs while the spec corpus governs — solo-maintainer
  honesty up front).
- **.github/**: issue FORMS (`bug_report.yml`, `topology_or_feature.yml`, `config.yml`),
  PR template.
- **GitHub metadata**: description (accurate — the exemplar's one bug is a stale tool-count in
  its description), topics, homepage, wiki off.

*Check:* every file exists; a cold reader can find "is my record safe to share" and "where do I
report" in under a minute.

## W2 — README reconstruction

Rebuild to the exemplar's proven order: badges → one-line what-it-is → **cold-open demo BEFORE
install** → Quick Start → the topology/pane table → How This Differs (with honest concessions,
named) → How It Works → Documentation table → Roadmap → Repo Layout → License. The cold open is
ours already: `pip install substrate-kernel` → `substrate demo replay code_review` →
`substrate narrate` output pasted verbatim — the record telling its own story before a single
concept is explained. Keep the current README's mental-model material; it moves down, not out.
Badges: PyPI, License, Python 3.12+; CI badge only when it points at something green (the local
gate is the bar until Actions returns — a red/never-run badge reads as abandonment).

*Check:* a reader who gives it 90 seconds sees a real replayed record and the install line;
`python -m pytest tests/` untouched; every claim in the new README traceable to a runnable
command.

## W3 — The comment sweep, recalibrated

The exemplar KEEPS review tags — `# …could mis-bind a pending /video job (review #9 F2)` — so
the rule is not deletion. Per reference, one of three dispositions:

1. **Constraint already stated concretely + tag** → KEEP as-is (the exemplar's exact pattern).
2. **Dangling citation** (the ref carries the load; the reason isn't on the line) → RESTATE the
   constraint in place; the tag may stay after it.
3. **Cross-project or unshipped-artifact refs** — `soundfield`, review-pipe numbers whose
   documents aren't in this repo, kit-internal jargon (waves, sprint numbers) → REWRITE to the
   concrete reason, no ref. KIT_DIARY/BLACKBOARD refs may stay (both ship in-repo) when the
   reason is inline.

Work through the measured list heaviest-first. Docstrings get the same pass (keep the length —
the talkative register is a feature; the archaeology is not).

*Check:* `grep -rE "soundfield" src/` returns zero; every surviving `review #N`/finding ref sits
on a line (or block) that states its constraint; `scripts/ci_local.sh` green.

## W4 — Prose cadence pass

Lexicon is already clean; finish it: the 2 "robust" + 1 "powerful" go. Then a read-aloud pass
over README (post-W2), tutorial, demo, walkthroughs for LLM cadence — the exemplar's register is
short declarative sentences and deliberate fragments ("Must stay running." / "Stateless — start
and stop freely."); ours tends toward long qualified clauses. Break them where breaking reads
better. Em-dashes stay wherever they're doing appositive work.

*Check:* zero lexicon hits repo-wide; spot-read three docs cold.

## W5 — Named-audience docs + agent onboarding

The exemplar's docs each declare an audience. Map ours and fill the two gaps:

- **RUNBOOK.md** (new; operator audience): install paths, the Ollama/model setup, every known
  failure mode with its typed error/exit code and remediation — the material exists scattered
  through CLI errors and docstrings; collect it.
- **AGENT_RUNDOWN.md** (new; LLM audience): the exemplar's best trick — a paste-in onboarding
  prompt that tells an agent to READ the source and synthesize rather than recall, and ships
  the discipline inside itself, including verbatim: *do not add any AI-attribution or
  "generated by" lines anywhere.*
- **process/README.md** (new; one paragraph): what the process/ directory is — the project's
  working record, history not documentation — and that `## Decisions` + KIT_DIARY are the
  readable spine.
- **Existing docs**: add a one-line audience header to tutorial/demo/walkthroughs/specs index;
  the dead `.github/workflows/ci.yml` gets a header comment: the canonical gate is
  `scripts/ci_local.sh` until hosted Actions returns.

*Check:* the docs table in the new README lists every doc with its audience; a fresh agent
given only AGENT_RUNDOWN.md produces a correct system summary (test it on a real session).

## W6 — Release mechanics

- `pyproject.toml`: name `substrate-kernel`, version `1.0.0`, real description, license
  expression, classifiers, URLs, `requires-python >=3.12`.
- Wheel-content gate: fresh venv, `pip install dist/*.whl`, `substrate demo replay code_review`
  works offline — proves the committed records ship.
- CHANGELOG entry; `scripts/ci_local.sh` full matrix green, observed.
- Publish with the **project-scoped** token (the account-scoped claim token is to be revoked —
  Architect action, PyPI settings). Repo public the same moment. Placeholder 0.0.1 is
  superseded automatically.

*Check:* `pip install substrate-kernel` on a machine that has never seen the repo → replayed
record in under five minutes.

---

**Total: agent-speed — minutes-to-hours of execution, not days.** The only real time is the
Architect reading the diffs. W1/W2/W4/W5 run in parallel; W3 is the judgment-per-reference one;
W6 is last. Nothing here blocks TestPyPI dry runs at any point.
