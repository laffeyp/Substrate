#!/usr/bin/env bash
# ci_local.sh — run the EXACT CI gate stack locally, per Python version. THE DEFAULT GATE.
#
# As of 2026-07-22 (Architect ruling) this is the project's primary verification gate:
# hosted GitHub Actions is unavailable (minutes exhausted) and the verification bar must
# never depend on a hosted runner. Mirrors .github/workflows/ci.yml step for step (lint,
# format-check, strict mypy, pytest, lint-imports, conformance --no-perf). "Gates green"
# means THIS script exiting 0, watched to conclusion — the finding-33/36 bar, local form.
#
# Differences from hosted CI, stated:
#   - OS axis: runs on THIS machine. For the ubuntu cells: scripts/ci_local_ubuntu.sh (Docker).
#   - realmodel tests: hosted CI has no Ollama (they skip); locally they RUN when the daemon
#     is up — strictly stronger on that axis.
#   - Each version runs in an ISOLATED env (uv run --isolated --extra dev), like CI's fresh
#     venv, so an undeclared dependency fails here the way it fails there (the httpx lesson).
#
# Usage: scripts/ci_local.sh [3.12 3.13 3.14]   (default: all three)
set -u
cd "$(dirname "$0")/.."
if [ $# -gt 0 ]; then versions=("$@"); else versions=(3.12 3.13 3.14); fi

overall=0
summary=()
for py in "${versions[@]}"; do
  echo "=== gates (local, py${py}) ==="
  fail=""
  for gate in "ruff check" "ruff format --check" "mypy" "python -m pytest" "lint-imports" "substrate conformance --no-perf"; do
    echo "--- ${gate}"
    if ! uv run --isolated --python "${py}" --extra dev ${gate}; then
      fail="${fail}[${gate}] "
      overall=1
    fi
  done
  if [ -z "${fail}" ]; then
    summary+=("py${py}: PASS")
  else
    summary+=("py${py}: FAIL ${fail}")
  fi
done
echo
echo "=== local CI matrix summary ($(uname -s) $(uname -m)) ==="
printf '%s\n' "${summary[@]}"
exit ${overall}
