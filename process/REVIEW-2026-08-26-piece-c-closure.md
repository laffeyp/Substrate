# Review — piece C, daily-driver arc (sprints 211 + 212 + 213a + 213b)

Reviewer: Claude. Date: 2026-08-26.
Scope: correctness of the discharge, SDD adherence, code style, substrate-primitive use across the four commits that closed piece C (`16537e8`, `5c98594`, `1714a56`, `ce2bce6`).
Read in full: `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §5 + §1.6.5 + §1.8; `substrate/process/sprints/sprint-{211,212,213,213a,213b}.md`; `substrate/process/WORKING_AGREEMENT.md` canonical-home rows; `substrate/process/BLACKBOARD.md` piece-C surfacings; `substrate-ui/session_registry.py` (568 lines); `substrate-ui/server.py` boot hook + `_agent_models`; `substrate/src/substrate/topologies/tool_loop/delegate.py` (592 lines); `substrate/src/substrate/topologies/tool_loop/tools.py`; every sprint-added test file across both repos (`test_delegate_backwards_compat.py`, `test_delegate_schema_six_fields.py`, `test_delegate_per_call_{model,context,baseline,child_session_name}.py`, `test_delegate_provenance.py`, `test_delegate_via_standing_session.py`, `test_delegate_session_ended_mid_delegate.py`, `test_session_manifest_survives_daemon_restart.py`, `test_session_registry_{by_name,name_collision}.py`).

## What piece C ships

`substrate-ui/session_registry.py` holds an in-memory catalog of standing sessions, an on-disk name index at `~/.substrate/sessions/by-name.json` guarded by `fcntl.flock` on a stable `.by-name.lock` sibling, a per-session manifest at `~/.substrate/sessions/<session_id>/manifest.json`, a boot scan that reclassifies status against the record's last envelope, and a `turn_sync` seam that drives one `Runtime.resume` in a worker thread under a per-session `threading.Lock`. `substrate/src/substrate/topologies/tool_loop/delegate.py::make_delegate` grew three constructor kwargs (`session_registry`, `parent_session_id`, `parent_record_root`) and one resolver kwarg (`model_resolver`); `Tool.run` dispatches four ways against a six-field JSON schema carrying `x-args-passthrough: true`; provenance rides on every child's `substrate.RunStarted.baseline` via a `_with_baseline` wrapper.

Fifty substrate-side tests + eight substrate-ui tests all green. Full-suite regression 928 passed / 5 skipped / 0 failures on the substrate tier. Ruff + mypy strict clean.

## Real findings

### 1. Path 1 stuffs the parent's seq into the reviewer's turn_index field

`delegate.py:430-435` builds the resume event as

```python
resume_event = UserMessage(
    text=task,
    turn_index=parent_seq_at_call if parent_seq_at_call is not None else 0,
    ...
)
```

`UserMessage.turn_index` is the reviewer session's per-turn counter (sprint 205's session vocab), not the parent's record seq. If the parent's record has 47 envelopes at the moment of the delegate call, the reviewer receives `UserMessage(turn_index=46)` even when the reviewer is on its second turn — a jump from 0 to 46 in one step. Every downstream reviewer trigger keyed on turn_index (`resume-on-user`, `park-on-final`, `end-on-cap`, transcript renderer rolling-window buckets) sees a discontinuity that the reviewer topology never produced on its own. `test_delegate_routes_into_standing_session` asserts `payload["text"]` and `payload["slash_source"]` but never `payload["turn_index"]`, so the bug is invisible to the current suite.

The reviewer's next turn_index should come from the reviewer's own state (its manifest, or the tail UserMessage seq on the reviewer's record + 1), not from the parent record's tail seq. The two records are unrelated numerically.

### 2. Path 1 reads `finals[-1]` off the reviewer's record — will return a stale answer when this turn produced no FinalAnswer

`delegate.py:447-453`:

```python
finals = [e for e in api.read_record(Path(reviewer_root)) if e["kind"] == "FinalAnswer"]
if not finals:
    raise ValueError("... produced no FinalAnswer for this turn")
