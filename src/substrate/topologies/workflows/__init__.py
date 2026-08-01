"""Workflow applications — the agent-CLI workflow patterns as substrate topologies.

Each is a real topology composed from primitives that exist and are tested, fed REAL input
instead of a demo blob, so the pattern is one launch away and its run is a replayable record.
The first is `fanout_review` (a review panel over a real git diff); best-of-N-verified and
research-sweep follow (docs/cockpit/WORKFLOW-PARITY-SPRINTS-2026-07-31.md, phase W1).

These COMPOSE existing topologies; they do not reimplement them. `fanout_review` gathers a
diff and hands it to `code_review_topology` unchanged.
"""

from __future__ import annotations

from .best_of_n_verified import best_of_n_verified_topology
from .fanout_review import changed_files, fanout_review_topology

__all__ = ["best_of_n_verified_topology", "changed_files", "fanout_review_topology"]
