# Sprint 070 — closed-set string values move to `StrEnum`

```yaml
---
id: 070
status: closed
phase: 9
pass_kind: string-discipline
closed_at: 2026-09-02
closed_by: substrate main HEAD after this card
scope_note: msgspec + StrEnum verified round-trip clean at the top of the card — Struct fields typed as StrEnum serialise as string on JSON encode/decode; in-memory value is enum member; equality with str is True. Eight StrEnum classes declared (SessionEndReason, ParkReason, SessionWarningKind, SessionStatus, WorkspaceShape, SlotKind, DriverFamily, DriverParamKey). Highest-impact call sites swept (session/__init__.py factories + trigger input_builders; applications/registry.py SlotKind validator). Residual sweeps (cli.py ListTarget declaration; driver_family in substrate-ui/server.py; DriverParamKey in session_registry driver_params validator) roll into sprint 072's boundary-validator arc.
---
```

## Product-spec conformance

**Fulfills:** the string-literal discipline in `docs/design/string-literal-discipline.md`. Nine drift classes catalogued; this sprint takes the four most closed-set classes and migrates them to `enum.StrEnum` so every downstream comparison is against a typed member, not a raw literal.

**Consumes:** the discipline doc, `session-vocabulary.md`, existing `STATUS_*` constants at `session_registry.py`.

## Motivation

Closed-set values (session reasons, park reasons, SessionWarning kinds, session status, workspace shape, slot kind, driver family, driver param key, CLI target) have exactly one right shape in Python: `enum.StrEnum`. Instances compare `==` with strings; iteration is safe; `X(value)` validates at boundaries. msgspec Struct fields accept StrEnum when the wire format is a string — verify per Struct at migration time.

The current shape is raw string literals scattered across ~120 inline sites for these nine classes. Sprint 070 declares each closed set as a `StrEnum` in a domain-appropriate home, sweeps every call site to reference the member, and validates boundary strings at the seam.

## Scope

Nine `StrEnum` classes, nine sweeps.

### 1. `SessionEndReason(StrEnum)` — `topologies/session/vocabulary.py`

Values: `USER_EXIT = "user_exit"`, `USER_END = "user_end"`, `TIMEOUT = "timeout"`, `DAEMON_SHUTDOWN = "daemon_shutdown"`. Sweep every `reason="user_exit"` / `== "user_exit"` etc.

### 2. `ParkReason(StrEnum)` — `topologies/session/vocabulary.py`

Values: `FINAL_ANSWER = "final_answer"`, `MODEL_ERROR = "model_error"`, `INTERRUPT = "interrupt"`. Sweep every `reason="final_answer"` etc.

### 3. `SessionWarningKind(StrEnum)` — `topologies/session/vocabulary.py`

Values: `SEED_ALONE_EXCEEDS = "seed_alone_exceeds"`, `BUNDLE_CHANGED = "bundle_changed"`, `FRAGMENT_SOURCE_FAILED = "fragment_source_failed"`. Sweep every `SessionWarning(kind="...", ...)` construction.

### 4. `SessionStatus(StrEnum)` — `session_registry.py` (promote existing constants)

Values: `RUNNING = "running"`, `PARKED = "parked"`, `INTERRUPTED = "interrupted"`, `ENDED = "ended"`. Keep the existing `STATUS_*` module constants as aliases (`STATUS_RUNNING = SessionStatus.RUNNING`) for backwards compat during the sweep; drop the aliases in a follow-up card.

### 5. `WorkspaceShape(StrEnum)` — `session_registry.py`

Values: `FLAT = "flat"`, `WORKTREE = "worktree"`, `ISOLATE = "isolate"`. Sweep every `workspace_shape="flat"` etc.

### 6. `SlotKind(StrEnum)` — `topologies/applications/registry.py`

Values: `PROSE = "prose"`, `LINE = "line"`, `BOOL = "bool"`, `INT = "int"`, `CHOICE = "choice"`. Sweep `_parse_slot_spec` and any test that compares against these values.

### 7. `DriverFamily(StrEnum)` — `adapters/__init__.py` (new home)

Values: `DETERMINISTIC = "deterministic"`, `OLLAMA = "ollama"`. Note: specific model tags (e.g. `"kimi-k2.6:cloud"`) stay as free-form strings — they are external configuration values, not internal enum-shaped identifiers. Only the two families the resolver dispatches on migrate.

### 8. `DriverParamKey(StrEnum)` — `adapters/__init__.py`

