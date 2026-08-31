# Review — Python config & linting hygiene (2026-08-07)

Scope: the project's *tooling configuration*, not its runtime logic. What was
examined: `pyproject.toml`, `.githooks/pre-commit`, `.github/workflows/ci.yml`,
`scripts/ci_local.sh`, `conftest.py`, `src/substrate/testing.py`, `.gitignore`,
`CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`. Every gate was run, not read:
`ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `pytest --co`, plus a
probe of the codebase under an extended ruleset. The test *harness machinery* was
read in full; the 74 individual `test_*.py` files were sampled, not read end to end.

## Correction (2026-08-07, after Architect pushback)

The first cut of this review stopped at the tooling gate and explicitly declined to
read the code. That was the wrong line to draw for *this* repo. Finding 0 below —
stringly-typed vocabulary, the single most important item here — is invisible to the
gates (mypy sees `str`, ruff sees a valid literal) and is only findable by reading the
source. It leads the review now; the config items that follow are secondary to it.

## Finding 0 — the vocabulary is stringly-typed; the canonical home is bypassed

This is the lead defect and it is a direct violation of the project's own first
principle (vocabulary is the contract) and hard rule 7 (canonical home registry).

`constants.py:39` defines the twelve reserved lifecycle kinds — but only as a flat
`LIFECYCLE_KINDS: tuple[str, ...]`. There are **no individually-named members**: no
`RUN_FINALISED = "substrate.RunFinalised"` to import. So every site that needs a
*specific* kind has nothing to reference and retypes the raw literal. The result:

- `"substrate.RunFinalised"` ×16, `"substrate.ProducerCompleted"` ×16,
  `"substrate.ProducerStarted"` ×14, `"substrate.ProducerFailed"` ×13,
  `"substrate.ProducerEmittedInvalidEvent"` ×13, `"substrate.InputBuildFailed"` ×12,
  `"substrate.ProducerCancelled"` ×10, plus a bare `"substrate."` prefix ×13 —
  spread across **17 files** (runtime, sequencer, composition, views, all five
  projections, both conformance modules, cli, two reference topologies, code_review).

The smoking gun: `kernel/runtime.py:28` does
`from ..constants import BUDGET_US, HYSTERESIS_K, VOCAB_VERSION, is_reserved`, then
hand-types `"substrate.RunFinalised"` (lines 311, 346), `"substrate.RunStarted"`
(359, 415), `"substrate.ProducerCompleted"` (425) a few lines later. The file that
owns the lifecycle imports *from the very module that lists the kinds* and still
retypes them.

Why it matters, not as style: the closed set is defined once and enforced nowhere.
`is_reserved()` (constants.py:55) checks only the `"substrate."` *prefix* — there is
no membership check against `LIFECYCLE_KINDS` at any emit site. A typo like
`"substrate.RunFinalized"` (US spelling) passes strict mypy, passes ruff, passes the
import contract, and detonates only at replay — the exact failure the append-only
record exists to make impossible. And because mypy sees `str`, a future rename of a
kind cannot be driven by the type checker; it becomes a manual 17-file grep-and-pray.

Two more tiers of the same defect, one layer down the stack:

- **Run status** — `"finalised"` ×14, `"failed"` ×16, `"paused"` ×12, `"running"`
  ×6. The `RunResult.status` closed set, with no named home at all (~43 raw uses).
- **Domain verdicts** — `"PASS"` ×7 / `"FAIL"` ×4 (the best_of_n / code_review
  verdict contract, parsed by `_verdict_passed()`), `"Solved"` ×11, `"OK"` ×10
  (swebench outcomes). The decision vocabulary as bare strings.

Fix (a behavior-preserving refactor, technique #43, split as a chain of ≤2-file
sprints per hard rule 6):

1. Promote the kinds to a closed type in `constants.py` — a `class Kind(StrEnum)`
   whose members equal today's wire strings (`RUN_FINALISED = "substrate.RunFinalised"`).
   `StrEnum` keeps `Kind.RUN_FINALISED == "substrate.RunFinalised"`, so the emitted
   bytes are byte-identical and every existing record still reads — nothing on the
   wire changes. Rebuild `LIFECYCLE_KINDS` from `tuple(Kind)`; add `is_lifecycle_kind`.
2. Sweep the 17 files to import `Kind.*` instead of retyping. Each sprint closes with
   the record-shape tests unchanged — the observation contract is "same bytes out."
3. Same treatment for `RunStatus` and the verdict/outcome enums in their owning
   modules; register each in the `WORKING_AGREEMENT.md` canonical-home table.

The dividend is exactly what SDD promises: after this, a mistyped kind is a mypy
error at author time, not a corrupted record at replay time.

---

## Verdict (config layer)

The gates are green and the config is already above the median OSS bar. Strict mypy
passes clean across 101 source files. The import-linter contract (`cli` imports only
`substrate.api`) is real and KEPT. `ruff check` / `ruff format --check` pass on 202
files. 615 tests collect in 0.64s. `py.typed` exists and ships in the wheel, so the
`Typing :: Typed` classifier is honored — I checked the built artifact, I did not
assume it. The config comments are unusually disciplined: nearly every non-obvious
choice cites the finding or review that motivated it (the pinned ruff, the
`python_classes = []` collection guard, the swebench mypy override).

So this is a polish review, not a rescue. Four gaps are worth fixing; the largest
one — the lint ruleset — is the direct answer to "is linting configured
professionally." One caution: the extended-ruleset probe reports 1,917 findings, and
**most of them are noise you should not chase.** The real signal is small and named
below.

---

## Findings worth acting on

### 1. Ruff runs the default rule set only — import order is never enforced

`pyproject.toml` has a `[tool.ruff]` block (target-version, line-length,
extend-exclude) but no `[tool.ruff.lint]` section, so linting uses ruff's default
set: `E4`, `E7`, `E9`, `F`. That is Pyflakes plus a slice of pycodestyle. isort
(`I`), bugbear (`B`), pyupgrade (`UP`), and ruff's own rules (`RUF`) are all off.

Evidence from the probe (src only): 12 files with unsorted imports (`I001`), 14
unsorted `__all__` (`RUF022`), 12 stale `# noqa` that no longer suppress anything
(`RUF100`), plus a handful of real modernizations (`UP035`/`UP041`) and bug-prone
patterns (`B905` zip-without-strict, `B008` call-in-default-arg). Today there is *no*
enforced import ordering at all — a reviewer's diffs and an agent's diffs will
reorder imports differently and nothing catches it.

