# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 051 — Ollama silently truncates a prompt larger than num_ctx.

Regression pin for the mismatch surfaced by the sprint 050 audit: our
compaction budgeted against the model's advertised context length
(`resolve_driver_context_tokens` reads `/api/show`), but the responder
capped Ollama input via `num_ctx` — a hardcoded 32768 in server.py before
the fix. When the two disagreed, Ollama dropped the front of the prompt
silently. No error, no warning. Only `prompt_eval_count` on the response
tells you.

This test pins the behaviour:

1. Send a ~2000-token prompt with num_ctx=512 to llama3.2:1b. Assert
   `prompt_eval_count < 512` and confirm the RESPONSE is coherent for
   the TAIL of the prompt only — a lower cap means the head silently
   disappeared. This is a live behavioural test of Ollama itself.

2. Same prompt with num_ctx=4096 (comfortably above the prompt). Assert
   `prompt_eval_count >= 400` — Ollama read most of the prompt this time.
   Match compaction budget to num_ctx and truncation stops.

Gate: @pytest.mark.realmodel. Skipped when Ollama or llama3.2:1b is absent.
"""

from __future__ import annotations

import json
import urllib.request

import httpx
import pytest

pytestmark = pytest.mark.realmodel

_MODEL = "llama3.2:1b"
_OLLAMA_V1 = "http://localhost:11434/v1"
_OLLAMA_CHAT = "http://localhost:11434/api/chat"


def _require_model() -> None:
    try:
        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — any unreachability is a SKIP
        pytest.skip(f"num_ctx test skipped — Ollama not reachable ({type(exc).__name__})")
    if _MODEL not in ids:
        pytest.skip(f"num_ctx test skipped — model absent: {_MODEL}")


def _chat(prompt: str, *, num_ctx: int, num_predict: int = 40) -> dict:
    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": 0},
    }
    req = urllib.request.Request(
        _OLLAMA_CHAT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 — localhost only
        return json.load(r)


@pytest.mark.timeout(90)
def test_ollama_silently_truncates_when_prompt_exceeds_num_ctx() -> None:
    """Send ~2000 tokens to num_ctx=512. Ollama returns
    prompt_eval_count << 2000 with no warning. The tail survives; the head
    is gone. This is not a substrate bug — it is Ollama's design — but
    substrate must ALIGN num_ctx with the compaction budget (sprint 051)
    to avoid the silent-drop mode where compaction says "I dropped K
    turns" but Ollama actually dropped K + a lot more."""
    _require_model()
    # ~2000 tokens: "The quick brown fox jumps over the lazy dog. " is 10
    # tokens, ×200 = 2000. The TAIL asks the model to reply with HELLO so
    # a coherent reply proves the tail survived.
    prompt = "The quick brown fox jumps over the lazy dog. " * 200
    prompt += "\n\nFINAL_QUESTION: Reply with the single word HELLO."

    tight = _chat(prompt, num_ctx=512)
    tight_eval = tight.get("prompt_eval_count")
    tight_text = (tight.get("message") or {}).get("content", "").strip()

    assert isinstance(tight_eval, int), f"missing prompt_eval_count in tight response: {tight}"
    assert tight_eval < 512, (
        f"Ollama should truncate when prompt exceeds num_ctx=512; got "
        f"prompt_eval_count={tight_eval} (expected < 512). Either Ollama "
        f"changed behaviour or the test prompt undershot the cap."
    )
    # The tail's FINAL_QUESTION survived → the model can still reply with HELLO.
    assert "HELLO" in tight_text.upper(), (
        f"expected HELLO in the response tail (proves the FINAL_QUESTION at "
        f"the end of the prompt survived truncation); got: {tight_text!r}"
    )
    assert tight.get("done_reason") == "stop", (
        f"expected done_reason=stop (no error surfaced by Ollama despite "
        f"truncation); got {tight.get('done_reason')!r}"
    )


@pytest.mark.timeout(90)
def test_ollama_reads_whole_prompt_when_num_ctx_is_sized_up() -> None:
    """Same ~2000-token prompt, num_ctx=4096. Ollama reads the whole
    prompt this time — prompt_eval_count crosses 400. This is the
    "matched num_ctx and compaction budget" mode substrate now targets
    (server.py _responder_for probes /api/show for the model's advertised
    context and passes it into OllamaResponder)."""
    _require_model()
    prompt = "The quick brown fox jumps over the lazy dog. " * 200
    prompt += "\n\nFINAL_QUESTION: Reply with the single word HELLO."

    wide = _chat(prompt, num_ctx=4096)
    wide_eval = wide.get("prompt_eval_count")
    wide_text = (wide.get("message") or {}).get("content", "").strip()

    assert isinstance(wide_eval, int), f"missing prompt_eval_count in wide response: {wide}"
    assert wide_eval >= 400, (
        f"with num_ctx=4096 Ollama should have read most of a ~2000-token "
        f"prompt; got prompt_eval_count={wide_eval}. If this is much lower "
        f"than expected, Ollama may be doing something new we need to trace."
    )
    assert "HELLO" in wide_text.upper(), f"expected HELLO in the response; got: {wide_text!r}"
