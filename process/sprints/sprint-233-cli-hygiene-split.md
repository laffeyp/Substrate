# Sprint 233 — cli.py hygiene split into a package

```yaml
---
id: 233
status: pending
phase: hygiene
pass_kind: architecture
---
```

## scope

REVIEW-2026-08-28 F6 flagged `src/substrate/cli.py` at 1,750 lines,
hosting five to seven concerns: the group + core verbs (chat, tail,
run, resume), REPL + SSE reader, signal handlers + SUBSTRATE_SESSION
env, the slash router, the session/bundle subverbs. Each individual
piece-D sprint (218-222) honored SDD rule 6 in isolation; the
aggregate did not.

Split `cli.py` into a `cli/` package with behavior-preserving surface:

- `cli/main.py` — the click group, `main()` entry, exit codes, the
  narration Console. Imports every subcommand from siblings and
  re-registers them on the group.
- `cli/chat.py` — `chat` verb + `_defaults` + `_load_config` +
  `_daemon_server_path` + `_ensure_daemon_running` + `_double_fork_daemon`.
- `cli/repl.py` — `_repl` + `_readline_with_interrupt` + `_sse_stream`
  + `_render_stream_line` + signal handlers (`_sigint_handler`,
  `_sighup_handler`) + `SUBSTRATE_SESSION` env write.
- `cli/slash.py` — `_slash_route` + the nine slash-command helpers +
  `_SLASH_HELP`.
- `cli/subverbs.py` — the `session`, `bundle`, `builder` groups + all
  their subverbs + `_BUNDLES_ROOT` + `_resolve_session` +
  `_run_bundle_wizard`.
- `cli/run.py` — the `run` verb + `_load_topology` + `_load_attr` +
  `_run_maybe_tailing` + `_resume_maybe_tailing` + `_drive_maybe_tailing`
  + `_failure_summary`.
- `cli/tail.py` — `tail` + `_format_event_line` + `_producer_label`.
- `cli/__init__.py` — re-exports so every existing `from substrate.cli
  import <name>` continues to work. F-API-6 audit test updated to walk
  the package instead of the file.

Contract: dual contract unchanged before and after; every existing test
still passes; no behavior change.

## prerequisites

- REVIEW-2026-08-28 ratified.

## artifact contract

### Files

- `substrate/src/substrate/cli/` (new package, 7 files above + `__init__.py`).
- `substrate/src/substrate/cli.py` — deleted after the package is in
  place; the deletion IS the split. Rule 12: file lives in git history.

### Assertions

- Every existing CLI test file passes unchanged.
- `substrate --help` output unchanged (byte-compare against pre-split
  capture).
- `from substrate.cli import <name>` for every previously-exported name
  still works.
- Every file in `cli/` under 300 lines.

### Tests

- Existing CLI tests re-run (218 5, 219 3, 220 3, 221 10, 222 6+5) =
  32 tests; all pass without modification.
- New: `test_cli_package_reexports.py` — imports every previously-
  exported symbol from `substrate.cli` to lock the re-export shape.

## signal contract

Emits: (none — hygiene split; no runtime emit sites in the diff).

## observation contract

`substrate --help`, `substrate chat`, `substrate session ls`, `substrate
bundle create foo` all work identically to pre-split, byte-compare on
`--help` and structural compare on the session/bundle output.

## halt conditions

- `dual_contract_fail` if any test drifts.

## definition of done

Every existing test passes; `substrate/src/substrate/cli.py` is gone;
`substrate/src/substrate/cli/` is a package; F-API-6 audit adapted.
