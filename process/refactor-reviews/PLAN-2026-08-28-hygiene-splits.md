# PLAN — hygiene splits for the oversized modules

**Author:** Claude session 2026-08-28.
**Companion to:** `REVIEW-2026-08-28-code-quality.md` (findings Q2, Q3, Q10, Q11, plus F6 from the SDD review).
**Scope:** every non-test module that has grown past the point where per-sprint sweet-spot discipline can hold it. Five modules; one cross-cutting primitive extraction. This is a plan, not a set of edits — nothing lands until Architect ratification.

Read against: `sdd-kit-2/AGENTS.md` hard rules 6/7/12; `TECHNIQUES.md` #43 (refactor as chain of behavior-preserving sprints), #44 (SEARCH/REPLACE edits preserve accreted detail), #45 (deprecation entries instead of removals); `foundations/01-signal-driven-development.md` (the vocabulary is architecture); `WORKING_AGREEMENT.md ## Canonical home registry`; PEP 8 (module layout), PEP 20 (Zen — flat, explicit, one-obvious-way), PEP 257 (docstrings), Fowler *Refactoring* second edition on Extract Class / Extract Function / Move Method.

---

## Preface — Python best practice read through SDD and substrate

Python best practice on module shape is not folklore. The regularities are:

- **A module is one concept.** PEP 20's "flat is better than nested" is a corollary of this, not a competing rule. A 2,000-line module carrying eight concerns has a package hiding inside it. The refactor is to name each concern and let it become a file.
- **A class is a data + behavior bundle with a single responsibility.** Fowler's Extract Class rule of thumb: if you can name a coherent subset of a class's fields and methods that would work together outside it, that subset is a class. `SessionRegistry` (Q3) has three coherent subsets.
- **Composition over inheritance for orchestration; inheritance only when the "is-a" survives every method.** `BaseHTTPRequestHandler` subclassing is the one honest use of inheritance in `server.py`; every other cross-cutting concern (auth, error shaping, JSON parse, registry-availability guard) wants composition or middleware, not more methods on the handler.
- **Public surface small; private surface deep.** PEP 8 leading-underscore is the discipline. `substrate.api` is the load-bearing example — one module re-exports the surface every external user is meant to import. Every module below it should have the same shape.
- **Import inside function only when circular imports demand it or the import is expensive enough that laziness is the point.** Ten delayed imports across delegate/registry/cli/server say the module graph has a cycle. The cycle wants a `types.py` at the seam.

SDD reads these through the vocabulary-as-contract lens. The specific corollaries:

- **A module boundary is a vocabulary boundary.** `session_topology` is one vocabulary (eight Structs); `session_registry` is another (SessionManifest, SessionStatus, SessionEndedMidTurn); the daemon's HTTP surface is a third (wire shapes). Each vocabulary's owning module is its canonical home. Cross-vocabulary references travel through explicit imports at the top of the file, not lazy imports mid-function.
- **The dual contract survives the split.** For every existing sprint's observation contract that hits a moved surface, the same contract must pass after the move. TECHNIQUE #43 says this explicitly: "same dual-contract outcomes before and after."
- **The audit trail is the work.** No deletions. Rule 12. A split is additive: the new files land; the old file becomes a re-export shim that keeps every existing import working; a follow-up sprint (a *release later*) removes the shim once the ecosystem has moved.
- **Sprint sweet spot is ≤2 files / one concept.** A split is a *chain*, not one sprint. Estimating each chain's length is half the plan.

Substrate's own architecture adds one more rule:

- **The kernel is small and stable; the application surface may grow, but growth wants a package, not a file.** `kernel/` is a package (runtime, sequencer, topology, composition, runstate, append_cycle, …); each file ~200-900 lines; each one concept. The application code (server, registry, cli) has not yet earned the same shape and needs it.

Every plan below is one Architecture-band sprint (design + landing site) followed by a Functional-band chain (the moves). Every sprint respects rule 6. Every module split is a package (`X/__init__.py` becomes a re-export shim; internal modules are new siblings) so no import path outside the package changes.

---

## Plan 1 — `substrate-ui/server.py`, 2,608 lines → a `handlers/` package

### Current shape

One module. Twenty-seven module-level helper functions. One `RequestHandler` class with 39 methods. Six method-level handlers over 100 lines each. Six copies of the `if _SESSION_REGISTRY is None: 503` prelude. Twenty-seven `except Exception` sites, 10 of them "poll the record for a landed cancel."

Class inventory (grouped by concern, mine):

