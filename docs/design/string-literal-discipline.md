# String-literal discipline

*Draft, 2026-09-02. Standards doc + drift catalog for the substrate repo. Not a spec amendment — this is the working reference the sprint-070 arc will implement against.*

## Philosophy

Every string literal in production code that names a stable identifier — an event kind, a producer kind, a trigger id, a status value, an enum-shaped field value — is a named symbol declared in one place. Call sites reference the symbol, not the literal. The literal appears exactly once: at the declaration.

Two consequences follow. First, a typo in a call site becomes a `NameError` at import time, not a silent-nothing bug at run time. Second, the reader who wants to know every place a kind is compared against greps for the symbol name and finds every one; a literal-string grep would miss a comparison spelled with different quotes or a substring match.

The pattern already ships in `constants.py` (kernel lifecycle kinds — `RUN_STARTED = "substrate.RunStarted"`, etc.) and in `topologies/session/vocabulary.py` (session Struct kind names + PromptSource enum values). Both modules also expose a `frozenset[str]` mirror (`LIFECYCLE_KINDS`, `SESSION_KINDS`) for membership checks. That is the shape to extend everywhere else.

## What counts as drift

A string literal is drift when it satisfies one of these:

1. It compares against a value whose set is closed and named somewhere on the wire (a Struct field, a JSON key, an enum-shaped value).
2. It appears in more than one call site.
3. Its value is defined by a spec, a lock file, or an authoritative doc, and changing it in one place without changing the others would break behavior.

A string literal is NOT drift when:

- It is a one-off error message intended for a human reader.
- It is a format template (`f"USER: {text}"`) where the literal parts are formatting, not identifiers.
- It arrives at the process boundary (client JSON, CLI argv, TOML manifest) and is validated to a typed value in the first function that reads it — after that boundary, code uses the typed value, not the literal.

## Correct Python usages

Four idioms cover every drift class in substrate.

### 1. `enum.StrEnum` for closed sets

Python 3.11+. Instances are strings; `X.MEMBER == "value"` is True; iteration is safe; `X(value)` validates at boundaries and raises on mismatch.

```python
from enum import StrEnum

class SessionEndReason(StrEnum):
    USER_EXIT = "user_exit"
    USER_END = "user_end"
    TIMEOUT = "timeout"
    DAEMON_SHUTDOWN = "daemon_shutdown"
```

Use for closed sets where the full set is known: session end reasons, Park reasons, SessionWarning kinds, session status, workspace shapes, slot kinds. At the wire boundary, validate incoming strings via `SessionEndReason(raw_value)` — mismatch raises `ValueError` with the offending value named. msgspec Struct field types accept StrEnum when the wire format is a string; verify per Struct at migration time.

### 2. `typing.Literal[...]` for type-checked function signatures

No runtime object. mypy `--strict` enforces the value at call sites.

```python
from typing import Literal

def resolve_status(status: Literal["running", "parked", "interrupted", "ended"]) -> ...:
    ...
```

Use when a function accepts one of a small closed set and the caller should know the options without importing an enum. Best when the set is small (three or four values) and the values are already validated upstream — Literal does not run at runtime, so a boundary layer with StrEnum still owns validation.

### 3. Module-level `Final[str]` constants for open-ish sets

Instance-independent typed constants. Immutable by contract (mypy `--strict` flags reassignment).

```python
from typing import Final

MODEL: Final[str] = "model"
TOOL: Final[str] = "tool"
PARK: Final[str] = "park"
SESSION_END: Final[str] = "session_end"

PRODUCER_KINDS: Final[frozenset[str]] = frozenset({MODEL, TOOL, PARK, SESSION_END})
```

Use when a downstream topology might extend the set (producer kinds, trigger ids, tool names). A `frozenset` sibling gives membership checks. Every constant carries `Final` so mypy catches accidental reassignment.

### 4. `Final[str] = "..."` for singletons

Anything that names one thing forever (a hostname, a magic path, a header name).

```python
from typing import Final

DAEMON_HOST: Final[str] = "127.0.0.1"
DAEMON_PORT: Final[int] = 8765
```

## Which idiom for which class

| Class | Idiom | Home |
|---|---|---|
| Session end reason | StrEnum | `topologies/session/vocabulary.py::SessionEndReason` |
| Park reason | StrEnum | `topologies/session/vocabulary.py::ParkReason` |
| SessionWarning kind | StrEnum | `topologies/session/vocabulary.py::SessionWarningKind` |
| SessionManifest status | StrEnum (already partial via `STATUS_*` module consts — promote) | `session_registry.py::SessionStatus` |
| Workspace shape | StrEnum | `session_registry.py::WorkspaceShape` |
| SlotSpec kind | StrEnum | `topologies/applications/registry.py::SlotKind` |
| Session-topology producer kinds | `Final[str]` + frozenset | `topologies/session/vocabulary.py::PRODUCER_KIND_*` (new block) |
| Session-topology trigger ids | `Final[str]` + frozenset | `topologies/session/vocabulary.py::TRIGGER_ID_*` (new block) |
| Tool-loop tool names | `Final[str]` + frozenset | `topologies/tool_loop/tools.py::TOOL_NAME_*` |
| Driver family names | StrEnum (small closed set: deterministic, ollama) | `adapters/__init__.py::DriverFamily` |
| Driver params keys | StrEnum | `adapters/__init__.py::DriverParamKey` |
| CLI target strings | StrEnum | `cli.py::ListTarget` |