answer_text = str(finals[-1]["payload"].get("text", ""))
```

The tail FinalAnswer is filtered across the reviewer's whole record, not scoped to this turn. If the reviewer is on turn 6 and the delegated turn spins out at `turn_max_steps=4` without emitting FinalAnswer, `finals` still holds five entries from turns 0-5; `finals[-1]` returns turn 5's answer; the parent gets a plausible answer that names an earlier question. The `if not finals:` guard only fires when the reviewer has NEVER produced a FinalAnswer.

The reviewer's `session_topology` wrap-up path emits FinalAnswer at the end of every turn on the happy path; a driver that hits `turn_max_steps` without wrapping does not. The `model_producer` `_refuse_all_completed` guard also blocks emission on some policy paths. Neither the failure mode nor the test suite ("6 cases + concurrent FIFO across two files") pins the this-turn scope.

Correct scope needs the reviewer's tail seq before `turn_sync` invokes resume, then filter `finals` to `seq > that snapshot`. Or read `read_record` once inside `turn_sync` after resume returns and thread the this-turn slice back through the return value.

### 3. `turn_sync` guards with `threading.Lock`; `lock_for` returns `asyncio.Lock`; two locks guard one invariant

`SessionRegistry.__init__` maintains two lock dicts (`session_registry.py:150-151`):

```python
self._locks: dict[str, asyncio.Lock] = {}
self._turn_threading_locks: dict[str, threading.Lock] = {}
```

`lock_for(session_id)` returns from `_locks` (asyncio); `turn_sync` acquires from `_turn_threading_locks` (threading). Product-spec §6 promises "one turn at a time per session_id." Two separate lock primitives around the same `Runtime.resume` writer do not honor that promise.

The bug is latent today because sprint 214 (the daemon's async `POST /api/session/<id>/turn`) has not landed — delegate is the only caller of `turn_sync`, and no other code calls `lock_for`. Sprint 214 will wire the async path and both locks will be live against the same record. Two `Runtime.resume` calls will race the writer.

The `RunRecord`'s own file lock catches the resulting collision at the substrate layer (`Runtime(persistent=True)`), but the collision surfaces as a substrate-level RecordGap or SegmentBusy error rather than as a clean FIFO queue. The manifest becomes untrustworthy while both callers think their write landed.

Design fix belongs at the seam, not the caller: pick one lock primitive and route both paths through it, either by making `turn_sync` schedule the resume onto the daemon's asyncio loop (so both callers acquire the same `asyncio.Lock`), or by making the async endpoint acquire the threading lock via `run_in_executor`.

### 4. `_extract_context_slice` single-oversize branch silently drops the rest of the matching set

`delegate.py:226-231`:

```python
if not kept and block_bytes > cap_bytes:
    note = (f"\n... this single event is {block_bytes} bytes, larger than the "
            f"{cap_bytes}-byte slice cap; no other events fit")
    return block + note, 0, 0, True
