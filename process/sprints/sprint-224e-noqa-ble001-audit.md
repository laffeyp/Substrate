# Sprint 224e — audit and thin `# noqa: BLE001` sites

```yaml
---
id: 224e
status: closed
phase: testing-discipline
pass_kind: functional
---
```

## scope

`grep -rn "noqa: BLE001" substrate/src substrate-ui/*.py` returns 42.
Every site catches `Exception` and silences the "catch by class" lint.
Some sites are legitimate — the outer HTTP handler, the shutdown sweep,
`_record_state`, `boot_scan`'s corrupt-manifest branch. Most others
name the class in the trailing comment or should catch it by class.

For each of the 42, do one of three things:
  1. Replace `Exception` with the actual class name (`SyntaxError`,
     `ImportError`, `OSError`, etc.) and drop the `noqa`.
  2. Keep `Exception` and drop the `noqa` where the comment already
     lists the classes — the catch IS the class list, made explicit.
  3. Keep `# noqa: BLE001` where the site is a documented boundary
     (HTTP handler top, sweep loop, corrupt-manifest tolerant read).

Goal: not zero. Goal: every remaining `BLE001` names a boundary in its
comment. A site with no boundary rationale becomes typed or gets
narrowed.

## artifact contract

### Files

- `substrate/src/substrate/**/*.py` — narrow where possible.
- `substrate-ui/*.py` — narrow where possible.

### Assertions

- `grep -rn "noqa: BLE001" substrate/src substrate-ui/*.py | wc -l`
  drops by half (from 42 to ≤ 21).
- Every remaining site has a rationale line naming the boundary or the
  classes the wide catch subsumes.
- Test suite stays green (no behavior change).
