"""Sprint 054 Phase A — substrate-side SessionRegistry core contract.

The class moved from substrate-ui into substrate; this test pins the
public shape from the library side. Every method here operates on
on-disk manifests + threading locks; nothing touches HTTP, SSE, or
a daemon process.

Deeper daemon-facing tests (SSE broadcast, cross-process file locks,
first-turn resume against a real record) stay in substrate-ui/tests
where they were — those exercise product-side behaviour, not the
library primitive.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from substrate.adapters import DeterministicResponder
from substrate.session_registry import (
    STATUS_ENDED,
    STATUS_PARKED,
    NameCollision,
    SessionManifest,
    SessionRegistry,
)
from substrate.topologies.session import session_topology


def _session_factory(
    manifest: SessionManifest, first_turn_user_message: Any = None
) -> Callable[[Any], None]:
    del first_turn_user_message
    return session_topology(
        driver=DeterministicResponder(seed=0),
        driver_name="deterministic",
        driver_context_tokens=4096,
        seed=manifest.seed,
        tools={},
        per_turn="",
        max_turns=200,
        turn_max_steps=4,
        session_id=manifest.session_id,
        workspace_path=manifest.workspace,
        record_root=Path(manifest.record_root),
        script=None,
    )


def test_registry_creates_manifest_on_disk(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    manifest = reg.create(
        session_id="s_alpha",
        name="alpha",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="hi",
    )
    assert manifest.session_id == "s_alpha"
    assert manifest.name == "alpha"
    assert (tmp_path / "s_alpha" / "manifest.json").exists()
    assert reg.by_name("alpha") == "s_alpha"
    assert reg.get("s_alpha") == manifest


def test_registry_by_name_returns_none_for_missing(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    assert reg.by_name("nobody") is None
    assert reg.get("s_nobody") is None


def test_registry_rejects_duplicate_name(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg.create(
        session_id="s_a",
        name="dup",
        driver="deterministic",
        workspace=str(tmp_path / "ws1"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    with pytest.raises(NameCollision) as excinfo:
        reg.create(
            session_id="s_b",
            name="dup",
            driver="deterministic",
            workspace=str(tmp_path / "ws2"),
            workspace_shape="flat",
            bundle=None,
            seed="",
        )
    assert excinfo.value.name == "dup"
    assert excinfo.value.existing_session_id == "s_a"


def test_registry_list_all_returns_every_manifest(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    for name in ("alpha", "beta", "gamma"):
        reg.create(
            session_id=f"s_{name}",
            name=name,
            driver="deterministic",
            workspace=str(tmp_path / name),
            workspace_shape="flat",
            bundle=None,
            seed="",
        )
    manifests = reg.list_all()
    assert {m.session_id for m in manifests} == {"s_alpha", "s_beta", "s_gamma"}


def test_registry_survives_a_fresh_instance_at_same_base(tmp_path: Path) -> None:
    """Registry state lives on disk; a second SessionRegistry at the
    same `base` picks up every existing session. This is the property
    that lets the daemon restart without losing standing sessions."""
    reg1 = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg1.create(
        session_id="s_persistent",
        name="persistent",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="a seed",
    )

    reg2 = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    # boot_scan hydrates the in-memory manifest cache from on-disk state —
    # the daemon calls this at startup (server.py:2819). A fresh instance
    # that skips it sees an empty cache; the on-disk state is intact.
    reg2.boot_scan()
    manifest = reg2.get("s_persistent")
    assert manifest is not None
    assert manifest.name == "persistent"
    assert manifest.seed == "a seed"
    assert reg2.by_name("persistent") == "s_persistent"


def test_registry_status_transitions_via_update_status(tmp_path: Path) -> None:
    reg = SessionRegistry(base=tmp_path, session_topology_factory=_session_factory)
    reg.create(
        session_id="s_x",
        name="x",
        driver="deterministic",
        workspace=str(tmp_path / "ws"),
        workspace_shape="flat",
        bundle=None,
        seed="",
    )
    parked = reg.update_status("s_x", STATUS_PARKED)
    assert parked.status == STATUS_PARKED
    ended = reg.update_status("s_x", STATUS_ENDED)
    assert ended.status == STATUS_ENDED
