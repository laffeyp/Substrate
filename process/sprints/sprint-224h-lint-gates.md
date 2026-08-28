# Sprint 224h — enforce the discipline with lint gates

```yaml
---
id: 224h
status: closed
phase: testing-discipline
pass_kind: architecture
---
```

## scope

Whatever 224a-g reach today is a snapshot. A gate makes the discipline
survive. Four lint rules to add or tighten on both `substrate` and
`substrate-ui`:

1. **Ban duplicate string literals across files where a constant would
   do.** Ruff's `PLR6301` / a `flake8-no-implicit-concat` or a custom
   check that scans for the same wire-tag-shape string in ≥2 files.
   `session_ended_mid_delegate` regressing (a fresh literal reappearing
   somewhere) fails CI.

2. **Ban new `# noqa: BLE001` without a rationale.** A pre-commit hook
   or `flake8` rule: `noqa: BLE001` with no colon-comment fails. The 40
   sites left after 224e all carry rationales; the gate makes drift
   loud.

3. **Enforce one-letter-variable-name ban outside a defined allow-list**
   (loop indices `i`/`j`/`k` in short scopes, `_` for unused, math
   variables `x`/`y`/`z` in explicit formulas). Ruff's E741 covers
   ambiguous single-char names; extend with a project rule for arbitrary
   two-three-letter names (`wt`, `ws`, `b`, `q`, `r`, `th`, `srv`) when
   they name concepts rather than local temporaries.

4. **Enforce F-API-6 as a runtime import guard, not just a static grep.**
   Current `test_cli.py` parses import lines. A dynamic
   `importlib.import_module("substrate.kernel.runtime")` from `cli.py`
   would slip through. Ship an import hook (an `sys.meta_path`
   installer, or an import-linter contract) that raises when the CLI
   process reaches for anything outside the allow-list.

## artifact contract

### Files

- `substrate/pyproject.toml` and `substrate-ui/pyproject.toml` —
  ruff/flake8 rule additions.
- `substrate/.pre-commit-config.yaml` and matching on substrate-ui —
  hook wiring.
- `substrate/tests/test_import_hook.py` — the runtime F-API-6 guard.

### Assertions

- Introducing a new BLE001 without rationale fails `pre-commit`.
- Adding a duplicate wire-tag literal in a second file fails CI.
- Renaming a variable to a one-letter name (outside allow-list) fails
  ruff.
- A dynamic import of `substrate.kernel.*` from cli.py raises at run
  time in the test suite.

### Tests

- Existing tests continue to pass.
- Each of the four gates has a red-then-green demo test proving the
  gate fires on the anti-pattern.