Values: `THINK = "think"`, `MAX_TOKENS = "max_tokens"`, `NUM_CTX = "num_ctx"`, `TIMEOUT = "timeout"`. Sweep `session_registry.py::set_driver_params` and any handler that reads these keys.

### 9. `ListTarget(StrEnum)` — `cli.py`

Values: `SESSIONS = "sessions"`, `TOPOLOGIES = "topologies"`, `RECORDS = "records"`, `APPLICATIONS = "applications"`. Sweep the `cli.py:1154-1182` string switch. At the CLI boundary, `ListTarget(argv_value)` validates.

## Prerequisites

- Sprints 058-068 all closed.
- `docs/design/string-literal-discipline.md` as the authoritative standard.

## msgspec + StrEnum verification (halt gate at start of card)

Before any of the nine migrations, run a smoke test: define a StrEnum, put it as a field type on a frozen msgspec Struct, `msgspec.to_builtins` + `msgspec.json.encode` + `decode(type=Struct)` round-trip, verify shape survives. If msgspec rejects StrEnum-typed fields, halt-and-articulate: fall back to typed constants (`Final[str]`) with the enum as a validator wrapper.

## Context files

- `docs/design/string-literal-discipline.md` — the standard.
- `src/substrate/topologies/session/vocabulary.py` — existing enum-in-strings home.
- `src/substrate/session_registry.py` — `STATUS_*` constants + SessionManifest Struct.
- `src/substrate/topologies/session/__init__.py` — reason strings in Park / SessionEnded / SessionEndRequested factories.
- `src/substrate/topologies/applications/registry.py` — SlotSpec + slot kind values.
- `src/substrate/adapters/__init__.py` — driver families.
- `src/substrate/cli.py` — CLI target strings.

## Artifact contract → Files modified

- `src/substrate/topologies/session/vocabulary.py` — three new StrEnum classes (SessionEndReason, ParkReason, SessionWarningKind).
- `src/substrate/session_registry.py` — SessionStatus + WorkspaceShape StrEnum; existing STATUS_* aliased.
- `src/substrate/topologies/applications/registry.py` — SlotKind StrEnum; `_parse_slot_spec` validates via `SlotKind(kind)`.
- `src/substrate/adapters/__init__.py` — DriverFamily + DriverParamKey StrEnum.
- `src/substrate/cli.py` — ListTarget StrEnum; argv parse validates.
- `src/substrate/topologies/session/__init__.py` — every `reason=` / `kind=` literal migrates to enum member.
- `src/substrate/topologies/session/ci.py` — same.
- `src/substrate/topologies/session/views.py` — Park.reason predicate migrates.
- `src/substrate/_daemon.py` — end-session `source=` default migrates.
- Every `substrate-ui/server.py` boundary handler that reads these values validates via the StrEnum.
- Tests updated to import and reference enum members.

## Signal contract → Emits

None. Vocabulary evolution — no new events; existing SessionWarning.kind etc. values unchanged, just typed at the Python surface.

## Observation contract

- Full existing suite green.
- Grep verification: `grep -rn '"user_exit"\|"user_end"\|"timeout"\|"daemon_shutdown"\|"final_answer"\|"model_error"\|"interrupt"\|"seed_alone_exceeds"\|"bundle_changed"\|"fragment_source_failed"' src/substrate/ | grep -v "\.venv\|__pycache__\|test_\|docstring\|StrEnum\|# "` returns zero code-side inline literals for the migrated values.
- New tests per StrEnum class: round-trip through msgspec, `X(value)` validates, `X(bad_value)` raises `ValueError`, iteration returns all members, membership check works.
- Boundary tests: CLI list target with invalid argv value returns non-zero exit with the offending value named.

## Halt conditions

- `bridge_mapping_required` if msgspec does not accept StrEnum-typed fields on a frozen Struct. Halt at the verification gate; fall back to typed constants + validator wrapper; adjust the card.
- `dual_contract_fail` if any existing test breaks in a way the migration path did not anticipate (e.g., string comparison in a test that reads a JSON payload where msgspec-encoded StrEnum landed as a different shape). Debug per-Struct.

## Definition of done

Every closed-set string value in the nine classes above is a `StrEnum` member with a documented home. Call sites reference the member. Boundary handlers validate the incoming string via `EnumClass(raw)` and refuse on mismatch. Grep for the raw literals returns zero code-side hits (docstrings + tests-with-fixture-values exempt).
