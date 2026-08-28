# Sprint 224c — observation-half tests for 223b tools + 223c isolate

```yaml
---
id: 224c
status: closed
phase: testing-discipline
pass_kind: test-add
---
```

## scope

223b's `test_tools_named_list_lands_on_manifest` asserts the manifest
holds the tool list but never runs a `/turn` to prove the topology
bound only those tools. 223c's isolate tests assert
`workspace_shape == "isolate"` but never fire a tool call that would
write outside the workspace. Both are manifest-only — schema without
observation. Dual contract needs both halves.

Add one observation test per card:

- 223b: fire one `/turn`; assert the running topology's tool set matches
  the allow-list (via `_build_session_topology_from_manifest` inspection
  or by driving a tool call and asserting the disallowed tool is absent
  from the tool-registry the model saw).
- 223c: fire a `write_file` tool call at path `foo.txt`; assert the file
  lives at `<isolated_workspace>/foo.txt`, never at the caller-supplied
  `workspace/foo.txt`.

## artifact contract

### Files

- `substrate-ui/tests/test_server_session_create_tools.py` — one new test.
- `substrate-ui/tests/test_server_session_isolate.py` — one new test.

### Assertions

- Tools observation: with `tools=["read_file"]`, a driver forced to emit
  a `grep` tool call gets `ToolResult(ok=false, error="unknown tool")`,
  not a real result.
- Isolate observation: after write_file, `(caller_workspace / "foo.txt").exists()`
  is False; `(isolated_workspace / "foo.txt").exists()` is True.
