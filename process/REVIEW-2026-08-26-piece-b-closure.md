# Review — piece B, daily-driver arc (sprints 214a + 214b + 214c)

Reviewer: Claude. Date: 2026-08-26.
Scope: correctness of the discharge, SDD adherence, substrate-principle adherence, code quality across the four commits that closed piece B on the substrate-ui side (`754b857`, `877957c`, `e466150`) plus the piece-C review fold that landed alongside them (`ab62024` / `8bf9d13`).
Read in full: sprint cards 214, 214a, 214b, 214c; `substrate-ui/session_registry.py` (641 lines, post-fold); `substrate-ui/server.py` piece-B regions (module imports, `_daemon_driver_resolver`, `_build_session_topology_from_manifest`, `do_POST`, `do_GET`, `do_DELETE`, `_read_json_body`, `_session_create`, `_session_turn`, `_session_list`, `_session_by_name`, `_session_delete`, `_session_events`, `main`); every sprint-added test file (`test_server_session_create.py`, `test_server_session_turn.py`, `test_server_session_list.py`, `test_server_session_by_name.py`, `test_server_session_delete.py`, `test_server_session_sse.py`); `substrate/src/substrate/projections/attach.py` for the `LiveRecord.follow` seam the SSE endpoint reimplements; `substrate/src/substrate/topologies/session/__init__.py:150-224` for the `assembled_prompt` consumer; tech-spec §4 endpoint list + concurrency contract.

## What piece B ships

Six HTTP endpoints on `substrate-ui/server.py`:

- `POST /api/session` — `_session_create` (sprint 214a).
- `POST /api/session/<id>/turn` — `_session_turn` (sprint 214a). Runs one turn via `SessionRegistry.turn_sync`; computes next `turn_index` inside the per-session `threading.Lock` via a `resume_event_builder` closure.
- `GET /api/session` — `_session_list` (sprint 214b). Buckets by `live | parked | ended | interrupted`.
- `GET /api/session/by-name/<name>` — `_session_by_name` (sprint 214b).
- `DELETE /api/session/<id>` — `_session_delete` (sprint 214b). Removes manifest + by-name entry; leaves the record directory (SDD hard rule 12).
- `GET /api/session/<id>/events?since_seq=N` — `_session_events` (sprint 214c). SSE via `api.attach(record_root).read_new()` with a manual `time.sleep(0.2)` poll loop.

The piece-C review's finding 3 landed alongside: `SessionRegistry._locks: dict[str, asyncio.Lock]` and `lock_for` deleted; every `turn_sync` caller (delegate seam, POST /turn handler) acquires the same per-session `threading.Lock`. `turn_sync` grew `resume_event_builder` so record-derived state runs under the lock.

Tests: 22 new test cases across five files, all green in ~30s. Substrate-side full-suite regression 930 passed / 5 skipped / 0 failures. Ruff clean.

## Real findings

### 1. Piece B closes with six endpoints; TECH-SPEC §4 lists thirteen for piece B

Tech-spec §4 lists these endpoints under piece B:

```
POST   /api/session
POST   /api/session/<id>/turn
POST   /api/session/<id>/interrupt
POST   /api/session/<id>/end
GET    /api/session/<id>/events
GET    /api/session
GET    /api/session/by-name/<name>
PATCH  /api/session/<id>
DELETE /api/session/<id>
POST   /api/topology/<name>/run
GET    /api/topology/<name>/status
GET    /api/applications
POST   /api/bundle
GET    /api/bundle
```

Fourteen entries. Sprints 214a + 214b + 214c ship six: `POST /api/session`, `POST /api/session/<id>/turn`, `GET /api/session/<id>/events`, `GET /api/session`, `GET /api/session/by-name/<name>`, `DELETE /api/session/<id>`. Missing: `interrupt`, `end`, `PATCH`, both `topology` routes, `applications`, both `bundle` routes.

The BLACKBOARD entry for sprint 214c reads: "Piece B of the daily-driver arc closes. Sprints 214a + 214b + 214c ship the six endpoints TECH-SPEC §4 named for piece B." Tech-spec §4 names fourteen. The claim is untrue as written.