```

When the first matching event is oversize, the function returns immediately with `elided_count=0` and `elided_bytes=0` — regardless of how many small events sat behind it in `matching`. `test_slice_includes_single_oversize_event_with_note` builds `envs = [huge, small]` and asserts `elided_count == 0` and `"seq=1" not in text`. The test locks the wrong behavior: `seq=1` is elided (never rendered, never mentioned in the trailing note) and the caller has no way to learn it existed.

For a request like `context={parent_seq_range: [0, 100], kinds: ["ModelReply"]}` where seq=0's ModelReply happens to be 12 KiB, every subsequent ModelReply in that range vanishes from the slice AND from the elision count. The note reads "no other events fit," which is a claim about capacity — but the function never counted the ones that would have fit under a 4-byte header if the header hadn't been sacrificed.

Report shape should be `elided_count = len(matching) - 1`, `elided_bytes = sum(block_bytes for the rest)`, and the trailing note should name both facts.

### 5. `turn_sync` docstring promises a mid-turn `SessionEndedMidTurn` raise that the code never delivers

`session_registry.py:299-303`:

> Raises `KeyError` on unknown session_id; `SessionEndedMidTurn` when the session's status is `ended` at call time OR when the run finalises during this turn (the reviewer session's `/exit` fired between the caller's resolve and this call).

The pre-check at lines 314-317 raises `SessionEndedMidTurn` when `manifest.status == "ended"` at entry, and the re-check under the lock at lines 320-325 raises again if a concurrent turn ended the session first. Neither guard fires when this turn is itself the finaliser. Lines 331-333:

```python
status_str = getattr(result, "status", "paused")
new_status: SessionStatus = "ended" if status_str == "finalised" else "parked"
updated = self.update_status(session_id, new_status)
return updated, record_root
```

When the reviewer's `/exit` chain fires inside this turn, `_run_resume_sync` returns a `RunResult` with `.status == "finalised"`; `turn_sync` writes `"ended"` and returns cleanly. No exception. Delegate reads `finals[-1]` from the record — see finding 2 — and returns an answer as if the session were still standing. The delegated task lands, but the session is dead on the next call.

Two choices: teach `turn_sync` to raise `SessionEndedMidTurn` when `status_str == "finalised"` (matches the docstring), or trim the docstring to describe the actual behavior. The behavior itself is defensible for `/exit` cases where the user actually asked to end — but the delegate has no way to distinguish that from a topology bug that terminates unexpectedly.

### 6. Per-call `baseline` can spoof `parent_session_id` when the constructor didn't set one

`delegate.py:507-513`:

```python
merged_baseline: dict[str, Any] = {}
if isinstance(per_call_baseline, dict):
    merged_baseline.update(per_call_baseline)
if parent_session_id is not None:
    merged_baseline["parent_session_id"] = parent_session_id
if parent_seq_at_call is not None:
    merged_baseline["parent_seq_at_call"] = parent_seq_at_call
```

Provenance takes precedence when the constructor set it (the merge order writes provenance keys on top of per-call keys). But when the constructor did NOT set `parent_session_id`, a per-call `baseline={"parent_session_id": "s_MALICIOUS"}` slips through and lands in the child's `substrate.RunStarted.baseline`. `api.trace_ancestry` walking that child now returns a parent that never existed.

The `test_per_call_baseline_and_provenance_merge_together` test uses `parent_session_id="s_authoritative"` at construction — the spoof is defeated in that shape, and the test locks that guarantee. But a delegate constructed with `parent_session_id=None` (the whole test tree does this pervasively — see `test_delegate_backwards_compat.py`, most of `test_delegate_per_call_context.py`) accepts the spoof silently.

Fix: pop `parent_session_id` and `parent_seq_at_call` from `per_call_baseline` before the merge, unconditionally.

## Smaller items

### 7. `_scan_record_status` labels every non-terminal envelope as `interrupted`

`session_registry.py:511-521` returns `interrupted` for any last envelope that is neither `substrate.RunFinalised` nor `substrate.TerminationMatched(decision="pause-await-input")`. A record whose last envelope is a producer event mid-turn — because the daemon died between producer output and the trigger's Park emission, but the writer sealed the segment cleanly — reads as interrupted, which is honest. A record whose last envelope is `substrate.TerminationMatched(decision="finalise-run")` but whose `substrate.RunFinalised` never landed also reads as interrupted; this shape can occur if the finalise write races a segment rotation. The class label is broad, not wrong, but the label carries no distinction between "truly torn" and "clean-but-not-paused." Sprint 214's resume UX may want that distinction.

### 8. `_manifest_from_dict` casts status to the `Literal` type without runtime validation

`session_registry.py:548` reads `status=str(d["status"])  # type: ignore[arg-type]`. A hand-edited manifest with `"status": "quiescent"` deserializes into a `SessionManifest` whose status is nominally `SessionStatus` but factually outside the four allowed values. The boot scan will overwrite this on next start, so the practical blast radius is small; still, a msgspec enum type or an explicit `if v not in ("running", "parked", "interrupted", "ended"): raise` would fail loud instead of quiet.

### 9. `SessionTopologyFactory` type alias is `Callable[["SessionManifest"], Callable[[Any], None]]`

