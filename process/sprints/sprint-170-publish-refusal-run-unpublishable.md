# Sprint 170 — Publish-refusal: `RunUnpublishable` in `Report` + `graded_rate_floor` in `Preregistration` (fold external review F3)

---

```yaml
---
id: 170
status: closed
phase: 1
pass_kind: functional
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Land the design-v3 § "The report contract" publish-refusal branch. Two
changes:

- `src/substrate/assay/preregistration.py` — `Preregistration` gains a
  `graded_rate_floor: float = 1.0` field; `load_preregistration` parses it
  from the `.preg.json` (missing defaults to 1.0, matching the
  pre-Sprint-170 strict arm-completeness gate); out-of-range values raise
  `PreregistrationViolation` with `reason == "malformed_graded_rate_floor"`.
- `src/substrate/assay/report.py` — new frozen `RunUnpublishable` dataclass
  carries `arm: str, graded_rate: float, threshold: float, reason: str`.
  `Report` gains `unpublishable: tuple[RunUnpublishable, ...] = ()`.
  `build_report` accepts an optional `graded_rate_floor: float | None = None`;
  when set, the existing arm-completeness gate generalizes to a floor-based
  `_meets_floor` predicate. Any arm below the floor lands a `RunUnpublishable`
  entry and has its delta / CI / equivalence / fdr collapsed to None.

Closes external review F3 (BLOCKER) at
`docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`.
Design v3 mandated this branch: "The report refuses to publish 'confirmatory'
if graded_rate below threshold. Pre-reg pins the threshold." A run whose
82% throttled cells collapsed the resolve rate now refuses to publish a
headline computed against a below-floor M — the reader sees the completion
gap on the report's face instead of inferring it from
`reason_counts={rate_limited: N}`.

---

## prerequisites

- H-4 ratification 2026-08-10 (design v3's report contract).
- Sprint 143+ pre-registration gate.
- External review at
  `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`
  finding F3.

---

## context_files

- `sdd-kit-2/AGENTS.md` (hard rule 6 sweet spot).
- `docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` § "The report
  contract" (the specification this sprint implements).
- `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`
  finding F3.
- `src/substrate/assay/report.py:145` (Report class; `build_report` at line
  296; McNemar + bootstrap gate around line 396).
- `src/substrate/assay/preregistration.py:66` (Preregistration dataclass;
  `load_preregistration` at line 148).
- `docs/preregistrations/2026-08-swebench-lite.preg.json` (target pre-reg
  file the runner reads; `graded_rate_floor` may be added here once
  Sprint 170 lands).
- `tests/test_assay_report.py` (file modified; existing shape for
  `_cr` helper + `_floor_suite` new helper).
- `tests/test_assay_preregistration.py` (file modified; existing shape for
  `_write_preg` helper).

---

## signal contract

### Emits

None at runtime. `RunUnpublishable` is a data class in the Report
projection; producers do not emit it. The report layer builds it from the
arm's `graded_rate` compared against the pre-registered floor.

### Consumes

Files listed in `context_files`.

### Invariants

- Backward compat: every existing `build_report(suite, results)` call
  behaves identically. Without a `graded_rate_floor` kwarg the effective
  floor is 1.0 (matching the pre-Sprint-170 arm-completeness gate), and
  `Report.unpublishable` is always the empty tuple.
- Backward compat: every existing `.preg.json` file without a
  `graded_rate_floor` field parses cleanly with `graded_rate_floor = 1.0`.
- `RunUnpublishable.threshold` matches the value passed to
  `graded_rate_floor`; `graded_rate` matches `ArmReport.graded_rate` for
  the same arm.
- Arms below the floor have `delta_pass_k`, `ci_low`, `ci_high`,
  `bootstrap_p`, `equivalence`, `fdr_significant`, and `delta_vs_control`
  all None.
- Control arm below the floor collapses every non-control arm's delta to
  None (a delta requires a valid control comparison).
- Every existing pre-registration test continues to pass; every existing
  report test continues to pass.

---

## artifact contract

### Files modified

- `src/substrate/assay/preregistration.py` — add `graded_rate_floor: float = 1.0`
  field on the `Preregistration` dataclass; parse from `raw.get("graded_rate_floor", 1.0)`
  in `load_preregistration` with `[0, 1]` bounds check; raise
  `PreregistrationViolation("malformed_graded_rate_floor", ...)` on
  non-number or out-of-range.
- `src/substrate/assay/report.py` — add `RunUnpublishable` frozen
  dataclass with `arm`, `graded_rate`, `threshold`, `reason` fields; add
  `unpublishable: tuple[RunUnpublishable, ...] = ()` to `Report`;
  `build_report` accepts `graded_rate_floor: float | None = None`; add
  `_meets_floor(cells)` helper; replace `arm_complete` / `control_complete`
  gate variables with `arm_meets_floor` / `control_meets_floor`; build
  the `RunUnpublishable` tuple from below-floor arms; pass to Report
  construction.
- `tests/test_assay_report.py` — append six tests: default no floor →
  empty tuple; below-floor arm produces one entry naming the arm;
  above-floor arms yield an empty tuple with the delta gate open;
  multi-arm below floor produces multiple entries; control below floor
  collapses every non-control delta; reason string contains the
  arithmetic.
- `tests/test_assay_preregistration.py` — append four tests:
  `graded_rate_floor` defaults to 1.0 when absent; parses from JSON when
  present; out-of-range raises `malformed_graded_rate_floor`; non-numeric
  raises `malformed_graded_rate_floor`.

### Content assertions

- `src/substrate/assay/report.py` contains `class RunUnpublishable:`.
- `Report` has `unpublishable: tuple[RunUnpublishable, ...] = ()` field.
- `build_report`'s signature contains `graded_rate_floor: float | None = None`.
- `Preregistration` has `graded_rate_floor: float = 1.0` field.
- `load_preregistration` reads `raw.get("graded_rate_floor", 1.0)`.

### Command exit codes

- `uv run python -m pytest tests/test_assay_report.py tests/test_assay_preregistration.py --timeout 15` returns 0 (50/50 pass).
- `uv run ruff check src/substrate/assay/report.py src/substrate/assay/preregistration.py tests/test_assay_report.py tests/test_assay_preregistration.py` returns 0.
- `uv run mypy --strict src/substrate/assay/report.py src/substrate/assay/preregistration.py` returns 0.

---

## observation contract

Six report-side pins observe the branch:

- **Default no floor → empty tuple.** Backward-compat pin; without the
  kwarg the report behaves identically to pre-Sprint-170.
- **Below-floor arm → one entry.** The primary pin: a synthetic run with
  30% NO_VERDICT under a 0.8 floor produces one `RunUnpublishable`
  naming the arm; delta collapses to None.
- **Above-floor arms → empty tuple.** Same 70% graded rate against a
  0.5 floor lands no `RunUnpublishable`; the delta gate opens.
- **Multi-arm below floor.** Two arms below floor produce two entries.
- **Control below floor collapses non-control deltas.** The report does
  not silently exempt the control arm from the discipline it applies to
  every other arm.
- **Reason string carries the arithmetic.** A reader without the
  ArmReport in front of them sees the fraction, the threshold, and the
  NO_VERDICT count in the human-readable reason.

Four preregistration-side pins observe the parsing:

- **Default 1.0 when absent.** Backward-compat pin.
- **Parses from JSON.** Round-trip.
- **Out-of-range raises.** Bounds check.
- **Non-numeric raises.** Type check.

---

## done criteria

`Preregistration.graded_rate_floor` parses cleanly from `.preg.json` with
`[0, 1]` bounds enforcement; `Report.unpublishable` populates from
below-floor arms; `build_report` collapses below-floor arm deltas to None;
50/50 tests pass across both test files; ruff + mypy strict clean. The
runner (`scripts/assay_swebench_confirmatory.py`) will consume this in a
follow-on wiring sprint that threads `pre.graded_rate_floor` from the
pre-reg into `build_report`.

---

## notes

- **F3 finding.** Reviewer at
  `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md:56-66`:
  "Under design v3, that run's report would emit `RUN_UNPUBLISHABLE`.
  Under the current code, the same report would publish a headline
  computed against a badly-throttled M, and the reader would have to
  notice from `reason_counts={rate_limited: N}` that the number is not
  credible."
- **Design v3 alignment.** § "The report contract" specified the branch
  verbatim. Sprint 170 lands the specified shape; naming (`RunUnpublishable`
  vs `RUN_UNPUBLISHABLE` — the design used the block-header form, this
  landing uses PascalCase per Python convention) is the only variance.
- **Runner wiring is a follow-on.** The runner does not yet read
  `pre.graded_rate_floor` and pass it to `build_report` — that's a
  three-line edit at `scripts/assay_swebench_confirmatory.py` in a
  follow-on sprint. Sprint 170 lands the substrate; the runner's opt-in
  edit is small and independent.
- **Roughly 90 minutes.** Two source files (report.py + preregistration.py)
  + two test files (report + preregistration).

---

## plan-mode review checklist

- [x] `RunUnpublishable` frozen dataclass with named fields.
- [x] `Report.unpublishable` defaults to empty tuple (backward-compat).
- [x] `build_report` accepts optional `graded_rate_floor`.
- [x] Below-floor arm collapses delta / CI / equivalence / fdr to None.
- [x] Control below floor collapses non-control deltas.
- [x] Reason string contains graded fraction + threshold + NO_VERDICT count.
- [x] `Preregistration.graded_rate_floor` parses with bounds check.
- [x] 50 tests pass across two test files; ruff + mypy strict clean.
- [x] Two source files + two test files — within sweet spot.
