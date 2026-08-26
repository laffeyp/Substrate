# Sprint 208 — driver context lookup + seed-alone-exceeds warning

```yaml
---
id: 208
status: closed
phase: daily-driver-piece-A
pass_kind: bridge
---
```

## scope

Wire per-driver `driver_context_tokens` resolution. For Ollama tags, `GET <OLLAMA_BASE_URL>/api/show` and read whichever `model_info.*.context_length` key is present (family-scoped: `llama.context_length`, `qwen2.context_length`, `deepseek.context_length`, etc.); cache per tag with a 60-second TTL. For CLI drivers (Claude / Codex / Gemini), read from `~/.substrate/config.toml`'s `[driver.<name>]` block. For `DeterministicResponder`, 4096 (irrelevant — deterministic responders bypass rendering). For a custom `[[responder]]` entry, read the entry's `context_tokens` field. Add a session-open check: if `_est_tokens(seed) + _est_tokens(per_turn) > driver_context_tokens * 0.6`, write a `SessionWarning{"kind": "seed_alone_exceeds"}` event on the record and print a stderr line naming the driver + the bundle. `pass_kind: bridge` because the Ollama `/api/show` API surface is external.

## prerequisites

- Sprint 207 closed.
- `WORKING_AGREEMENT.md` bridge mapping row for the Ollama `/api/show` endpoint IS ALREADY AUTHORED before this sprint dispatches. Post-review 2026-08-25: TECHNIQUE #46 requires the row before the code, not folded into the same sprint. Sprint 207.5 (or the tail of sprint 207 if the row is one line) authors the row and closes it separately. This sprint refuses to dispatch until the row exists — that is a `bridge_mapping_required` halt condition on OPEN, not on close.

## context_files

- Sprint 207 output: `substrate/src/substrate/topologies/session/transcript.py`.
- `substrate/src/substrate/adapters/models.py` — `OllamaResponder`, `OLLAMA_BASE_URL` env, existing httpx pattern.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §3a driver context lookup table.
- Verified live: `curl :11434/api/show -d '{"name":"llama3.2:1b"}'` returns `model_info.llama.context_length = 131072`.

## signal contract

### Emits

- `SessionWarning{kind: "seed_alone_exceeds", seed_tokens: int, driver_context_tokens: int}` — fires at most once per session_id per condition. Cadence per §3a.

### Consumes

`GET /api/show` for Ollama tags; `~/.substrate/config.toml` for CLI + custom drivers.

## artifact contract

### Files created or modified

- `substrate/src/substrate/topologies/session/transcript.py` — grow with `resolve_driver_context_tokens(driver_name, responder) -> int` + 60-s TTL cache.
- `substrate/src/substrate/adapters/models.py` — add `context_tokens(self) -> int` method on `OllamaResponder` that calls `/api/show` and reads the first `*.context_length` key.
- `substrate/src/substrate/topologies/session/__init__.py` — session-open check that emits `SessionWarning` when the ratio trips.
- `substrate/process/WORKING_AGREEMENT.md` — bridge mapping row for `/api/show`.

### Content assertions

- `resolve_driver_context_tokens` for a `DeterministicResponder` returns 4096.
- For an `OllamaResponder` it calls `/api/show` and returns the family-scoped `context_length`. Cache honored: two calls within 60s return the same value with one HTTP hit.
- For a `CliResponder` it reads `~/.substrate/config.toml`'s `[driver.<name>].context_tokens`, defaulting to 100000 if absent (documented as user-settable).
- `SessionWarning` fires exactly once per (session_id, "seed_alone_exceeds") pair — a second session-open on the same session_id with the same bundle does NOT re-fire (cadence per §3a).

### Command exit codes

- `uv run python -m pytest tests/test_render_ollama_context_lookup.py tests/test_render_cli_config_context.py tests/test_render_seed_alone_exceeds.py -q` exits 0.
- Ruff + mypy strict clean.

## observation contract

Live realmodel test (gated on `SUBSTRATE_REALMODEL=1` per existing pattern): `resolve_driver_context_tokens("llama3.2:1b")` against a live Ollama returns a positive integer that equals `model_info.llama.context_length` from `/api/show`. Session opened with a bundle whose assembled seed exceeds 60% of that number emits exactly one `SessionWarning` on the record and prints the stderr line naming the driver.

## halt conditions to watch

- `bridge_mapping_required` if `WORKING_AGREEMENT.md` has no row for the Ollama `/api/show` endpoint yet.
- `vocabulary_change_required` if `SessionWarning` needs a payload field not in v0.6.

## definition of done

Driver context resolution works for four driver classes. SessionWarning cadence honored. Live Ollama test green. Sprint 209 (bundled registration + CI record) can dispatch.
