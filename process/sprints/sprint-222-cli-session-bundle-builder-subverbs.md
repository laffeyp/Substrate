# Sprint 222 — CLI session / bundle / builder subverbs

```yaml
---
id: 222
status: pending
phase: daily-driver-piece-D
pass_kind: functional
---
```

## scope

Add CLI subverbs to `substrate/src/substrate/cli.py`:

- `substrate session ls` → `GET /api/session`; renders live + parked table.
- `substrate session end <name-or-id>` → resolve via `GET /api/session/by-name/<name>`; `POST /api/session/<id>/end`.
- `substrate session rm <name-or-id> [--force]` → `DELETE /api/session/<id>`; `--force` required if session was active in the last 24 hours (check manifest `created_at` + last-event timestamp).
- `substrate session set-name <session_id> <new>` → `PATCH /api/session/<id> {name: <new>}` (registry atomically renames in `by-name.json`).
- `substrate bundle create <name>` → creates `~/.substrate/bundles/<name>/` scaffold with empty methodology.md, personality.md, per-turn.md, corpus/, bundle.toml.
- `substrate bundle ls` → lists directories under `~/.substrate/bundles/`.
- `substrate bundle show <name>` → prints `bundle.toml` + methodology + corpus tree.
- `substrate bundle edit <name>` → opens the bundle dir in `$EDITOR`.
- `substrate builder` → opens `~/.substrate/studio.html` in the default browser (mac: `open`, linux: `xdg-open`); if the file is missing, prints the URL of the running daemon's `/studio.html`.
- `substrate daemon [--foreground]` → starts the daemon; `--foreground` keeps it attached.

The `--wizard` variant of `bundle create` defers to sprint 232.

**Scope amendment folded 2026-08-28.** Two changes to the original card:

1. **`substrate daemon [--foreground]` subverb removed.** Sprint 218's amendment now ships the `daemon` verb (needed there for auto-launch). This card drops it.

2. **Bundle subverb scope narrows to CLI-side scaffolding only.** The card's assertion at line 49 references `bundles.load_bundle("test-bundle")` (piece H, sprint 229) which does not exist. `substrate bundle create`, `ls`, `show`, `edit` ship as CLI file-system operations (create directory + template files; list directories; print file contents; open in `$EDITOR`). No dependency on `bundles.py`. The load-round-trip assertion moves to piece H's sprint 229 tests.

## prerequisites

- Sprint 221 closed.

## context_files

- Sprint 218-221 output.
- `substrate/src/substrate/cli.py` — click subcommand group patterns.
- `substrate-ui/server.py` — `/api/session/*` endpoints from piece B.

## artifact contract

### Files

- `substrate/src/substrate/cli.py` — three subcommand groups (`session`, `bundle`, plus `daemon` + `builder` as top-level verbs).

### Assertions

- `substrate session ls` renders a table with columns: name, session_id, driver, status, workspace_shape, elapsed.
- `substrate session rm reviewer` without `--force` for a recently-active session refuses; with `--force` deletes.
- `substrate bundle create test-bundle` scaffolds a valid directory that `bundles.load_bundle("test-bundle")` (piece H, sprint 229) can read without error.
- `substrate builder` opens the URL (assert exit code 0; do not actually verify browser).

### Tests

- `test_cli_session_ls.py`, `test_cli_session_end.py`, `test_cli_session_rm_force.py`, `test_cli_session_set_name.py`.
- `test_cli_bundle_create.py`, `test_cli_bundle_show.py`.
- `test_cli_daemon_start.py`.

## observation contract

Manual: `substrate` bare, `/exit`; then `substrate session ls` shows the just-ended session as `ended`. `substrate bundle create foo` scaffolds directory; `substrate bundle show foo` prints the config.

## halt conditions

- `bridge_mapping_required` if `xdg-open` needs a mapping.

## definition of done

Ten subverbs wired. Piece D closes. Pieces E, F, H unblock (E dispatches independently; F depends on A which is already done; H depends on E).