The sprint 214c card at line 14 is more careful: "Piece B closes with this landing (sprint 215 is a distinct piece — SessionEndRequested + PATCH + interrupt + shutdown)." That reads as a scope amendment — piece B has been quietly narrowed from "the daemon's session API" to "the read + create + delete subset," and `end`/`interrupt`/`PATCH` moved to sprint 215, with `topology`/`applications`/`bundle` presumably split to pieces E and H. The narrowing is not folded on any sprint card as an explicit scope amendment against tech-spec §4. Sprint 214 (meta) card at line 14 lists the same six endpoints as the actual landing, so the meta card's scope was already narrower than §4.

If piece B closes here, tech-spec §4's piece-B endpoint list needs an explicit annotation naming which endpoints moved to which piece. Otherwise a future reader consulting the spec will conclude the daemon is more capable than it is.

### 2. `_session_events` filter-then-check ordering hangs on RunFinalised past the caller's `since_seq`

`server.py:806-816`:

```python
for env in follower.read_new():
    seq = int(env.get("seq", -1))
    if seq <= since_seq:
        continue
    frame = ("data: " + msgspec.json.encode(env).decode() + "\n\n").encode()
    self.wfile.write(frame)
    self.wfile.flush()
    if env.get("kind") == "substrate.RunFinalised":
        finalised = True
        break
```

The seq filter runs before the finalisation check. A client reconnecting to a finalised session with `since_seq >= runfinalised_seq` hits the `continue` on every envelope, `finalised` stays `False`, and the outer `while not finalised:` loop polls forever at 200 ms until the socket times out at the client's end or the daemon shuts down.

`LiveRecord.follow(until_finalised=True)` at `attach.py:112-123` handles this correctly — it checks `env.get("kind") == "substrate.RunFinalised"` and returns from the generator without regard to any external cursor. The manual reimplementation dropped that ordering.

Fix: check the finalisation kind regardless of the filter, or use `follow(until_finalised=True)` (see finding 10).

### 3. `do_DELETE` matches every path under `/api/session/`, including sub-resources

`server.py:1129-1133`:

```python
if path.startswith("/api/session/"):
    session_id = path[len("/api/session/") :]
    self._session_delete(session_id)
    return
```

A `DELETE /api/session/s_x/turn` reaches this branch with `session_id = "s_x/turn"`. `SessionRegistry.delete("s_x/turn")` raises `KeyError`; the handler returns 404 with `unknown session_id 's_x/turn'`. Not a corruption bug; the DELETE is honestly refused. But the parsing is wrong: a DELETE against a sub-resource should be a 404 or 405 keyed on the sub-resource, not a 404 that pretends the sub-resource is a mangled session name.

The `do_POST` branches are more careful — they check `path == "/api/session"` for create and `path.startswith("/api/session/") and path.endswith("/turn")` for turn. The DELETE branch could apply the same shape: require `path.count("/") == 3` (namely `["", "api", "session", "<id>"]`) or reject any `session_id` containing `/`.

### 4. `SessionRegistry.delete` races with an in-flight `turn_sync`

`session_registry.py:383-411`. `delete` removes the manifest from `self._manifests` (line 409) and the threading lock from `self._turn_threading_locks` (line 410).

If `turn_sync` is in-flight for that session_id, the in-flight call is inside `_run_resume_sync` under the threading lock. It holds a local reference to the lock, so the `.pop` on `_turn_threading_locks` does not release its hold. When `_run_resume_sync` returns, `turn_sync` calls `self.update_status(session_id, new_status)` at line 367. `update_status` at line 372-375 reads `self._manifests.get(session_id)`; the delete already removed the entry; the check `if manifest is None: raise KeyError(...)` fires; the in-flight turn crashes with `KeyError` instead of completing cleanly.

The caller — either a POST /turn handler or a delegate — sees a mid-flight KeyError. The POST /turn handler at `server.py:686-693` wraps every exception into a 500 response; the delegate wraps `SessionEndedMidTurn` specifically but re-raises everything else, so the parent's ToolResult surfaces the KeyError text.

The race is narrow (delete during a running turn) but real. Options: hold delete on the per-session threading lock too (so the delete waits for the current turn to finish); mark the manifest `status="ended"` at delete time instead of dropping it from `_manifests`; or reshape `update_status` to be a no-op on a missing manifest instead of raising.

### 5. Tech-spec §4's per-session queue cap is not implemented

