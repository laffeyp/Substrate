#!/usr/bin/env bash
# A live walk through what Substrate actually does, run entirely against the
# committed reference records — no LLM, no network, no setup beyond the dev install.
#
#   uv run bash demo.sh        (or: source .venv/bin/activate && bash demo.sh)
#
# Everything below reads committed artifacts under docs/walkthroughs/records/.
# Each record is the durable, replayable output of one reference topology; the
# Producers in these records are deterministic stand-ins, so the runs reproduce
# byte-for-byte on any machine. See docs/demo.md for the annotated version.

set -euo pipefail
R=docs/walkthroughs/records
hr() { printf '\n\033[1m%s\033[0m\n' "$*"; }

hr "1. Ensemble + adjudicator (R-1) — concurrent Producers, predicate-triggered spawn"
substrate tail $R/r1
hr "   replay it back (state + every decision, each input verified by hash):"
substrate replay $R/r1 --level 2

hr "2. Retry / escalate / pause-for-operator (R-2) — failure feedback over Routes"
substrate tail $R/r2
hr "   replay:"
substrate replay $R/r2 --level 2

hr "3. Streaming code synth + concurrent checker (R-3 inner) — per-declaration Triggers"
substrate tail $R/r3-inner
hr "   replay:"
substrate replay $R/r3-inner --level 2

hr "4. Provenance: how did the final artifact come to exist? (causal chain to RunStarted)"
substrate inspect $R/r3-inner \
  --producer "artifact[01KV1VGAYWVBTJ35V5Q54W7A72]" --ancestry

hr "5. The release gate: conformance suite (one canonical topology per spec property)"
substrate conformance --no-perf

hr "Done. Every line above is a query over a committed record — read the log, never the runtime's mind."
