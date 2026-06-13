# Phase 1 — Implementation roadmap (PROPOSED)

*Build-organizer planning artifact. Status: PROPOSED, pending (a) Sprint-0 vocabulary lock and (b) Architect go. Not a dispatch. Each wave below becomes a chain of sprint cards authored with the locked `signals/0.1.json` in hand — this document fixes the wave structure, the dependency order, the ≤2-file decomposition, and the conformance-check mapping so the chains can be authored fast and in the right sequence.*

*Grounded in: technical_spec/draft5.md (module decomposition, §-refs), product_spec/draft7.md §7 (the 17 conformance checks = the acceptance spine, technique CT-5) and §8 (R-1..R-3), and the canonical home registry in WORKING_AGREEMENT.md.*

---

## Sequencing principle (why this order)

Two hard constraints from the specs drive the order:

1. **Bytes before storage before behavior** (technical §2). "Canonical encoding (§4) is decided *before* the storage format (§3) because frames are CRC-protected canonical bytes — storage wraps encoding, never the reverse." And the record is the product surface, so it precedes the writer that fills it.
2. **The build is conjunctive** (product §2 — "half a substrate orchestrates nothing"). So waves are ordered by *dependency*, not by user value: nothing demonstrable ships until late, but each wave closes the conformance checks its subsystems span, so progress is verifiable wave-by-wave rather than only at the end.

Sweet spot honored throughout: **≤2 files / one concept per sprint** (hard rule 6). Cross-cutting contracts open each wave via **Wave-0-carry** (technique 15). Every wave ends with an **N.INT** integration sprint (technique 16) asserting its conformance checks end-to-end. `pass_kind` noted per sprint.

---

## Wave 0 — Shared contracts + project skeleton  *(architecture; Wave-0-carry)*

Pre-fills the canonical shapes every later subsystem consumes (technique 15). Resolves B-Q-1 (package name) at its first sprint.

- **S-0.1** `pyproject.toml` + package skeleton + `uv` lockfile + CI matrix scaffold (ruff, mypy --strict, pytest, pytest-benchmark) + `py.typed`. *(architecture)* — resolves B-Q-1 import root.
- **S-0.2** `types.py` — `Event`, `BlobRef`, `ProducerRef`, `Subscription` as frozen msgspec Structs; the on-disk envelope fields (tech §3.4). *(architecture)*
- **S-0.3** `protocols.py` (`Producer`, `View` Protocols) + `constants.py` (tech §19 named defaults). *(architecture)*
- **S-0.bridge** `WORKING_AGREEMENT.md` SDK bridge mappings for **msgspec** and **rfc8785** — reverse-engineer the real API surface (technique 46 / hard rule on `bridge_mapping_required`). *(bridge)* — MUST land before Wave 1.
- **S-0.INT** Import-lint rule (`substrate.cli` → `substrate.api` only, F-API-6) wired in CI; skeleton imports clean; `mypy --strict` green on the empty public surface.

---

## Wave 1 — Canonical encoding  *(architecture/functional)*  →  closes parts of checks 6, 9

The bytes everything hashes over. Decided first (tech §2, §4).

- **S-1.1** `encoding.py` — the JCS pipeline (`msgspec.to_builtins` → `rfc8785` → bytes); `B_hash` vs `B_disk` two-form rule (tech §3.3); `sha256` content-hash helper. *(functional)*
- **S-1.2** the §4.2 type whitelist + validation failure paths (registration-time + emission-time); fixed-size byte types (`bytes16/20/32` hex); int/float/NaN-Inf rules. *(functional)*
- **S-1.INT** RFC 8785 conformance vectors green in CI; round-trip property tests (hypothesis); determinism across the 3.12/3.13/3.14 matrix. *(observation)* — seeds check 9.

---

## Wave 2 — Run record on disk + durability  *(architecture/functional)*  →  closes 16, 10; seeds 3

Storage wraps encoding (tech §3, §5). The product surface.

- **S-2.1** `record.py` — segment files, the `.open` infix, frame format (length + CRC32), sealing protocol (fsync → rename → dirfd fsync). *(functional)*
- **S-2.2** torn-tail recovery (scan-verify-truncate on the `.open` segment only) + the manifest (advisory; rebuildable). *(functional)* — closes **check 16**.
- **S-2.3** blob store (write-ahead, content-addressed, two-level fanout) + `BLOB_THRESHOLD` inline/reference rule. *(functional)*
- **S-2.4** durability/fsync policies (`none`/`interval`/`always`); macOS `F_FULLFSYNC`; the fsync-failure path (no `RunFinalised` on a failed medium — tech §5.2). *(functional)*
- **S-2.5** locking: `flock` on persistent roots; Windows `UnsupportedPlatformError` at config time (tech §11). *(functional)* — closes **check 10**.
- **S-2.INT** record round-trips; simulated crash recovers to exact last complete frame; lock contention fails fast.

