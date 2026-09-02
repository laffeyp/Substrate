# Sprint 072 — tool-name constants + boundary-validator sweep

```yaml
---
id: 072
status: closed
phase: 9
pass_kind: string-discipline
closed_at: 2026-09-02
closed_by: substrate main HEAD after this card
scope_note: eighteen TOOL_NAME_* Final[str] constants + TOOL_NAMES frozenset in topologies/tool_loop/tools.py. Sweep of every Tool(...) ctor first-arg + every `if tool ==` predicate in agency.py. Boundary-validator sweep DEFERRED to a follow-up sprint 073 — CLI ListTarget declaration + validation, DriverFamily validation in substrate-ui/server.py boundary handlers, DriverParamKey use in session_registry driver_params validator all remain drift.
---
```

## Product-spec conformance

**Fulfills:** string-literal discipline drift class 9 (tool names, ~30 sites) + the boundary rule from § "Rules for boundary code". Ships the last remaining named-symbol block for the substrate-side tool suite AND enforces the "validate at the seam" pattern on every daemon handler that reads a class-migrated value (from sprints 070-071) off the wire.

**Consumes:** sprints 070 (StrEnum classes) + 071 (producer/trigger constants). This card closes the arc.

## Motivation

Two remaining threads. First: tool names (`bash`, `edit_file`, `read_file`, `grep`, `inspect_record`, `list_records`, `run_topology`, etc.) — same drift class as producer kinds but with a longer sprawl across `tool_loop/tools.py`, `tool_loop/substrate_tools.py`, and every test. Second: boundary validation. Sprints 070-071 declared the typed shapes; sprint 072 makes sure every place an external string (client JSON body, CLI argv, TOML manifest) enters substrate is mapped to the typed value at that seam. Downstream code sees only typed values; mypy `--strict` catches drift when a downstream function forgets to migrate.

## Scope

Two blocks + a boundary sweep + `ruff` rule enablement.

### Tool-name constants

```python
# topologies/tool_loop/tools.py — additions
from typing import Final

TOOL_NAME_BASH: Final[str] = "bash"
TOOL_NAME_EDIT_FILE: Final[str] = "edit_file"
TOOL_NAME_WRITE_FILE: Final[str] = "write_file"
TOOL_NAME_READ_FILE: Final[str] = "read_file"
TOOL_NAME_GREP: Final[str] = "grep"
TOOL_NAME_DELEGATE: Final[str] = "delegate"

# Substrate tools (topologies/tool_loop/substrate_tools.py — kept there or lifted)
TOOL_NAME_INSPECT_RECORD: Final[str] = "inspect_record"
TOOL_NAME_LIST_RECORDS: Final[str] = "list_records"
TOOL_NAME_LIST_SESSIONS: Final[str] = "list_sessions"
TOOL_NAME_LIST_TOPOLOGIES: Final[str] = "list_topologies"
TOOL_NAME_LIST_APPLICATIONS: Final[str] = "list_applications"
TOOL_NAME_RUN_TOPOLOGY: Final[str] = "run_topology"
TOOL_NAME_RUN_TOPOLOGY_POLL: Final[str] = "run_topology_poll"

TOOL_NAMES: Final[frozenset[str]] = frozenset({...all above...})
```

Sweep: every `Tool("bash", ...)` registration, every `if name == "grep": ...` predicate, every test that names a tool by string literal.

### Boundary-validator sweep

Every handler in `substrate-ui/server.py` and every CLI entry in `src/substrate/cli.py` that reads a string from an external source (JSON body, argv, TOML) validates via the enum / constant at the top of the function. Downstream signatures take the typed value.

Representative handlers to audit:

- `POST /api/session` — `driver`, `workspace_shape`, `bundle`, `role`. Validate each: `DriverFamily(body["driver"])`, `WorkspaceShape(body["workspace_shape"])`, etc.
- `PATCH /api/session/<id>` — `driver`, `driver_params` keys.
- `POST /api/session/<id>/end` — `source` value validated to `SessionEndReason`.
- `POST /api/topology/<name>/run` — `runs` field validated (already partially; formalise).
- CLI `list <target>` — `ListTarget(argv_value)`.
- CLI `chat --driver-family=...` — DriverFamily validation.

Every validator refusal returns a 400 (server) or non-zero exit (CLI) with the offending value named.

### ruff rule enablement

Enable `PLR2004` (magic-value comparisons) in `pyproject.toml` scoped to the files sprints 070-072 touched. New drift in those files trips pre-commit. Extending the rule to the whole repo is a follow-up.

## Prerequisites

- Sprints 070 + 071 both closed.

## Context files

- `docs/design/string-literal-discipline.md` — § "Rules for boundary code" is the authority for the validator sweep.
- `src/substrate/topologies/tool_loop/tools.py` — CALCULATOR + full_suite Tool registrations.
- `src/substrate/topologies/tool_loop/substrate_tools.py` — substrate tools.
- `substrate-ui/server.py` — every JSON-body handler.
- `src/substrate/cli.py` — every argv entry point.

## Artifact contract → Files modified

- `src/substrate/topologies/tool_loop/tools.py` — TOOL_NAME_* constants + TOOL_NAMES frozenset.
- `src/substrate/topologies/tool_loop/substrate_tools.py` — substrate tool_name constants.
- `substrate-ui/server.py` — validator top-of-handler for every boundary read.
- `src/substrate/cli.py` — same for every argv entry.
- `pyproject.toml` — enable `PLR2004` scoped to the string-discipline-migrated files.
- Tests updated to reference named tool constants.

## Signal contract → Emits

None. Wire strings unchanged.

## Observation contract

- Full suite green.
- Grep verification: `grep -rn '"bash"\|"edit_file"\|"read_file"\|"grep"\|"inspect_record"\|"list_records"\|"run_topology"\|...' src/substrate/topologies/tool_loop/ | grep -v "tools\.py:.*Final\|test_\|# "` returns zero literal tool names outside the declaration.
- Boundary tests: each daemon handler + CLI entry that reads a class-migrated value shows a validation error with the offending value named when the wire value does not match.
- ruff run passes on the migrated files with `PLR2004` enabled.

## Halt conditions

- `bridge_mapping_required` if any Tool registration uses the name as part of a computed value (e.g., a helper that builds tool sets by name prefix). Case-by-case: the constants stay, the helper reads the constant.
- `dual_contract_fail` if a boundary handler's validator refuses a value that the pre-migration code silently accepted (probably a legitimately-open field the sprint migrated too aggressively). Revert the specific validator; open a mini-card.

## Definition of done

Every tool name is a `Final[str]` constant with a frozenset mirror. Every boundary handler validates its external-string inputs at the seam. Downstream signatures take typed values. ruff `PLR2004` runs on the migrated files. Grep finds zero drifted literals in the arc's scope.

The string-literal discipline arc (sprints 070-072) closes here. Every drift class from `docs/design/string-literal-discipline.md`'s catalog either has a named-symbol home or is documented as intentional non-migration (§ "Non-migration").
