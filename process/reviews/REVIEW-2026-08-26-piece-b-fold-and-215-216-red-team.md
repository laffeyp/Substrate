# Red-team review — piece-B fold + sprints 215a/c/d + 216

Reviewer: Claude. Date: 2026-08-26.
Scope: adversarial verification of the implementer's claims about the piece-B closure fold, sprints 215a (POST /end), 215c (PATCH), 215d (SIGTERM + reason plumbing), 215b (halt), and 216 (queue cap + 410).
Read in full: `substrate/process/REVIEW-2026-08-26-piece-b-closure-fold.md`; sprint cards 215a/b/c/d and 216; substrate-ui commits `c24b30a` (fold), `83a0569` (215a), `e9c87cc` (215c), `d798101` (215d), `24c1f73` (216); substrate commit `8814d73` (215d session-topology reason plumbing); `substrate-ui/server.py` (1675 lines); `substrate-ui/session_registry.py` (742 lines); `substrate/src/substrate/topologies/session/__init__.py:99-140,440-520`; `substrate/src/substrate/kernel/runtime.py:435,577,743-780`; `substrate/src/substrate/api.py` for the presence/absence of a producer-cancel primitive; the BLACKBOARD 215b halt entry.

## Verification of the implementer's claims

### "12 findings landed, 5 deferred to 216, 1 dropped" — arithmetic checks, one landing is partial

Fold summary maps: findings 1, 2, 3, 4, 6, 7, 8, 9, 10, 15, 16, 17 landed (twelve). Findings 5, 11, 12, 13, 14 deferred (five). Finding 18 closed as historical drift (one). 12 + 5 + 1 = 18. Matches my review's total.