`session_registry.py:98`. The inner callable is a `TopologyBuilder → None`, not `Any → None`; the docstring names `Callable[[api.TopologyBuilder], None]` twice. The `Any` widens the seam past what the code expects. Import `TopologyBuilder` from `substrate.api` at the top and tighten the alias.

### 10. `_ = session_registry` at delegate.py:373 is dead

The variable is captured by `run`'s closure directly; the outer no-op assignment does not affect what the closure sees. Removing it changes nothing.

### 11. `delegate.py` is 592 lines with three responsibilities

Delegation dispatch, model-resolver fallback, and the context-slice helpers all live in one file. `_default_model_resolver`, `_extract_context_slice`, `_format_context_event`, `_prefix_context_slice` are self-contained; extracting them into siblings would leave the dispatch code more legible. Not a defect — a hygiene note.

### 12. `boot_scan` silently swallows every corrupt manifest

`session_registry.py:182-186` catches `OSError`, `json.JSONDecodeError`, `KeyError`, `TypeError` on a per-manifest basis and continues without recording the skip. `server.py::main` prints a summary of `parked`/`interrupted`/`ended` counts; a corrupt manifest disappears from every count and from any operator report. A daemon that boots with three sessions on disk but two parseable ones has no signal that one went missing. A one-line counter and a stderr note per skipped manifest closes the observability gap.

### 13. `parent_seq_at_call` reads the whole parent record on every delegate call

`delegate.py:410` computes `count = sum(1 for _ in api.read_record(parent_record_root))` per invocation. A parent record with 10,000 envelopes reads 10,000 envelopes for one integer. A parent that delegates 100 times reads 1,000,000 envelopes for 100 metadata fields. The substrate `record/` API exposes a tail-seek path (per WORKING_AGREEMENT.md canonical-home row); `api.read_record` iterates the full log. Efficiency; not a defect until a parent record grows.

### 14. `_run_resume_sync` catches `BaseException` inside the worker thread

`session_registry.py:408`. A `BaseException` catch swallows `KeyboardInterrupt` and `SystemExit` in addition to `Exception`. In a daemon-thread worker, the practical risk is small — `KeyboardInterrupt` arrives at the main thread by default — but the shape is footgun-shaped. `_run_child_to_answer` at `delegate.py:101` uses the same pattern; both are documented as "carried back to the caller thread, not swallowed," which is honest for `Exception` and less so for `BaseException`. Tightening to `Exception` costs nothing.

### 15. Delegate catches `SessionEndedMidTurn` by string-comparing exception type names

`delegate.py:441`:

```python
except Exception as exc:
    if type(exc).__name__ == "SessionEndedMidTurn":
        raise ValueError(f"delegate: session_ended_mid_delegate ...") from exc
    raise
```

The type-name comparison is a workaround for F-API-6: `substrate/` cannot import `session_registry` from `substrate-ui/`. Any other module in any process defining a class named `SessionEndedMidTurn` masks this check; if the class gets renamed in a future sprint, this branch silently stops firing. Two cleaner shapes exist: define the exception class in a shared kernel module both sides import (breaks F-API-6 in the wrong direction), or attach a well-known attribute (`is_session_ended_mid_turn = True`) on the exception class and `getattr`-check for it. Neither is free; the string-name check is the least-bad among the current constraints, and worth documenting so the next reader does not casually rename the class.

### 16. Test opener uses `.resume()` for a first-turn open; production semantics undefined for daemon

`test_delegate_via_standing_session.py::_open_reviewer` calls `api.Runtime(record_root, persistent=True).resume(_reviewer_factory(None), resume_event=UserMessage(...))` against a record path that has never been touched. `Runtime.resume`'s docstring at `runtime.py:113-154` reads "opens the EXISTING record for append" — the first-turn case has no existing record. The test lands (8/8 green), so substrate either creates the record on the fly or the test exercises an undocumented code path. Sprint 214's daemon needs a clear rule: does the first turn use `.run()` and subsequent turns use `.resume()`, or does every turn use `.resume()` and substrate handles the empty-record case? The current test's pattern will bind sprint 214's implementation to one choice without the choice being stated.

