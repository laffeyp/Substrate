# Sprint 054 — move SessionRegistry into substrate

```yaml
---
id: 054
status: open
phase: 7
pass_kind: architectural
---
```

## Product-spec conformance

**Fulfills:** the spec's own naming rule. PRODUCT-SPEC-2026-08-17-round12.md §6 (standing sub-agents) puts every noun on the substrate side: `substrate chat --name reviewer`, `substrate session ls`, `substrate session end <name>`, `substrate session rm <name>`, the session topology at `substrate/topologies/session/`, the manifest at `~/.substrate/sessions/<id>/manifest.json`. The mechanism (product §6 line 296): "the `delegate` tool sees `child_session_name="reviewer"` and routes the task as a UserMessage into the reviewer's live record." Every noun there is a substrate concept.

TECH-SPEC-2026-08-25-round6.md §5 ("Piece C — named standing sessions") describes the same mechanism and names the seam as `session_registry.by_name(name)` + `session_registry.turn_sync(session_id, resume_event)`. The spec does not say which repo owns the registry. Today it lives in `substrate-ui/session_registry.py`. This card moves it to substrate where the concept belongs.

**Consumes:** nothing new. The move re-parents an existing implementation; behaviour is preserved.

## Motivation (why now)

The current split leaves three visible signals of architectural drift:

1. `src/substrate/topologies/tool_loop/delegate.py::make_delegate` types `session_registry: Any` — the parameter cannot be typed correctly because the concrete class lives on the wrong side of the F-API-6 boundary.
2. Same file, path 1 exception handling: `if type(exc).__name__ == "SessionEndedMidTurn": raise ValueError(...)` — a duck-typed catch by class name string because the exception class cannot be imported (F-API-6 forbids substrate importing substrate-ui).
3. Tests split by which repo can `import SessionRegistry`. Standing-session live tests must live in substrate-ui/tests/, breaking the "tests live with the code" convention for the substrate side of the wire.

Every one of those three shapes is what the drift looks like on disk. The wire is telling us the concept is on the wrong side of the boundary.

## Scope

Move the SessionRegistry primitive into substrate. Substrate-ui adopts it. The daemon's process-boundary responsibilities (HTTP, SSE, cross-process invariants) stay in substrate-ui. Nothing in the daemon's user-visible behaviour changes.

Decomposed into four phases, each landable independently. Halt-and-articulate between phases if the shape shifts.

### Phase A — introduce the substrate-side registry, no consumer change

Add `src/substrate/session_registry.py` alongside `topologies/session/`. Its public surface matches the current substrate-ui SessionRegistry's shape 1:1: `create`, `get`, `by_name`, `list_all`, `turn_sync`, `end`, `remove`. Plus the exception `SessionEndedMidTurn`. Plus the manifest struct `SessionManifest`.

The substrate-side registry keeps state on disk at a caller-supplied `base: Path` (matches current signature) — no assumption about `~/.substrate/sessions/`. In-process locking is `threading.Lock` per session_id (matches current). No HTTP, no asyncio loop scheduling — those are the daemon's concerns.

Test at substrate side: `tests/test_session_registry_core.py` — unit tests covering the manifest lifecycle, by_name uniqueness, per-session lock serialisation, on-disk manifest survival across `SessionRegistry` instances.

Nothing else changes yet. Substrate-ui keeps its own copy; nothing consumes the new one. This is a non-breaking add.

### Phase B — substrate-ui adopts the substrate-side registry

`substrate-ui/session_registry.py` becomes a thin subclass of `substrate.session_registry.SessionRegistry` that adds daemon-specific concerns:

- HTTP-shaped payload validation delegated back to the base class.
- SSE stream registration alongside `turn_sync`.
- Cross-process file lock for the by-name map (the base uses in-process only).
- Whatever the daemon's `server.py` currently touches directly.