- **Session lifecycle handlers** (`_session_create`, `_session_turn`, `_session_end`, `_session_interrupt`, `_session_patch`, `_session_delete`, `_session_list`, `_session_by_name`, `_session_events`) — nine methods, roughly 700 lines together.
- **Topology run handlers** (`_topology_run`, `_topology_run_composite`, `_topology_status`) — three methods, ~200 lines.
- **Legacy/bridge handlers** (`_agent`, `_agent_legacy`) — two methods, ~180 lines.
- **Static + reader handlers** (`_static`, `_api_record`, `_diff`, `_records_index` via `_static`, `_explain`) — module-plus-method mix, ~200 lines.
- **Launch/build/validate/resume** (`_launch`, `_build`, `_validate`, `_resume`, `_clear_runs`) — five methods, ~300 lines. Legacy from the pre-daemon era; some paths overlap with `/api/session` now.
- **HTTP primitives** (`_error`, `_send`, `_json`, `_body`, `_read_json_body`, `_origin_ok`, `log_message`, `__init__`) — small, shared.
- **Dispatchers** (`do_POST`, `do_GET`, `do_DELETE`, `do_PATCH`) — thin routing tables.

Module-level helpers group similarly: session-topology construction (`_build_session_topology_from_manifest`, `_tools_for_manifest`, `_agent_models`, `_responder_for`, `_daemon_driver_resolver`, `_load_daemon_config`, `_shutdown_all_sessions`), application-topology construction (`_build_code_review_from_inputs`, `_build_best_of_n_verified_from_inputs`, `_build_research_sweep_from_inputs`, `_build_pair_coding_composite`, `_validate_topology_inputs`, `_application_spec_to_wire`), workspace/repo helpers (`_session_worktree`, `_worktree_diff`, `_record_path`, `_record_names`, `_resolve_child_name`, `_builtins`, `_records_index`, `_io`, `_assays_index`, `_assay_report`), and one demo residue (`_slow_topology`).

### Diagnosis (Python + SDD + substrate lens)

- Fowler's Extract Class applies twice at the class level (session-lifecycle → its own handler class; topology-run → its own handler class) and three times at the module level (session-topology builders, application-topology builders, workspace helpers → three collaborator modules).
- PEP 20 "flat is better than nested" reads *against* keeping everything in one file when the file has grown into three concerns. Nested-package with clear names beats a flat 2,608-line god file.
- SDD: each of the three sub-vocabularies (session lifecycle wire, topology run wire, legacy/bridge wire) has its own dual contract. Extracting them lets each one's observation contract point at its own module rather than lines-in-a-file.
- Substrate: the daemon is substrate-ui's canonical home (per `WORKING_AGREEMENT.md ## Canonical home registry`). Splitting server.py into a package with `server/__init__.py` as the entry point preserves the canonical-home invariant: the *package* is the home, the *files* inside are the internal decomposition.

### Proposed shape

```
substrate-ui/
├── server.py                      # re-export shim: `from .server_pkg import main`; keeps every import working
└── server_pkg/                    # (name TBD — could be `daemon/`)
    ├── __init__.py                # exports main, RequestHandler
    ├── app.py                     # ThreadingHTTPServer setup, main(), SIGTERM handler, module globals
    ├── http.py                    # RequestHandler base: _send, _json, _error, _read_json_body, _body, _origin_ok, log_message, __init__; the dispatcher do_POST/do_GET/do_DELETE/do_PATCH is here as a thin routing table
    ├── handlers/
    │   ├── __init__.py
    │   ├── session.py             # _session_create, _turn, _end, _interrupt, _patch, _delete, _list, _by_name, _events
    │   ├── topology.py            # _topology_run, _topology_run_composite, _topology_status
    │   ├── agent.py               # _agent, _agent_legacy (both retained; legacy is one-release deprecation)
    │   ├── static.py              # _static, _api_record, _diff, _explain, _records_index
    │   └── legacy.py              # _launch, _build, _validate, _resume, _clear_runs (pre-daemon legacy)
    ├── builders/
    │   ├── __init__.py
    │   ├── session_topology.py    # _build_session_topology_from_manifest, _tools_for_manifest, _responder_for, _agent_models, _daemon_driver_resolver, _load_daemon_config
    │   ├── applications.py        # _build_code_review_from_inputs, _build_best_of_n_verified_from_inputs, _build_research_sweep_from_inputs, _build_pair_coding_composite, _validate_topology_inputs, _application_spec_to_wire, _APP_BUILDERS, _COMPOSITE_APP_BUILDERS
    │   └── workspace.py           # _session_worktree, _worktree_diff, _record_path, _record_names, _resolve_child_name, _records_index, _io, _assays_index, _assay_report, _builtins
    ├── polling.py                 # _poll_record_until(record_root, predicate, *, timeout_ms, poll_ms) — collapses the ten "record mid-write; poll again" sites
    ├── globals.py                 # _SESSION_REGISTRY, _APPLICATIONS, _TOPOLOGY_RUNS, _SHUTDOWN_STARTED, _RESPONDER_CACHE, _APP_BUILDERS, _COMPOSITE_APP_BUILDERS, _LAUNCHES, _EXTRA_TOPOS, _WEB_SRC, _SESSIONS_BASE, _SESSION_PREFIXES, _CT
    └── shutdown.py                # _shutdown_all_sessions, SIGTERM installer (extracted from main)
```

