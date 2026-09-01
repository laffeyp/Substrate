#!/usr/bin/env bash
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
# ci_local_ubuntu.sh — the ubuntu cells of the CI matrix, run locally via Docker.
#
# Companion to scripts/ci_local.sh (the host-OS cells): covers the linux/glibc axis the host
# can't. The repo is COPIED into the container (mounted read-only), so the run never writes
# root-owned files into the working tree. Honest caveats vs hosted CI:
#   - Arch: runs linux/arm64 natively on Apple Silicon (hosted ubuntu-latest is x86_64).
#     Same glibc/linux axis, different ISA; pass `--platform linux/amd64` via DOCKER_PLATFORM
#     for the emulated x86 run if the ISA matters (slow).
#   - realmodel tests skip (no Ollama in the container) — same as hosted CI.
#
# Usage: scripts/ci_local_ubuntu.sh [3.12 3.13 3.14]   (default: 3.12 only — the smoke cell)
set -u
cd "$(dirname "$0")/.."
if [ $# -gt 0 ]; then versions=("$@"); else versions=(3.12); fi
platform="${DOCKER_PLATFORM:-}"
overall=0
summary=()
for py in "${versions[@]}"; do
  echo "=== gates (docker ubuntu, py${py}) ==="
  # the NON-slim image: it carries git, which the swebench workspace/solver tests need (hosted
  # ubuntu runners preinstall it; the slim image's absence failed 29 tests — a real env diff).
  img="ghcr.io/astral-sh/uv:python${py}-bookworm"
  if docker run --rm ${platform:+--platform "$platform"} -v "$(pwd):/src:ro" "$img" sh -c '
      set -e
      cp -r /src /w && cd /w
      uv venv --python '"${py}"' >/dev/null 2>&1 || uv venv
      uv pip install -q -e ".[dev]"
      uv run ruff check
      uv run ruff format --check
      uv run mypy
      uv run python -m pytest -q
      uv run lint-imports
      uv run substrate conformance --no-perf
    '; then
    summary+=("ubuntu py${py}: PASS")
  else
    summary+=("ubuntu py${py}: FAIL")
    overall=1
  fi
done
echo
echo "=== docker ubuntu matrix summary ==="
printf '%s\n' "${summary[@]}"
exit ${overall}
