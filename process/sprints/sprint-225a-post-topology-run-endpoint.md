# Sprint 225a — POST /api/topology/<name>/run (generic launcher)

```yaml
---
id: 225a
status: closed
phase: daily-driver-piece-E
pass_kind: functional
---
```

## split rationale

Sprint 225 (parent) landed as four sub-cards to honor SDD rule 6.
This card ships the generic one-shot dispatch endpoint TECH-SPEC §7.6
line 1043 names. 225b ships composite lifecycle infra;
225c ships the pair_coding composite factory; 225d ships the async
status poll.

## scope

New endpoint `POST /api/topology/<name>/run`. Body:
```
{ inputs: {...}, bundle?: str, baseline?: {...}, await_completion?: bool }
```

- Resolves `<name>` via `_APPLICATIONS` (sprint 223).
- Reads the manifest's `[inputs]` schema; for each `<role>_model` key,
  resolves the string value via `_daemon_driver_resolver` into a
  Responder (same registry `_agent_models` uses at server.py:118).
- For non-model inputs, passes the value through as-is (int/str/list).
- Imports the topology factory from the module the manifest names
  (convention: manifest `name` == module basename under
  `substrate.topologies.applications.<name>`).
- Runs the topology on a fresh record dir under
  `~/.substrate/runs/<run_id>/`; run_id is a `s_topo_<uuid[:20]>`.
- `await_completion=true` (default) blocks; returns `{run_id,
  record_root, status, final_seq}`. `await_completion=false` starts a
  background thread; returns immediately with `{run_id, record_root,
  status: "running"}`.

Session-shape manifests (`runs = "session"` or `runs =
"session_composite"`) return 400 — those dispatch through
`POST /api/session` (daily) or `POST /api/session/composite` (225c).
The launcher is one-shot only.

## artifact contract

### Files

- `substrate-ui/server.py` — new handler `_topology_run` + POST routing
  branch.

### Assertions

- `POST /api/topology/best_of_n_verified/run {inputs: {task: "double 3",
  n: 3, drafter_model: "deterministic", verify_model: "deterministic"}}`
  returns `{run_id, record_root, status: "finalised", final_seq}` and
  the record has a `Solved` (or `MaxRoundsExhausted`) terminal.
- Unknown application name → 404.
- Session-shape manifest → 400 with a message pointing at
  `POST /api/session`.
- Missing required input → 400 naming the field.

### Tests

- `substrate-ui/tests/test_server_topology_run_225a.py` — four cases.

## observation contract

`curl -X POST http://localhost:8765/api/topology/best_of_n_verified/run
-d '{"inputs":{"task":"double 3","drafter_model":"deterministic","verify_model":"deterministic"}}'`
returns 200; record on disk shows RunStarted + terminal envelope.

## halt conditions

- `vocabulary_change_required` if a manifest input needs a shape the
  daemon cannot resolve (e.g. a Responder callable literal).

## definition of done

One-shot applications dispatch via the endpoint. 225c depends on this
for the composite factory's daemon-client call.
