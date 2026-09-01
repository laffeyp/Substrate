# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Probe the actual behavior of a provider's rate-limit surface at rising concurrency.

Sprint 178 (closes external round-2 M4): the 2026-08-12 halt's reason (2) named a load-
bearing gap — "I read Ollama Cloud's '3 concurrent models' (Pro) as '3 concurrent requests
per model' and built the per-model semaphore against that misread invariant. The
actual documented cap is distinct-model count; per-request rate limits are not published
and I never checked the 429 response body or headers to learn what was actually being
denied." Twelve sprints later, Sprint 168 released the semaphore during sleep and
Sprint 174 added a 20% sustained-denial bound; both are sized against an unmeasured
invariant. Every future boundary defense (roadmap v2 S5.2 `RateLimitProducer`, S5.3
`ContainerProducer`, S5.4 `ImageProducer`) will inherit the same guess unless someone
measures.

This script hits the endpoint at rising concurrency and captures every response's
status_code, headers (especially Retry-After and any x-ratelimit-* keys), and the first
1000 bytes of the response body. Output goes to `process/probes/<timestamp>_probe.csv`
so subsequent analysis reads it back without re-hitting the tier. A CSV per (attempt_n,
model, status, wall_ms, retry_after, body_head) is the ground-truth artifact the roadmap
v2 producer sprints size their contracts against.

Usage
-----
    SUBSTRATE_PROBE_MODEL=deepseek-v4-pro:cloud \\
    SUBSTRATE_PROBE_N_MAX=10 \\
    SUBSTRATE_PROBE_DURATION_S=60 \\
    OLLAMA_HOST=https://ollama.com \\
    OLLAMA_API_KEY=... \\
    uv run python scripts/probe_provider_rate_limit.py

Env
---
    SUBSTRATE_PROBE_MODEL:      the model tag to hit (e.g. "deepseek-v4-pro:cloud")
    SUBSTRATE_PROBE_N_MAX:      max concurrent workers (default 10)
    SUBSTRATE_PROBE_DURATION_S: probe duration per concurrency level, seconds (default 30)
    SUBSTRATE_PROBE_N_STEPS:    comma-separated concurrency ladder (default "1,2,3,5,8,10")
    OLLAMA_HOST:                base URL (default "https://ollama.com")
    OLLAMA_API_KEY:             required for cloud endpoints
    SUBSTRATE_PROBE_OUT:        override output CSV path

What it does NOT do
-------------------
- Not a substrate topology (yet). Roadmap v2 S5.2's `RateLimitProducer` will run under a
  substrate topology and emit typed events; this probe is the ground-truth measurement
  the producer's contract sizes against. Keeping the probe outside substrate for now
  keeps it fast to iterate — a topology adds ceremony that the measurement does not need.
- Not a load test. The concurrency ladder is small (1..10) because the goal is
  measurement, not stress. A load test that saturates the tier is a different tool.
- Does not commit its output. The CSV lands under `process/probes/`; the caller decides
  what to publish in `docs/preregistrations/` alongside the roadmap v2 S5.2 card.
"""

from __future__ import annotations

import asyncio
import csv
import os
import sys
import time
from pathlib import Path

import httpx


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None:
        raise SystemExit(f"required env var missing: {name}")
    return v


MODEL = _env("SUBSTRATE_PROBE_MODEL")
N_MAX = int(_env("SUBSTRATE_PROBE_N_MAX", "10"))
DURATION_S = float(_env("SUBSTRATE_PROBE_DURATION_S", "30"))
N_STEPS = [int(s.strip()) for s in _env("SUBSTRATE_PROBE_N_STEPS", "1,2,3,5,8,10").split(",")]
OLLAMA_HOST = _env("OLLAMA_HOST", "https://ollama.com")
OLLAMA_API_KEY = _env("OLLAMA_API_KEY")
OUT_PATH = Path(
    _env(
        "SUBSTRATE_PROBE_OUT",
        f"process/probes/{int(time.time())}_probe_{MODEL.replace(':', '_').replace('/', '_')}.csv",
    )
)

# One prompt across every call so the response-length variance is bounded. Small enough that
# the tier's true per-request limit fires before a payload-size limit kicks in.
_PROMPT = "Write the number 1 in one word."


async def _one_call(
    client: httpx.AsyncClient, attempt_n: int, worker_id: int, started_at: float
) -> dict[str, object]:
    """Fire one /api/chat call, capture the response's shape whatever it is (200/429/503/other)."""
    started = time.monotonic()
    try:
        r = await client.post(
            "/api/chat",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": _PROMPT}],
                "stream": False,
            },
            headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
            timeout=60.0,
        )
        wall_ms = int((time.monotonic() - started) * 1000)
        return {
            "attempt_n": attempt_n,
            "worker_id": worker_id,
            "t_offset_ms": int((time.monotonic() - started_at) * 1000),
            "status_code": r.status_code,
            "wall_ms": wall_ms,
            "retry_after": r.headers.get("Retry-After", ""),
            "x_ratelimit_remaining": r.headers.get("x-ratelimit-remaining", ""),
            "x_ratelimit_reset": r.headers.get("x-ratelimit-reset", ""),
            "x_ratelimit_limit": r.headers.get("x-ratelimit-limit", ""),
            "body_head": r.text[:1000].replace("\n", " ")[:1000],
            "error_kind": "",
        }
    except httpx.HTTPError as exc:
        wall_ms = int((time.monotonic() - started) * 1000)
        return {
            "attempt_n": attempt_n,
            "worker_id": worker_id,
            "t_offset_ms": int((time.monotonic() - started_at) * 1000),
            "status_code": -1,
            "wall_ms": wall_ms,
            "retry_after": "",
            "x_ratelimit_remaining": "",
            "x_ratelimit_reset": "",
            "x_ratelimit_limit": "",
            "body_head": str(exc)[:1000],
            "error_kind": type(exc).__name__,
        }


