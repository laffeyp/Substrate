# Sprint 175 — CI guard against `_deprecated/` deletions (fold external F13)

---

```yaml
---
id: 175
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Close F13. AGENTS.md hard rule 12 says restructures land as new files and the audit trail is the work; `_deprecated/` directories under `topologies/` and elsewhere hold retired-in-place artifacts whose bodies are the reference the reviews and postmortems cite back to. Nothing in the tooling prevented a fast-follow commit from `rm`-ing a `_deprecated/` file. Sprint 175 adds a CI guard.

## files created

- `scripts/check_deprecated_preserved.sh` — bash script. `git diff --diff-filter=D --name-only "${BASE}"...HEAD | grep _deprecated/` — non-empty output fails the run with the deleted paths named. `SUBSTRATE_DEPRECATED_GUARD_BASE` defaults to `origin/main`. `SUBSTRATE_ALLOW_DEPRECATED_DELETION=1` escape hatch for the rare Architect-ratified deprecation-pruning case (a KIT_DIARY entry per use). Fails-open when the base ref is unresolvable (shallow clone) — the guard fails-closed only on positive detection.

## files modified

- `scripts/ci_local.sh` — invokes `check_deprecated_preserved.sh` once outside the per-Python-version gate loop; appends the pass/fail line to the summary.
- `.github/workflows/ci.yml` — adds a `Fetch base ref for _deprecated/ guard` step (so origin/main is resolvable in the runner) and a `_deprecated/ preservation guard` step calling the same script.

## contracts

- Bash script exits 0 on HEAD (no `_deprecated/` deletions between origin/main and HEAD). Verified locally: "PASS — no _deprecated/ file deletions between origin/main and HEAD."
- A commit that deletes a `_deprecated/` file trips the guard both locally (via `ci_local.sh`) and in GitHub Actions.
- Bypass discipline: Architect ruling in `## Decisions` + `SUBSTRATE_ALLOW_DEPRECATED_DELETION=1` on the specific commit. Every use logs to KIT_DIARY.

## done

Three files (one new + two modified). The audit trail depends on the tree, not on reviewer memory. Twenty seconds of CI, forever.