Rough sizes: `app.py` 100, `http.py` 200, each handler module 300-500, each builder module 100-300, `polling.py` 80, `globals.py` 100, `shutdown.py` 80. Total ≈ 2,700 lines (a little larger than the current god file because a few duplicated preludes become one shared helper plus explicit imports; the net LOC does not shrink much but the *per-file* LOC drops by 4-6×).

### Sprint chain

Each sprint is one concept per rule 6. The chain is behavior-preserving: dual contract before and after; the existing pytest suite (109 substrate-ui tests) is the regression gate; each sprint must land 109/109 green (or 109+ if new tests come in) before the next dispatches. TECHNIQUE #43.

| # | Sprint | Scope | Files | Rule-6 fit |
|---|---|---|---|---|
| S1 | Establish `server_pkg/` skeleton + re-export shim | Create `server_pkg/__init__.py` re-exporting the current `server.py` contents verbatim; make `server.py` a one-line `from server_pkg import *`; nothing else moves. | 2 files (create `server_pkg/__init__.py`, edit `server.py` shim). | ≤2, one concept. |
| S2 | Extract `polling.py` and adopt at 10 sites | `_poll_record_until(record_root, predicate, *, timeout_ms=3000, poll_ms=50) -> bool`; replace the ten "record mid-write; poll again" inline try/except sites with calls. | 2 files (create `server_pkg/polling.py`; edit `server_pkg/__init__.py`). | ≤2, one concept. |
| S3 | Extract `http.py` (RequestHandler primitives + dispatcher) | Move `_error`, `_send`, `_json`, `_read_json_body`, `_body`, `_origin_ok`, `log_message`, `__init__`, `do_POST`, `do_GET`, `do_DELETE`, `do_PATCH` to `server_pkg/http.py`. `RequestHandler` in `__init__.py` inherits from it and defines every handler method still. | 2 files. | ≤2. |
| S4 | Extract `handlers/session.py` | Move nine session handlers. `RequestHandler` inherits `SessionHandlersMixin`. | 2 files. | ≤2. |
| S5 | Extract `handlers/topology.py` | Move three topology handlers as `TopologyHandlersMixin`. | 2 files. | ≤2. |
| S6 | Extract `handlers/agent.py` | Move two agent handlers as `AgentHandlersMixin`. | 2 files. | ≤2. |
| S7 | Extract `handlers/static.py` | Move five static/reader handlers as `StaticHandlersMixin`. | 2 files. | ≤2. |
| S8 | Extract `handlers/legacy.py` | Move five legacy launch/build/validate/resume/clear handlers as `LegacyHandlersMixin`. | 2 files. | ≤2. |
| S9 | Extract `builders/session_topology.py` | Move seven session-topology construction helpers. | 2 files. | ≤2. |
| S10 | Extract `builders/applications.py` | Move seven application-topology builders + the two registry dicts. | 2 files. | ≤2. |
| S11 | Extract `builders/workspace.py` | Move ten workspace + record + assay helpers. | 2 files. | ≤2. |
| S12 | Extract `globals.py` + `shutdown.py` + `app.py`; delete the shim | Everything remaining moves to `app.py`; `_SESSION_REGISTRY` and friends move to `globals.py` (a fresh import site); `_shutdown_all_sessions` moves to `shutdown.py`. `server.py` shim becomes a two-line `from server_pkg.app import main; if __name__ == "__main__": main()`. | 4 files (create three, edit `server.py`). Rule-6 stretch acknowledged. | Stretch. |

Twelve sprints. Roughly one working day per sprint at review-and-run cadence, meaning about a week end-to-end. S3 through S8 are the load-bearing moves; S1, S2, S12 are scaffolding.

### Observation contract per sprint

Each sprint's observation contract: run the existing `substrate-ui/tests/` suite (`uv run python -m pytest substrate-ui/tests`, expected 109 passed at review open, 141 at review close counting the new fold-in tests); ruff clean on every touched file; mypy strict clean on every touched file (adopting the fix from Q1 first). Fold each sprint's Signal Report into `## Sprint tail`.

### Risk

- **Cyclic imports.** `handlers/session.py` will need `builders/session_topology.py`; `handlers/topology.py` will need `builders/applications.py`. If the builders ever back-import a handler, the cycle appears. Mitigation: builders never import handlers; handlers import builders. One-directional.
- **Mixin discipline.** The mixin-of-handlers pattern is a Python best-practice grey area — some shops prefer composition (a handler holding a helper object) over multiple inheritance. Mixins are lighter for this specific case (each handler needs `self._error`, `self._json`, `self._read_json_body` from the base class); a composition rewrite would require passing the base as a parameter. Ruling: use mixins with narrow interface (each mixin declares only what it adds); revisit if the mixin chain grows past four.
- **Global state.** `globals.py` is a code smell but a genuine one — the daemon *is* a process-lifetime singleton. Naming the globals in one file makes them auditable. Q9 (`_RESPONDER_CACHE`) is a separate architectural decision (per-session vs per-provider Responder ownership) that this refactor does not resolve.

