"""Sprint 221 — CLI REPL slash-command router.

Nine slashes: /exit, /model, /tools, /context, /inspect, /list, /replay,
/run, /help. `_slash_route(line, session, pending_context)` returns True
when it handled the line (REPL should NOT call daemon.turn); False for
non-slash text OR for `/exit` (the one slash the model observes — the
REPL sends it as a UserMessage so the daemon's `end-on-exit` trigger
fires SessionEnded{user_exit}).

Coverage:
  - /help prints the slash list (True).
  - /model calls patch_session(driver=...).
  - /tools calls patch_session(tools=[...]).
  - /context stores {parent_seq_range, kinds} in pending_context.
  - /list sessions calls list_sessions.
  - /run prints the piece-E deferral hint.
  - /exit returns False (REPL sends as UserMessage).
  - Non-slash text returns False.
  - Unknown slash returns True + prints hint.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _stub_err(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from substrate import cli

    lines: list[str] = []

    def _cap(msg: Any, **_kw: Any) -> None:
        lines.append(str(msg))

    monkeypatch.setattr(cli._err, "print", _cap)
    return lines


@pytest.fixture
def session() -> dict[str, Any]:
    return {"session_id": "s_abc", "name": "test", "record": "/tmp/x"}


def _route(
    line: str, session: dict[str, Any], pending: dict[str, Any] | None = None
) -> tuple[bool, dict[str, Any]]:
    from substrate import cli

    p = pending if pending is not None else {}
    handled = cli._slash_route(line, session, p)
    return handled, p


def test_help_prints_slash_list_and_returns_true(
    session: dict[str, Any], _stub_err: list[str]
) -> None:
    handled, _ = _route("/help", session)
    assert handled is True
    body = "\n".join(_stub_err)
    for slash in (
        "/exit",
        "/model",
        "/tools",
        "/context",
        "/inspect",
        "/list",
        "/replay",
        "/run",
        "/help",
    ):
        assert slash in body, f"/help output missing {slash}"


def test_model_calls_patch_session_driver(
    monkeypatch: pytest.MonkeyPatch, session: dict[str, Any]
) -> None:
    from substrate import _daemon

    captured: dict[str, Any] = {}

    def _patch(sid: str, **kw: Any) -> dict[str, Any]:
        captured["sid"] = sid
        captured.update(kw)
        return {}

    monkeypatch.setattr(_daemon, "patch_session", _patch)
    handled, _ = _route("/model kimi-k2.6:cloud", session)
    assert handled is True
    assert captured == {"sid": "s_abc", "driver": "kimi-k2.6:cloud"}


def test_tools_calls_patch_session_tools_list(
    monkeypatch: pytest.MonkeyPatch, session: dict[str, Any]
) -> None:
    from substrate import _daemon

    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        _daemon, "patch_session", lambda sid, **kw: captured.update({"sid": sid, **kw}) or {}
    )
    handled, _ = _route("/tools read_file,grep,write_file", session)
    assert handled is True
    assert captured["tools"] == ["read_file", "grep", "write_file"]


def test_context_stores_pending_range_and_kinds(session: dict[str, Any]) -> None:
    handled, pending = _route("/context 3-9 --kind ToolResult", session)
    assert handled is True
    assert pending == {"parent_seq_range": [3, 9], "kinds": ["ToolResult"]}


def test_list_sessions_calls_daemon(
    monkeypatch: pytest.MonkeyPatch, session: dict[str, Any]
) -> None:
    from substrate import _daemon

    def _list() -> dict[str, list[dict[str, Any]]]:
        return {"running": [{"session_id": "s1", "name": "a", "driver": "det"}]}

    monkeypatch.setattr(_daemon, "list_sessions", _list)
    handled, _ = _route("/list sessions", session)
    assert handled is True


def test_list_applications_prints_piece_e_deferral(
    session: dict[str, Any], _stub_err: list[str]
) -> None:
    handled, _ = _route("/list applications", session)
    assert handled is True
    body = "\n".join(_stub_err)
    assert "piece-E" in body or "piece E" in body


def test_run_prints_piece_e_deferral(session: dict[str, Any], _stub_err: list[str]) -> None:
    handled, _ = _route("/run coding_flow", session)
    assert handled is True
    body = "\n".join(_stub_err)
    assert "piece-E" in body or "piece E" in body


def test_exit_returns_false_so_repl_sends_as_user_message(session: dict[str, Any]) -> None:
    handled, _ = _route("/exit", session)
    # The ONLY slash the router does NOT swallow — the daemon's end-on-exit
    # trigger fires on a `/exit` UserMessage, not on a daemon-side flag.
    assert handled is False


def test_non_slash_returns_false(session: dict[str, Any]) -> None:
    handled, _ = _route("hello there", session)
    assert handled is False


def test_unknown_slash_returns_true_with_hint(
    session: dict[str, Any], _stub_err: list[str]
) -> None:
    handled, _ = _route("/nonsense", session)
    assert handled is True
    body = "\n".join(_stub_err)
    assert "unknown slash" in body
    assert "/help" in body


def test_model_missing_arg_prints_error(session: dict[str, Any], _stub_err: list[str]) -> None:
    handled, _ = _route("/model", session)
    assert handled is True
    body = "\n".join(_stub_err)
    assert "exactly one" in body
