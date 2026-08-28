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

from pathlib import Path
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


# ── sprint 227: inspect_record + progressive disclosure + HMAC cursor ────


_INSPECT_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "record": {"type": "string"},
        "format": {
            "type": "string",
            "enum": ["summary", "narrate", "events", "first_divergence", "run_graph"],
        },
        "filter": {
            "type": "object",
            "properties": {
                "kinds": {"type": "array", "items": {"type": "string"}},
                "seq_range": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "producer": {"type": "string"},
                "application": {"type": "string"},
                "time_range": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
        },
        "limit": {"type": "integer"},
        "continue_from": {"type": "string"},
        "compare_record": {"type": "string"},
    },
    "required": ["record"],
}


_DEFAULT_INSPECT_CAP_TOKENS = 1024
_INSPECT_CAP_HEADROOM_FRAC = 0.25


def _cap_tokens(driver_context_tokens: int | None) -> int:
    """Budget cap per TECH-SPEC §8 line 1058, corrected round-6: both
    operands are token counts. `min(1024, 0.25 * driver_context_tokens)`.
    Fall back to 1024 when the caller cannot supply the context size."""
    if driver_context_tokens is None or driver_context_tokens <= 0:
        return _DEFAULT_INSPECT_CAP_TOKENS
    return min(_DEFAULT_INSPECT_CAP_TOKENS, int(driver_context_tokens * _INSPECT_CAP_HEADROOM_FRAC))


def _estimate_tokens(text: str) -> int:
    """Local re-export of `session.transcript._est_tokens` so this module
    does not reach into that private symbol at import time (the piece-A
    module is loaded via the same package tree; this indirection also
    lets tests substitute an alternative estimator)."""
    from ..session.transcript import _est_tokens

    return _est_tokens(text)


def _sign_cursor(payload: dict[str, Any], hmac_key: bytes) -> str:
    """Base64-encoded HMAC-SHA256 signature over `msgspec.json.encode(payload)`.
    The tool returns a `cursor` string opaque to the model: base64 of
    `<sig>.<payload_bytes>`. `_verify_cursor` splits and re-signs. Per-
    daemon-boot random key means a cursor is one-boot-live only, which
    matches the `_TOPOLOGY_RUNS` in-memory-only shape (§13.5 red-team)."""
    import base64
    import hmac
    import hashlib

    import msgspec

    payload_bytes = msgspec.json.encode(payload)
    signature = hmac.new(hmac_key, payload_bytes, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + b"." + payload_bytes).decode("ascii")