---

## Plan 2 — `substrate-ui/session_registry.py`, 1,232 lines → a `session_registry/` package

### Current shape

One module. Two exception classes (`SessionEndedMidTurn`, `TornRecordOnResume`). One `SessionStatus` string type. One `SessionManifest` msgspec Struct. One `SessionRegistry` class with 25 public methods and 5 internal ones. One context manager `_ByNameLockGuard`. One 134-line `turn_sync` method. Two `def worker()` inner functions inside `turn_sync` and `_run_resume_sync`.

Method inventory:

- **Lifecycle** (create, get, delete, list_all, list_children, has_session_dir, boot_scan, update_status) — 8 methods, ~250 lines.
- **Naming** (by_name, set_name, _read_by_name_index, _write_by_name_index) — 4 methods + guard class, ~150 lines.
- **Mutation** (set_tools, set_per_turn, set_driver) — 3 methods, ~90 lines.
- **Turn execution** (turn_sync, _run_resume_sync, try_enqueue_turn, dequeue_turn, turn_queue_cap, next_turn_index, advance_turn_index) — 7 methods + one internal helper, ~350 lines.
- **Interrupt** (interrupt) — 1 method, ~59 lines.

### Diagnosis

- Fowler's Extract Class rule of thumb applies cleanly: the four groups above are each cohesive, and each has an independent test story (the piece-C review already treated them separately).
- SDD: session-registry has one vocabulary (SessionManifest + SessionStatus + the two exceptions). It should not be split across separate packages *at the vocabulary layer* — the Struct is one Struct — but the *behavior* around it should be. The naming discipline is: `session_registry` remains one package; the internal modules do not export new Structs; only the package's `__init__.py` re-exports the vocabulary.
- Substrate: the piece-C review (finding 11, deferred) already proposed the same three-way split for `delegate.py`. Same shape, different module. If S1 lands the split pattern for both, the discipline becomes uniform.

### Proposed shape

```
substrate-ui/
├── session_registry.py            # re-export shim: `from .session_registry_pkg import ...`
└── session_registry_pkg/          # (or rename directory to session_registry/ once shim removed)
    ├── __init__.py                # exports SessionRegistry, SessionManifest, SessionStatus, SessionEndedMidTurn, TornRecordOnResume, SessionTopologyFactory
    ├── vocabulary.py              # SessionManifest, SessionStatus, SessionEndedMidTurn, TornRecordOnResume, SessionTopologyFactory type alias, _VALID_STATUS
    ├── manifest.py                # SessionRegistry lifecycle: __init__, create, get, delete, list_all, list_children, has_session_dir, boot_scan, update_status, _manifest_path, _manifest_from_dict, _atomic_write_json
    ├── naming.py                  # SessionRegistry.by_name, set_name, _read_by_name_index, _write_by_name_index, _ByNameLockGuard, NameCollision
    ├── mutation.py                # SessionRegistry.set_tools, set_per_turn, set_driver
    ├── turn.py                    # SessionRegistry.turn_sync, _run_resume_sync, try_enqueue_turn, dequeue_turn, turn_queue_cap, next_turn_index, advance_turn_index
    └── interrupt.py               # SessionRegistry.interrupt
```

Rough sizes: `vocabulary.py` 120, `manifest.py` 300, `naming.py` 200, `mutation.py` 100, `turn.py` 350, `interrupt.py` 100, `__init__.py` 40. Total ≈ 1,200 lines, roughly matching current.

The `SessionRegistry` class is *one class defined across six files* via the mixin pattern (each behavior module contributes a mixin; `__init__.py` composes them into the final class). Alternative: keep `SessionRegistry` as a single class in `__init__.py`, and let the six behavior modules export free functions that the class methods delegate to. Fowler calls this Move Method with a thin delegate. The choice is stylistic; mixins fit the current shape better because most methods share `self._lock`, `self._catalog`, `self._sessions_base` state.

### Sprint chain

| # | Sprint | Scope | Files |
|---|---|---|---|
| S1 | Establish `session_registry_pkg/` skeleton + shim | Same shape as server.py S1. | 2 files. |
| S2 | Extract `vocabulary.py` | Move the four Struct/exception/type-alias declarations. `__init__.py` re-exports. No behavior change. | 2 files. |
| S3 | Extract `manifest.py` (LifecycleMixin) | Move eight lifecycle methods. | 2 files. |
| S4 | Extract `naming.py` (NamingMixin + `_ByNameLockGuard`) | Move four methods + guard class. | 2 files. |
| S5 | Extract `mutation.py` (MutationMixin) | Move three set_* methods. | 2 files. |
| S6 | Extract `turn.py` (TurnMixin) | Move seven turn-execution methods + `_run_resume_sync`. | 2 files. |
| S7 | Extract `interrupt.py` (InterruptMixin); delete the shim | Move interrupt; delete the shim. | 2 files. |

