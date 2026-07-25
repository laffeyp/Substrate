"""Bundled topology registry — makes `substrate run --topology <name>` work (review #16).

The CLI advertises `--topology <name>` and an error that names a registry, but the registry
ships empty, so a newcomer hits a dead end. This module populates it with CI-default (no-network,
deterministic) configs of the bundled topologies; `cli._load_topology` imports this module
DYNAMICALLY on a `--topology` lookup, so the CLI's static import surface stays substrate.api-only
(F-API-6 — import-linter checks static imports, not a runtime importlib call).

CI defaults run anywhere with no Ollama and produce a replayable record (tail / replay / inspect
all work). The richer real-LLM walkthrough is a separate path (the demo's `walkthrough=True`).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import api
from ..adapters import DeterministicResponder
from .adversarial_pair import adversarial_pair_topology
from .code_review import DEFAULT_ROLES, code_review_topology
from .debate import debate_topology
from .intel_asymmetry import intel_asymmetry_topology
from .natural_conversation import natural_conversation_topology
from .prisoners_dilemma import prisoners_dilemma_topology
from .pair_coding import pair_coding_topology
from .game_of_life import game_of_life_topology, glider
from .recursive_decomposition import recursive_decomposition_topology
from .tool_loop import tool_loop_topology

_Topo = Callable[[api.TopologyBuilder], None]


def _code_review() -> _Topo:
    # slow_roles + linger so the demo (and the committed record, now generated from THIS factory)
    # actually demonstrates cancel-all-others: the lingering reviewers are cancelled when the judge
    # fires (review #25 finding A — `demo run` must show what `demo replay` shows).
    return code_review_topology(
        "def f(x):\n    return x / 0\n",
        responders={r: DeterministicResponder(seed=i) for i, r in enumerate(DEFAULT_ROLES)},
        judge=DeterministicResponder(seed=99),
        quorum=3,
        slow_roles=frozenset({"correctness", "clarity"}),
        linger_seconds=0.5,
    )


def _pair_coding() -> _Topo:
    return pair_coding_topology(
        "write solve()",
        driver_model=DeterministicResponder(seed=1),
        navigator_model=DeterministicResponder(seed=2),
        chunks=["def solve(x):\n", "    y = x + 1\n", "    return y\n"],
    )


def _recursive() -> _Topo:
    return recursive_decomposition_topology(
        "build a feature", solver_model=DeterministicResponder(seed=3), max_depth=2, fanout=2
    )


# name -> a zero-arg factory returning the CI-default configured topology.
BUNDLED: dict[str, Callable[[], _Topo]] = {
    "code_review": _code_review,
    "pair_coding": _pair_coding,
    "recursive_decomposition": _recursive,
    "debate": debate_topology,
    "prisoners_dilemma": prisoners_dilemma_topology,
    "intel_asymmetry": intel_asymmetry_topology,
    "natural_conversation": lambda: natural_conversation_topology(instruments=True),
    # the WITHOUT arm, so the ablation is a runnable WITH-vs-WITHOUT contrast (review #17):
    # run both and diff the records to SEE what the instruments buy.
    "natural_conversation_bare": lambda: natural_conversation_topology(instruments=False),
    "adversarial_pair": adversarial_pair_topology,
    "tool_loop": tool_loop_topology,
    "game_of_life": game_of_life_topology,
    # an asymmetric, MOVING glider (vs the symmetric blinker) — the fixture that lets the pixel-decode
    # harness catch a pure mirror render bug the mirror-symmetric blinker cannot show.
    "game_of_life_glider": lambda: game_of_life_topology(initial=glider(), generations=4),
}

_registered = False


def register_all() -> None:
    """Register every bundled topology under its name (idempotent). Called on demand by the CLI."""
    global _registered
    if _registered:
        return
    for name, factory in BUNDLED.items():
        api.register_topology(name, factory())
    _registered = True


def names() -> list[str]:
    """The bundled topology names (for `topology list` / discovery)."""
    return sorted(BUNDLED)


def record_path(name: str) -> Path:
    """The committed CI-mode record path for a bundled topology (for `demo replay <name>`)."""
    return Path(__file__).resolve().parent / name / "records" / "ci_mode.record"
