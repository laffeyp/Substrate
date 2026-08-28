# Sprint 218 — CLI `chat` verb + bare dispatch + config.toml defaults

```yaml
---
id: 218
status: pending
phase: daily-driver-piece-D
pass_kind: architecture
---
```

## scope

Add `chat` verb to `substrate/src/substrate/cli.py`. Bare `substrate` (no subcommand) dispatches to `chat` with defaults from `~/.substrate/config.toml` `[defaults]` block (`driver`, `role`, `bundle`, `workspace`, `isolate`). Daemon auto-launch when socket + TCP both fail to connect: double-fork POSIX (`os.setsid`), start `substrate daemon` in background, wait up to 3s for socket, then try again. If still no daemon: `[config] daemon failed to start; try `substrate daemon --foreground`` and exit 64.

**Scope amendment folded 2026-08-28.** Two changes to the original card:

1. **`substrate daemon [--foreground]` verb moves in from sprint 222.** The card as written auto-launches "substrate daemon" without shipping that verb — chicken-and-egg. This sprint now ships the `daemon` verb alongside `chat`. Card 222 drops it from its subverb list.

2. **Daemon-launch mechanism reads `~/.substrate/config.toml [daemon] server_path` for the substrate-ui/server.py path.** The CLI (in the `substrate` package) does not know where `substrate-ui/server.py` lives on disk (different repo, no shared packaging today). The `daemon` verb reads `server_path` from config and shells `python <server_path>`. Missing config or missing file → exit 64 with a clear message naming the config key. Piece D's initial demo path: user sets `[daemon] server_path` once, then `substrate chat` auto-launches through the config-resolved path. A follow-up card (post-piece-D) can replace this with proper packaging.

## prerequisites

- Sprint 217 closed (piece B done).
- Sprint 210 closed (piece A done).

## context_files

- `substrate/src/substrate/cli.py` (829 lines) — existing verb + click pattern.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §6 (chat verb + bare dispatch + config.toml shape).
- `substrate/src/substrate/cli.py:2-8` — F-API-6 (`substrate.api` only + click + rich).

## artifact contract

### Files

- `substrate/src/substrate/cli.py` — new `chat` command; bare-dispatch handler at the group level; small `_daemon.py` client module for socket/TCP fallback.
- `substrate/src/substrate/templates/config.toml` — shipped default config.

### Assertions

- `substrate` (no args) opens a session with config default driver.
- `substrate chat kimi` opens a session with `kimi` driver.
- Config file at `~/.substrate/config.toml` overrides shipped defaults when present.
- Daemon not running + no socket: CLI auto-launches, waits up to 3s, then retries; on success proceeds; on failure prints `[config]` and exits 64.
- CLI imports only `substrate.api` + click + rich + stdlib (import-linter check passes).

### Tests

- `test_cli_bare_dispatches_chat.py`
- `test_cli_chat_verb_smoke.py`
- `test_cli_daemon_autolaunch.py` (subprocess isolation).
- `test_cli_socket_fallback.py`.

## observation contract

`substrate` (bare) in a fresh shell with no daemon running: CLI launches the daemon in background, session opens, prompt appears. `substrate session ls` from another terminal shows the running session.

## halt conditions

- `bridge_mapping_required` if socket handling needs a mapping (stdlib `socket` should suffice).

## definition of done

`substrate` bare works. Config defaults respected. Daemon auto-launches. Sprint 219 (REPL + SSE streaming) can dispatch.
