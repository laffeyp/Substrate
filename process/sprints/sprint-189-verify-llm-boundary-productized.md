# Sprint 189 — Verify LLM boundary is already productized (roadmap v2 S5.1)

---

```yaml
---
id: 189
status: closed
phase: 0
pass_kind: docs
---
```

## scope

Roadmap v2 S5.1 says: verify B1 (LLM via provider) is already productized via `OllamaResponder` + `ModelUsage`. Sprint 189 walks the code to confirm and updates the WORKING_AGREEMENT boundary table row with the verification receipt.

## what was verified

Every SWE-bench topology producer that calls a model uses `call_responder_metered` at `adapters/models.py:395` which returns `(text, ModelUsage)` and emits the `ModelUsage` event onto the run's record:

- `repair.py:74` — drafter
- `localize.py:74` — file-level localizer
- `localize_elements.py:130` — element-level localizer
- `reproduction.py:110` — repro-test generator

Every rate-limit failure surfaces as a typed `ProviderRateLimited` exception (`adapters/rate_limit.py`); the runner's `_classify_cell_error` at `scripts/assay_swebench_confirmatory.py:180` catches it typed and maps to `REASON_RATE_LIMITED` on the cell row.

`swebench_repair_topology`'s producer registrations declare `ModelUsage` in the schema lists — `assemble.py:293` (localizer) and `topologies/best_of_n/__init__.py:130` (drafter via the shared sub-topology).

B1 needs no code change. The boundary is producer-shaped, typed-event on the record, typed-exception on failure. Every future assay that touches an LLM via `Responder` inherits the same shape.

## files modified

- `process/WORKING_AGREEMENT.md` — B1 row updated with the verification receipt naming every call site.

## contracts

- Doc-only change.
- No new tests — the verification IS reading the code and recording what's there.

## done

One line updated. B1 marked verified. Next roadmap step: S5.3 (ContainerProducer) or S5.5 (RepoCloneProducer) — both dispatchable without probe results.
