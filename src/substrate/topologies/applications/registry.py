# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Application registry — scan `applications/*.manifest.toml` at daemon boot.

TECH-SPEC §7.6 (round 6) locks the flat manifest shape: one
`<name>.manifest.toml` next to each application module, parsed at boot,
served by the daemon at `GET /api/applications`. The daemon reads the
`[inputs]` schema at `POST /api/topology/<name>/run` and resolves each
`<role>_model` value into a Responder via the same registry
`_agent_models` uses (spec line 1038).

`load_manifests()` returns `{name: ApplicationSpec}`. An empty
applications directory returns `{}` — a fresh install has no crash
surface. A malformed manifest raises `ManifestError` naming the file
and the parse failure; the daemon catches and logs, then boots without
that entry.
"""

from __future__ import annotations

import tomllib
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from msgspec import Struct


class ManifestError(Exception):
    """A manifest file exists but does not parse or does not carry the
    required fields. Carries the file path and the underlying cause."""

    def __init__(self, path: Path, cause: str) -> None:
        super().__init__(f"application manifest at {path}: {cause}")
        self.path = path
        self.cause = cause


class SlotSpec(Struct, frozen=True):
    """Sprint 230: one entry in a manifest's `[slots]` block per §9.

    `kind`: `"prose" | "line" | "bool" | "int" | "choice"`.
    `required`: `True` marks the slot as mandatory for the topology; the
    consumer that reads a `SlotSpec` decides how to enforce (the previous
    `bind_slots` binder was deleted in sprint 065 alongside the rest of
    the dead prompt-composition machinery; the type stays as a shape
    declaration until a real consumer surfaces).
    `default`: a literal (bool, int, str), the marker `"bundle:<field>"`
    (falls back to the loaded bundle's field), or `"none"`.
    `choices`: for `kind = "choice"`, the tuple of allowed values.
    """

    kind: str
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()


def _parse_slot_spec(raw: Any, slot_name: str, path: Path) -> SlotSpec:
    if not isinstance(raw, dict):
        raise ManifestError(path, f"[slots].{slot_name} must be a table")
    kind = str(raw.get("kind", "prose"))
    if kind not in ("prose", "line", "bool", "int", "choice"):
        raise ManifestError(
            path, f"[slots].{slot_name}.kind must be prose|line|bool|int|choice; got {kind!r}"
        )
    choices_raw = raw.get("choices") or ()
    if kind == "choice" and not choices_raw:
        raise ManifestError(path, f"[slots].{slot_name}: kind='choice' requires `choices`")
    return SlotSpec(
        kind=kind,
        required=bool(raw.get("required", False)),
        default=raw.get("default"),
        choices=tuple(str(v) for v in choices_raw)
        if isinstance(choices_raw, (list, tuple))
        else (),
    )


class ApplicationSpec(Struct, frozen=True):
    """One parsed manifest. Fields match TECH-SPEC §7.6 line 1044.

    - `name`: registry key + `POST /api/topology/<name>/run` slot.
    - `description`: one-line human summary.
    - `runs`: `"one-shot"` | `"session"` | `"session_composite"`.
    - `inputs_schema`: `[inputs]` verbatim.
    - `output_kind`: `[output].kind`.
    - `default_bundle`: optional bundle name for piece-H binding.
    - `slots`: parsed `[slots]` block — every value is a `SlotSpec`
      per sprint 230 (was `dict[str, Any]` in sprint 223; the round-6
      spec always wanted typed slots but 223 punted until 230 shipped
      the binding algorithm).
    """

    name: str
    description: str
    runs: str
    inputs_schema: dict[str, Any]
    output_kind: str
    default_bundle: str | None
    slots: dict[str, "SlotSpec"]


_REQUIRED_TOP_LEVEL_KEYS = frozenset({"name", "description", "runs"})


def _parse_one(path: Path) -> ApplicationSpec:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(path, f"TOML parse failed: {exc}") from exc
    except OSError as exc:
        raise ManifestError(path, f"could not read: {exc}") from exc
    missing = _REQUIRED_TOP_LEVEL_KEYS - set(raw)
    if missing:
        raise ManifestError(path, f"missing top-level keys: {sorted(missing)}")
    name = raw["name"]
    if not isinstance(name, str) or not name:
        raise ManifestError(path, "`name` must be a non-empty string")
    runs = raw["runs"]
    # Sprint 225c added `session_composite` for apps that open two or more
    # related sessions together (e.g. pair_coding — a builder + a
    # standing reviewer sub-agent). Sprint 225b's cascade lifecycle ties
    # them together via SessionManifest.composite_of.
    if runs not in ("one-shot", "session", "session_composite"):
        raise ManifestError(
            path,
            f"`runs` must be 'one-shot' | 'session' | 'session_composite'; got {runs!r}",
        )
    inputs_schema = raw.get("inputs", {})
    if not isinstance(inputs_schema, dict):
        raise ManifestError(path, "`[inputs]` must be a table")
    output_block = raw.get("output", {})
    if not isinstance(output_block, dict):
        raise ManifestError(path, "`[output]` must be a table")
    output_kind = str(output_block.get("kind", "text"))
    default_bundle = raw.get("default_bundle")
    if default_bundle is not None and not isinstance(default_bundle, str):
        raise ManifestError(path, "`default_bundle` must be a string or absent")
    slots_raw = raw.get("slots", {})
    if not isinstance(slots_raw, dict):
        raise ManifestError(path, "`[slots]` must be a table")
    slots = {name: _parse_slot_spec(spec, name, path) for name, spec in slots_raw.items()}
    return ApplicationSpec(
        name=name,
        description=str(raw["description"]),
        runs=runs,
        inputs_schema=inputs_schema,
        output_kind=output_kind,
        default_bundle=default_bundle,
        slots=slots,
    )


def load_manifests(
    root: Path | None = None, *, on_error: str = "skip"
) -> dict[str, ApplicationSpec]:
    """Scan `<root>/*.manifest.toml`; parse each; return `{name: spec}`.

    `root` defaults to the installed `substrate.topologies.applications`
    directory via `importlib.resources.files`. A caller can pass an
    absolute path for tests or for a per-install override.

    `on_error`:
      - `"skip"` (default): a malformed manifest is skipped; the
        rest load. The daemon logs and boots without that entry. This
        matches the "no crash surface at boot" invariant.
      - `"raise"`: the first `ManifestError` propagates. Useful for
        tests that assert on the failure shape.
    """
    if root is None:
        package_root = files("substrate.topologies.applications")
        with as_file(package_root) as materialised:
            return _scan(Path(materialised), on_error=on_error)
    return _scan(root, on_error=on_error)


def _scan(root: Path, *, on_error: str) -> dict[str, ApplicationSpec]:
    specs: dict[str, ApplicationSpec] = {}
    if not root.is_dir():
        return specs
    for manifest_path in sorted(root.glob("*.manifest.toml")):
        try:
            spec = _parse_one(manifest_path)
        except ManifestError:
            if on_error == "raise":
                raise
            continue
        specs[spec.name] = spec
    return specs


def spec_to_wire(spec: ApplicationSpec) -> dict[str, Any]:
    """Serialize one spec for `GET /api/applications`. Matches the response
    shape at TECH-SPEC §7.6 line 1044: `{name, description, inputs_schema,
    output_kind, runs}` — `slots` and `default_bundle` are excluded from
    the wire response by design (they are internal to the registry's
    binding step, not visible to a caller browsing the app catalog)."""
    return {
        "name": spec.name,
        "description": spec.description,
        "runs": spec.runs,
        "inputs_schema": spec.inputs_schema,
        "output_kind": spec.output_kind,
    }


__all__ = [
    "ApplicationSpec",
    "ManifestError",
    "SlotSpec",
    "load_manifests",
    "spec_to_wire",
]
