# Sprint 225c — pair_coding_composite.py + manifest + composite dispatch

```yaml
---
id: 225c
status: closed
phase: daily-driver-piece-E
pass_kind: functional
---
```

## split rationale

Third of four sub-cards splitting sprint 225. Depends on 225a
(one-shot launcher — for reference shape) and 225b (composite
lifecycle infra). Ships the actual factory + manifest + a
new dispatch endpoint for `runs = "session_composite"` apps.

## scope

- `substrate/src/substrate/topologies/applications/pair_coding_composite.py`.
  Public: `pair_coding_application(*, builder_driver_name, reviewer_driver_name,
  workspace, session_registry) -> tuple[str, str]` returning
  `(builder_session_id, reviewer_session_id)`. Registers builder
  session with auto-name `pair-<uuid8>`; registers reviewer with
  name `f"{builder_name}-reviewer"` and `composite_of=builder_id`.
  No DaemonClient — the factory reaches into the SessionRegistry
  directly (session_registry is already the composition seam).
- `substrate/src/substrate/topologies/applications/pair_coding.manifest.toml`.
  `runs = "session_composite"`. Inputs: builder_driver_model,
  reviewer_driver_model, workspace.
- `substrate-ui/server.py` — new POST endpoint routing for
  `runs = "session_composite"` manifests. Returns
  `{builder_session_id, reviewer_session_id, builder_record, reviewer_record}`.

The reviewer's seed instructs it as a review-only role (no tool
that writes). The builder's seed instructs it to call `delegate`
with the reviewer's session_name after every unit of work.

## artifact contract

### Files

- `substrate/src/substrate/topologies/applications/pair_coding_composite.py` (new)
- `substrate/src/substrate/topologies/applications/pair_coding.manifest.toml` (new)
- `substrate-ui/server.py` — one new branch in the topology-run handler.

### Assertions

- POST /api/topology/pair_coding/run returns two session_ids.
- Both sessions land in the registry; child's `composite_of` == parent's id.
- `substrate session ls` shows both, with the child bucketed under
  parked (fresh sessions before first turn).
- 225b's cascade works on the pair: ending the parent ends both.

### Tests

- `substrate-ui/tests/test_pair_coding_composite_opens_two_225c.py`
- `substrate-ui/tests/test_pair_coding_composite_lifecycle_225c.py`
  (drives the cascade end-to-end via /end).

## observation contract

`curl -X POST http://localhost:8765/api/topology/pair_coding/run
 -d '{"inputs":{"builder_driver_model":"deterministic",
                "reviewer_driver_model":"deterministic",
                "workspace":"/tmp/pair"}}'` returns both session_ids;
subsequent `POST /api/session/<builder>/end` cascades.

## halt conditions

- `dual_contract_fail` if the pair opens but the manifest says runs
  is something other than session_composite.
