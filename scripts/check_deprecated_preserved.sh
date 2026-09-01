#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
# check_deprecated_preserved.sh — CI guard for hard rule 12's audit-trail discipline.
#
# Sprint 175 (external F13 fold). AGENTS.md hard rule 12: "New thinking goes into new files /
# folders / round-N versions. The audit trail is the work." `_deprecated/` directories under
# `topologies/`, `scripts/`, and elsewhere hold retired-in-place artifacts whose bodies must
# survive as the reference the reviews and postmortems cite back to. Nothing in the tooling
# prevents a fast-follow commit from `rm`-ing a `_deprecated/` file — the discipline lives
# in code review, not in the tree.
#
# This script fails when a commit reachable from HEAD deletes a file under any `_deprecated/`
# path. Runs against `origin/main...HEAD` by default (matches the CI baseline). Twenty seconds
# of CI, forever; the audit trail then depends on the tree, not on reviewer memory.
#
# Called from scripts/ci_local.sh and .github/workflows/ci.yml as a `substrate conformance`
# sibling. Silent success (exit 0) on the common case; loud failure with the deleted paths
# named on trip.
#
# Bypass discipline: if the Architect genuinely wants to prune a `_deprecated/` file (a rare
# override — e.g., a superseded revival path a later sprint retires from `_deprecated/`
# itself), the ruling is recorded in `## Decisions` and the guard is disabled for that one
# commit via `git commit --no-verify` OR the guard's `SUBSTRATE_ALLOW_DEPRECATED_DELETION=1`
# escape hatch. Every use of either is a KIT_DIARY entry.
set -u

BASE="${SUBSTRATE_DEPRECATED_GUARD_BASE:-origin/main}"

if [ "${SUBSTRATE_ALLOW_DEPRECATED_DELETION:-0}" = "1" ]; then
  echo "check_deprecated_preserved: SUBSTRATE_ALLOW_DEPRECATED_DELETION=1 — skipping."
  exit 0
fi

# `git diff --diff-filter=D` reports files DELETED between the range's endpoints.
# Silent when the range is unresolvable (e.g., a shallow clone with no origin/main) — the
# guard fails-closed only on positive detection, not on missing history.
if ! git rev-parse --verify "${BASE}" >/dev/null 2>&1; then
  echo "check_deprecated_preserved: base ref '${BASE}' not resolvable; skipping."
  exit 0
fi

deleted=$(git diff --diff-filter=D --name-only "${BASE}"...HEAD 2>/dev/null | grep '_deprecated/' || true)

if [ -n "${deleted}" ]; then
  echo "check_deprecated_preserved: FAIL — files under _deprecated/ were deleted between ${BASE} and HEAD:"
  echo "${deleted}" | sed 's/^/  - /'
  echo
  echo "AGENTS.md hard rule 12: the audit trail is the work. Restore the deleted files, or"
  echo "record an Architect ruling in process/BLACKBOARD.md ## Decisions naming this"
  echo "deprecation-pruning and set SUBSTRATE_ALLOW_DEPRECATED_DELETION=1 for the specific"
  echo "commit that lands the removal."
  exit 1
fi

echo "check_deprecated_preserved: PASS — no _deprecated/ file deletions between ${BASE} and HEAD."
exit 0