Seven sprints. Roughly half a week.

### Observation contract per sprint

Each sprint runs the 40+ `SessionRegistry` tests plus the 8 delegate-via-standing-session tests (which reach `turn_sync` through the delegate seam). No behavior change; every test still green.

### Risk

- **Method dependencies.** `turn.py` needs `manifest.py`'s `update_status`; `interrupt.py` needs `turn.py`'s producer instance lookup; `naming.py` needs `manifest.py`'s catalog. Mitigation: import the mixins in a fixed order in `__init__.py` so MRO is deterministic; each mixin declares its required attributes as `Protocol`-typed class-level annotations.
- **Test coupling.** Tests that patch `SessionRegistry._something_private` may need import-path updates. Grep first; the count is likely ≤5.

---

## Plan 3 — `substrate/src/substrate/cli.py`, 1,750 lines → a `cli/` package with Command classes

### Current shape

One module. 12 module-level helpers (config, defaults, daemon-launch, sse-stream, readline, event-format). One 163-line `_slash_route` chain-of-`if`. One 112-line `_repl` main loop. 24 `@main.command` / `@session_group.command` / `@bundle_group.command` / `@topology.command` / `@demo.command` verb registrations (click decorators).

Verb inventory (grouped by concern):

- **Runtime verbs**: `run`, `tail`, `inspect`, `narrate`, `replay`, `validate`, `stats`, `conformance`, `score`. Nine verbs, ~600 lines.
- **Session/chat verbs**: `chat`, `daemon`, `resume`, plus the `session` group (ls, end, rm, set-name). Seven verbs, ~350 lines.
- **Bundle verbs**: bundle group (create, ls, show, edit) + `builder`. Five verbs, ~200 lines.
- **Topology + demo groups**: topology (list), demo (replay, run). Three verbs, ~80 lines.
- **REPL internals**: `_slash_route` (163), `_repl` (112), `_sse_stream` (65), `_readline_with_interrupt` (12), `_render_stream_line` (40), `_sighup_handler` (75). Six helpers, ~450 lines.
- **Config + daemon-launch internals**: `_load_config`, `_defaults`, `_daemon_server_path`, `_double_fork_daemon`, `_ensure_daemon_running`, plus the `_daemon` module (279 lines, separate file). ~200 lines in cli.py.
- **Helpers**: `_load_topology`, `_load_attr`, `_failure_summary`, `_producer_label`, `_format_event_line`, `_resolve_version`, `_resolve_session`. ~150 lines.

### Diagnosis

- Fowler's Extract Method + Extract Class. `_slash_route`'s chain-of-`if` is a canonical case for the Command pattern (GoF): one class per slash, all implementing a `SlashCommand.execute(session, daemon) → None` interface, registered in a dict. Every branch becomes a ~15-line class.
- PEP 20: click groups already give us "flat is better than nested" for verbs — each verb is a callable. The 163-line `_slash_route` is where the flat pattern breaks and wants Extract Class.
- SDD: the REPL is a vocabulary consumer (it emits UserMessage to the daemon; the slash `/exit` is a distinguished value in that vocabulary; every other slash is *out-of-vocabulary from the topology's view* but *in-vocabulary from the CLI's own local grammar*). Naming the CLI's local slash-grammar explicitly (as a data structure: `SLASH_COMMANDS: dict[str, SlashCommand]`) makes it inspectable and testable.

### Proposed shape

```
substrate/src/substrate/
├── cli.py                         # re-export shim: `from .cli_pkg import main`
└── cli_pkg/
    ├── __init__.py                # exports main (the click group)
    ├── main.py                    # the @click.group main; @main.command registrations; --version
    ├── config.py                  # _load_config, _defaults, _daemon_server_path, _double_fork_daemon, _ensure_daemon_running
    ├── verbs/
    │   ├── __init__.py
    │   ├── runtime.py             # run, tail, inspect, narrate, replay, validate, stats, conformance, score
    │   ├── session.py             # chat, daemon, resume, session_group (ls, end, rm, set-name)
    │   ├── bundle.py              # bundle_group (create, ls, show, edit), builder, _run_bundle_wizard, _write_rendered_bundle
    │   └── topology.py            # topology_group (list), demo_group (replay, run)
    ├── repl/
    │   ├── __init__.py
    │   ├── loop.py                # _repl (main loop), _sighup_handler, _readline_with_interrupt
    │   ├── stream.py              # _sse_stream, _render_stream_line
    │   └── slash.py               # SlashCommand base + one class per slash; SLASH_COMMANDS dict; router
    └── helpers.py                 # _load_topology, _load_attr, _failure_summary, _producer_label, _format_event_line, _resolve_version, _resolve_session
```

Rough sizes: each verb module 200-500, each repl module 100-200, helpers 150, config 150, main 100. Total ≈ 1,800 lines.

