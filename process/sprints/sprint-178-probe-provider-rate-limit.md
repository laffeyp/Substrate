# Sprint 178 — Probe the actual Ollama Cloud rate-limit surface (closes external round-2 M4)

---

```yaml
---
id: 178
status: closed
phase: 0
pass_kind: functional
---
```

## scope

Round-2 review M4: the 2026-08-12 halt named four reasons; reason (2) was "I read Ollama Cloud's '3 concurrent models' (Pro) as '3 concurrent requests per model' and built the shim's per-model semaphore against that misread invariant. The actual documented cap is distinct-model count; per-request rate limits are not published and I never checked the 429 response body or headers to learn what was actually being denied." Twelve sprints later, the tier's real behavior remained unmeasured. Sprint 168's semaphore-scope fix, Sprint 174's 20 percent sustained-denial threshold, and roadmap v2 S5.2's `RateLimitProducer` all size against guesses.

Sprint 178 lands the measurement instrument. A ~230-line script hits `/api/chat` at rising concurrency (1, 2, 3, 5, 8, 10 by default), captures every response's `status_code`, `Retry-After`, any `x-ratelimit-*` headers, and the first 1000 bytes of the body. Output is CSV per row so subsequent analysis reads it without re-hitting the tier.

Runs outside a substrate topology deliberately. Roadmap v2 S5.2's `RateLimitProducer` will run under a topology and emit typed events; this probe is the ground-truth measurement its contract sizes against. Ceremony deferred until the numbers land.

## files created

- `scripts/probe_provider_rate_limit.py` — the probe. Reads env for model, concurrency ladder, duration, host + API key; writes a CSV under `process/probes/<timestamp>_probe_<model>.csv`.

## contracts

- `uv run ruff check scripts/probe_provider_rate_limit.py` returns 0.
- Script parses.
- No new tests — the probe IS the test. Correctness is verified by running against the real endpoint and reading the output.

## how it runs

```
SUBSTRATE_PROBE_MODEL=deepseek-v4-pro:cloud \
SUBSTRATE_PROBE_N_MAX=10 \
SUBSTRATE_PROBE_DURATION_S=60 \
OLLAMA_HOST=https://ollama.com \
OLLAMA_API_KEY=... \
uv run python scripts/probe_provider_rate_limit.py
```

Consumes tier quota; run against the tier the confirmatory will fire on (Pro, Max, whichever). Output CSV goes to `process/probes/`; the caller pins the observed limits alongside the roadmap v2 S5.2 sprint card in `docs/preregistrations/` before the producer authoring dispatches.

## what the output looks like

A row per HTTP call: concurrency_n, worker_id, attempt_n, t_offset_ms, status_code, wall_ms, retry_after, x_ratelimit_* headers, error_kind (if httpx raised), body_head (first 1000 bytes of the response). Summary line at exit: `N denied of M total (P%)` across the ladder.

## what closes when the probe runs

- **M4.** The tier's actual rate-limit behavior is measured, not guessed.
- **Roadmap v2 S5.2 blocker.** `RateLimitProducer`'s Budget can name a limit derived from the probe's numbers rather than the misread doc-string.
- **Sprint 174's threshold.** The 20 percent sustained-denial bound gets calibrated to the tier's actual denial curve; the guess becomes a floor derived from data.
- **Sprint 168's fix.** Once measured, the semaphore's sizing is either confirmed or corrected against the real invariant.

## done

One file. Ships as a measurement instrument, not a substrate topology. The Architect runs it against the tier and reads the CSV; the numbers land as pins in `docs/preregistrations/` before S5.2 dispatches.