---

## Wave 3 — The writer + the append cycle  *(architecture)*  →  closes 1, 2, 4; 3

The single-writer heart (tech §6, §8). Architecture-band; candidate for **CT-4 best-of-N** (load-bearing contract).

- **S-3.1** `runtime.py` skeleton — the writer task loop, bounded admission queue, control queue (bypasses admission), reentrancy guard. *(architecture)*
- **S-3.2** the 6-step append cycle: validate → seq+append → update Views → stage Routes → eval Predicates/fire Triggers → drain control queue; the cycle exception handling (§6.3). *(architecture)*
- **S-3.3** validation at the boundary (§8) — pre-built `msgspec` decoders per (kind, version); the three failure classes → `ProducerEmittedInvalidEvent`; input sealing (§8.3, immutability by construction). *(functional)* — closes **check 4**.
- **S-3.INT** retry enrichment (check 1: failure reason staged same-cycle), single legal cascade (check 2), backpressure liveness (check 3: N+1 through bound-N, log intact, spill).

---

## Wave 4 — The primitives  *(functional)*  →  closes 5, 8, 17

The eight primitives layered on the cycle (tech §9, §10; kernel §5–8).

- **S-4.1** `views.py` — standard Views (buffer, kind-count, per-kind-latest, started/completed counts) + the subscription index (§6.5). *(functional)*
- **S-4.2** `triggers.py` — firing policies (Once/PerEvent/PerKey/WhileTrue), PerKey canonical-key extraction, cooldowns (Logical/WallClock + replay-ceiling demotion). *(functional)*
- **S-4.3** predicate budget enforcement (§9) — wall-time measure, hysteresis k=3 quarantine, off-hot-path sidecar buffer. *(functional)* — closes **check 8**.
- **S-4.4** Routes (`route` staging in step 4; push + pull) + `InjectionApplied`; `InputBuildFailed` on builder/transform raise. *(functional)* — closes **check 17**.
- **S-4.5** `policies.py` — TerminationPolicy callback + quiescence definition + standard recipes (cancel-all-others, let-finish, quiescence-with-watchdog, threshold-count, all-completed, subtree-cancellation, pause-await-input, any_of/all_of). *(functional)* — closes **check 5**.
- **S-4.6** `topology.py` — `TopologyBuilder` (one method per primitive), the registry, `b.initial`, registration validation. *(architecture)*
- **S-4.INT** quiescence finalises (check 5); over-budget predicate quarantines after k=3 + policy escalates (check 8); InputBuildFailed visible, no producer starts (check 17).

---

## Wave 5 — RunStarted, schema versioning, provenance  *(architecture/functional)*  →  closes 11

Frame 0 + self-describing records (tech §7; product F-SCHEMA-*, F-OBS-1/2).

- **S-5.1** `RunStarted` manifest emission — topology manifest, JSON-Schema descriptors from msgspec Structs, fingerprints, baseline. *(functional)*
- **S-5.2** schema versioning (per-run fixity; honest refusal on unsupported version) + provenance closure (every Producer → TriggerFired/resume/RunStarted). *(functional)* — closes **check 11**.
- **S-5.INT** provenance closure holds; no dangling ProducerIds; manifest rebuildable.

---

## Wave 6 — Replay + inspection  *(functional)*  →  closes 6, 12, 13

The replay engine and the deterministic query surface (tech §12, §14).

- **S-6.1** `replay.py` — Level 1 (state reconstruction) + Level 2 (decision reconstruction from recorded `substrate.*`). *(functional)*
- **S-6.2** Level 3(a) native (precondition-checked from metadata) + Level 3(b) substitution (log-backed deterministic emitters, recorded admission order). *(functional)* — closes **check 6** (byte-identical 3b) with Wave 1's encoding.
- **S-6.3** `inspect.py` — `explain_producer`, `trace_ancestry`, `view_at`, `decisions_between`. *(functional)* — closes **check 12** (view-at fidelity).
- **S-6.4** `first_divergence` under the D-8 equivalence relation. *(functional)* — closes **check 13**.
- **S-6.INT** replay round-trip + view-at + divergence localization end-to-end.

---

## Wave 7 — Live attach + CLI + sidecars  *(functional)*  →  closes 14; F-PERS-4

The reader surfaces; the CLI as F-API-6 existence proof (tech §13, §6.4; design §5).