### 17. Delegate module docstring densely references review letters (`F-2`, `F-3`, `F-5`, `F-8`, `C-1`, `C-9`, `C-10`, `R-2`)

`delegate.py:1-34`. Each letter refers to a numbered finding in an out-of-tree review file. A fresh reader cannot decode any of them without the index. Trimming the letters or linking to the review index once at the top of the module keeps the historical rationale without turning the docstring into a cipher.

## What holds

- Canonical-home registry gained three rows for `SessionRegistry` module, `by-name.json`, and `manifest.json`. Each cites its sprint.
- The `fcntl.flock` sits on the stable `.by-name.lock` sibling, not on `by-name.json` itself. The 100-concurrent-create test surfaced the wrong-inode bug during sprint 211 and the fix landed with the sprint.
- Boot scan reads `read_record` (not `recover_open_segment`, which writes). The docstring at `session_registry.py:502-504` names the pitfall.
- Atomic writes use tempfile + `os.replace` + `fsync`. Idempotent recreate on the same `(session_id, name)` pair is honored; second creator on the same name with a different session_id raises `NameCollision` carrying the winner's id.
- Ten-thread first-writer-wins race resolves consistently to a single winner; nine losers report the same `existing_session_id`.
- Delegate schema declares all six properties and the `x-args-passthrough: true` marker; `ollama_tools(suite)` exposes every field to native tool-calling.
- Backwards-compat contract holds: `run(["hello"])` still returns `{answer, child_root, steps}` with no `via` field. Depth-cap and fan-out-cap raises survive the new parse.
- Provenance flows both directions: parent's ToolResult carries `child_root`; child's `substrate.RunStarted.baseline` carries `parent_session_id` and `parent_seq_at_call` when the constructor set them.
- Context-slice extractor drops at the event boundary as promised; the multi-event boundary test asserts `1 ≤ elided_count ≤ 2` so a JSON-encoding tweak that shifts block size by a few bytes does not trip the test.
- Delegate path 1 concurrent FIFO test lands: two parent threads both complete, reviewer's record ends with three UserMessages in seq order, no interleaving.
- Session-ended, unknown-name, and no-factory failure paths raise typed exceptions with error strings that name the missing piece.
- `_run_resume_sync` mirrors `_run_child_to_answer` on the timeout + cross-thread cancellation shape (F-8 pattern reused).
- The `substrate.topologies.session.UserMessage` import inside path 1 is lazy — pure `tool_loop` tests pay no import cost for the standing-session seam.

## SDD adherence

- Rule 2 (no invented vocabulary): sprint 213 adds no wire kinds. The `via` field is a return-dict key, not a wire signal. Baseline overrides land at `TopologyBuilder.baseline(**merged)`, a builder-level metadata path.
- Rule 6 (≤2 files / one concept): sprint 213 as originally written spanned two repos, five files, seven test files. The card was split into 213a (substrate side, one source + five tests, one concept) and 213b (substrate-ui + substrate crossing, four files, one concept). Sprint 213b acknowledges the file-count stretch on the card and prose-explains why splitting further would ship half a feature.
- Rule 7 (canonical home registry): three rows added by sprint 211 for `SessionRegistry`, `by-name.json`, `manifest.json`. Every row cites its sprint. The `SessionRegistry` row's sprint stamp ("sprint 211") is right for the file; a separate stale row at line 95 attributes the daemon module `session_registry.py` to "daemon piece B — sprint 211," which conflates piece B and piece C — piece B is sprints 214-217 per the card and the pieces-list at the top of the BLACKBOARD. Small drift on that one row's phase label.
- Rule 9 (observation contract for behavior-touching sprints): sprints 211 and 213 both rescoped their observation contracts to defer the CLI-dependent pieces (sprint 222 `substrate session ls`, sprint 221 `substrate chat` two-terminal test). Rescopes are folded honestly on the cards and in BLACKBOARD. The substituted record-level tests exercise every non-CLI assertion.
- Rule 10 (hand-author requires authorization): no hand-authored bypasses. Every change lands through sprint cards.
- Rule 11 (originals over summaries): tech-spec §5 is the referenced canon; the sprint cards cite line ranges into `delegate.py` and `runtime.py` for the surfaces they extend.
- Rule 12 (no deletions): the sprint 210 review folded a `git mv` of `two_turns.json` → `three_turns.json`; the rename preserves git history. Piece C introduces no deletions.