The existing `substrate-ui/session_registry.py` MODULE surface stays imported from the same path — `from session_registry import SessionRegistry, SessionManifest` still resolves. The class inherits from substrate's; every existing method still works. All 24 tests in substrate-ui/tests/ that touch SessionRegistry continue to pass without changes.

### Phase C — delegate.py drops the duck-typing hacks

Two edits in `src/substrate/topologies/tool_loop/delegate.py`:

- Change `session_registry: Any = None` to `session_registry: SessionRegistry | None = None`. Import the class from `substrate.session_registry`. Type errors flushed to correct.
- Replace `if type(exc).__name__ == "SessionEndedMidTurn":` with a real `except SessionEndedMidTurn:` (imported). Drop the comment about F-API-6 needing the duck-typed catch — no longer true.

Substrate's `test_delegate_per_call_child_session_name.py` grows a real registry fixture (was: raises when None; now: routes through a real registry, no more daemon dependency).

### Phase D — the standing-session live test moves back to substrate

`substrate-ui/tests/test_realmodel_delegate_standing.py` (sprint 053) moves to `substrate/tests/test_realmodel_delegate_standing.py`. The reviewer + parent shape is unchanged; only the import path shifts.

Substrate-ui's `test_delegate_via_standing_session.py` (the pre-existing unit test) stays where it is — it exercises daemon-shaped features (HTTP flow, SSE) that phase B kept on the daemon side. Rename its docstring so the split reads clearly: unit tests for the DAEMON's session flow stay in substrate-ui; unit tests for the REGISTRY's own contract live in substrate.

## Prerequisites

- Sprint 053 (live standing-session test, delegate MappingProxyType fix) — landed.
- Sprint 049 (delegate + substrate-tools Mapping widening) — landed.
- No unfinished dependents on `substrate-ui/session_registry.SessionRegistry` beyond what's grep-visible today.

## Context files

Substrate side:
- `src/substrate/topologies/tool_loop/delegate.py` — path 1 at 437-521; construction args at 333-355; the two hacks (`session_registry: Any` at 348 area; exception catch at 493 area).
- `src/substrate/topologies/session/__init__.py` — the session topology itself, unchanged by this move.
- `tests/test_delegate_per_call_child_session_name.py` — the raise-without-registry unit; extend in phase C.

Substrate-ui side:
- `substrate-ui/session_registry.py` — the whole file. Public surface: `SessionRegistry` class, `SessionManifest` struct, `SessionEndedMidTurn` exception, roughly 800 lines. Phase A copies the core; phase B keeps a thin subclass.
- `substrate-ui/server.py` — every consumer of `SessionRegistry`. Grep for `session_registry.` and `SessionRegistry(`. Should all continue to work without change once phase B lands.
- `substrate-ui/tests/test_delegate_via_standing_session.py` — the daemon-side unit test. Docstring rename in phase D.
- `substrate-ui/tests/test_realmodel_delegate_standing.py` — moves to substrate side in phase D.

## Artifact contract → Files created / modified

Phase A:
- `src/substrate/session_registry.py` — NEW. The core registry + manifest + exception.
- `tests/test_session_registry_core.py` — NEW. Unit contract.

Phase B:
- `substrate-ui/session_registry.py` — refactored to `class SessionRegistry(substrate.session_registry.SessionRegistry):`. Body shrinks by the amount that moved.

Phase C:
- `src/substrate/topologies/tool_loop/delegate.py` — `session_registry: SessionRegistry | None`, real exception catch. Duck-typing comment removed.
- `tests/test_delegate_per_call_child_session_name.py` — add a case that instantiates a real registry and asserts path 1 routes correctly (previously only the raise-without-registry case existed).

Phase D:
- `tests/test_realmodel_delegate_standing.py` — moved from substrate-ui.
- `substrate-ui/tests/test_realmodel_delegate_standing.py` — deleted.
- `substrate-ui/tests/test_delegate_via_standing_session.py` — docstring rename to reflect the new split.

## Signal contract → Emits

None. This is a re-parenting sprint; no new events or tags.

