# applications — locked record vocabulary

Status: RATIFIED retroactively (2026-07-31 review remediation, F-17). These records shipped in sprints
137-139 as topology-local Structs (the code_review precedent — `CritiquePosted`/`VerdictRendered` are
undocumented in the same way). The review's point stands: the project's more recent discipline
(`swebench-solver-vocabulary.md`) locks records BEFORE the topology (KIT_DIARY #14, "the check that made
it REAL not nominal"), and `Finding`/`Gaps` are exactly the generic names a second topology will want.
This doc locks them now and registers the home so a future topology reconciles against it rather than
colliding. Strict validator-extras (project posture).

Home: `src/substrate/topologies/applications/` (registered in `process/WORKING_AGREEMENT.md`).

## fanout_review — reuses code_review's records + one record-completeness kind

`fanout_review` composes `code_review_topology`; it emits `CritiquePosted` and `VerdictRendered` — the
code_review kinds — plus lifecycle, plus `ModelUsage` per reviewer/judge call (metered on the code_review
side, review C-7). It authors ONE record of its own:

| Record | Locked fields | Meaning |
|---|---|---|
| `ReviewSubject` | `ref:str, chars:int, content:str` | the material the panel reviewed (the gathered diff), emitted ONCE before the critiques so a replay carries the SUBJECT of the verdict, not just the verdict (review C-2). |

(code_review's own kinds remain undocumented in a vocabulary file; that is a pre-existing gap, not this
wave's.)

## best_of_n_verified — reuses best_of_n's records (no new vocabulary)

Composes `best_of_n_correction`; emits `Draft`/`Candidate`/`Verdict`/`Solved`/`Exhausted` + `ModelUsage`,
all locked in `swebench-solver-vocabulary.md` §A as the shared 3-consumer contract. Authors none.

## research_sweep — four topology-local records (AUTHORED — locked here)

Map-reduce has no existing whole to compose, so these four were authored. Frozen msgspec Structs,
`schema_version=1`, all `replayable` (pure data, no host-specific fields).

| Record | Locked fields | Meaning |
|---|---|---|
| `ReadRequest` | `index:int, source:str, content:str` | one document handed to one reader (the map seed); `content` is bounded to `_MAX_DOC_CHARS`. |
| `Finding` | `index:int, source:str, note:str` | EXACTLY ONE per `ReadRequest`, even on reader failure (`note`=`(read failed: …)` / `(no contribution)`), so the fan-in count always reaches n. |
| `Gaps` | `note:str` | the completeness critic's account of what the findings do NOT cover; `(critic failed: …)` on a failed critic call. |
| `Synthesis` | `text:str` | the reduce output grounded in findings + gaps; `(synthesis failed: …)` on a failed synthesizer call. |
| `ModelUsage` | (from `adapters.models`) | per reader/critic/synthesizer call, metered onto the record (F-18) so the sweep is assayable. Reused, not re-rolled. |

Naming note (F-17): `Finding` and `Gaps` are GENERIC. A future topology wanting the same names must
reconcile against these locked fields (reuse-as-canonical, like the swebench §A decision) rather than
declare a colliding kind. If a second consumer appears, extract these to a NEUTRAL home the way
`best_of_n/contracts.py` was extracted (review #61).

## dual-contract audit (#25)

- Signal: the kinds above + code_review's/best_of_n's for the composing apps; each app's contract test
  asserts the kinds, their order, AND the model-facing text (F-11), plus the `ModelUsage` count (F-18).
- Artifact: `ruff`/`ruff format --check`/`mypy --strict` clean across `topologies/applications/`.
