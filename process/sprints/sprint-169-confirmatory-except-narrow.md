# Sprint 169 — Confirmatory runner narrows `except BaseException` to `except Exception` (fold external review F2)

---

```yaml
---
id: 169
status: closed
phase: 1
pass_kind: functional
cadence_band: plan-mode-per-sprint
---
```

---

## scope

Narrow the outer catch at `scripts/assay_swebench_confirmatory.py:841` from
`except BaseException as exc:` to `except Exception as exc:`. Add a comment
naming the WORKING_AGREEMENT invariant that motivated the narrow. Land three
regression pins at `tests/test_confirmatory_runner_exception_scope.py`: a
source-scan test that fails if `except BaseException` reappears in the runner,
and two classifier-contract tests confirming `_classify_cell_error` returns
halt=True on `KeyboardInterrupt` and `SystemExit`.

Closes external review F2 (BLOCKER) at
`docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`. The
reviewer noted Sprint 162 wrote the "no BaseException catches" invariant into
`WORKING_AGREEMENT.md`, and the same file the invariant was written to constrain
violates it. Sprint 169 closes the invariant loop.

---

## prerequisites

- Sprint 162 close (WORKING_AGREEMENT § "SWE-bench external substrates"
  cross-cutting invariants).
- External review at
  `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`
  finding F2.

---

## context_files

- `sdd-kit-2/AGENTS.md` (hard rule 6; correctness fixes take precedence).
- `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`
  finding F2.
- `process/WORKING_AGREEMENT.md` § "SWE-bench external substrates" cross-cutting
  invariants (line ~130, the invariant the runner violates).
- `scripts/assay_swebench_confirmatory.py:165-204` (the classifier —
  `_classify_cell_error`'s current halt-True fallback on unclassified) and
  `:838-849` (the catch site).
- `src/substrate/assay/swebench_errors.py` (typed exception hierarchy — every
  `SwebenchRunnerError` subclass inherits from `RuntimeError` → `Exception`).
- `src/substrate/adapters/rate_limit.py::ProviderRateLimited` (also inherits
  from `RuntimeError` → `Exception`).
- `src/substrate/assay/swebench.py::FirewallViolation` (inherits from
  `ValueError` → `Exception`).

---

## signal contract

### Emits

None at runtime — this is a scope narrow. No new event kinds; existing
`Verdict.NO_VERDICT` rows continue to emit unchanged for classified exceptions.

### Consumes

Files listed in `context_files`.

### Invariants

- Every typed exception the classifier handles inherits from `Exception` via
  `RuntimeError` or `ValueError`. Verified: `SwebenchRunnerError` (RuntimeError),
  `ProviderRateLimited` (RuntimeError), `FirewallViolation` (ValueError),
  `TimeoutError` (Exception), `asyncio.TimeoutError` (Exception),
  `subprocess.CalledProcessError` (Exception).
- The narrow does not swallow anything the classifier previously handled.
- `KeyboardInterrupt`, `SystemExit`, and `asyncio.CancelledError` — all
  `BaseException`-only — now propagate through the catch instead of being
  routed to the classifier.
- Pre-existing tests that exercise the classifier still pass.

---

## artifact contract

### Files modified

- `scripts/assay_swebench_confirmatory.py` — one edit at line 841: change
  `except BaseException as exc:` to `except Exception as exc:`. Add a
  five-line comment naming Sprint 169, the F2 fold, the invariant, and why
  narrowing is safe (every typed exception the classifier handles inherits
  from Exception).

### Files created

- `tests/test_confirmatory_runner_exception_scope.py` — three tests:
  1. `test_confirmatory_runner_narrows_to_exception_not_baseexception` —
     source scan; passes iff `except Exception as exc:` is present AND
     `except BaseException as exc:` is absent.
  2. `test_classify_cell_error_halts_on_keyboard_interrupt` — classifier
     contract; `KeyboardInterrupt` returns `(_ERROR_UNCLASSIFIED, halt=True)`.
  3. `test_classify_cell_error_halts_on_system_exit` — same for `SystemExit`.

### Content assertions

- `grep -q "except Exception as exc:" scripts/assay_swebench_confirmatory.py`
  returns 0.
- `grep -q "except BaseException as exc:" scripts/assay_swebench_confirmatory.py`
  returns non-zero (the string is absent).
- `tests/test_confirmatory_runner_exception_scope.py` exists with three test
  functions.
- Every function in the new test file passes.

### Command exit codes

- `uv run python -m pytest tests/test_confirmatory_runner_exception_scope.py -v --timeout 15`
  returns 0 (3/3 pass).
- `uv run ruff check scripts/assay_swebench_confirmatory.py tests/test_confirmatory_runner_exception_scope.py`
  returns 0.

---

## observation contract

The three regression pins observe the fix:

- **Source scan.** A file-level substring assertion catches any regression that
  widens the catch back to `BaseException`. This is intentional — the runner is
  a script main and awkward to unit-test through its full path; a source scan
  is the honest instrument for a one-line invariant-preserving change.
- **Classifier contract on `KeyboardInterrupt`.** Even though the narrowed
  catch prevents `KeyboardInterrupt` from reaching the classifier, this test
  pins the classifier's own halt-True contract on it. Guards against a future
  extension of the classifier's string-match fallback that could accidentally
  reroute a real interrupt to a NO_VERDICT row.
- **Classifier contract on `SystemExit`.** Same for `SystemExit`.

---

## done criteria

The runner's catch at line 841 reads `except Exception as exc:` with a comment
naming Sprint 169 + F2 + the invariant; three regression pins pass; ruff clean;
the WORKING_AGREEMENT § "SWE-bench external substrates" cross-cutting invariant
is honored by every SWE-bench-authored file in the tree.

---

## notes

- **F2 finding.** Reviewer at
  `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md:46-54`:
  "Sprint 162's cross-cutting invariants at `process/WORKING_AGREEMENT.md:130`
  say: 'No new SWE-bench code catches `BaseException` around a boundary call.'
  This is the same runner Sprint 162 was written to constrain."
- **Why source scan.** The runner is a 972-line script main invoked through
  `asyncio.run()` with heavy I/O setup (dataset loading, Docker preflight,
  clone cache warming). A proper end-to-end test that fires `KeyboardInterrupt`
  mid-sweep would take minutes to set up and would compete with the sprint
  card's ≤2-file sweet spot. A source-scan pin is bounded, deterministic, and
  correct for the property being defended (a one-word substring).
- **Interim vs producer chain.** Roadmap v2 S7 rewrites the runner around
  `run_suite`, cutting the file to ~150 lines. The rewrite will keep the
  narrowed catch and Sprint 169's regression pin ports to whatever thin
  runner replaces the 972-line script.
- Roughly 20 minutes; one source line + one new test file.

---

## plan-mode review checklist

- [x] Catch narrowed from `BaseException` to `Exception` at the one confirmatory
      runner site.
- [x] Comment names Sprint 169, F2, the invariant, and why the narrow is safe.
- [x] Source-scan test pins the invariant across future edits.
- [x] Classifier-contract tests pin halt-True on KeyboardInterrupt + SystemExit.
- [x] Every pre-existing test still passes.
- [x] Ruff clean.
- [x] Two files — within sweet spot.