def _verify_cursor(cursor: str, hmac_key: bytes) -> dict[str, Any] | None:
    """Return the cursor's payload dict on valid signature; None otherwise.
    A tampered or otherwise-invalid cursor produces a typed
    ToolResult(ok=false) at the caller layer."""
    import base64
    import hmac
    import hashlib

    import msgspec

    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        signature, payload_bytes = raw.split(b".", 1)
        expected = hmac.new(hmac_key, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        data = msgspec.json.decode(payload_bytes)
    except (ValueError, msgspec.DecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _extract_application_name(record_root: str) -> str | None:
    """Read `substrate.RunStarted.payload.topology` (or `.config.topology`
    depending on version) so the `application` filter can compare
    against the record's own manifest section."""
    from pathlib import Path

    from ... import api

    try:
        envelopes = list(api.read_record(Path(record_root)))
    except Exception:  # noqa: BLE001 — torn record: application filter treats as no-match rather than propagating.
        return None
    for env in envelopes:
        if env.get("kind") == api.RUN_STARTED:
            payload = env.get("payload") or {}
            if not isinstance(payload, dict):
                return None
            topology = payload.get("topology")
            if isinstance(topology, str):
                return topology
            config = payload.get("config") or {}
            if isinstance(config, dict) and isinstance(config.get("topology"), str):
                return config["topology"]
            return None
    return None


def _filter_events(envelopes: list[dict[str, Any]], filt: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply the manifest-declared filter shape to a full envelope list.
    Empty filter returns everything. Order preserved."""
    kinds = set(filt.get("kinds") or [])
    seq_range = filt.get("seq_range")
    producer = filt.get("producer")
    time_range = filt.get("time_range")
    result: list[dict[str, Any]] = []
    for env in envelopes:
        if kinds and str(env.get("kind", "")) not in kinds:
            continue
        if isinstance(seq_range, list) and len(seq_range) == 2:
            seq = int(env.get("seq", -1))
            if seq < int(seq_range[0]) or seq > int(seq_range[1]):
                continue
        if producer is not None:
            producer_ref = env.get("producer") or {}
            if not isinstance(producer_ref, dict) or producer_ref.get("kind") != producer:
                continue
        if isinstance(time_range, list) and len(time_range) == 2:
            event_time = env.get("t")
            if event_time is None:
                continue
            if float(event_time) < float(time_range[0]) or float(event_time) > float(time_range[1]):
                continue
        result.append(env)
    return result


def _inspect_record_impl(
    args: list[Any], *, hmac_key: bytes, driver_context_tokens: int | None
) -> dict[str, Any]:
    """The inspect_record tool body. Five formats + five filters + a
    budget cap. On overflow, returns `{has_more, cursor}` — the model
    calls again with `continue_from=cursor` to paginate.

    Tampered cursor returns `{ok: false, error: "invalid cursor"}`; the
    caller's tool_loop layer wraps this into a ToolResult.
    """
    from pathlib import Path

    from ... import api

    if not args or not isinstance(args[0], dict):
        raise ValueError("inspect_record expects one dict argument")
    payload = dict(args[0])
    format_name = str(payload.get("format", "summary"))
    filt = payload.get("filter") or {}
    if not isinstance(filt, dict):
        raise ValueError("filter must be an object")
    continue_from = payload.get("continue_from")
    cap_tokens = _cap_tokens(driver_context_tokens)

    if continue_from is not None:
        cursor_data = _verify_cursor(str(continue_from), hmac_key)
        if cursor_data is None:
            return {"ok": False, "error": "invalid cursor"}
        record_root_str = str(cursor_data["record"])
        filt = {
            "kinds": cursor_data.get("kinds") or [],
            "seq_range": cursor_data.get("seq_range"),
            "producer": cursor_data.get("producer"),
            "application": cursor_data.get("application"),
        }
        start_seq = int(cursor_data["next_seq"])
    else:
        record_root_str = str(payload["record"])
        start_seq = -1

    record_root = Path(record_root_str)

    if format_name == "summary":
        summary = api.narration_summary(record_root)
        return {
            "format": "summary",
            "finalised": summary.finalised,
            "final_reason": summary.final_reason,
            "total_events": summary.total_events,
            "producers_started": summary.producers_started,
            "producers_completed": summary.producers_completed,
            "producers_cancelled": summary.producers_cancelled,
            "producers_failed": summary.producers_failed,
            "input_build_failures": summary.input_build_failures,
            "application_events": dict(summary.application_events),
        }

    if format_name == "run_graph":
        graph = api.run_graph(record_root)
        return {
            "format": "run_graph",
            "status": graph.status,
            "final_reason": graph.final_reason,
            "producers": [
                {
                    "kind": inst.kind,
                    "instance": inst.instance,
                    "status": inst.status,
                    "parent": inst.parent,
                    "trigger_id": inst.trigger_id,
                    "fired_seq": inst.fired_seq,
                    "started_seq": inst.started_seq,
                    "ended_seq": inst.ended_seq,
                    "emitted": list(inst.emitted),
                }
                for inst in graph.instances
            ],
        }

    if format_name == "first_divergence":
        compare_record = payload.get("compare_record")
        if not compare_record:
            raise ValueError("first_divergence requires `compare_record`")
        divergence = api.first_divergence(record_root, Path(str(compare_record)))
        if divergence is None:
            return {"format": "first_divergence", "diverged": False}
        return {
            "format": "first_divergence",
            "diverged": True,
            "seq": divergence.seq,
            "index": divergence.index,
            "kind_a": divergence.kind_a,
            "kind_b": divergence.kind_b,
        }

    if format_name == "narrate":
        lines = list(api.narrate(record_root))
        rendered = "\n".join(str(line) for line in lines)
        if _estimate_tokens(rendered) > cap_tokens:
            rendered = rendered[: cap_tokens * 4]
            return {
                "format": "narrate",
                "text": rendered,
                "has_more": True,
                "note": "truncated to fit token cap; call format='events' with a seq_range to page",
            }
        return {"format": "narrate", "text": rendered}

    if format_name == "events":
        if filt.get("application") is not None:
            record_app = _extract_application_name(record_root_str)
            if record_app != filt["application"]:
                return {"format": "events", "events": [], "has_more": False}
        envelopes = list(api.read_record(record_root))
        filtered = _filter_events(envelopes, filt)
        if start_seq > 0:
            filtered = [env for env in filtered if int(env.get("seq", -1)) >= start_seq]
        collected: list[dict[str, Any]] = []
        running_tokens = 0
        for env in filtered:
            env_tokens = _estimate_tokens(str(env))
            if running_tokens + env_tokens > cap_tokens and collected:
                cursor = _sign_cursor(
                    {
                        "record": record_root_str,
                        "kinds": list(filt.get("kinds") or []),
                        "seq_range": filt.get("seq_range"),
                        "producer": filt.get("producer"),
                        "application": filt.get("application"),
                        "next_seq": int(env.get("seq", -1)),
                    },
                    hmac_key,
                )
                return {
                    "format": "events",
                    "events": collected,
                    "has_more": True,
                    "cursor": cursor,
                }
            collected.append(env)
            running_tokens += env_tokens
        return {"format": "events", "events": collected, "has_more": False}

    raise ValueError(f"unknown format {format_name!r}")


def make_inspect_record(
    *,
    hmac_key: bytes | None = None,
    driver_context_tokens: int | None = None,
) -> Tool:
    """Sprint 227 — the `inspect_record` tool. Five formats
    (summary/narrate/events/first_divergence/run_graph); five filters
    (kinds/seq_range/producer/application/time_range); token-budget cap
    of `min(1024, 0.25 * driver_context_tokens)`; HMAC-signed cursor
    for pagination.

    `hmac_key` defaults to a fresh per-daemon-boot random key
    (`os.urandom(32)`). Cursors are one-boot-live only by design — a
    daemon restart invalidates every outstanding cursor, matching the
    same one-process lifetime as `_TOPOLOGY_RUNS`.

    `driver_context_tokens` is the calling session's context budget; the
    caller reads it from the session_registry and passes it here so the
    cap scales per-session.
    """
    import os as _os

    key = hmac_key if hmac_key is not None else _os.urandom(32)

    return Tool(
        name="inspect_record",
        describe=(
            "inspect_record(record, format?=summary|narrate|events|first_divergence|run_graph, "
            "filter?={kinds,seq_range,producer,application,time_range}, continue_from?) -> "
            "{format, ..., has_more?, cursor?}"
        ),
        deterministic=False,
        run=lambda args: _inspect_record_impl(
            args, hmac_key=key, driver_context_tokens=driver_context_tokens
        ),
        schema=_INSPECT_RECORD_SCHEMA,
    )


# ── sprint 228: four list-* read-only tool wrappers ─────────────────────


class _SessionRegistryLike(Protocol):
    """The subset of substrate-ui/session_registry.SessionRegistry
    substrate_tools reaches. Duck-typed for testability."""

    def list_all(self) -> list[Any]: ...


_LIST_RECORDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "since_ts": {"type": "number"},
        "topology": {"type": "string"},
        "session_name": {"type": "string"},
        "limit": {"type": "integer"},
    },
}

_LIST_TOPOLOGIES_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
_LIST_APPLICATIONS_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
_LIST_SESSIONS_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def _make_list_records_impl(records_root: Path, args: list[Any]) -> dict[str, Any]:
    """Walk `<records_root>/<sid>/manifest.json` plus `<records_root>/runs/*/`;
    newest first per the card. Filters: status, since_ts, topology,
    session_name. Default limit 20.

    The `topology` filter reads the record's `substrate.RunStarted`
    payload.topology (or payload.config.topology depending on version).
    A missing record dir on a session with a manifest entry contributes
    a row with `record_root: null` so an operator can see fresh sessions
    that never wrote.
    """
    import json
    import time

    from ... import api

    filt = args[0] if args and isinstance(args[0], dict) else {}
    status_want = filt.get("status")
    since_ts = float(filt["since_ts"]) if "since_ts" in filt else None
    topology_want = filt.get("topology")
    session_name_want = filt.get("session_name")
    limit = int(filt.get("limit", 20))

    rows: list[dict[str, Any]] = []
    if not records_root.is_dir():
        return {"records": [], "count": 0}
    for entry in records_root.iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        record_root_path = entry / "record" if (entry / "record").exists() else entry
        row: dict[str, Any] = {
            "session_id": entry.name,
            "record_root": str(record_root_path) if record_root_path.exists() else None,
            "created_at": None,
            "status": None,
            "name": None,
            "topology": None,
        }
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                row["created_at"] = manifest.get("created_at")
                row["status"] = manifest.get("status")
                row["name"] = manifest.get("name")
            except (OSError, ValueError):
                continue
        if row["created_at"] is None:
            try:
                row["created_at"] = entry.stat().st_mtime
            except OSError:
                row["created_at"] = 0.0
        if record_root_path.exists():
            try:
                for envelope in api.read_record(record_root_path):
                    if envelope.get("kind") == api.RUN_STARTED:
                        payload = envelope.get("payload") or {}
                        if isinstance(payload, dict):
                            row["topology"] = payload.get("topology") or (
                                payload.get("config") or {}
                            ).get("topology")
                        break
            except Exception:  # noqa: BLE001 — torn record: leave topology as None.
                pass
        rows.append(row)

    def _include(row: dict[str, Any]) -> bool:
        if status_want is not None and row["status"] != status_want:
            return False
        if since_ts is not None and float(row.get("created_at") or 0.0) < since_ts:
            return False
        if topology_want is not None and row.get("topology") != topology_want:
            return False
        if session_name_want is not None and row.get("name") != session_name_want:
            return False
        return True

    rows = [row for row in rows if _include(row)]
    rows.sort(key=lambda r: float(r.get("created_at") or 0.0), reverse=True)
    rows = rows[:limit]
    return {"records": rows, "count": len(rows), "generated_at": time.time()}


def _make_list_topologies_impl(_args: list[Any]) -> dict[str, Any]:
    from .. import bundled

    return {"topologies": bundled.names()}


def _make_list_applications_impl(app_registry: dict[str, Any], _args: list[Any]) -> dict[str, Any]:
    """Reads the application catalog dict piece E's `load_manifests`
    returns. Values are `ApplicationSpec` msgspec Structs; the wire
    shape returns their names + descriptions (a browsing surface)."""
    entries = [
        {
            "name": spec.name,
            "description": spec.description,
            "runs": spec.runs,
            "output_kind": spec.output_kind,
        }
        for spec in app_registry.values()
    ]
    return {"applications": entries, "count": len(entries)}


def _make_list_sessions_impl(
    session_registry: _SessionRegistryLike, _args: list[Any]
) -> dict[str, Any]:
    """Two buckets per §7.6 line 1062: live + parked. Uses the same
    STATUS_* constants substrate-ui/session_registry exports."""
    live: list[dict[str, Any]] = []
    parked: list[dict[str, Any]] = []
    for manifest in session_registry.list_all():
        entry = {
            "session_id": manifest.session_id,
            "name": manifest.name,
            "driver": manifest.driver,
            "workspace": manifest.workspace,
        }
        status = manifest.status
        if status in ("running", "parked"):
            (live if status == "running" else parked).append(entry)
    return {"live": live, "parked": parked}


def make_list_records(records_root: Path) -> Tool:
    """Sprint 228 — list_records. Walks the on-disk sessions catalog."""
    return Tool(
        name="list_records",
        describe=(
            "list_records(status?, since_ts?, topology?, session_name?, limit?=20) -> "
            "{records: [{session_id, record_root, created_at, status, name, topology}], count}"
        ),
        deterministic=False,
        run=lambda args: _make_list_records_impl(records_root, args),
        schema=_LIST_RECORDS_SCHEMA,
    )


def make_list_topologies() -> Tool:
    """Sprint 228 — list_topologies. Enumerates the BUNDLED registry."""
    return Tool(
        name="list_topologies",
        describe="list_topologies() -> {topologies: [<name>, ...]}",
        deterministic=True,
        run=_make_list_topologies_impl,
        schema=_LIST_TOPOLOGIES_SCHEMA,
    )


def make_list_applications(app_registry: dict[str, Any]) -> Tool:
    """Sprint 228 — list_applications. Piece E's `_APPLICATIONS` dict."""
    return Tool(
        name="list_applications",
        describe=(
            "list_applications() -> {applications: [{name, description, runs, output_kind}], count}"
        ),
        deterministic=False,
        run=lambda args: _make_list_applications_impl(app_registry, args),
        schema=_LIST_APPLICATIONS_SCHEMA,
    )


def make_list_sessions(session_registry: _SessionRegistryLike) -> Tool:
    """Sprint 228 — list_sessions. Live + parked buckets from piece C."""
    return Tool(
        name="list_sessions",
        describe="list_sessions() -> {live: [...], parked: [...]}",
        deterministic=False,
        run=lambda args: _make_list_sessions_impl(session_registry, args),
        schema=_LIST_SESSIONS_SCHEMA,
    )


__all__ = [
    "DaemonClient",
    "make_inspect_record",
    "make_list_applications",
    "make_list_records",
    "make_list_sessions",
    "make_list_topologies",
    "make_run_topology",
    "make_run_topology_poll",
]