Tech-spec §4:

> Two POSTs to the same session queue in FIFO up to a per-session queue cap (default 4, matching `delegate.py:196`); fifth caller gets `{"ok": false, "error": "session queue full: 4 turns queued"}`.

The landed handler acquires the per-session `threading.Lock` unconditionally. N concurrent callers all block on the lock in FIFO order; the fifth caller waits behind the fourth rather than getting an immediate queue-full response. There is no queue-depth counter and no early rejection.

Sprint 216 is titled "queue cap 410," which suggests this is planned. Piece B closes anyway; the tech-spec §4 promise is deferred without a card-side amendment naming the deferral.

Practical blast radius today: a client that fires many concurrent /turn calls occupies many ThreadingHTTPServer worker threads for up to 600 seconds each (see finding 12). The queue cap is what prevents that from turning into a resource exhaustion under load.

### 6. `POST /api/session` body accepts a subset of the tech-spec §4 fields

Tech-spec §4 request body:

```json
{
  "driver":     "kimi-k2.6:cloud",
  "workspace":  "/path/to/repo",
  "bundle":     "team-review",
  "role":       "reviewer",
  "name":       "reviewer",
  "tools":      ["read_file", "grep"],
  "isolate":    false,
  "seed_text":  "review this PR"
}
```

`_session_create` at `server.py:595-600` reads: `driver`, `name`, `workspace`, `workspace_shape`, `seed`, `bundle`. Missing: `role`, `tools`, `isolate`. Field-name drift: `seed` in the handler vs `seed_text` in the spec (payload `seed` and `seed_text` are different names for the same field, so a client following the spec's body shape sends `seed_text` and the handler silently reads `""`).

`role` is load-bearing per §1.6.5 role resolution — a session created without role handling falls back to whatever default the topology carries. `tools` gates the tool suite (a `--read-only` session per the tech spec cannot be constructed here). `isolate` gates Mode 3 workspace shape.

`workspace_shape` in the handler is not in the spec — the spec derives it from the presence of `workspace` and `isolate`, not from a body field. Small.

### 7. `POST /api/session/<id>/turn` response shape drifts from tech-spec §4

Tech-spec §4 response: `{"seq": 42, "status": "paused" | "running" | "finalised" | "failed", "final_seq": 84?}`. The handler at `server.py:698-704` returns `{"status", "final_seq", "record"}`. Missing: `seq` (the current seq at turn start). Extra: `record` (the record root path).

Client contract drift: a client following the spec looks for `seq` and does not find it.

### 8. `test_delete_leaves_the_record_directory_intact` never runs its record-content check

`test_server_session_delete.py:104-106`:

```python
envs_before = list((record_root / "events-000001.jsonl").read_bytes()) if (
    record_root / "events-000001.jsonl"
).exists() else None
```

Substrate records are named `events-NNNNNN.open.jsonl` while hot and `events-NNNNNN.sealed.jsonl` after seal (per `substrate/projections/attach.py:42-47`: `events-NNNNNN[.open].jsonl`). Neither shape is bare `events-000001.jsonl`. The `.exists()` check evaluates to `False`; `envs_before` is `None`; the `if envs_before is not None:` guard at line 113 skips the meaningful check.

The test passes on the two remaining assertions (`not manifest.exists()` and `record_root.exists()`) — but the load-bearing "record content unchanged" check that the SDD-rule-12 audit-trail invariant depends on never runs.

Fix: iterate the record via `api.read_record(record_root)` before delete, capture the envelope list, and diff against the same iteration after delete. `api.read_record` is the canonical shape.

## Smaller items

### 9. session_registry.py module + class docstrings still promise the removed `asyncio.Lock` map

Lines 8-9:

> In-memory name → session_id + per-session `asyncio.Lock` map + the manifest for every session on disk.

Lines 130-134:

> Owns three pieces of state: ... `_locks`: dict[str, asyncio.Lock] — one lock per session for turn serialization ...

The finding-3 fold removed `_locks` and `lock_for` from the code (line 162 replaces the two-lock design with just `_turn_threading_locks`). Neither docstring got updated. A fresh reader looking for the asyncio lock finds a promise that does not deliver.

### 10. `_session_events` reimplements `LiveRecord.follow(until_finalised=True)` inline

`server.py:800-824` runs a `while not finalised: for env in follower.read_new(): ... time.sleep(0.2)` loop. `LiveRecord.follow(until_finalised=True)` at `attach.py:112-123` runs exactly that loop, with cleaner ordering around the finalisation check (see finding 2) and using `LiveRecord`'s own `POLL_INTERVAL_MS` default (500 ms per the docstring) instead of the handler's hardcoded 200 ms. Two different poll cadences and two different orderings for the same job; one of the two has the finding-2 bug.

Fix: call `follow(until_finalised=True)` and let the seam handle both concerns.

### 11. SSE endpoint sends no keep-alive comments during idle

A session that produces no envelopes for minutes stays open on the socket with silence over the wire. Any proxy in front of the daemon with an idle timeout closes the connection; the client's `EventSource` sees a mid-stream close instead of a clean SSE heartbeat. Standard fix: emit `: ping\n\n` (an SSE comment; clients ignore) every ~15-30 s inside the poll loop. Not currently needed — no proxy — but the endpoint's contract with a real deployment is silent about this.

### 12. `POST /api/session/<id>/turn` has no worker-thread cap

`server.py:684` sets `timeout_seconds=600.0` per call. Every /turn holds a ThreadingHTTPServer worker for up to ten minutes. N concurrent slow turns pin N threads; `ThreadingHTTPServer` spawns a fresh thread per request without a hard cap. The `_launch` handler has `MAX_LIVE_RUNS` at line 507 (checked in `_at_run_capacity`); the /turn handler has no equivalent.

Under sustained load the daemon will grow threads until the host runs out. The tech-spec §4 queue cap (finding 5) is what closes this; without either, the daemon is a target for a slow-drain resource exhaust.

### 13. `_daemon_driver_resolver` builds a fresh Responder per turn

`_build_session_topology_from_manifest` at `server.py:80` calls `_daemon_driver_resolver(manifest.driver)` every time it fires, which happens once per POST /turn via `SessionRegistry.turn_sync`. `OllamaResponder` and `CliResponder` are constructed fresh — no HTTP client pooling, no CLI subprocess reuse, no rate-limiter state carried across turns. `deterministic` fires `DeterministicResponder(seed=0)` on every call — the seed is fixed, so the deterministic driver's state is identical per turn, but any state a real driver would carry across turns (rate-limit counters, retry backoff, connection pool) does not survive.

Not a bug for the current adapter set — none of them carry cross-turn state — but the seam is set up in a way that would silently break the moment one does.

### 14. `_session_turn` scans the entire record to compute `next_turn_index`

`server.py:664-670` iterates `api.read_record(record_root_locked)` and reads every UserMessage envelope to find the tail turn_index. For a 100-turn session, that is 100+ UserMessage payloads read on every turn. Same shape as the delegate's `parent_seq_at_call` (piece-C review finding 13 — deferred).

The substrate's record API has tail-seek primitives per WORKING_AGREEMENT.md's canonical-home rows. Reading forward from `LiveRecord`'s cursor or from a reverse-scan would give the tail without an O(n) walk.

### 15. Line 811 encodes/decodes/reencodes each SSE frame

`frame = ("data: " + msgspec.json.encode(env).decode() + "\n\n").encode()`. `msgspec.json.encode` returns bytes; `.decode()` renders to str; `+` string-concatenates; `.encode()` re-encodes to bytes. A byte-native shape reads: `b"data: " + msgspec.json.encode(env) + b"\n\n"`. Micro-efficiency and one fewer round trip.

### 16. `_session_delete` sends 204 without an explicit `Content-Length: 0`

`server.py:767-768` calls `self.send_response(204)` and `self.end_headers()`. HTTP 204 responses must not carry a body; some clients tolerate the missing `Content-Length` header, some do not. `http.server`'s default `send_response` writes `Connection: keep-alive` in HTTP/1.1 without a length; that ambiguity is handled by some clients as "read until close" which stalls a keep-alive session. Adding `self.send_header("Content-Length", "0")` before `end_headers()` closes the ambiguity.

### 17. `_session_events` does not validate `since_seq` before `int(...)`

`server.py:1152-1153`:

```python
since_seq = int(parse_qs(urlparse(self.path).query).get("since_seq", ["-1"])[0])
```

A caller passing `?since_seq=abc` triggers `ValueError` on `int("abc")`, which the outer `do_GET`'s `except Exception` at line 1196 catches and returns as 500. HTTP contract says a malformed query parameter is 400, not 500.

### 18. Sprint 214a card cross-references stale `asyncio.Lock` terminology

Sprint 214a card at line 45 (assertions): "Two concurrent POST /turn on the same session serialize on the per-session `asyncio.Lock`." The whole sprint's premise (finding-3 fix) is the removal of `asyncio.Lock`. Small cross-reference drift in the card body that survived the fold.

## SDD adherence

- **Rule 6 (≤2 files, one concept):** Sprint 214 as originally scoped touched `server.py` + 7 test files + inherited six review-deferred findings. Split into 214a (create + turn + finding-3 lock unification), 214b (list + by-name + delete), 214c (SSE events). Each sub-sprint carries one concept. The split is documented on every card.
- **Rule 7 (canonical home registry):** No new entities. `SessionRegistry` and the two persistent artifacts (by-name.json, manifest.json) already registered from sprint 211. Piece B is behavior over an existing catalog, not a new catalog.
- **Rule 9 (observation contract):** Sprint 214a's card explicitly rescopes the subprocess-daemon end-to-end harness to sprint 214d ("queued"); every sub-sprint substitutes an in-process `ThreadingHTTPServer` + `urllib` shape that hits the real handler + real registry + real `Runtime.resume`. Honest rescope, folded on the card. The SIGKILL/restart test defers to sprint 222 (CLI wiring).
- **Rule 10 (hand-author):** No hand-authoring.
- **Rule 11 (originals over summaries):** Sprint cards cite tech-spec §4 endpoint lists + concurrency contract; delete-preserves-record cites hard rule 12.
- **Rule 12 (no deletions):** `DELETE /api/session/<id>` explicitly preserves the record directory. `SessionRegistry.delete` docstring names hard rule 12 as the reason. `test_delete_leaves_the_record_directory_intact` locks the intent, though the specific check falls short (finding 8).
- **Discipline drift on scope:** finding 1 — piece B closes with the six endpoints the meta card names, not the fourteen tech-spec §4 lists. The narrowing is honest at the sprint level and drifted at the BLACKBOARD level.

## Substrate principles adherence

- **F-API-6 (public-surface-only imports):** `server.py` imports `substrate.api`, `substrate.reference`, `substrate.topologies.session`, `substrate.topologies.session.transcript`, `substrate.topologies.tool_loop.tools`, `substrate.topologies.tool_loop.delegate`, `substrate.topologies.bundled`. Every touch is through a public re-export module. No reach into `substrate.kernel.*` or `substrate.record.*`. `session_registry.py` imports `substrate.api` only, plus `msgspec` as a stated dependency. Clean.
- **Reserved `substrate.*` namespace:** No invented reserved kinds. `UserMessage`, `ModelReply`, `FinalAnswer`, `Park` are application vocab from the session topology. `substrate.RunFinalised` is checked for stream termination — read-only.
- **Record as source of truth, manifest as hint:** The SSE handler reads via `api.attach` — the substrate follower primitive. The turn handler computes `next_turn_index` from the record's own tail (under the per-session lock, so two concurrent callers see two distinct tail states). The delete handler removes the manifest hint and preserves the record. Finding 4's race is a coordination bug at the handler layer, not a substrate-invariant break — the record's own flock catches concurrent writers under it.
- **Single-writer per record:** The `turn_sync` per-session threading lock plus substrate's own record flock give two layers of protection. Piece-C review's finding 3 collapsed the earlier two-lock design (one threading, one asyncio) to a single primitive, so every caller passes through the same lock now. `_session_turn`'s `resume_event_builder` runs under that lock so record-derived state is atomic with the write.
- **F-COMP (composition):** No new composition shape. Piece B is a driver for existing standing sessions, not an embedded_substrate producer.
- **F-DET (determinism / replayability):** Replay reads the record. Daemon-side ephemeral state (fresh Responders per turn, in-memory catalog) does not touch the record. Level-3(a) replay is unaffected. Finding 13's fresh-Responder-per-turn is an efficiency shape, not a determinism shape.
- **`Runtime.resume` primitive gap acknowledged, not shipped:** Piece-C review finding 16 (`_resume_bootstrap` does not write `substrate.RunStarted` on a fresh record) is deferred to sprint 215 or 216. Sprint 214c's SSE test carries a prose note calling out the gap and adjusts its assertion to not depend on `RunStarted` in the SSE backlog. Honest defer.

## Code quality

- **Exception hygiene:** Broad `except Exception` in `do_POST`, `do_GET`, `do_DELETE` with `noqa BLE001` and server-side traceback logging + client-side typed 500. Consistent. `_session_events` catches `(BrokenPipeError, ConnectionResetError, OSError)` for client-hangup — the correct set for a socket write.
- **Cross-boundary duck-typing:** `_session_create` at line 614 catches by `type(exc).__name__ == "NameCollision"`; `_session_turn` at line 687 catches by `type(exc).__name__ == "SessionEndedMidTurn"`. Same F-API-6-preserving shape delegate uses. Not commented — the reader has to already know the pattern. Delegate's version carries a comment; this one doesn't.
- **Docstring accuracy:** `session_registry.py`'s module and class docstrings still describe the removed asyncio.Lock map (finding 9). The finding-3 fold updated the code but not the prose. Elsewhere the docstrings are honest (e.g., `_session_delete` names hard rule 12).
- **Test hygiene:** `test_delete_leaves_the_record_directory_intact` guard evaluates to False on the actual record filename convention (finding 8). Other tests use F-API-4 primitives (`assert_event`, `assert_no_event`) per TECHNIQUE #38 — sprint 214c's SSE tests plug the parsed frame list directly into `assert_event` without a synthetic record, which is the intended shape.
- **Efficiency:** Fresh-Responder-per-turn (finding 13); full-record-scan for `next_turn_index` (finding 14); encode/decode/reencode round trip per SSE frame (finding 15); 200 ms vs 500 ms poll cadence mismatch (finding 10). None are load-bearing today; all are shape choices that would matter under sustained use.
- **Dead / duplicated code:** `_session_events`'s manual poll loop duplicates `LiveRecord.follow` (finding 10). Otherwise nothing dead.
- **Structure:** `server.py` at 1329 lines carries the static file server, records API, records projections, agent seam, launch/resume handlers, delegate observation seam, worktree diff, assays index, and the six session endpoints. A future split into `server_session.py` for the piece-B surface would let each concern read as its own module. Not a defect — a hygiene note.
- **Naming:** `_session_events` reads as "list session events" (a REST-y collection GET) rather than "stream session events." `_session_stream` or `_session_events_sse` would name what it is. Small.
- **What reads well:** The `_daemon_driver_resolver` / `_build_session_topology_from_manifest` split — one seam names the driver mapping, the other names how a session is rebuilt per turn. `_session_delete`'s docstring names the SDD rule 12 reason for preserving the record inline. `_session_turn`'s `resume_event_builder` closure keeps the tail-read atomic with the write via one clean seam, and the concurrent-turn test locks the invariant. `test_by_name_survives_url_encoding` covers a real hazard — the space-in-name case that a naïve router would drop. The SSE test's `_read_sse_frames` helper documents the `read1` vs `read` distinction that a first-time SSE reader will hit.

## Test coverage vs contract

Sprint 214c's `test_sse_streams_backlog_when_session_already_has_events` explicitly does NOT assert `substrate.RunStarted` in the backlog, and the test body carries a prose note explaining why — the piece-C review finding 16 gap at `runtime.py:409`. Honest.

Sprint 214a's `test_two_concurrent_turns_on_same_session_serialize` accepts either arrival order but asserts both concurrent texts land at distinct `turn_index` values (0 and 1) — the finding-3 + builder-under-lock guarantee. This is the load-bearing race test for the whole piece.

Sprint 214b's `test_delete_leaves_the_record_directory_intact` locks the intent of SDD rule 12 but never actually verifies record content unchanged (finding 8). The dir-existence half of the check still runs; the content half is dead.

`test_server_session_lock_serialises.py` from the sprint 214 meta card's Tests list did not land. The equivalent behavior is covered by `test_two_concurrent_turns_on_same_session_serialize` inside `test_server_session_turn.py`. Same coverage, different file location than the card names.