async def _worker(
    client: httpx.AsyncClient,
    worker_id: int,
    started_at: float,
    duration_s: float,
    rows: list[dict[str, object]],
    concurrency_n: int,
) -> None:
    """One worker fires calls back-to-back for `duration_s` seconds; each call's row lands in `rows`."""
    attempt = 0
    while (time.monotonic() - started_at) < duration_s:
        attempt += 1
        row = await _one_call(client, attempt, worker_id, started_at)
        row["concurrency_n"] = concurrency_n
        rows.append(row)


async def _run_at_concurrency(n: int, duration_s: float) -> list[dict[str, object]]:
    """Fire `n` concurrent workers against the endpoint for `duration_s` seconds; return all rows."""
    print(
        f"  concurrency={n:>2d} for {duration_s}s ...",
        end=" ",
        flush=True,
        file=sys.stderr,
    )
    rows: list[dict[str, object]] = []
    started_at = time.monotonic()
    async with httpx.AsyncClient(base_url=OLLAMA_HOST) as client:
        workers = [_worker(client, i, started_at, duration_s, rows, n) for i in range(n)]
        await asyncio.gather(*workers)
    n_ok = sum(1 for r in rows if r["status_code"] == 200)
    n_429 = sum(1 for r in rows if r["status_code"] == 429)
    n_503 = sum(1 for r in rows if r["status_code"] == 503)
    n_other = len(rows) - n_ok - n_429 - n_503
    print(
        f"{len(rows)} calls ({n_ok} 200 / {n_429} 429 / {n_503} 503 / {n_other} other)",
        flush=True,
        file=sys.stderr,
    )
    return rows


async def _main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"probing {MODEL} against {OLLAMA_HOST}",
        flush=True,
        file=sys.stderr,
    )
    print(f"concurrency ladder: {N_STEPS}", flush=True, file=sys.stderr)
    print(f"duration per step: {DURATION_S}s", flush=True, file=sys.stderr)
    print(f"output: {OUT_PATH}", flush=True, file=sys.stderr)
    print("---", flush=True, file=sys.stderr)

    all_rows: list[dict[str, object]] = []
    for n in N_STEPS:
        if n > N_MAX:
            print(f"  skipping n={n} (exceeds N_MAX={N_MAX})", flush=True, file=sys.stderr)
            continue
        all_rows.extend(await _run_at_concurrency(n, DURATION_S))

    fields = [
        "concurrency_n",
        "worker_id",
        "attempt_n",
        "t_offset_ms",
        "status_code",
        "wall_ms",
        "retry_after",
        "x_ratelimit_remaining",
        "x_ratelimit_reset",
        "x_ratelimit_limit",
        "error_kind",
        "body_head",
    ]
    with OUT_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for row in all_rows:
            w.writerow({k: row.get(k, "") for k in fields})

    print(
        f"\nwrote {len(all_rows)} rows to {OUT_PATH}",
        flush=True,
        file=sys.stderr,
    )
    # A one-line summary the caller pastes into a decision log without opening the CSV.
    denied = sum(1 for r in all_rows if r["status_code"] in (429, 503))
    total = len(all_rows)
    print(
        f"summary: {denied}/{total} calls denied ({(100.0 * denied / total) if total else 0.0:.1f}%) "
        f"across concurrency ladder {N_STEPS}",
        flush=True,
        file=sys.stderr,
    )


if __name__ == "__main__":
    asyncio.run(_main())