The slash Command extraction is the load-bearing move. Sketch:

```python
# cli_pkg/repl/slash.py
from typing import Protocol
class SlashCommand(Protocol):
    name: str  # "/model"
    help: str
    def parse(self, args: list[str]) -> tuple[bool, str | None]: ...  # (ok, error_msg)
    def execute(self, session: dict[str, Any], pending_context: dict[str, Any], daemon) -> None: ...

class ModelCommand:
    name = "/model"
    help = "set the driver for the next turn"
    def parse(self, args): return (len(args) == 1, "requires exactly one driver name")
    def execute(self, session, pending_context, daemon):
        try:
            daemon.patch_session(session["session_id"], driver=self._driver)
            _err.print(f"[repl] driver → {self._driver} (next turn)")
        except daemon.DaemonError as exc:
            _err.print(f"[repl] /model failed: HTTP {exc.status}: {exc.body}")

SLASH_COMMANDS: dict[str, type[SlashCommand]] = {"/model": ModelCommand, ...}

def route(line, session, pending_context, daemon) -> bool:
    stripped = line.strip()
    if not stripped.startswith("/"): return False
    parts = stripped.split()
    slash, args = parts[0], parts[1:]
    if slash == "/exit": return False  # only slash the model observes
    cmd_cls = SLASH_COMMANDS.get(slash)
    if cmd_cls is None:
        _err.print(f"[repl] unknown slash: {slash}. Try /help.")
        return True
    cmd = cmd_cls()
    ok, err = cmd.parse(args)
    if not ok:
        _err.print(f"[repl] {slash} {err}")
        return True
    cmd.execute(session, pending_context, daemon)
    return True
```

163 lines becomes ~25 lines of routing + one 15-line class per slash. Adding `/interrupt` is one file.

### Sprint chain

| # | Sprint | Scope | Files |
|---|---|---|---|
| S1 | Establish `cli_pkg/` skeleton + shim | Same shape as prior S1s. | 2 files. |
| S2 | Extract `helpers.py` and `config.py` | Move seven helpers + five config functions. | 3 files (create two, edit one). Rule-6 stretch. |
| S3 | Extract `repl/stream.py` and `repl/loop.py` | Move `_sse_stream`, `_render_stream_line`, `_repl`, `_sighup_handler`, `_readline_with_interrupt`. | 3 files. Stretch. |
| S4 | Extract `repl/slash.py` — Command pattern | Rewrite `_slash_route` as `SlashCommand` protocol + one class per slash + a small router. | 2 files. |
| S5 | Extract `verbs/runtime.py` | Move nine runtime verbs. | 2 files. |
| S6 | Extract `verbs/session.py` | Move seven session/chat verbs. | 2 files. |
| S7 | Extract `verbs/bundle.py` | Move five bundle verbs + wizard helpers. | 2 files. |
| S8 | Extract `verbs/topology.py`; delete the shim | Move topology + demo groups; collapse shim. | 3 files. Stretch. |

Eight sprints. S2/S3/S8 are three-file stretches per rule 6; each is one concept (helpers + config are both "cross-cutting infra"; stream + loop are both "REPL runtime"; topology + demo groups are both "read-only browsing"). Acceptable stretches with the rationale on the card.

### Observation contract per sprint

Every sprint runs the `test_cli_*` suite (test_cli_chat_218, test_cli_repl_219, test_cli_signals_220, test_cli_slash_221, test_cli_session_subverbs_222, test_cli_bundle_subverbs_222, test_cli_failure_surfacing, test_cli). Full-suite `uv run python -m pytest tests/test_cli*` on each landing.

### Risk

- **Click decorator movement.** `@main.command()`, `@session_group.command("ls")` etc. depend on `main` and the groups being importable. Move order matters: `main.py` lands first with all `@main.group` declarations; then verb modules import `main` from it and register with decorators; the registration happens on import. This is a click idiom, well-tested, but any move that reverses the import direction breaks click's registry.
- **REPL state.** `pending_context` is a shared mutable dict across REPL turns. The `SlashCommand.execute` interface must pass it in explicitly (as shown in the sketch). Every command that mutates it does so explicitly.

---

## Plan 4 — `substrate/src/substrate/topologies/tool_loop/delegate.py`, 663 lines → a `delegate/` package

### Current shape

One module. Eight module-level helpers. One `make_delegate` factory that returns a `Tool` whose `run` is a 266-line closure. The closure carries five paths: standing-session, different-driver, context-slice, fresh-child, path-validation.

### Diagnosis

The piece-C review (finding 11, `substrate/process/REVIEW-2026-08-26-piece-c-closure.md`) already proposed the exact split: "delegate.py at 592 lines — hygiene split into `delegate/dispatch.py` + `delegate/context.py` + `delegate/model.py` when the seam settles." The seam has settled (piece C closed, piece B closed). The proposal is due.

### Proposed shape

