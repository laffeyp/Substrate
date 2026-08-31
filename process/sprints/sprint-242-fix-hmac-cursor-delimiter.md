# Sprint 242 — fix HMAC cursor delimiter (12% verify-failure rate under load)

```yaml
---
id: 242
status: closed-2026-08-31
phase: 6
pass_kind: correctness
---
```

## Product-spec conformance

**Fulfills:** PRODUCT-SPEC-2026-08-17-round12.md §5d "Pagination cursor. Cursor encodes `(record, filter, next_seq)` and is opaque to the model. This is the pattern every well-designed MCP list tool uses; substrate's log tools follow it." A cursor that silently fails ~12% of the time is not well-designed. Product-spec conformance requires a cursor that reliably round-trips.

**Consumes:** REVIEW-2026-08-31-session-topology-vs-specs.md COR-6 correction (the "flaky test" was a real defect).

## Root cause

`substrate_tools.py::_sign_cursor` (line 261):

```python
return base64.urlsafe_b64encode(signature + b"." + payload_bytes).decode("ascii")
```

`_verify_cursor` (line 276):

```python
signature, payload_bytes = raw.split(b".", 1)
```

`signature` from HMAC-SHA256 is 32 raw bytes. Any of those bytes may be `0x2E` (ASCII `.`). `split(b".", 1)` splits at the FIRST `.`, which cuts the signature short whenever byte 0..31 contains 0x2E. The HMAC check then compares a truncated signature against the recomputed 32-byte signature; comparison fails; verify returns None; caller returns `{"ok": false, "error": "invalid cursor"}`.

**Probability:** `1 - (255/256)^32 ≈ 11.8%`. Reproduced at ~10% over 30 runs of `test_events_pagination_with_hmac_cursor` in isolation.

## Scope

Replace the `.`-delimited encoding with a fixed-length prefix. HMAC-SHA256 signature is always exactly 32 bytes; the encoding does not need a delimiter — split at byte 32.

Two files. One concept.

## prerequisites

None.

## context_files

- `src/substrate/topologies/tool_loop/substrate_tools.py` — `_sign_cursor` at line 247 and `_verify_cursor` at line 264.
- `tests/test_substrate_tools_inspect_record_227.py` — `test_events_pagination_with_hmac_cursor` at line 65 (the intermittent-failure witness) and `test_hmac_sign_and_verify_roundtrip` at line 124 (the primitive test).

## artifact contract → Files created/modified

- `src/substrate/topologies/tool_loop/substrate_tools.py` — `_sign_cursor` encodes as `signature + payload_bytes` (no delimiter); `_verify_cursor` splits at byte 32 (`raw[:32]`, `raw[32:]`) and drops the `split(b".", 1)` call.
- `tests/test_substrate_tools_inspect_record_227.py` — add `test_hmac_cursor_survives_signature_containing_delimiter` that constructs a payload whose signature is guaranteed to contain 0x2E (or a stress test that runs sign+verify 200 times, asserts every round-trip verifies). Locks the fix against regression.

## signal contract → Emits

None (no runtime signals; internal primitive fix).

## observation contract

- `for i in $(seq 1 30); do uv run python -m pytest tests/test_substrate_tools_inspect_record_227.py::test_events_pagination_with_hmac_cursor -q --timeout=15 -p no:cacheprovider 2>&1 | tail -1; done` — all 30 runs PASS. Baseline before fix: 2-4 failures per 30 runs.
- `test_hmac_sign_and_verify_roundtrip` continues to pass.
- New regression test `test_hmac_cursor_survives_signature_containing_delimiter` PASS.
- Full substrate-tools test file PASS.

## halt conditions

- `dual_contract_fail` if 30 consecutive runs surface any failure post-fix.

## definition of done

Cursor verify round-trips 100% (30/30 runs). Regression test on file. `_sign_cursor` + `_verify_cursor` use fixed-length prefix, not delimiter.
