# Sprint 190 — `_mother_clone` emits typed events (roadmap v2 S5.5)

---

```yaml
---
id: 190
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Roadmap v2 S5.5 (RepoCloneProducer): typed events on the B5 GitHub-clone boundary. Prep runs before any substrate topology starts, so the events land on stderr as canonical JSON lines rather than on a run's bus. Kind names match vocab v0.3 § G.4 (`RepoCloneRequested`, `RepoCloneCached`, `RepoCloned`, `RepoCloneFailed`).

## files modified

- `src/substrate/assay/swebench_suite.py` — new `_emit_repo_clone_event` helper writes canonical JSON to stderr with `boundary=repo_clone`. `_mother_clone` emits `RepoCloneRequested` on entry; `RepoCloneCached` on cache hit (before or after acquiring the flock, since a peer may have fetched during the wait); `RepoCloned` on cache miss + successful fetch (with `fetch_ms` distinguishing fetch time from total wall_ms); `RepoCloneFailed` on subprocess failure.

## files created

- `tests/test_repo_clone_events.py` — two substance tests. Cache hit uses a pre-populated fake mother directory; cache miss + fetch failure uses monkeypatched `subprocess.run` to raise `CalledProcessError` without hitting the network.

## contracts

- 2/2 tests pass.
- 6 broader swebench_suite tests still pass.
- Ruff + mypy strict clean.
- Every `_mother_clone` call emits either `[Requested, Cached]` (fast path) or `[Requested, Cloned]` (fetch path) or `[Requested, Failed]` (error path).
- `_clone_at` unchanged — it wraps `_mother_clone` and inherits the events for free.

## why stderr, not a substrate bus

`_mother_clone` runs in the prep phase before any substrate topology has started. There is no run's bus to emit onto. Stderr as canonical JSON preserves the "typed events" discipline without requiring the prep phase to become its own substrate run first. When the prep phase does become a substrate topology later, the same event kinds ride the bus directly with no rename.

## done

Two files. Real typed-events on the B5 boundary. Every future run's clone-cache-hit rate and fetch latency lands on stderr for anyone counting.
