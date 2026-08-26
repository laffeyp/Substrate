"""Sprint 213a — path 1 (child_session_name) surfaces a typed deferral error.

The standing-session dispatch needs `SessionRegistry.turn()` on the substrate-ui
side. Sprint 211 shipped the registry without `.turn()`; sprint 213b adds it and
wires this path. Until then, a delegate call carrying `child_session_name`
raises ValueError with a clear message so the model reads a typed refusal via
the tool_loop's `ToolResult(ok=False, error=...)` shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from substrate.adapters import DeterministicResponder
from substrate.topologies.tool_loop.delegate import make_delegate


def test_child_session_name_dispatch_raises_typed_deferral(tmp_path: Path) -> None:
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    with pytest.raises(ValueError, match="child_session_name"):
        d.run([{"task": "review this", "child_session_name": "reviewer"}])


def test_deferral_message_names_sprint_213b(tmp_path: Path) -> None:
    """The error string names the sprint that will land the seam so the model
    (or a human reading the tool result) knows what unblocks the path.
    """
    d = make_delegate(responder=DeterministicResponder(seed=0), root=tmp_path)
    with pytest.raises(ValueError, match="sprint 213b"):
        d.run([{"task": "review", "child_session_name": "reviewer"}])