Fix: add a curated select. This is low-noise and aligned with the repo's py312 floor:

```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "C4", "SIM", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B", "SIM"]   # test bodies trip these legitimately
```

Enabling this fixes ~330 items automatically (`ruff check --fix`) and leaves a short
tail to hand-resolve. Land it in one commit, same discipline as the pinned-ruff
reformat.

**Do NOT enable** these, despite their high counts in the probe — they are the noise:

- `COM812` (265) — trailing commas. Ruff's own docs say it *conflicts with the
  formatter*; the formatter already manages them. Enabling it fights `ruff format`.
- `E501` (984) — line-too-long. `line-length = 100` already governs the *formatter*;
  the 984 are overwhelmingly long strings, URLs, and comments the formatter can't
  safely split. Turning on E501 would demand manual mangling for zero readability
  gain.
- `TID252` (259, relative imports), `EM101`/`EM102` (121, exception-message style),
  `TRY003` (119), `PTH` (30-ish, os.path→pathlib), `A00x`, `ARG00x` — opinionated,
  high false-positive, and several are wrong for this codebase (the `del config`
  and `_inp` unused-arg patterns are deliberate protocol conformance).

### 2. CI ignores the lockfile

`uv.lock` is committed (121 KB) but neither gate uses it. `ci.yml` and
`ci_local.sh` both run `uv pip install -e ".[dev]"`, which resolves dependencies
fresh on every run. So "gates green" means green against *whatever resolved that
day*, not against a known dependency set — the exact drift the pinned-ruff comment
already fought for one tool. Generalize that lesson: install from the lock.

