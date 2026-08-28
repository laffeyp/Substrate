"""Substrate toolkit — session-facing tool wrappers over substrate's own API.

Piece F. Seven tools total per TECH-SPEC §8 (line 1052-1064); this
module ships them in three sprints:

  - 226 (this file, initial): `run_topology`, `run_topology_poll`.
  - 227: `inspect_record` (progressive-disclosure + HMAC cursor).
  - 228: `list_records`, `list_topologies`, `list_applications`,
    `list_sessions`.

Every tool carries its own JSON schema on `Tool.schema` per
`tools.py:64`, so native tool-calling sees it via `ollama_tools` at
`tools.py:357` without touching the closed `_TOOL_SCHEMAS` literal.

`daemon_client` is injected — the module receives an object whose
methods match `substrate._daemon`'s wire client (`run_topology`,
`topology_status`). The real client in production is
`substrate._daemon`; tests inject a stub. This lets the tool run
against a co-resident daemon (same process, direct dispatch) or a
remote one (HTTP over UDS/TCP) — the seam is the same.
"""

from __future__ import annotations

from typing import Any, Protocol

from .tools import Tool


class DaemonClient(Protocol):
    """The wire-client shape substrate_tools needs. `substrate._daemon`
    is the shipped implementation. Tests inject a stub that satisfies
    the two methods this module calls."""

    def run_topology(
        self,
        application_name: str,
        inputs: dict[str, Any],
        *,
        bundle: str | None = ...,
        baseline: dict[str, Any] | None = ...,
        context: dict[str, Any] | None = ...,
        await_completion: bool = ...,
        timeout_seconds: float = ...,
    ) -> dict[str, Any]: ...

    def topology_status(self, application_name: str, run_id: str) -> dict[str, Any]: ...


_RUN_TOPOLOGY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "inputs": {"type": "object"},
        "bundle": {"type": "string"},
        "baseline": {"type": "object"},
        "context": {"type": "object"},
        "await_completion": {"type": "boolean"},
        "timeout_seconds": {"type": "number"},
    },
    "required": ["name", "inputs"],
}


_RUN_TOPOLOGY_POLL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "run_id": {"type": "string"},
    },
    "required": ["name", "run_id"],
}


def _run_topology_impl(daemon_client: DaemonClient, args: list[Any]) -> dict[str, Any]:
    """Called by the Tool's `run(args)` callable. args[0] is the tool-call
    dict (native tool-calling routes named args as one dict argument;
    text-parse pushes the parsed dict too, positional index 0)."""
    if not args or not isinstance(args[0], dict):
        raise ValueError("run_topology expects one dict argument")
    payload: dict[str, Any] = dict(args[0])
    name = str(payload.pop("name"))
    inputs = payload.pop("inputs")
    if not isinstance(inputs, dict):
        raise ValueError(f"run_topology inputs must be an object; got {type(inputs).__name__}")
    kwargs: dict[str, Any] = {}
    if "bundle" in payload and payload["bundle"] is not None:
        kwargs["bundle"] = str(payload["bundle"])
    if "baseline" in payload and payload["baseline"] is not None:
        kwargs["baseline"] = payload["baseline"]
    if "context" in payload and payload["context"] is not None:
        kwargs["context"] = payload["context"]
    if "await_completion" in payload:
        kwargs["await_completion"] = bool(payload["await_completion"])
    if "timeout_seconds" in payload:
        kwargs["timeout_seconds"] = float(payload["timeout_seconds"])
    response = daemon_client.run_topology(name, inputs, **kwargs)
    # Normalize to the shape §8 line 1056 names: {output, child_root, run_id}
    # for finalised; {run_id, record_root, status} for async.
    if response.get("status") == "finalised":
        # Pull the terminal envelope's payload as `output` — same as
        # sprint 225d's status handler does. Kept here (rather than on
        # the daemon side) so a synchronous run also returns output
        # without a follow-up status call.
        record_root = response["record_root"]
        output = _extract_terminal_output(record_root)
        return {
            "run_id": response["run_id"],
            "child_root": record_root,
            "status": "finalised",
            "output": output,
        }
    return {
        "run_id": response["run_id"],
        "record_root": response["record_root"],
        "status": response.get("status", "running"),
    }


def _run_topology_poll_impl(daemon_client: DaemonClient, args: list[Any]) -> dict[str, Any]:
    if not args or not isinstance(args[0], dict):
        raise ValueError("run_topology_poll expects one dict argument")
    payload = dict(args[0])
    name = str(payload["name"])
    run_id = str(payload["run_id"])
    response = daemon_client.topology_status(name, run_id)
    # Pass-through: the daemon side already shapes {status, record_root,
    # elapsed_seconds, output?} per TECH-SPEC §8 line 1057.
    return response


def _extract_terminal_output(record_root: str) -> Any:
    """Read the record's tail; return the payload of the last
    non-substrate.* envelope (the application terminal — Verdict,
    Solved, Synthesis). Returns None on empty record or read failure."""
    from pathlib import Path

    from ... import api

    try:
        envelopes = list(api.read_record(Path(record_root)))
    except Exception:  # noqa: BLE001 — a torn record is a real state, not our concern here; None output.
        return None
    for env in reversed(envelopes):
        kind = str(env.get("kind", ""))
        if kind.startswith("substrate."):
            continue
        return env.get("payload")
    return None


def make_run_topology(daemon_client: DaemonClient) -> Tool:
    """Sprint 226 — the `run_topology` tool. A session model calls
    `run_topology(name="code_review", inputs={repo: "."})` and the child
    run's Verdict flows back as the tool result's `output` field."""
    return Tool(
        name="run_topology",
        describe=(
            "run_topology(name, inputs, bundle?, baseline?, context?, "
            "await_completion?=true, timeout_seconds?=600) -> "
            "{output, child_root, run_id} on completion OR {run_id, "
            "record_root, status:'running'} when await_completion=false"
        ),
        deterministic=False,
        run=lambda args: _run_topology_impl(daemon_client, args),
        schema=_RUN_TOPOLOGY_SCHEMA,
    )


def make_run_topology_poll(daemon_client: DaemonClient) -> Tool:
    """Sprint 226 — the `run_topology_poll` tool. Called with the
    `run_id` a prior `run_topology(await_completion=false)` returned."""
    return Tool(
        name="run_topology_poll",
        describe=(
            "run_topology_poll(name, run_id) -> {status, record_root, output?, elapsed_seconds}"
        ),
        deterministic=False,
        run=lambda args: _run_topology_poll_impl(daemon_client, args),
        schema=_RUN_TOPOLOGY_POLL_SCHEMA,
    )


__all__ = [
    "DaemonClient",
    "make_run_topology",
    "make_run_topology_poll",
]