```
substrate/src/substrate/topologies/tool_loop/
├── delegate.py                    # re-export shim: `from .delegate_pkg import make_delegate`
└── delegate_pkg/
    ├── __init__.py                # exports make_delegate; the Tool schema declaration
    ├── dispatch.py                # make_delegate + the Tool.run closure; delegates each path to model/context/session modules
    ├── model.py                   # _default_model_resolver, _default_child_factory, path-2 build (different-driver)
    ├── context.py                 # _extract_context_slice, _format_context_event, _prefix_context_slice, path-3 build
    ├── session.py                 # path-1 (standing session) dispatch; the F-API-6 duck-typed catch of SessionEndedMidTurn
    ├── child.py                   # _run_child_to_answer, _unique_child_root, _with_baseline
    └── constants.py               # SESSION_ENDED_MID_DELEGATE, other shared strings
```

Rough sizes: dispatch 200, model 80, context 130, session 120, child 100, constants 30, __init__ 40. Total ≈ 700 lines.

### Sprint chain

| # | Sprint | Scope | Files |
|---|---|---|---|
| S1 | Establish `delegate_pkg/` skeleton + shim | | 2 files. |
| S2 | Extract `context.py` (three helpers + path-3 branch) | | 2 files. |
| S3 | Extract `model.py` (default resolver + default child factory + path-2 branch) | | 2 files. |
| S4 | Extract `session.py` (path-1 branch + duck-typed catch) | | 2 files. |
| S5 | Extract `child.py` (three helpers) + `constants.py` + collapse shim | | 3 files. Stretch. |

Five sprints. Two to three days.

### Observation contract per sprint

`tests/test_delegate*` — 50+ tests across five files. Each sprint runs the full delegate test tier.

### Risk

- **The 266-line closure inside `Tool.run` is hard to split.** The closure closes over ~15 variables (`session_registry`, `parent_session_id`, `parent_record_root`, `depth`, `max_depth`, `max_children`, `spawned`, `child_max_steps`, `timeout_seconds`, `model_resolver`, `suite_factory`, `factory`, `child_record_root`, `r`). Extracting a path into a separate module means passing those variables in explicitly. Mitigation: introduce a `DelegateContext` frozen dataclass carrying the fifteen fields; each path module is a free function taking `(ctx: DelegateContext, args_dict: dict) → dict`. `Tool.run` becomes a dispatcher: parse args, build ctx, delegate to the right path.

---

## Plan 5 — `substrate/src/substrate/topologies/tool_loop/substrate_tools.py`, 736 lines → a `substrate_tools/` package

### Current shape

Eight `make_*` factories (`run_topology`, `run_topology_poll`, `inspect_record`, four `list_*`). Each factory has a `_impl` free function and returns a `Tool`. Shared helpers: `_cap_tokens`, `_estimate_tokens`, `_sign_cursor`, `_verify_cursor`, `_extract_application_name`, `_filter_events`.

### Diagnosis

Cleaner than delegate.py — every factory is well-scoped. The concern is not the shape; it is the size. Two coherent groups: "topology-run tools" (run_topology, run_topology_poll) and "record-inspection tools" (inspect_record, list_records, list_topologies, list_applications, list_sessions). Each group is ~350 lines.

### Proposed shape

```
substrate/src/substrate/topologies/tool_loop/
├── substrate_tools.py             # re-export shim
└── substrate_tools_pkg/
    ├── __init__.py                # exports the eight make_* factories + DaemonClient protocol
    ├── run.py                     # make_run_topology, make_run_topology_poll, their _impls, _extract_terminal_output
    ├── inspect.py                 # make_inspect_record + _inspect_record_impl + the HMAC cursor primitives + progressive disclosure
    ├── listing.py                 # four make_list_* factories + their _impls
    ├── protocols.py               # DaemonClient, _SessionRegistryLike
    └── helpers.py                 # _cap_tokens, _estimate_tokens, _extract_application_name, _filter_events
```

### Sprint chain

Four sprints (S1 skeleton, S2 helpers+protocols, S3 run.py, S4 inspect.py+listing.py+delete shim). Two days.

### Risk

Low. The factories are already independent; the extraction is nearly mechanical.

---

## Cross-cutting extraction — Q10: one `run_topology_sync` primitive replaces four factories

### Current shape (four sites of the same shape)

- `delegate.py::_run_child_to_answer(topology, record_root, timeout_seconds)` — fresh event loop, run to first `FinalAnswer`, timeout.
- `session_registry.py::_run_resume_sync(topology, record_root, resume_event, timeout_seconds)` — fresh event loop, `Runtime.resume`, timeout.
- `session_registry.py::_run_run_sync(topology, record_root, first_turn_user_message, timeout_seconds)` — fresh event loop, `Runtime.run` with initial event, timeout (added in sprint 217a per BLACKBOARD).
- `server.py::_topology_run` inner — spawns a thread that runs the topology to completion, timeout implicit in daemon.

