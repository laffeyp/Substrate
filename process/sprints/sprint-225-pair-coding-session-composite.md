# Sprint 225 — pair_coding session-composite

```yaml
---
id: 225
status: superseded
phase: daily-driver-piece-E
pass_kind: architecture
---
```

## superseded by 225a + 225b + 225c + 225d (2026-08-28)

This card fused five concepts across two repos and depended on
infrastructure the roadmap did not spell out separately
(`POST /api/topology/<name>/run`, a SessionCompositeSpec type, a
DaemonClient from piece F). Split per SDD rule 6:

- **225a** — generic `POST /api/topology/<name>/run` for one-shot apps.
- **225b** — `SessionManifest.composite_of` field + cascade lifecycle
  infra (parent-child end/rm).
- **225c** — the `pair_coding_composite.py` factory + manifest +
  `runs = "session_composite"` dispatch branch.
- **225d** — `GET /api/topology/<name>/status?run_id=<id>` for
  225a's `await_completion=false` shape.

Original scope kept below for the audit trail.

---

## scope (original — not what shipped)

Author `substrate/src/substrate/topologies/applications/pair_coding_composite.py`. New `pair_coding_application(*, builder_driver, reviewer_driver, workspace, daemon_client) -> SessionCompositeSpec`. Opens two related sessions via the daemon: (1) a builder session with `session_topology`, driver `builder_driver`, name auto-generated as `pair-<uuid8>`; (2) a standing reviewer sub-agent with `session_topology`, driver `reviewer_driver`, name `f"{builder.name}-reviewer"`, role `"reviewer"`, tools `[read_file, grep, list_dir, web_fetch, delegate]`. Builder's seed instructs it to call `delegate(task="review the change I just made in <file>", child_session_name="<builder.name>-reviewer")` after every logical unit of work. Reviewer inherits builder's baseline on creation.

Composite lifecycle: `substrate session end <builder-name>` ends BOTH sessions. `substrate session rm <builder-name>` removes both. Piece C's `session_registry` grows a small `composite_of` field on manifests to enforce this.

## prerequisites

- Sprint 224 closed.
- Sprint 211-213 closed (piece C — standing sub-agents work).

## context_files

- Sprint 211-213 output (SessionRegistry + delegate per-call args).
- `substrate/src/substrate/topologies/pair_coding/__init__.py` — the chunked-writer topology (NOT what this application does; disambiguate in the docstring).
- `substrate/src/substrate/topologies/applications/registry.py` — for the `SessionCompositeSpec` shape.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §7.3.

## artifact contract

### Files

- `substrate/src/substrate/topologies/applications/pair_coding_composite.py` — new.
- `substrate/src/substrate/topologies/applications/pair_coding.manifest.toml` — new; `runs = "session_composite"`.
- `substrate-ui/session_registry.py` — grow `composite_of: str | None` on manifest.
- `substrate-ui/server.py` — `POST /api/topology/pair_coding/run` handler returns both session_ids; `POST /api/session/<id>/end` on a composite parent cascades to children.

### Assertions

- `substrate run pair_coding` opens two sessions; `substrate session ls` shows both with composite_of linkage.
- `session end <builder-name>` cascades — both sessions land `SessionEnded` on their respective records.
- Reviewer's manifest.json carries `composite_of: <builder_session_id>`.

### Tests

- `test_pair_coding_composite_opens_two.py`
- `test_pair_coding_composite_lifecycle.py` — end parent → both end.
- `test_pair_coding_reviewer_gets_delegate_call.py`.

## observation contract

`substrate run pair_coding --builder-driver deterministic --reviewer-driver deterministic --workspace /tmp/pair-test` opens both sessions; drive one builder turn that calls `delegate` on the reviewer; verify the reviewer's record grows one turn; `substrate session end pair-<...>` cascades.

## halt conditions

- `dual_contract_fail` if cascade lifecycle drops one side.

## definition of done

`pair_coding` opens + tears down as composite. Piece E closes.