Fix: `uv sync --frozen --extra dev` (or `--locked`) in both gates, with a periodic
deliberate `uv lock` bump. The unpinned `mypy`/`pytest`/`hypothesis` floats then
become reproducible without giving up the ability to bump on purpose.

### 3. `coverage` is a declared dev dependency that nothing runs

`coverage` sits in the `dev` extra. There is no `[tool.coverage.*]` config, no
`--cov` in pytest's options, no `coverage run` in either gate. It is installed and
never invoked. Dead tooling in the config is precisely the "not quite professional"
smell — a reader assumes coverage is measured; it isn't.

Fix: pick one. Either wire it in (`uv run coverage run -m pytest && uv run coverage
report`, non-failing to start, or with a floor once a baseline is known) and add a
minimal `[tool.coverage.run] source = ["src/substrate"]`, or drop the dependency.

### 4. pytest is missing the standard strictness flags

`[tool.pytest.ini_options]` sets `asyncio_mode`, `testpaths`, `python_classes`,
`markers`, and `timeout` — all good. It has no `addopts`, and therefore no
`--strict-markers`, `--strict-config`, `xfail_strict`, or `filterwarnings`.

This one bites the repo's own discipline. Demonstrated: a test decorated
`@pytest.mark.realmdel` (a one-character typo of `realmodel`) **passes with only a
`PytestUnknownMarkWarning`.** `realmodel` is the single marker this project relies on
to self-skip when Ollama is absent and to be deselected with `-m "not realmodel"`. A
typo silently defeats both — the test runs where it should skip, or hides where it
should run, and nothing fails.

Fix:

```toml
[tool.pytest.ini_options]
addopts = ["--strict-markers", "--strict-config", "-ra"]
xfail_strict = true
filterwarnings = ["error", "ignore::DeprecationWarning"]  # tighten the ignore list over time
```

`--strict-markers` turns the typo above into a hard collection error.

---

## Smaller, defensible-but-note

### 5. tests/ and scripts/ are outside type-checking

`mypy` runs on `files = ["src/substrate"]` only. The 74 test files and ~31 scripts
are untyped. Untyped tests are a normal, defensible line to draw. But `scripts/`
ships runnable entry points (`run_fanout_review.py`, `run_tool_agent.py`, …) that a
user actually invokes, and they get no type checking. Consider a second, non-strict
mypy pass over `scripts/`, or state explicitly that scripts are out of scope.

### 6. The only *automated* gate is the two fast ruff checks

`CONTRIBUTING.md` is honest that hosted Actions is dead (minutes exhausted) and the
real bar is `ci_local.sh` run by a human, watched to conclusion. The pre-commit hook
enforces only `ruff format --check` + `ruff check`. So mypy, pytest, lint-imports,
and conformance are gated by *a person remembering to run a script*. That is a real
hole in "configured professionally," even though no config file is syntactically
wrong. Options, cheapest first: extend the pre-commit hook to the full stack on push
(a `pre-push` hook, so commits stay fast); or restore a hosted runner; or state the
manual bar as the accepted process and stop implying CI enforces it.

---

## Credits (so the review is calibrated)

Real strengths, not filler: strict mypy clean on 101 files; a genuinely enforced
architectural import boundary (import-linter, KEPT); ruff pinned with a correct,
documented reason (format output is version-sensitive across releases); a CI matrix
spanning {ubuntu, macOS} × py{3.12, 3.13, 3.14}; `py.typed` present and shipping;
a bytecode-clearing `conftest` that prevents stale-`.pyc` phantom failures (a real
past near-miss, cited); a 30s per-test non-termination backstop; and a full
complement of meta docs (SECURITY, CHANGELOG in Keep-a-Changelog shape, LICENSE,
CONTRIBUTING). The tooling here was clearly built by someone who has been burned and
wrote down why. The gaps above are the last 10%, not the first.

## Suggested order

1, then 4 — the two that change what the gates actually catch. Then 2 (reproducible
installs), then 3 (resolve the dead dependency), then 6 (decide the enforcement
story). 5 is optional.