## Current usage catalog (drift, per class)

Counts from 2026-09-02 audit of `src/substrate/` (excluding tests, docs, .venv, __pycache__). Grep count of inline `== "string"` or `.get("string")` comparisons: 334. Named-symbol usages of the same values: variable per class.

### 1. Session reason strings — ~40 inline sites

Values: `user_exit`, `user_end`, `timeout`, `daemon_shutdown`, `final_answer`, `model_error`, `interrupt`.

Sites (representative):
- `topologies/session/__init__.py:162, 170, 881, 892, 903, 1004, 1020, 1038-1040` — reason values as literal defaults and as branch keys.
- `topologies/session/ci.py:16, 78` — docstring references (comment-only, low priority).
- `topologies/session/views.py:7` — docstring reference.
- `_daemon.py:180, 277` — `source="user_end"` default.
- `cli.py:1287, 1468` — `source="user_end"` at CLI-side end-session calls.

Named-const home today: **none**. Existing best practice: `constants.py`'s lifecycle-name pattern.

### 2. Producer-kind names — ~60 inline sites

Values: `model`, `tool`, `park`, `session_end`, `session_warning`, `per_turn_fragment`, `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `parent_context_fragment`, `tools_suite_fragment`, `user_message_fragment`, `prompt_composer`, `fragment_error_warning`, `session_started`, `session_open`, `driver_stepper`.

Sites (representative):
- `topologies/session/__init__.py:845, 856, 909, 924, 960` — `_producer_kind_from_ref(ctx) == "model"` predicates.
- Every `b.producer_kind("...", ...)` call in `session_topology` — the registration side names them.
- `session/ci.py`, `session/roles.py`, `session/tools_suite_producer.py`, etc — factory registrations at build time.

Named-const home today: **none**. Sprint 068's `FRAGMENT_SOURCE_KINDS` frozenset covers seven of the seventeen — a partial start.

### 3. Trigger IDs — ~30 inline sites

Values: `resume-on-composed`, `run-tool`, `continue`, `wrap-up`, `park-on-final`, `park-on-model-error`, `park-on-interrupt`, `end-on-exit`, `end-on-cap`, `end-on-user-end`, `emit-per-turn-fragment`, `emit-user-message-fragment`, `compose-on-cohort-complete`, `warn-on-fragment-error`, `advance-on-park`.

Sites: every `b.trigger("...", ...)` call in `session_topology` plus every test that asserts trigger_id membership.

Named-const home today: **none**. Test `tests/test_session_topology_e2e.py:207` currently asserts `{"resume-on-composed", "park-on-final", "end-on-exit", "advance-on-park"} <= trigger_ids` with literal strings — sprint-068 already had to update this once when the trigger renamed. Named constants would have avoided the update.

### 4. SessionWarning.kind values — 10 inline sites

Values: `seed_alone_exceeds`, `bundle_changed`, `fragment_source_failed`.

Sites:
- `topologies/session/__init__.py:685` (factory `kind="seed_alone_exceeds"`), `:469` (factory `kind="fragment_source_failed"`).
- `topologies/session/transcript.py:183` (docstring).
- `substrate-ui/server.py` — any handler that surfaces the warning to the console.
- `tests/test_fragment_source_failure_handling.py:80, 127, 135` — assertions.

Named-const home today: **none**. Only three values; StrEnum is the right idiom.

### 5. Status strings — done (bookkeeping only)

Values: `running`, `parked`, `interrupted`, `ended`.

Named-const home today: `session_registry.py::STATUS_RUNNING`, `STATUS_PARKED`, `STATUS_INTERRUPTED`, `STATUS_ENDED`. **This class is already migrated.** Pattern to preserve. Consider promoting to `SessionStatus(StrEnum)` for the type-checker benefit.

### 6. Driver family names — ~15 inline sites

Values: `deterministic`, `ollama`, `kimi-k2.6:cloud`, `kimi-k2.7-code:cloud`, `claude`.

Sites:
- `substrate-ui/server.py:_daemon_driver_resolver` — string switch on driver name.
- Every test that constructs `session_topology(driver_name="deterministic", ...)`.
- `topologies/session/ci.py:85` — `driver_name="deterministic"`.

Named-const home today: **none**. Split into two idioms: `DriverFamily(StrEnum)` for the two families (`deterministic`, `ollama`) that the resolver dispatches on; specific model tags stay as free-form strings (they're external configuration values, not internal enum-shaped identifiers).

### 7. Slot / config kinds — ~20 inline sites

Values: `prose`, `line`, `bool`, `int`, `choice` (slot kinds); `think`, `max_tokens`, `num_ctx`, `timeout` (driver params).

Sites:
- `topologies/applications/registry.py:_parse_slot_spec` (slot kinds).
- `session_registry.py:568, 587, 591, 595` (driver params keys).

Named-const home today: **none**. Both are closed sets; both are StrEnum candidates.

### 8. CLI target strings — ~10 inline sites

Values: `sessions`, `topologies`, `records`, `applications`.

Sites: `cli.py:1154-1182` — one string-switch block.

Named-const home today: **none**. Small closed set; StrEnum.

### 9. Tool names — ~30 inline sites

Values: `bash`, `edit_file`, `write_file`, `read_file`, `grep`, `inspect_record`, `list_records`, `run_topology`, `list_applications`, `list_sessions`, `list_topologies`, `run_topology_poll`.

Sites: `topologies/tool_loop/tools.py` (registration side); `topologies/tool_loop/substrate_tools.py` (implementations); tests.

Named-const home today: **none**. `Final[str]` per name; `TOOL_NAMES` frozenset for the full set.

## Rules for boundary code

External inputs arrive as arbitrary strings. Substrate's rule at the boundary:

1. The first function that touches an external string maps it to a typed value or refuses.
2. Refusal returns a 400-shaped error naming the offending value.
3. Downstream code sees only typed values.

Example: `POST /api/session` receives `{"driver": "..."}`. The daemon's handler should do `driver = DriverFamily.validate(body["driver"])` at the top; every downstream call takes `driver: DriverFamily`, not `driver: str`. mypy `--strict` catches the drift when any downstream function accepts `str` and should accept the enum.

The Struct fields on the wire stay `str` for msgspec compatibility (StrEnum-typed fields in msgspec may work — verify before committing). Internal Python code that reads a Struct field validates or casts it once, at the read seam.

## Migration shape

Three sprint cards, in order:

- **Sprint 070 — closed-set values move to StrEnum.** SessionEndReason, ParkReason, SessionWarningKind, SessionStatus (promote), WorkspaceShape, SlotKind, DriverFamily, DriverParamKey, ListTarget. Ships one new module or extends existing vocabulary modules with `StrEnum` classes plus their `frozenset` mirrors. Sweeps every call site.
- **Sprint 071 — producer-kind + trigger-id constants.** New identifier blocks in `topologies/session/vocabulary.py` (or a sibling module). Every `b.producer_kind("...", ...)` and `b.trigger("...", ...)` call migrates to the constant. Every predicate that compares `producer.kind == "..."` migrates.
- **Sprint 072 — tool-name constants + boundary-validator sweep.** `TOOL_NAME_*` constants for the tool-loop tools. Every boundary handler in `substrate-ui/server.py` gets a validator that maps incoming strings to typed values or refuses at the seam.

Each sprint closes with `ruff`'s magic-value rule (`PLR2004`) enabled on the file classes it touched, so new inline literals in that class trip pre-commit.

## Non-migration: what stays as string literals

- Error message text intended for human readers (`"role {role!r}: both {path} and {folder}/ ..."`).
- Format templates (f-strings whose literal parts are prose, not identifiers).
- Test setup data that constructs a fixture (e.g., `"MARK-PER-TURN"` in a per_turn test — that IS the fixture value).
- One-off command-line arguments in scripts (`scripts/*.py`) where the value is the command being run.

## Reference: existing patterns worth copying

`src/substrate/constants.py` — the reference for kernel lifecycle names + config defaults. `Final` not yet applied; add it as sprint 070 sweeps.

`src/substrate/topologies/session/vocabulary.py` — the reference for session-topology kind names + PromptSource. Same pattern with a `frozenset` mirror. `is_prompt_source(name)` predicate is the shape for typed boundary checks.

`src/substrate/session_registry.py::STATUS_RUNNING, STATUS_PARKED, STATUS_INTERRUPTED, STATUS_ENDED` — the module-const pattern for the status class. Promote to `SessionStatus(StrEnum)` at migration time; keep the module constants as aliases for backwards compatibility during the sweep.

## Deferred: what this doc does not cover

- `substrate-ui`'s own string discipline (TypeScript side, sprint 070+ span will pick that up separately).
- Log-message text (structured logging is a separate discipline; not in scope here).
- Test-side literals — tests can use literals for the value under test; the discipline applies to production code.

---

*Draft 2026-09-02. Rewrites land as new dated versions per the "no in-place edits" rule.*
