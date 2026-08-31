# REVIEW — code quality, brutal pass across substrate + substrate-ui

**Reviewer:** Claude session 2026-08-28, main-loop.
**Scope:** every non-test `.py` in `substrate/src/` and every top-level `.py` in `substrate-ui/` (server, session_registry, builder, demo_topologies). Follow-up to `REVIEW-2026-08-28-un-reviewed-sprints-217-through-232b.md`, which covered SDD discipline. This one is about the code as an engineering artifact — coupling, exception hygiene, function shape, type discipline, and the gap between what the record claims and what the tree contains.

**Ground truth run at review open.** `uv run ruff check src tests` returns one violation (E402 in `src/substrate/topologies/session/transcript.py:56` — imports below a docstring after sprint 224a's constants extraction). `uv run mypy --strict src/substrate` returns **10 errors across 6 files**. Full-suite pytest still returns 1,093 passed, 5 skipped, 0 failed in 257 s. The BLACKBOARD's PIECE B CLOSED entry (2026-08-27) reads "Mypy strict is clean on the substrate side; pre-existing errors on `server.py`'s launch/agent paths are unchanged (not in the 217c/a diff surface)." Reality does not match that claim: the ten errors are in `src/substrate/`, not `server.py`. See Q1.

Findings ranked most severe first. Every finding names the exact file, line, and the shape of the fix.

---

## Q1 — "Mypy strict is clean on the substrate side" is false. Ten errors on file.

`uv run mypy --strict src/substrate` at review open:

```
src/substrate/_daemon.py:84             Incompatible types in assignment
src/substrate/bundles.py:166–169        Item "None" of "Any | dict | None" has no attribute "get"  (four times)
src/substrate/assay/report.py:359–360   arg-type: str | None passed where str expected
src/substrate/cli.py:998                Argument "timeout" to "_connect" has incompatible type "None"; expected "float"
src/substrate/topologies/tool_loop/substrate_tools.py:308  Returning Any from function declared "str | None"
```

Six files. Zero in `server.py`. The `bundles.py:166` cluster is real: `raw.get("bundle")` may be `None`; the code then calls `.get("name")` on it. mypy caught it, the code shipped anyway, and the sprint entry claimed "mypy strict clean" — a claim that grep-search across `process/BLACKBOARD.md` finds 111 times across the 2026-06 through 2026-08 window. Either the check was not being run at the tightness the claim implies, or the errors accumulated after the last honest run.

That is exactly the "green is not proven" class the memory `be-your-own-skeptic-green-is-not-proven` warns about. `mypy --strict src/substrate` is a two-second command; the claim's truth-value is either checked or not.

**Cost.** Two hours to fix all ten by hand. The `bundles.py` cluster is a real bug that hits any bundle whose TOML lacks a `[bundle]` section — the four `metadata.get(...)` calls at lines 166-169 all raise `AttributeError` before the `or raw.get(...)` fallback lands (because metadata is `None`, not a dict). Grep confirms it: `metadata = raw.get("bundle") if isinstance(raw.get("bundle"), dict) else {}` at line 162 does guard against non-dict, so metadata is `{}` not `None` — but mypy cannot narrow across the ternary because both branches use different accessors. The runtime is safe; the type is wrong. Same class in `_daemon.py:84`, `cli.py:998` (a `None` timeout on `_connect` — real bug on the UDS path), `assay/report.py:359-360`, `substrate_tools.py:308`.

**Fix.** Add a mypy-strict check to the local CI gate the 2026-07-22 Housekeeping ruling names as the default gate (`scripts/ci_local.sh`). Fix the ten errors. Retract the 111 "mypy strict clean" claims in one BLACKBOARD entry — do not edit the old entries (rule 12), name the correction as a new dated entry.

## Q2 — server.py has grown into a god handler (2,608 lines, one class, 27 blind-except sites).

`substrate-ui/server.py` at review open: 2,608 lines. One HTTP-handler class carrying every endpoint. The `do_POST` dispatcher (line 830) is a chain of nine `if path.startswith(...) return` branches followed by `except Exception: self._error(500, ...)` at the end. The handlers it dispatches to are large:

| Handler | Lines | Line count |
|---|---|---|
| `_session_turn` | 1027 | 178 |
| `_agent_legacy` | 1935 | 133 |
| `_session_end` | 1206 | 119 |
| `_topology_run` | 1556 | 115 |
| `_agent` | 1820 | 114 |
| `_session_create` | 914 | 112 |

Six handlers averaging 128 lines, each doing body-parse + validation + registry access + record polling + response shaping. Six copies of the "`if _SESSION_REGISTRY is None: self._error(503, …); return`" prelude (grep confirms nine call sites).

Twenty-seven `except Exception` sites in the file (all marked `noqa: BLE001`, so ruff is silenced but the shape remains). Ten of them are in "record mid-write; poll again" loops — a legitimate pattern but replicated inline in five different handlers. One helper `_poll_record_until(record_root, predicate, *, timeout)` would collapse them.

The class has no natural place for a middleware layer; every cross-cutting concern (auth via `_origin_ok`, JSON body parse, error shaping, registry-availability guard) is copied per handler. That is the shape a Flask/FastAPI/Starlette project outgrows in its first month, and it is what a stdlib `BaseHTTPRequestHandler` looks like when it is asked to do the work of a framework.

**Cost.** Real refactor — one week of hygiene sprints per TECHNIQUE #43 (behavior-preserving chain). Suggested split:

- `substrate-ui/handlers/session.py` — create, turn, end, patch, delete, interrupt.
- `substrate-ui/handlers/topology.py` — run, status.
- `substrate-ui/handlers/agent.py` — the legacy bridge.
- `substrate-ui/handlers/system.py` — launch, resume, validate, build, clear_runs.
- `substrate-ui/http.py` — the base handler + `_json`, `_error`, `_read_json_body`, `_poll_record_until` primitives.

Each handler module ~300-400 lines. The dispatcher becomes a small routing table, not a chain of `if`s.

Not urgent; blocking piece G's UI work on top of this god file will make G harder.

## Q3 — session_registry.py at 1,232 lines with a 134-line `turn_sync`.

`substrate-ui/session_registry.py`. Same shape as server.py but for state. The `SessionRegistry` class does: create, get, delete, list, by_name, set_name, set_driver, set_tools, set_per_turn, set_workspace, set_bundle, has_session_dir, boot_scan, turn_sync, interrupt, try_enqueue_turn, dequeue_turn, next_turn_index, turn_queue_cap, plus internals — 18 public methods on one class.

`turn_sync` (line 539) is 134 lines. It handles: manifest lookup, resume-event build via the injected `resume_event_builder`, hot-segment detection, `Runtime.resume` composition on a worker thread, timeout handling, cross-thread cancel, sealed-record recovery on timeout, `SessionEndedMidTurn` typed raise, manifest status update. That is the ATM of session lifecycle. Every one of the 27 tests against `SessionRegistry` exercises some corner of `turn_sync`; when it breaks, it breaks everything.

The three-way split the piece-C review proposed for `delegate.py` (into `dispatch.py`, `context.py`, `model.py`) applies here: `session_registry/manifest.py` (create, get, delete, boot_scan, JSON serialization), `session_registry/name.py` (by_name + fcntl.flock discipline), `session_registry/turn.py` (turn_sync, _run_resume_sync, queue cap, worker-thread coordination), `session_registry/mutation.py` (set_driver, set_tools, set_per_turn, patch). One class becomes a package with narrower responsibilities.

**Cost.** Half a week. Same behavior-preserving chain shape as Q2.

## Q4 — Six invented `pass_kind` values reflect real work the template does not name.

Cross-referenced from the SDD review (F2). Six values were minted inline: `refactor`, `test-refactor`, `test-add`, `correctness`, `cleanup`, `infra`. Reading the seven cards that use them, three are legitimate patterns the kit's five-value enum genuinely does not cover:

- `cleanup` (224e, 224g) — pure lint / dead-code / naming pass. `functional` mis-labels it (nothing functional changes); `architecture` mis-labels it (no contract changes). The kit's `docs` is prose-only.
- `infra` (224h) — CI gate additions (`ruff` + `mypy strict` in the local pipeline). Not a code change; not documentation; a change to the verification substrate.
- `test-add` (224c, 224f) — adding coverage for existing behavior. Different from `observation` (which is a behavior-touching sprint that RUNS the observation contract); different from `functional` (which adds new behavior).

The move is not "reclassify against the five." The move is propose a v0.2 of the sprint-frontmatter vocabulary with these three additions ratified. That is what `NEW_TAG_PROPOSED` exists for. The proposal doc is short.

## Q5 — Type discipline: 710 `Any` uses, 262 `dict[str, Any]`, 22 `type: ignore`.

`grep -c 'dict\[str, Any\]'` across `src/substrate` + `substrate-ui` returns 262. `Any` alone: 710 usages. `type: ignore`: 22.

The kernel is honest about `Any` — event payloads are heterogeneous, `msgspec.Struct` shapes cross module boundaries, and typing every dict envelope as a TypedDict would drown the code. Fair.

Two specific problem sites:

- `session_registry.py` types `session_topology_factory: Callable[[SessionManifest], Callable[["TopologyBuilder"], None]] | None`. That is correct after the piece-C review fold (finding 9). Adjacent code paths (`_run_resume_sync`, `turn_sync`) accept and return `Any`; the concrete types are known from the factory. Tighten opportunistically.
- The delegate `Tool.run(a: list[Any]) -> dict[str, Any]` at delegate.py:397 is genuinely dynamic (parses per-call args from a schema-declared dict), but the `dict[str, Any]` return shape is documented across three sites: the docstring, the schema, and the callers. A TypedDict `DelegateResult` with the six known fields (answer, child_root, steps, via?, and the two provenance fields) is worth the ~15 lines it costs; every caller then gets IDE completion and mypy narrowing.

**Cost.** Low. `TypedDict` per handler-return in server.py + session_registry.py. Do it during Q2/Q3's refactor, not standalone.

## Q6 — 27 `except: pass` sites, ten of them in server.py's poll loops.

The pattern:

```python
try:
    for env in api.read_record(record_root):
        if env.get("kind") == api.PRODUCER_CANCELLED and matches(env):
            landed = True
            break
except Exception:  # noqa: BLE001 — mid-write; poll again
    pass
```

This is at `server.py:1388`, `:1814`, `:2053`, `:2109`, `:2172` and again in `substrate_tools.py:615`. The comment is honest about the intent ("record mid-write; poll again"). The shape is not honest about the surface area: `except Exception` catches every bug in `api.read_record` + every bug in the filter predicate + every bug in the payload access. A `KeyError` because a payload shape drifted would be swallowed as "mid-write." A `TypeError` from a broken filter would be swallowed as "mid-write."

The correct shape names the class:

```python
try:
    ...
except (RecordGapError, CRCMismatchError, FileNotFoundError, OSError):
    pass  # mid-write; poll again
```

or, for the general case, a helper that catches the record-io errors and re-raises everything else. Substrate already has the typed exceptions (`RecordGapError`, `CRCMismatchError` are on record). Using them closes the class.

**Cost.** Half a day across the six sites. Adds one helper (`_read_record_or_none`) that expresses the intent.

## Q7 — `kernel/composition.py:190` catches `(asyncio.CancelledError, Exception)` in a cleanup `finally` and swallows.

```python
finally:
    if not run_task.done():
        run_task.cancel()
        try:
            await run_task
        except (asyncio.CancelledError, Exception):
            pass
```

This is the kernel. Cleanup swallowing is defensible in a `finally` — you cannot propagate from cleanup cleanly. But `except (CancelledError, Exception)` is the widest possible net; `BaseException` is the only wider one, and `pass` gives you no diagnostic. If the inner run_task raised a bug during teardown, the record has no trace.

Two lines fix it:

```python
except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001 — cleanup path
    logger.warning("composition cleanup swallowed: %r", exc)
```

The kernel is the one place where every swallowed exception is an information loss the reader cannot recover.

## Q8 — 180 `noqa` suppressions; 55 of them `BLE001` (blind except) and 110 `E402` (import not at top).

`noqa` breakdown:

| Rule | Count | Class |
|---|---|---|
| E402 | 110 | Module-level import not at top of file |
| BLE001 | 55 | Blind `except Exception` |
| N802 | 4 | Name should be lowercase |
| SLF001 | 3 | Private-member access |
| PLC0415 | 3 | Import outside toplevel |
| S310/S603/S602 | 4 | URL open / subprocess with untrusted input |
| E731 | 1 | Lambda assignment |

110 E402 hits: mostly test files that do `sys.path.insert(0, ...)` before importing substrate. That is a test-scaffold pattern, not a code smell, and the noqa is honest.

55 BLE001: real signal. 27 of them are in `server.py`, 10 in `cli.py`, 6 in `session_registry.py`. Q6 addresses ten of the server.py cases; the remaining 45 want a pass: each should either narrow the exception type or add a logger.warning that says why the swallow is intentional. `# noqa: BLE001 — mid-write; poll again` is honest prose; a typed except is honest code.

The four `S310`/`S603`/`S602` are worth spot-checking (subprocess + URL open on untrusted paths) — bundle-loader and workspace-shape code passes user-supplied paths to subprocess.run and `urllib.request.urlopen`. Not obviously exploitable in a local-daemon context but worth a threat-model sentence in each noqa comment.

## Q9 — `_RESPONDER_CACHE` global still lives in server.py:111 (piece-B review finding 13, deferred, still open).

The piece-B closure review named "F13 fresh Responder per turn — no cross-turn state" as a deferred finding "still open, no natural home yet." At review open: `_RESPONDER_CACHE: dict[str, Any] = {}` at server.py:111; hit at :123 (`cached = _RESPONDER_CACHE.get(name)`); written at :134 (`_RESPONDER_CACHE[name] = responder`).

That is process-lifetime global mutable state keyed by driver name. Every session's responder is shared. A responder that carries state (a rate-limited responder with a semaphore, an Ollama client with an httpx session, an ensemble responder with pending tasks) will bleed state across sessions. `RateLimitedResponder` from `substrate.adapters.rate_limit` (200 lines, per BLACKBOARD 2026-08-11) explicitly carries an `asyncio.Semaphore`. Sharing it across two concurrent sessions is either intentional (a per-provider global rate limit) or a bug (per-session isolation would want per-session semaphores).

The comment on the cache does not name the intent. That is the missing decision: is this rate-limit sharing (keep it, document as intentional) or is this a leak (remove it, per-session ownership).

## Q10 — Duplicate work across `session_topology_factory` shapes.

`_build_session_topology_from_manifest(manifest, first_turn_user_message=None)` appears in server.py (BLACKBOARD 2026-08-27 entry). `_default_child_factory(responder, suite_factory, ...)` appears in delegate.py:158. `_run_run_sync(topology, record_root, ...)` mirrors `_run_resume_sync(topology, record_root, ...)` mirrors `_run_child_to_answer(topology, record_root, timeout_seconds)`. Four factories, four worker-thread runners, one substrate primitive. The shape is: fresh event loop → run topology to completion / to first pause / with timeout → return the sealed record.

`substrate.testing` (or `substrate.api`) is the natural home for one primitive: `run_topology_sync(topology, record_root, *, timeout_seconds, mode="run"|"resume"|"until_answer")`. Four callers collapse to one. Cross-thread cancel logic (which delegate.py and session_registry.py both re-implement with `loop.call_soon_threadsafe(task.cancel)`) lives once.

**Cost.** One architecture-band sprint on the substrate side proposing the primitive; then three follow-up sprints (delegate, session_registry, server) that adopt it.

## Q11 — `cli.py:_slash_route` at 163 lines is a chain of `if slash == "/foo"` branches.

`src/substrate/cli.py:1053`, 163 lines. Ten branches: `/exit`, `/help`, `/model`, `/tools`, `/context`, `/inspect`, `/list`, `/replay`, `/run`, unknown-fallback. Each branch parses args, hits the daemon over HTTP, catches `_daemon.DaemonError`, prints to stderr.

The Gang-of-Four shape here is Command: one class per slash with `parse(args) → validate() → execute(session, daemon) → format_result() → str`. Each command file is 15-30 lines. The router is ten lines: `COMMANDS[slash].execute(...)`. Adding `/interrupt` (which the sprint 220 card mentions but does not name in the slash list) is one new file, not one new branch in a 163-line function.

Same shape argument as Q2 (dispatcher-turned-god-handler). Priority is lower — 163 lines is not 2,608 — but it is on the growth curve of the same class.

## Q12 — Delayed imports scatter across delegate.py, session_registry.py, cli.py, server.py.

`from substrate.topologies.session import UserMessage as SessionUserMessage` inside `_session_turn` (server.py:1133). `from substrate.topologies.tool_loop.delegate import _prefix_context_slice` inside `_build` (server.py:1147). `from ..session import UserMessage` inside `Tool.run`'s path-1 branch (delegate.py:450). `from substrate import _daemon` inside `_slash_route` (cli.py:1068). `import shutil` inside `_clear_runs` (server.py:889). `import os as _os`, `import signal as _signal`, `import threading as _threading`, `from substrate import _daemon` all inside `_repl` (cli.py:1228-1232).

Two reasons to import inside a function: circular-dependency avoidance and cost-of-import avoidance. The delegate.py case (comment: "lazily to avoid dragging session_topology into every tool_loop test") is the second — legitimate. The server.py cases and the cli.py cases are the first, and the class of fix is a small `types.py` or `protocols.py` at the seam. Circular imports mean the module graph has a cycle; the cycle is what wants attention.

Not urgent; each delayed import is a smell, not a bug. Ten sites total; a half-day cleanup once the modules-are-packages work of Q2/Q3 lands.

## Q13 — Sprint 224d card promises "delete `_agent_legacy`" but keeps `_agent_legacy` as `?legacy=true` opt-in.

`_agent_legacy` at server.py:1935 is a 133-line handler. Sprint card 224d titled "delete-agent-legacy-fallback." Reading the card body: the scope is delete the *fallback* (the `if _SESSION_REGISTRY is None: self._agent_legacy(q)` branch), not delete the handler itself. `_agent_legacy` stays and is reachable via `?legacy=true` per TECH-SPEC §7 line 690's "one release" deprecation window.

The card is correct; the file name mis-labels the work ("delete-agent-legacy-fallback" reads as "delete _agent_legacy fallback function"; the scope is "delete the silent-fallback branch"). Minor. A better slug would have been `sprint-224d-delete-silent-legacy-fallback.md`.

**Cost.** One rename. Or leave it — the audit-trail rule 12 prefers stability, and the card body is clear about scope.

## Q14 — The E402 import cluster in `session/transcript.py:56` is sprint 224a's own drift.

Sprint 224a extracted kind constants into `session/vocabulary.py`. `transcript.py` at line 56 imports from that module, but the import lands *below* a module docstring / prose comment block (lines 40-55). Ruff catches it; the noqa is not there. The one violation ruff surfaces at review open.

Two lines fix it: move the docstring above the import, or `# noqa: E402` if the prose-then-imports order is deliberate (per PEP 8, imports go before code but after docstring — the file has a comment block masquerading as a docstring, which E402 legitimately flags).

**Cost.** One file edit.

---

## Positive checks worth naming

- The kernel is small. `kernel/runtime.py` at 887 lines, `sequencer.py` at 441, `topology.py` at 408, `composition.py` at ~200. Each is one concept; each is properly guarded (Q7 aside). The `RunPhase.FAILED` / `kernel_error` / `_try_record_kernel_error` shape at runtime.py:242-249 is exactly the "record the kernel error on the log if the record exists" honest posture that Q6's server.py `except: pass` sites lack.
- Constants extraction (`constants.py`) closed 22 files' worth of retyped lifecycle literals cleanly. Only one stray in production code (`cli.py:1024`, SDD review F7).
- `msgspec.Struct` typing on the session vocabulary catches shape drift at construction; the concern (SDD F5) is kind-name-string drift, not payload-field drift.
- `pyproject.toml` is clean, `py.typed` shipped, `[project.scripts]` names one entry (`substrate = "substrate.cli:main"`). Distribution is disciplined.
- Full test suite runs 1,093/5/0 in 257 s on the local box. That is a real suite, not a smoke, and it runs fast enough that the mypy-strict + ruff gate can be added to the local CI without slowing the loop.
- Zero TODO/FIXME/XXX/HACK comments in `src/` or `substrate-ui/`. That is unusual and worth naming — either the discipline is holding or the comments got compacted out. Cross-checking against KIT_DIARY: real defects have real closure entries, so I read the zero as discipline holding.

---

## Verdict

The code is not sloppy. It is *maturely bloated*. The kernel is small and honest; the surface (server.py, session_registry.py, cli.py, delegate.py) has grown past the point where per-sprint sweet-spot discipline can catch aggregate module bloat. Q1 is the one hard bug (the mypy claim vs reality) and it is the exact class the memory `be-your-own-skeptic-green-is-not-proven` warns about. Q2-Q3 is the load-bearing refactor before piece G roots more UI code on top of a 2,608-line handler and a 1,232-line registry. Q4 folds into the SDD review's F2. Q5-Q13 are gradual hygiene, none blocking.

Ratify or reject the sequence: fix Q1 (mypy), then Q7 (kernel one-line), then Q14 (ruff one-line) — three under-an-hour wins. Then Q2 + Q3 as the load-bearing refactor sprint chain. Q4 folds with the SDD F2 fix. Q5-Q13 as opportunistic hygiene during Q2/Q3.

---

*REVIEW-2026-08-28-code-quality.md. Ground truth: 1,093/5/0 pytest; 1 ruff violation; 10 mypy strict errors. Fourteen findings; three under-an-hour fixes, two week-scale refactors, the rest opportunistic. Kernel intact; surface bloated. Author: Claude session 2026-08-28.*