- **S-7.1** `attach.py` — follower (poll-based, CRC-verify, ignore partial tail; never opens for write). *(functional)* — F-PERS-4.
- **S-7.2** `cli.py` part A — `run`, `tail` (with required filters), `validate`; Click + Rich; public-API-only. *(functional)*
- **S-7.3** `cli.py` part B — `inspect`, `replay` (+ `--diff`), `resume`, `conformance`. *(functional)*
- **S-7.4** writer-stats sidecar (§6.4) + diagnostic sidecar (§3.8, off hot path) + `stats` command. *(functional)* — closes **check 14** (diagnostic invariance: bus log bit-identical on/off).
- **S-7.INT** CLI drives a run end-to-end; tail/inspect/replay output matches design §5 shapes; import-lint confirms public-API-only.

---

## Wave 8 — Composition  *(architecture/functional)*  →  closes 7

Substrate-as-Producer + export maps (tech §20; kernel §"composes with itself").

- **S-8.1** embedded-substrate Producer + `b.export` export-map declaration + boundary translator (inner→outer, validated at outer boundary). *(architecture)*
- **S-8.2** backpressure cascade at the boundary; unmapped/`substrate.*` kinds don't cross; inner failure → outer `ProducerFailed`. *(functional)* — closes **check 7**.
- **S-8.INT** export boundary check end-to-end; nested depth smoke test.

---

## Wave 9 — Conformance suite + reference topologies + docs  *(observation/docs)*  →  closes 15; release gate

The acceptance spine made executable (product §7, §8, §12).

- **S-9.1** the 17-check conformance harness wired to `substrate conformance` (most checks already proven per-wave; this assembles + gates them). *(observation)*
- **S-9.2** R-1 Ensemble+adjudicator (dual-mode: CI deterministic + walkthrough local-LLM). *(observation)*
- **S-9.3** R-2 Pipeline with structured error cascade (the §0.1 miniature, full). *(observation)*
- **S-9.4** R-3 Code-synthesis-with-overlap, composed (embedded substrate, tree-sitter). *(observation)*
- **S-9.5** perf gates — N-PERF-1 floor (≥100K appends/sec, reference shape) + check-15 regression vs previous tag. *(observation)* — closes **check 15**.
- **S-9.6** docs per N-DOC-1 (first-topology tutorial + per-topology walkthroughs; API ref from docstrings). *(docs)*
- **S-9.INT** all 17 green in CI on Linux+macOS; N-DET-1 verified; R-1..R-3 green CI-mode + run walkthrough-mode; **definition-of-done (product §12) met**.

---

## Conformance-check → wave map (CT-5 acceptance spine)

| Check | Closed in | | Check | Closed in |
|---|---|---|---|---|
| 1 retry enrichment | W3 | | 10 persistent-bus locking | W2 |
| 2 single cascade | W3 | | 11 provenance closure | W5 |
| 3 backpressure liveness | W3 (W2 spill) | | 12 view-at fidelity | W6 |
| 4 invalid-emission cascade | W3 | | 13 divergence localization | W6 |
| 5 quiescence | W4 | | 14 diagnostic invariance | W7 |
| 6 replay byte-identical 3b | W6 (+W1 encoding) | | 15 perf regression | W9 |
| 7 export boundary | W8 | | 16 torn-tail recovery | W2 |
| 8 quarantine visibility | W4 | | 17 InputBuildFailed | W4 |
| 9 determinism | W1 | | | |

---

## Parallelism / orchestration notes

- **Worktrees (CT-3):** within a wave, file-disjoint sprints can run concurrently in separate git worktrees. Candidates: W2's S-2.3 (blobs) ∥ S-2.4 (fsync); W4's S-4.1 (views) ∥ S-4.2 (triggers) ∥ S-4.5 (policies); W6's S-6.3 (inspect) ∥ S-6.4 (divergence); W9's R-1/R-2/R-3. *Across* waves stays sequential — later waves depend on earlier contracts.
- **Best-of-N (CT-4):** reserve for the load-bearing architecture sprints — W1 encoding, W2 frame/recovery, W3 the append cycle. A wrong contract there is expensive (conformance is conjunctive).
- **Wave-0-carry (technique 15):** S-0.2/S-0.3 pre-fill `types.py`/`protocols.py`/`constants.py` so parallel later sprints merge against fixed shapes instead of re-declaring them (canonical home registry, hard rule 7).

---

*PHASE1_PLAN.md — proposed wave structure for Substrate v1.0. Nine waves + Wave 0, dependency-ordered (encoding → record → writer → primitives → manifest/provenance → replay/inspect → attach/CLI → composition → conformance/topologies/docs), each closing its conformance checks, each ending in an N.INT. Sprint cards authored per-wave once the vocabulary locks. Pending vocabulary lock + Architect go.*
