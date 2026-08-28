# Sprint 224b — BUNDLED CI-mode factories for the four shipped applications

```yaml
---
id: 224b
status: pending
phase: daily-driver-piece-E
pass_kind: functional
---
```

## scope amendment note

Sprint 224 (parent) landed the four `.manifest.toml` files + the
`pair_coding` → `pair_coding_chunked` BUNDLED rename. It deferred the
BUNDLED CI-mode factories for the four apps to this follow-up because
each factory needs a real fixture the parent's ≤2-files-one-concept
scope does not carry:

- `code_review` (fanout_review wrapper): needs a git repo fixture with
  a diff at `HEAD~1`. `_code_review` in `bundled.py:37` already wraps
  the inner `code_review_topology` with a Python-string fixture; the
  fanout_review wrapper wants `repo` on disk.
- `best_of_n_verified`: needs a `task` + a `drafter` responder + a
  `verify` Check function. Deterministic factory is straightforward
  (deterministic responder + calculator-style check), but the fixture
  choice is a new decision.
- `research_sweep`: needs a documents list `[(label, text), ...]` and
  three responders. Fixture choice again.
- `daily` (session wrapper): needs the same CI-mode scripted opener
  the `session` key uses (`ci_session_topology` at
  `topologies/session/ci.py`). Simplest: alias `daily` to
  `ci_session_topology`, matching `session`. Two aliases naming the
  same thing is not ideal; a `daily` variant should differ (fresh CI
  script? distinct seed?).

## scope

Land four BUNDLED entries under CI-default (deterministic, no-network)
factories, one committed CI record per app in
`topologies/applications/<name>/records/ci_mode.record/`, and update
`gen_topology_records.py` to know about the new records.

- `_code_review_fanout()` — writes a temp git repo with one file per
  role name, commits, then dirties. `fanout_review_topology(repo, ref)`
  fans a `DeterministicResponder(seed=i)` per role + judge.
- `_best_of_n_verified()` — task `"double 3"`; drafter
  `DeterministicResponder(seed=1)`; verify a `Check` that pattern-matches
  `"6"` in the text. `n=3`, `max_rounds=2`.
- `_research_sweep()` — question `"what is 40 plus 2?"`; documents a
  three-entry fixture list; three deterministic responders.
- `_daily()` — either alias `ci_session_topology` under a second key,
  or ship a distinct three-turn script that ends in `/exit`.

## artifact contract

### Files

- `substrate/src/substrate/topologies/bundled.py` — four new BUNDLED
  entries + factories.
- `substrate/src/substrate/topologies/applications/<name>/records/ci_mode.record/`
  (four new dirs, one per app; generated via `gen_topology_records.py`).

### Assertions

- `substrate topology list` shows the four new names.
- `substrate demo replay code_review` walks the committed record.
- `substrate demo run <name>` reproduces byte-for-byte for each.
- The existing `test_ci_record_replays_level_2` parametrization gets
  four new (name, thunk) entries; all pass.

### Tests

- `test_ci_record_replays_level_2` extended.
- `test_bundled_topologies.py` extended.

## observation contract

`substrate demo run code_review` walks a real fanout_review over the
temp-repo fixture; the record has ReviewSubject + Verdict envelopes.
Same shape for the other three apps.
