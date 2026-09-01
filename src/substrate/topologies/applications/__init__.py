# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Applications — the agent-CLI orchestration patterns as substrate topologies.

Each is a real topology composed from primitives that exist and are tested, fed REAL input
instead of a demo blob, so the pattern is one launch away and its run is a replayable record:
`fanout_review` (a review panel over a real git diff), `best_of_n_verified` (generate N,
verify, select), `research_sweep` (map readers over a document set, critique, synthesize).
See `docs/applications.md`.

Two COMPOSE an existing topology and one is authored from primitives; none reimplements the
kernel. `fanout_review` gathers a diff and hands it to `code_review_topology` unchanged.

("application", not "workflow": the lexicon (design_spec draft1 / product principle 6) bans reframing
SUBSTRATE'S OWN concepts in marketing terms — a topology as a "workflow", a firing as a "step", a run
as a "task". This package was renamed from `workflows/` per that rule. The word "task" for the PROBLEM
an agent solves is the input domain, not a reframe, and stays — Architect-ruled 2026-08-03, review C-6.)
"""

from __future__ import annotations

from .best_of_n_verified import best_of_n_verified_topology
from .fanout_review import changed_files, fanout_review_topology
from .research_sweep import gather, research_sweep_topology

__all__ = [
    "best_of_n_verified_topology",
    "changed_files",
    "fanout_review_topology",
    "gather",
    "research_sweep_topology",
]