Vocabulary check: SessionRegistry manifest fields (session_id, name, driver, workspace, workspace_shape, bundle, status, record_root, seed, created_at) all stay identical. No signal-vocab bump.

## Observation contract

**After Phase A:**
- `uv run python -m pytest tests/test_session_registry_core.py -v` → PASS (new unit tests).
- Every existing substrate test still green (nothing consumes the new module yet).
- Every existing substrate-ui test still green (its own registry unchanged).

**After Phase B:**
- Every existing substrate-ui test still green — `from session_registry import SessionRegistry` still resolves; every consumer still works.
- New assertion in `tests/test_session_registry_core.py`: substrate-ui's SessionRegistry is a subclass of substrate's. Type check plus one behaviour test that isinstance holds.
- Server smoke: bring the daemon up, open a session, POST a turn, verify the record grows. Nothing in the user-visible flow changed.

**After Phase C:**
- `tests/test_delegate_per_call_child_session_name.py` — the extended test passes; the delegate routes through a real registry, ok=True, standard {answer, child_root, steps, via} shape.
- `uv run mypy src/substrate` — 122 files, zero errors, `session_registry: SessionRegistry | None` types cleanly.
- Grep for `type(exc).__name__ == "SessionEndedMidTurn"` in `src/substrate/` — zero hits (was one).

**After Phase D:**
- `uv run python -m pytest tests/test_realmodel_delegate_standing.py -v` → PASS live (3 consecutive runs, matching sprint 053's reliability probe).
- The substrate-ui version is gone; grep confirms.
- The substrate-ui daemon flow test still passes.

**Overall (after all four phases):**
- Full pytest across both repos: green.
- All three drift signals gone (typed argument, real exception catch, standing test on the substrate side).

## Halt conditions

- `spec_ambiguity` if the SessionRegistry public surface has behaviour that only makes sense with a daemon around it (HTTP endpoint side effects, SSE registration, cross-process behaviours). Named methods to audit at phase-A start: `turn_sync` (may bind to an SSE broadcaster today), `create` (may write to a by-name map that shares a lock with a HTTP handler). If any surface is entangled with daemon-only concerns, phase A stops and articulates before writing the substrate-side version.

- `dual_contract_fail` if a substrate-ui test that used to pass fails after phase B. That means the subclass split did not preserve semantics.

- `bridge_mapping_required` if `SessionManifest` (the msgspec Struct) is imported by any substrate-ui-owned code that depends on daemon-only fields. Audit before phase A: `grep -rn "SessionManifest" substrate-ui/`.

- `vocab_change_required` if the manifest fields need to shift to make the split clean. Should not happen (sprint 054 is re-parenting, not shape change); if it does, halt and articulate to the Architect.

## Definition of done

SessionRegistry primitive lives in substrate. Substrate-ui inherits the class and adds daemon-shaped concerns. Every user-visible test (including the live standing-session probe) still passes. Every visible drift signal — the `Any`-typed argument, the class-name string exception catch, the standing test on the wrong side of the boundary — is closed.

The library owns the concept. The product wraps the process boundary. Clean.

## Non-goals

- No new features. Zero changes to the delegate mechanism's four dispatch paths. Zero changes to the session topology itself. Zero changes to product-user-visible commands (`substrate chat`, `substrate session ls`, etc.).
- No signal-vocab bump. This is not a v0.4 → v0.5 sprint.
- No move of daemon-shaped concerns (HTTP handlers, SSE) into substrate. Those stay on the product side by design.
- No refactor of `delegate.py`'s four dispatch paths (path 1 wire is what moves cleaner; paths 2/3/4 stay identical).

## Sequence

Phase A → B → C → D. Each phase landable and reviewable independently. A halt-and-articulate at any phase boundary if the shape shifts.

Estimated size: A is ~800 line copy + ~200 line test; B is refactor-and-shrink of substrate-ui/session_registry.py (net −600 lines expected); C is two edits in delegate.py plus one test extension; D is a file move + one docstring rename. Total ≤ 3 focused work sessions.
