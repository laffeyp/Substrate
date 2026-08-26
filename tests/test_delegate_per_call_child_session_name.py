"""Sprint 213a/b — path 1 (child_session_name) requires a session_registry.

Sprint 213a's original stub raised a "deferred to sprint 213b" error unconditionally.
Sprint 213b (2026-08-26) wires the standing-session dispatch when `session_registry`
is bound at construction. When it is NOT bound, path 1 still raises a typed
ValueError so the model reads a clear refusal via tool_loop's
`ToolResult(ok=False, error=...)` shape. Integration tests that fire path 1 with
a real SessionRegistry live in `substrate-ui/tests/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop.delegate import make_delegate


def test_child_session_name_dispatch_without_registry_raises_typed(tmp_path: Path) -> None:
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    with pytest.raises(ValueError, match="child_session_name"):
        d.run([{"task": "review this", "child_session_name": "reviewer"}])


def test_error_message_names_the_registry_seam(tmp_path: Path) -> None:
    """The error string names `session_registry` so the model (or a human reading
    the tool result) knows what unblocks the path.
    """
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    with pytest.raises(ValueError, match="session_registry"):
        d.run([{"task": "review", "child_session_name": "reviewer"}])