Each carries: cross-thread cancel via `loop.call_soon_threadsafe(task.cancel)`, `concurrent.futures.Future` marshalling, timeout handling, sealed-record recovery on timeout.

### Proposed primitive

```python
# substrate/src/substrate/testing.py  (adds to existing module; substrate.testing is already a canonical home)

def run_topology_sync(
    topology: Callable[[TopologyBuilder], None],
    record_root: Path,
    *,
    mode: Literal["run", "resume", "until_answer"],
    resume_event: Any | None = None,
    initial_event: Any | None = None,
    timeout_seconds: float = 600.0,
) -> RunResult:
    """Run a topology synchronously from a worker thread. Fresh event loop, cross-thread
    cancel on timeout, sealed record on completion or timeout. Returns the RunResult;
    raises TimeoutError on timeout, propagates topology exceptions."""
```

Four callers collapse to one; the ~150 lines of duplicated cross-thread bookkeeping become one primitive with one set of tests.

### Sprint chain

| # | Sprint | Scope | Files |
|---|---|---|---|
| S1 | Author `substrate.testing.run_topology_sync` (architecture pass) | Design + primitive + tests. Not adopted by callers yet. Halt with `awaiting_architect_decision` if the API shape needs a Decision. | 2 files (create primitive + tests). |
| S2 | Adopt in `delegate.py::_run_child_to_answer` | Replace the inline shape with a call to the primitive. | 2 files. |
| S3 | Adopt in `session_registry.py::_run_resume_sync` and `_run_run_sync` | Both callers move to the primitive. | 2 files. |
| S4 | Adopt in `server.py::_topology_run` | Replace the thread-spawn shape. | 2 files. |

Four sprints. Two to three days. Blocks nothing; unblocks a cleaner shape for future callers (e.g., piece G's UI-side runners).

### Risk

- **Cross-repo change.** The primitive lives in substrate; three of the four adopters live in substrate-ui. Standard cross-repo landing shape (already practiced in the piece-A/B/C arc).
- **Test coverage.** The four current implementations each have their own tests. After adoption, those tests should still pass unchanged — the primitive is a refactor, not a behavior change. If any test breaks, it caught a behavior difference between the four implementations (which is itself a finding worth surfacing).

---

## Sequencing and dispatch order

Not all five plans dispatch at once. The dependencies:

1. **Q1 (mypy fix) lands first.** Every subsequent sprint's observation contract includes "mypy strict clean." Cannot honestly gate on that until Q1's ten errors are fixed.
2. **Q7 (kernel one-line) and Q14 (ruff one-line) land second.** Under-an-hour wins; clear the noise before starting the refactor chain.
3. **Q10's primitive (Plan 6) lands third.** Blocks nothing but simplifies Plan 2 and Plan 4 by pre-collapsing the duplication.
4. **Plans 4 and 5 (delegate + substrate_tools) land next in parallel.** Smaller. Independent. Same pattern; validating it once here before applying to the bigger plans is prudent.
5. **Plans 2 and 3 (session_registry + cli) land in parallel.** Medium size. Cross-repo (registry in substrate-ui, cli in substrate) so no shared merge conflicts.
6. **Plan 1 (server.py) lands last.** Largest. Highest risk. Blocks piece G. But piece G has not started; a week of hygiene here saves months of pain later.

Total: ≈ 40 sprints, one to three per module, roughly three weeks of Architect-and-Agent time at the observed cadence. Piece G unblocks at the end of week two (after Plans 4/5 land and Plans 2/3 are underway); the server.py refactor (Plan 1) can proceed in parallel with piece G's first UI sprints if Plan 1 avoids touching handlers piece G reads.

## What this plan does NOT do

- **Does not fix Q9** (`_RESPONDER_CACHE` per-session vs per-provider ownership). That is an architectural decision, not a refactor; needs a Decision entry.
- **Does not adopt any new dependency** (pydantic, FastAPI, structlog). Every plan uses stdlib + msgspec + click + api primitives already in the tree.
- **Does not delete anything** (rule 12). Every old module survives as a re-export shim for at least one release. A follow-up plan a release later removes the shims.
- **Does not touch the kernel.** `kernel/runtime.py` at 887 lines is one concept and stays. `composition.py`'s one swallow (Q7) is a two-line fix, not a split.
- **Does not touch the tests.** Every plan's observation contract is "the existing test suite still passes." New tests may be added; existing ones are not rewritten.

---

*PLAN-2026-08-28-hygiene-splits.md. Five plans + one cross-cutting primitive. ~40 sprints across ~3 weeks of Architect-and-Agent time. Read against sdd-kit-2 rules 6, 7, 12; TECHNIQUES.md #43, #44, #45; PEP 8, PEP 20, PEP 257; Fowler Extract Class / Extract Function / Move Method. Author: Claude session 2026-08-28. Not yet ratified; every sprint dispatches only on Architect entry into `## Decisions`.*