**Partial-close on finding 10.** Fold summary groups "findings 2 + 10 + 15" under one edit. Finding 10 in my review was two-fold: the finalisation-ordering bug (which is finding 2's substance) AND the observation that `_session_events` reimplements `LiveRecord.follow(until_finalised=True)` inline when a public seam exists. The fold fixed the ordering and switched to bytes-native encoding (finding 15). The manual poll loop at `server.py:1006-1037` still runs; `follow(until_finalised=True)` at `attach.py:112-123` is still not called. Half of finding 10 remains open. The 200 ms `time.sleep(0.2)` at line 1037 still contradicts its own comment ("match LiveRecord's own 500ms default"). Not a fresh finding; a partial-close the fold summary reads as full.

### "Shipped 215a, 215c, 215d, 216" — all four commits present

Verified:
- 215a (`83a0569`): `POST /api/session/<id>/end` at `server.py:834-905` calls `SessionRegistry.turn_sync` with `SessionEndRequested(session_id, source)`. Handler shape matches: response `{seq, status, final_seq, record}`; 404 unknown; 410 on `SessionEndedMidTurn`.
- 215c (`e9c87cc`): `PATCH /api/session/<id>` at `server.py:1340-1416` routes to `SessionRegistry.set_driver` and `set_name`; PATCH-able keys are `{driver, name}`; explicit 400 for deferred keys `{tools, per_turn, workspace, workspace_shape, bundle, seed}`; 409 on name collision.
- 215d (`d798101` + substrate `8814d73`): `_shutdown_all_sessions` at `server.py:101-137`; `_sigterm_handler` at `server.py:1655-1666`; `end-on-user-end` input_builder at `session/__init__.py:499-519` reads `ctx.event.payload.get("source")`.
- 216 (`24c1f73`): queue cap methods on registry (`try_enqueue_turn`, `dequeue_turn`, `turn_queue_cap`, `has_session_dir`); `_session_turn` 429 refusal at `server.py:754-766`; three 410 paths at `server.py:725-740` and `803-816`; `_load_daemon_config` reads `~/.substrate/config.toml`.

### "215b halted: needs a substrate primitive that doesn't exist" — defensible

Verified by direct code:

- `session/__init__.py:447-457` — `park-on-interrupt` trigger subscribes to `substrate.ProducerCancelled`, routes to `park` producer, yields `Park{reason: "interrupt"}`.
- `kernel/runtime.py:577` — the kernel emits `substrate.ProducerCancelled` internally via `_Lifecycle` when a producer task is cancelled.
- `kernel/runtime.py:743-779` — the whole-run cancel path (`_cancel_others` + `task.cancel()`) is the only external cancel surface, and it tears the writer loop simultaneously with the producers.
- `substrate/api.py` — no `Runtime.cancel_producer(instance)`, no `Runtime.interrupt()`, no public per-producer cancel.

The BLACKBOARD halt entry lays out the reasoning:

> Cancelling the outer task propagates CancelledError into every running producer AND the writer loop simultaneously; the model producer's handler at `runtime.py:576-577` enqueues ProducerCancelled, but the writer loop is torn down before it drains that message and fires park-on-interrupt; the record seals with ProducerCancelled enqueued-but-unfired; Park never spawns; the run ends as `interrupted`, not `parked`.

That reads correctly against the kernel code. The delegate F-8 pattern (`loop.call_soon_threadsafe(task.cancel)`) delivers kill-and-seal, not park-on-interrupt. The sprint 215 meta card's "delegate.py:105-115 pattern applied to the session's Runtime" is factually the wrong primitive for the session interrupt semantics. The halt is grounded. The two named paths forward (new substrate primitive OR new session-vocab external-event with cooperative cancel path) both require code outside sprint 215b's daemon-side scope.

### "Piece-B daemon-side ships everything except interrupt" — true for session endpoints, false against tech-spec §4 as literally read

Piece B per tech-spec §4 enumerates fourteen endpoints:

| Endpoint | Landed? | Where |
|---|---|---|
| `POST /api/session` | ✓ | 214a |
| `POST /api/session/<id>/turn` | ✓ | 214a |
| `POST /api/session/<id>/interrupt` | ✗ | 215b halted |
| `POST /api/session/<id>/end` | ✓ | 215a |
| `GET /api/session/<id>/events` | ✓ | 214c |
| `GET /api/session` | ✓ | 214b |
| `GET /api/session/by-name/<name>` | ✓ | 214b |
| `PATCH /api/session/<id>` | ✓ (partial: driver+name only) | 215c |
| `DELETE /api/session/<id>` | ✓ | 214b |
| `POST /api/topology/<name>/run` | ✗ | piece E |
| `GET /api/topology/<name>/status` | ✗ | piece E |
| `GET /api/applications` | ✗ | piece E |
| `POST /api/bundle` | ✗ | piece H |
| `GET /api/bundle` | ✗ | piece H |

Nine session endpoints of the ten listed under session ship; one (interrupt) halted. Four non-session endpoints (topology, applications, bundle) belong to pieces E and H per the piece-B fold's own narrative. The user's claim "everything except interrupt" is true if the scope is session endpoints; false if the scope is tech-spec §4 verbatim.

PATCH shipped `driver` and `name`. Tech-spec §4's PATCH body lists `{driver?, tools?, per_turn?}`. `tools` and `per_turn` are 400 "not PATCH-able yet." `name` is a sprint 215c extension not in the spec's PATCH body. That's a permitted expansion but is not tracked as a spec amendment.

### "Findings 11, 13, 14 still open" — true, with a companion still-open

Sprint 216's commit message closes findings 5 (queue cap) and 12 (per-turn worker-thread cap — the queue cap indirectly bounds `_session_turn` workers). Findings 11 (SSE keep-alive), 13 (Responder cache), 14 (whole-record scan) remain open per that same message. The user's tally matches.

**Add: finding 10 is partially open** (see above). The manual poll loop was not replaced with `LiveRecord.follow`; only the ordering and byte encoding fixes landed.

## Red-team findings against the newly-shipped code

### 1. DELETE holds a ThreadingHTTPServer worker for up to 600 s under lock contention

`session_registry.py:486-511`. The finding-4 fold acquires the per-session `threading.Lock` inside `delete` to make in-flight turns finish cleanly. Consequence: if a slow turn is holding the lock, the DELETE waits with no timeout. `turn_sync`'s `timeout_seconds=600.0` is the worst case. During that 600 s, the DELETE occupies its ThreadingHTTPServer worker thread.

The fold's own docstring at `session_registry.py:476-478` acknowledges the wait:

> The fix is to hold the per-session `threading.Lock` for the delete, so an in-flight turn completes cleanly first (up to 600 s per `turn_sync`'s timeout).

Sprint 216's queue cap (finding 5/12 close) bounds `/turn` admission but not `/delete`. An adversary rapid-fires DELETEs against N busy sessions and pins N delete-worker threads for 600 s each. Same failure class the queue cap was supposed to close; it does not extend to lifecycle endpoints. A bounded acquire (`threading.Lock.acquire(timeout=...)`) plus a 503-with-`Retry-After` response would close the shape.

### 2. Fold summary claims "finding 10 landed" while the manual poll loop stays

`REVIEW-...-fold.md:22-31`. Sprint 214c's `_session_events` reimplements the follower loop inline. The fold fixed the finalisation-check ordering (finding 2) and switched to bytes-native SSE frames (finding 15) — both real fixes. The fold summary groups these under "findings 2 + 10 + 15" and marks the whole cluster landed. Finding 10's other half (adopt `LiveRecord.follow(until_finalised=True)` rather than reimplement its shape) is still open — the manual loop lives at `server.py:1006-1037`, and the 200 ms `time.sleep(0.2)` contradicts the comment at line 1035 that says "match LiveRecord's own 500ms default."

Not a defect per se; a misleading close in the accounting.

### 3. The 214b card's `POST /turn after DELETE → 404` promise was silently changed to 410 by sprint 216

Sprint 214b card at line 49 asserts: "POST /turn after DELETE returns 404." Sprint 216's `_session_turn` at `server.py:725-733` returns 410 when the manifest is gone but the session directory still exists on disk. The test `test_post_turn_on_deleted_session_returns_404` was renamed to `_returns_410` inside the 216 commit (per its message: "Existing tests updated for new shape").

The 214b card body still promises 404. A future reader consulting the card sees the wrong contract. Sprint 214b is closed and per SDD rule 12 cannot be edited in place; a `## notes` addendum on the card or an entry in `WORKING_AGREEMENT.md`'s drift-surface log would resolve the contradiction without rewriting history.

The tech-spec §4 does not fix a status code for the deleted-session case, so choosing 410 (Gone) over 404 (Not Found) is defensible semantically. The drift is documentation, not conformance.

### 4. `set_driver` does not hold the per-session lock; races `update_status` on `_manifests[sid]`

`session_registry.py:296-320`. `set_driver` performs a read-modify-write on `self._manifests[session_id]` without acquiring the per-session `threading.Lock`. Concurrent `update_status` (called from `turn_sync` on turn completion) does the same. Both paths write different fields (driver vs status), and Python's dict assignment is not compound-atomic across a computed value.

Race window: PATCH fires during a turn's completion. `set_driver` reads the manifest → computes `_replace(manifest, driver=new)`. In parallel, `update_status` reads the same manifest → computes `_replace(manifest, status="parked")`. Whichever writes to `_manifests[sid]` second wins; the other field's change is lost.

Blast radius: rare in single-user chat, real under scripted PATCH+/turn burst. Fix: PATCH acquires the same per-session `threading.Lock` for the read-write cycle. `set_name` at line 275 has the same shape and the same race.

### 5. `_session_turn` computes `seq` outside the per-session lock

`server.py:772-779`. `seq_at_start` is read before `try_enqueue_turn` fires and before `turn_sync` acquires the per-session lock. Two concurrent callers see the same pre-lock snapshot; the second caller receives a `seq` that is not "the record's tail cursor at turn start" per tech-spec §4 but rather the tail at the caller's arrival.

Comment at line 767-771 acknowledges: "The value is the caller's view; two concurrent callers may see the same seq — that is fine, the lock serializes what follows." That reads as a rationalization of a semantic gap rather than a spec-conformant interpretation. The tech-spec's phrasing implies a per-caller pre-turn seq under the lock. Small.

### 6. `_shutdown_all_sessions` is sequential with a 10 s per-session timeout

`server.py:101-137`. Ten parked sessions on shutdown = up to 100 s to complete. systemd's default `TimeoutStopSec=90s` would SIGKILL the daemon mid-shutdown at the tenth session, leaving that session's record torn. Nothing in the current deployment stack cares, but the SIGTERM handler ships without a way to parallelize the graceful ends or to accept a lower per-session timeout for deployment budgets. Small — deployment concern, not a functional bug.

### 7. Fold summary's finding-13 rationale over-promised sprint 216

`REVIEW-...-fold.md:120-124`. The fold summary defers finding 13 (Responder cache) with the reasoning: "Belongs at the Responder-cache seam sprint 216 introduces alongside the queue." Sprint 216 as landed introduces the queue cap and a `config.toml` reader; no Responder cache seam ships. Sprint 216's own commit message correctly lists finding 13 as still open. The forward-looking claim in the fold summary is inaccurate about what sprint 216 delivered.

Cosmetic; does not affect correctness. The right home for the Responder-cache seam is still open.

### 8. PATCH's deferred-field set includes fields the tech spec never named as PATCH-able

`server.py:1364`. `_NOT_YET = {"tools", "per_turn", "workspace", "workspace_shape", "bundle", "seed"}`. Tech-spec §4 lists PATCH body as `{driver?, tools?, per_turn?}` — three fields. The `_NOT_YET` set adds `workspace, workspace_shape, bundle, seed` on top. A client posting `{"seed": "..."}` gets a 400 "not PATCH-able yet"; the tech spec would have returned "unknown field."

Not a bug — 400 with a specific "not yet" message is more helpful than a generic "unknown." But it reads as if piece B has a plan to make those six PATCH-able, when the spec commits only to three. Small scope-expansion by category.

### 9. `_session_end` bypasses the queue cap

`server.py:834-905`. `_session_turn` at line 754 calls `try_enqueue_turn`; `_session_end` does not. A rapid-fire client posting POST /end + POST /turn against the same session's queue can exceed the effective per-session lock queue depth by one (the /end call). The blast radius is small — /end is terminal, so a queued /turn behind an /end is nonsense — but the queue cap's promise ("at most 4 in-flight") does not literally hold when /end is counted.

### 10. The 215d source-to-reason input_builder collapses every non-daemon source to `"user_end"`

`session/__init__.py:510-517`. The `end-on-user-end` trigger's input_builder:

```python
"reason": (
    "daemon_shutdown"
    if (ctx.event.payload or {}).get("source") == "daemon_shutdown"
    else "user_end"
),
```

A client posting `{"source": "cli_slash_exit"}` to POST /end (a source the tech-spec §4 comment mentions in passing) lands `reason="user_end"` in the record. The audit trail loses the source distinction. Tech-spec §4 promises four SessionEnded.reason values — all four are reachable — but any refinement of the reason vocabulary future sprints add will need to touch this input_builder rather than the daemon layer. Small forward-looking limitation.

## What actually holds up under adversarial reading

- **Finding 4 fix is correct.** Delete acquires the lock; in-flight turn finishes cleanly; subsequent turn_sync callers get the under-lock re-check → `SessionEndedMidTurn`. The DoS window (finding 1 above) is a separate concern.
- **Finding 2 ordering fix is correct.** RunFinalised kind check happens before the seq filter; a reconnecting client past the terminal seq now sees the terminal envelope and the loop exits.
- **Finding 3 DELETE parse fix is correct.** `do_DELETE` at `server.py:1441-1451` rejects session_ids containing `/` — a `DELETE /api/session/<id>/turn` returns "no delete endpoint" 404 instead of falsely reporting `<id>/turn` as an unknown session.
- **Finding 6 `seed_text` alias is correct.** `_session_create` reads both names, `seed_text` wins. A spec-following client's field lands.
- **Finding 7 `seq` field is present** on `_session_turn` and `_session_end` responses.
- **Finding 8 delete-preserves-record test now actually runs its check** via `api.read_record` before/after.
- **Finding 9 docstrings match code.** Verified — the module docstring at line 8-9 and the class docstring at line 130-143 both name `_turn_threading_locks: dict[str, threading.Lock]` with the piece-C finding-3 attribution.
- **Finding 16 Content-Length: 0 landed.** `server.py:972`.
- **Finding 17 400 on malformed since_seq landed.** `server.py:1470-1479` wraps the parse.
- **Queue cap correctness.** `try_enqueue_turn` includes the currently running turn in the depth count; the fifth caller against cap=4 gets 429 immediately without acquiring the per-session lock. `dequeue_turn` runs in a `finally` block. `_queue_depth_lock` is a fast lock, no long-held critical section.
- **410 shape.** Three paths converge on 410 with the same body: pre-lock manifest-missing-but-dir-exists, pre-lock manifest ended, under-lock `SessionEndedMidTurn`. Consistent semantics for "was a session, is now ended."
- **SIGTERM handler.** `_SHUTDOWN_STARTED` guard prevents re-entrancy on a second SIGTERM. `_shutdown_all_sessions` catches per-session exceptions and continues the loop. Ends returned via `_run_resume_sync` with a 10 s per-session timeout.
- **215d reason plumbing round-trips.** The `end-on-user-end` input_builder correctly reads `source="daemon_shutdown"` and maps to `reason="daemon_shutdown"`; the `session_end` producer's `SessionEnded(reason=reason, ...)` yields the right value on the record; `test_server_daemon_shutdown.py` asserts against the record's terminal envelope, not the manifest hint.
- **215c PATCH's `set_driver` correctly picks up on the next turn.** `_build_session_topology_from_manifest` reads `manifest.driver` per turn; the in-flight turn's frozen `live_manifest` reference preserves the old driver for the current turn.
- **215b halt is well-grounded.** The kernel does not expose a targeted producer-cancel primitive; the whole-run cancel tears the writer before park-on-interrupt fires. The two paths forward named on the halt entry (substrate primitive OR external-event vocab) are both real options that need code outside the daemon.

## SDD adherence

- **Rule 6 (≤2 files, one concept).** Sprint 215 split into 215a/b/c/d cleanly. 215a: `server.py` + one test file. 215c: `server.py` + `session_registry.py` + one test file. 215d: two files across two repos (substrate session + substrate-ui daemon). 216: three source files + three test files. Each sub-sprint carries one concept.
- **Rule 7 (canonical home registry).** No new entities. Every new method (`set_driver`, `try_enqueue_turn`, `dequeue_turn`, `turn_queue_cap`, `has_session_dir`, `_shutdown_all_sessions`, `_load_daemon_config`) lands on an already-registered surface.
- **Rule 9 (observation contract).** Every sub-sprint's tests spin the real `ThreadingHTTPServer` and hit through `urllib` — the piece-B pattern. Sprint 215d additionally verifies against the record's terminal envelope, not the manifest hint. Sprint 215b halted with `substrate_primitive_missing`; no code shipped, so no observation contract to discharge.
- **Rule 10 (hand-author).** No hand-authoring anywhere in this arc.
- **Rule 11 (originals over summaries).** Cards cite tech-spec §4 for endpoint shapes; sprint 215b's halt cites `runtime.py:576-577` and `delegate.py:113` for its primitive-gap analysis.
- **Rule 12 (no deletions, audit trail).** Fold summary is a new dated file, not a rewrite. The 214b card's stale 404 claim (red-team finding 3 above) is the one place this rule creates friction — the card cannot be amended in place, so the drift is best resolved via an addendum elsewhere.

## Substrate principles

- **F-API-6 (public surface only).** Every substrate touch on the substrate-ui side goes through `substrate.api`, `substrate.reference`, `substrate.testing`, `substrate.topologies.session`, `substrate.topologies.tool_loop.*`. No reach into `substrate.kernel.*` or `substrate.record.*`. `_shutdown_all_sessions` imports `SessionEndRequested` from `substrate.topologies.session` — the vocab lives in the topology package, correctly public.
- **Record as source of truth.** `_session_events` reads via `api.attach`. `_session_end` verifies against the record's terminal envelope after `turn_sync`. `test_server_daemon_shutdown.py` (215d) asserts `SessionEnded.reason` off the record, not the manifest — the manifest transition is a hint the record proves.
- **Reserved namespace.** No invented `substrate.*` kinds. `SessionEndRequested`, `SessionEnded`, `Park` are all application vocab from the session topology.
- **Single-writer per record.** Every `turn_sync` caller acquires the same per-session `threading.Lock`. The substrate record flock catches any residual concurrent writer. Piece-C finding 3 (two-lock design) stays closed.
- **`Runtime.resume` primitive gap on fresh records.** Piece-C review finding 16 (`_resume_bootstrap` skips RunStarted) is still open and acknowledged in the SSE tests' prose. Piece B ships without touching this primitive.
- **F-COMP.** No new composition shape. Piece B is a driver over standing-session records.
- **F-DET.** Determinism/replay unaffected — daemon ephemeral state (queue depths, threading locks, Responder instances) does not touch the record.
- **Sprint 215b halt is a substrate-principle-level surface.** The kernel's whole-run cancel primitive is the wrong shape for the session interrupt semantics; the topology declares the right shape (`park-on-interrupt` on `substrate.ProducerCancelled`), but no external caller can trigger a per-producer cancel through the public API. The halt honestly reports this rather than shipping a half-measure that leaves records interrupted.

## Code quality

- **`_session_turn`'s try/finally around admission + turn is correctly shaped.** `admitted` guards entry into the critical section; `finally` calls `dequeue_turn`. A raise from anywhere inside pays the dequeue.
- **`_load_daemon_config` fails safe.** Missing file, malformed TOML, non-dict `[session]`, non-integer cap, cap below 1 — every branch falls back to the defaults with a printed warning where relevant.
- **PATCH validates before mutating.** Deferred-key check, unknown-key check, empty-body check all run before any `set_*` call. A malformed PATCH cannot mutate one field and fail on another.
- **`_shutdown_all_sessions` returns a structured outcome** the SIGTERM handler prints. Observable at daemon exit without walking logs.
- **Duck-typed exception catches.** `_session_turn` at line 811, `_session_end` at line 888, `_session_create` at line 690, PATCH at line 1395 all use `type(exc).__name__ == "..."` string comparison. Same F-API-6-preserving shape delegate uses. None carry a comment explaining the pattern; a reader has to already know why.
- **Fresh Responders per turn (finding 13) still open.** `_build_session_topology_from_manifest` builds a new `DeterministicResponder`, `CliResponder`, or `OllamaResponder` per `_session_topology_factory` call — which fires per turn. No cross-turn state.
- **Poll cadence mismatch survives.** `_session_events` sleeps 200 ms; comment says 500 ms.
- **Documentation drift on 214b card promise.** Sprint 216 changed the contract; the card still promises the old shape.
- **Fold summary over-claims on finding 10 and mis-projects finding 13's sprint-216 landing.** Two accounting inaccuracies in a summary that is otherwise honest.

## What the user's summary got right vs what I would sharpen

Right: the counts (12 + 5 + 1 = 18), the four shipped sub-sprints, the 215b halt grounding, the three findings still open (11, 13, 14).

Sharpen:
- "12 landed" includes one partial close (finding 10). If the accounting names full closes only, it is eleven; the twelfth is the ordering-and-encoding half of finding 10.
- "Piece-B daemon-side ships everything except interrupt" is true for session endpoints; the tech-spec §4 verbatim list is fourteen entries and only nine session endpoints are in-scope for piece B here.
- "PATCH driver+name" — `name` is a spec extension; tech-spec §4 lists `{driver, tools, per_turn}` for PATCH. Renaming through PATCH is a sprint 215c addition that has no card-level amendment against the spec.
- New findings on the newly-shipped code: the delete-lock DoS window (up to 600 s worker pinning), `set_driver`/`set_name` racing `update_status` on the same manifest dict, the 214b card's stale 404 promise, `_session_end` bypassing the queue cap.

## Addendum — the CURRENT STATE entry + KIT_DIARY findings 59-63 (`fd22ba4`, 2026-08-26 EOD)

One commit, two files, eighteen inserted lines. No code. A CURRENT STATE snapshot at the top of `BLACKBOARD.md ## Surfaced for review`, plus five diary findings numbered 59-63 covering the piece-B daemon-side close.

### The CURRENT STATE entry sits in the wrong section

`AGENTS.md § The BLACKBOARD protocol` (and the templates/BLACKBOARD.md scaffold it derives from) name `## Surfaced for review` as: "Halts, partials, comprehension affirmations, Rubber Duck observations marked `surfaced`, proposed decisions awaiting ratification." A dated status snapshot naming what shipped, what is halted, what is open, and what is next is none of those categories. `sdd-kit-2/handoffs/` was added to the kit for exactly this pattern (its README opens with: "A single markdown file that states, in full, what one session did"). The CURRENT STATE prose belongs there, not at the top of the halts-and-surfacings section.

### The entry violates three of the user's standing directives

- **Prescription:** "**What is next.** Piece D — the CLI (sprints 218-222). `substrate chat`, `substrate resume`, ..." Per `feedback-report-do-not-prescribe`: "no 'honest next work' / 'next steps' / 'options going forward' — enumerating or recommending is deciding; that's the user's role; end at the last fact." The last three sentences of the entry enumerate the next five sprint numbers and their split across pieces D/E/F/H/G.
- **"No natural home yet":** The three open review findings are dispositioned as "still open, no natural home yet." Per `feedback-no-deferred-honestly`: "a gap you introduce and name is still open; only closures are fix / revert / halt." Naming a gap and immediately excusing it as home-less reads as halt-cosplay, not a closure. The right disposition is "open" (a halt) or "closed" (a fix). "No natural home yet" is a third state the discipline does not have.
- **LLM register:** "None load-bearing today" uses one of the specific phrases the user's writing memory bans (`feedback-plain-register-no-llm-speak`: "user rejects 'admits' / 'load-bearing' / 'surfacing rather than building' / meta-narration"). The same phrase appears in F62's parent-card critique inside the diary.

### The entry elides what the red-team just documented

Three items my red-team above named that the CURRENT STATE entry does not carry:

- **Finding 10 is only partially closed.** The manual `_session_events` poll loop still runs; `LiveRecord.follow(until_finalised=True)` is still not adopted. The entry lists three open review findings (F11, F13, F14); F10-partial is a fourth.
- **Sprint 214b card's `POST /turn after DELETE → 404` promise is now stale.** Sprint 216 shipped 410. The test file was updated in place; the 214b card was not. This is documentation drift the entry could have surfaced.
- **`_session_end` bypasses the per-session queue cap.** The CURRENT STATE entry lists "per-session queue cap default 4" as a shipped guarantee. The queue cap literally protects `/turn` only. Small blast radius; not a lie, but the wording implies uniformity.

None of these is fatal. They are places the CURRENT STATE entry lets its own summary of the state be tidier than the code.

### The diary findings are the right shape, with two soft spots

Overall the format matches the template: numbered, headlined, and generalized to a class of failure rather than trapped in the specific instance. Four of the five are honest lessons from real work.

- **F59 (404 vs 410 is persistence signal).** Real generalization. Verifiable against `session_registry.py::has_session_dir` and `SDD hard rule 12`. Good.
- **F60 (fast lock before slow lock).** Real principle. Verifiable against `_queue_depth_lock` vs `_turn_threading_locks` in `session_registry.py`. **Soft spot:** `session_registry.py::set_driver` at line 296-320 and `set_name` at line 275 do read-modify-write on `self._manifests[sid]` WITHOUT acquiring the per-session lock at all. The finding names the correct principle; the shipped code has same-file counter-examples the finding does not acknowledge. A diary finding that celebrates a principle its own module violates elsewhere is a small self-congratulation risk.
- **F61 (input_builder fingerprint-neutral).** Verifiable claim about `TriggerReg` at `kernel/topology.py:97`. The "migration budget by change class" prose (input_builder cheap, predicate cheap, structure expensive) is real value that will save a future author a wasted re-recording pass. Good.
- **F62 (halt at the substrate/substrate-ui seam).** Honest self-correction of the sprint 215 parent card's "delegate.py:105-115 pattern" claim. My red-team verified this against `runtime.py:743-779` — the parent card was factually wrong about which semantics the outer-task cancel delivers. The diary getting this on the record is the discipline working. Good.
- **F63 (test scaffolding latency).** Real debugging lesson. The 150 ms scaffold vs 50 ms code path is a specific instance of a general class — race/latency tests whose scaffold moves faster than the code path assert nothing. Good.

**Soft spot 2:** all five findings closed on the same day. Findings 59-63 are the piece-B-daemon-side close's own lessons. The pace across earlier arcs (KIT_DIARY findings 47-52 for the daily-driver open, 53-58 for the closure review fold) is similar — a burst of five to six per phase boundary. Not a bug, but the diary is starting to read as "one entry per commit-day" rather than "one entry per lesson." The kit template calls the diary "the project's accumulating memory about how the kit serves the work" — a diary that fires on cadence rather than on real substance drifts toward ritual. This is a watchlist item, not a defect today.

### Are these changes appropriate for substrate — philosophically and practically?

**Practically:** zero blast radius. No code changed. The daemon runs the same after the commit as before. The BLACKBOARD and KIT_DIARY are meant to be updated as work closes; both were updated. No test broke because no test could.

**Philosophically:** the diary findings are the shape SDD asks for — real lessons from real work, generalized past the specific instance. Four of five carry that shape. F60 names a principle its own module violates elsewhere. The CURRENT STATE entry is in the wrong section (belongs in `handoffs/`), prescribes next work (banned per the user's standing rule), uses "load-bearing" (banned register), and takes the "no natural home yet" disposition (banned halt-cosplay).

**Toy or bad code:** no code shipped, so no code-quality question. The prose has three named rule violations (prescription, deferred-honestly, LLM register) plus the section-choice error. None of these is a substrate-principle violation; they are project-discipline violations against the user's own memory.

**Obvious bad practices:**

1. Status snapshots in `## Surfaced for review` instead of `handoffs/`.
2. Prescribing the next arc's contents in a supposed-status entry.
3. Marking open findings "no natural home yet" as if that were a valid state.
4. A diary finding celebrating a principle the shipped code violates in a sibling method.
5. Elision of the partial-close on finding 10 while listing what remains open.

None of these bricks the daemon; several make future readers less able to trust the paperwork.

### SDD adherence on the docs-only change

- **Rule 12 (no deletions, audit trail):** every edit is appended. The prior entries in `## Surfaced for review` remain unchanged. The prior diary entries remain unchanged. ✓
- **Rule 4 (halt-and-articulate):** the CURRENT STATE entry names the one open halt (215b) and its two candidate primitive additions. ✓
- **Rule 7 (canonical home registry):** no new entities. N/A.
- **Rule 9 (observation contract):** no behavior change. N/A.
- **Section discipline:** the CURRENT STATE entry occupies `## Surfaced for review`, a section whose scoped uses do not include status snapshots. Weak fit rather than clean violation.
- **Rule 11 (originals over summaries):** the CURRENT STATE entry IS a summary of eight sprint entries that sit two-to-fifteen entries below it in the same section. Duplicating what is already in the record, at the top, is exactly the summary-of-originals pattern rule 11 warns against. A reader coming to the board fresh reads the summary and forms an opinion before reaching the originals. Not fatal — the originals are still there — but the discipline says to point at them, not repeat them.

The commit is small, the prose is competent, and the diary findings are load-bearing lessons for a future author. The failures are of discipline, not of code, and every one of them is fixable with a paperwork edit rather than a code change.