## Substrate principles adherence

- **F-API-6 (public-surface-only imports).** `substrate-ui/session_registry.py` imports `from substrate import api`; every substrate touch — `api.read_record`, `api.recover_open_segment` (referenced but not called), `api.Runtime(persistent=True).resume` — goes through the public re-export module. No import from `substrate.kernel.*` or `substrate.record.*`. Delegate imports the same `api` module plus `substrate.adapters` for the concrete Responder classes; both are public. The one seam where the boundary bends is the string-name catch for `SessionEndedMidTurn` in `delegate.py:441` — substrate cannot import from substrate-ui, which is the F-API-6 direction the constraint is meant to protect. The workaround is the smallest one that keeps the boundary honest.
- **Reserved `substrate.*` namespace.** No new reserved kinds. The delegated `UserMessage` is an application event; `Runtime.resume` at `runtime.py:148` refuses reserved-namespace resume events at config time, and the tests exercise the honest path.
- **Record as source of truth; manifest as hint.** `session_registry.py:24-29` names this explicitly and the boot scan implements it — every manifest's `status` field is reclassified against the record's own last envelope, and stale manifests get rewritten. `_manifest_to_dict` / `_manifest_from_dict` are a lossless round-trip; the record's `substrate.RunStarted.payload` can rebuild the manifest from scratch if the manifest file is lost (per the module docstring's promise, though no code exercises this path in piece C).
- **Single-writer per record.** The substrate layer's per-record flock catches concurrent `Runtime.resume` calls at the file level — a second `.resume()` on a record already held would fail on flock acquisition rather than corrupt the log. The two-lock design flagged in finding 3 is a coordination gap at the daemon layer, not a corruption gap at the substrate layer. The substrate primitive holds; the daemon builds two lock objects around one invariant it did not need to guard twice.
- **`Runtime.resume` termination constraint.** The runtime docstring at `runtime.py:133-139` warns that a resumable run "MUST finalise on a PROCESS-LOCAL condition — quiescence or a threshold over event counts — NOT `all_completed`." The reviewer session's `session_topology` uses `pause_await_input(Park)` termination, which is process-local. Sprint 209a added a `_refuse_all_completed` regex guard at topology-build time, so a caller cannot silently violate the constraint. Piece C composes onto that guard cleanly.
- **F-COMP (composition) — new provenance shape unnamed by the spec.** Delegate's path 1 threads the parent's ToolResult with `child_root` pointing at the reviewer's record. Many parents delegating to one standing session over time produces a many-to-one provenance graph — many parents, each citing the same child record. `api.trace_ancestry` walking the reviewer's record will discover multiple `parent_session_id` values across the many `substrate.RunStarted.baseline` envelopes the reviewer accumulates over turns. The tech spec §5 names the provenance shape "both directions" without naming this fan-in. Not a bug; a graph shape the spec does not yet document.
- **Determinism / Level-3(a) replay.** `_run_resume_sync` spawns a fresh event loop per call. The event-loop identity is a harness-side detail; the record captures append-cycle events, not loop handles. Replay reads the record. No determinism cost.
- **Baseline metadata shape.** `parent_session_id` and `parent_seq_at_call` land on `substrate.RunStarted.payload.baseline` via `TopologyBuilder.baseline(**merged)`. The tech spec §5 explicitly permits per-call baseline pass-through; adding provenance keys is inside that contract.

## Code quality

