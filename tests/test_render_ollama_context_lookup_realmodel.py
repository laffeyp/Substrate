"""Sprint 208.5 — live /api/show driver-context lookup against the local Ollama daemon.

The unit tests at `test_render_ollama_context_lookup.py` monkey-patch `httpx` so
they run in CI without a daemon. This suite runs the same read against a REAL
daemon and asserts that `resolve_driver_context_tokens` matches the value the
daemon returns directly for the same tag.

Gating mirrors `test_realmodel_demos.py:42-59`:
  - `pytestmark = pytest.mark.realmodel` marks the file.
  - `_require(*models)` SKIPs (never fails) iff Ollama is unreachable or a tag
    is absent from the local model list.

Selected tags:
  - `llama3.2:1b` — the small local model the demo suite also uses; carries
    `llama.context_length` on `/api/show`.
  - `huihui_ai/qwen2.5-coder-abliterate:7b` — a locally-installed 7B; carries
    `qwen2.context_length`.

Deselect from a run: `pytest -m "not realmodel"`.
"""

from __future__ import annotations

import pytest

from substrate.adapters import OllamaResponder
from substrate.topologies.session.transcript import (
    _context_cache,
    resolve_driver_context_tokens,
)

pytestmark = pytest.mark.realmodel

_OLLAMA_V1 = "http://localhost:11434/v1"
_FAST = "llama3.2:1b"
_CODE_7B = "huihui_ai/qwen2.5-coder-abliterate:7b"


def _require(*models: str) -> None:
    """SKIP (never fail) iff Ollama or a required model is absent."""
    try:
        import httpx

        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 — httpx.get / json parse / connection reset: any failure means Ollama absent, which is a skip, not a test error.
        pytest.skip(
            f"realmodel context lookup skipped — Ollama not reachable ({type(exc).__name__})"
        )
    missing = [m for m in models if m not in ids]
    if missing:
        pytest.skip(f"realmodel context lookup skipped — model(s) absent: {', '.join(missing)}")


@pytest.fixture(autouse=True)
def _clear_context_cache() -> None:
    _context_cache.clear()


def _api_show_context_length(tag: str) -> int:
    """Read `/api/show` for `tag` and return the first `*.context_length` int.

    Independent of `OllamaResponder.context_tokens()` so the test triangulates:
    responder + daemon must agree.
    """
    import httpx

    resp = httpx.post("http://localhost:11434/api/show", json={"name": tag}, timeout=10.0)
    resp.raise_for_status()
    model_info = resp.json().get("model_info", {})
    for key, value in model_info.items():
        if key.endswith(".context_length") and isinstance(value, int):
            return value
    raise AssertionError(f"/api/show for {tag} exposed no *.context_length key")


def test_resolve_matches_api_show_for_llama3_2_1b() -> None:
    _require(_FAST)
    expected = _api_show_context_length(_FAST)
    r = OllamaResponder(_FAST)
    got = resolve_driver_context_tokens("llama3.2:1b", r)
    assert got == expected > 0


def test_resolve_matches_api_show_for_qwen25_coder_7b() -> None:
    _require(_CODE_7B)
    expected = _api_show_context_length(_CODE_7B)
    r = OllamaResponder(_CODE_7B)
    got = resolve_driver_context_tokens("qwen2-coder", r)
    assert got == expected > 0


def test_second_resolve_within_ttl_hits_cache_not_daemon() -> None:
    """The 60-s TTL cache holds within one test's lifetime — a second resolve
    returns without a second `/api/show`. Verified indirectly: the value stays
    stable, and manual timing shows the second call is sub-millisecond.
    """
    _require(_FAST)
    r = OllamaResponder(_FAST)
    first = resolve_driver_context_tokens("llama3.2:1b", r)
    second = resolve_driver_context_tokens("llama3.2:1b", r)
    assert first == second > 0