- **Exception hygiene.** `_run_resume_sync` and `_run_child_to_answer` both catch `BaseException` in worker threads — see finding 14. `_scan_record_status` catches bare `Exception` with a noqa BLE001 that names the reason ("a corrupt record is a real state, not a crash"), which is the right way to justify a broad catch.
- **Cross-boundary duck-typing.** `SessionTopologyFactory` is typed `Callable[[SessionManifest], Callable[[Any], None]]` because pulling `TopologyBuilder` into `session_registry.py` would either add a `substrate.kernel.*` dependency or route through `substrate.api` (fine either way, and finding 9 says do the latter). The `type(exc).__name__ == "SessionEndedMidTurn"` catch at `delegate.py:441` is the mirror-image workaround from the other direction (finding 15). Both are load-bearing under F-API-6; both deserve a comment naming why the shape is what it is. The former has no such comment; the latter has a brief one.
- **Docstring accuracy.** `turn_sync`'s docstring promises a mid-turn `SessionEndedMidTurn` raise the code never delivers (finding 5). `_run_resume_sync` lacks the equivalent of `_run_child_to_answer`'s honest "only reachable if cancelled without a timeout" note on its dead `if box.get("cancelled")` branch. Delegate's module docstring loads reader burden with review-letter references (finding 17).
- **Efficiency.** `parent_seq_at_call` full-record scan per delegate call (finding 13); `_extract_context_slice` iterates the record once to filter, then once more to accumulate — the second pass runs over `matching`, not the record, so the cost is bounded by the filtered set. Fine.
- **Dead / redundant code.** `_ = session_registry` at `delegate.py:373` (finding 10). `SessionTopologyFactory`'s forward reference `"SessionManifest"` in string quotes at `session_registry.py:98` is no longer necessary — `SessionManifest` is defined earlier in the file. Cosmetic.
- **Test hygiene.** `test_slice_includes_single_oversize_event_with_note` locks the wrong behavior (finding 4) — a test asserting a bug is worse than an absent test. `test_delegate_via_standing_session.py` uses `.resume()` for a first-turn opener (finding 16), which either exercises undocumented substrate behavior or bakes a fragile assumption into every daemon-side rewrite. `test_run_with_empty_list_does_not_crash` in backwards-compat calls out to a real DeterministicResponder for a trivial no-crash assertion; realistic, slightly slower than needed.
- **Naming.** `SessionEndedMidTurn` reads as "the session ended in the middle of THIS turn" but the class fires in three shapes: (a) session was already ended before the call, (b) the pre-lock re-check found it ended, (c) — per the docstring — the current turn's resume finalises. Shape (c) is not implemented (finding 5), but the name promises all three. Trimming the docstring or teaching (c) restores name-vs-behavior parity.
- **Module structure.** `delegate.py` at 592 lines carries dispatch + resolver fallback + context-slice extraction (finding 11); `session_registry.py` at 568 lines carries the catalog + boot scan + `turn_sync` seam + the flocked-index context manager + `_run_resume_sync`. Both are within readable range; splitting is optional. `_run_resume_sync` and `_FlockedIndex` are the most naturally separable pieces of `session_registry.py`.
- **What reads well.** The boot-scan reconciliation loop (`session_registry.py:161-196`) is small, linear, and each branch is documented. The `_FlockedIndex` context manager (`session_registry.py:432-484`) states the wrong-inode failure mode in prose before showing the fix. The delegate path 1 dispatch (`delegate.py:415-459`) is a plain if-tree with typed exits at every branch. The `x-args-passthrough` marker in `tools.py::_named_to_positional` is the smallest possible fix for the middle-optional-drops bug; the comment names the failure mode. `NameCollision` carries the existing session_id in the exception itself, which lets the caller shape the 409 response without a second lookup.

## Test coverage vs contract

Sprint card 213's assertion table declares seven test surfaces; the tree carries the substance of six. `test_session_queue_serialization.py` (two parents delegate to same standing session, second FIFO-blocks) does not exist as a separate file. The concurrent FIFO behavior is verified inside `test_delegate_via_standing_session.py::test_two_parents_delegating_to_same_reviewer_serialize`. Same behavior, different file location than the card names; no lost coverage.

The two-terminal observation contract from sprint 213's original card is explicitly deferred to sprint 221. The record-level substitute in sprint 213b covers the parent-to-reviewer chain in-process.
