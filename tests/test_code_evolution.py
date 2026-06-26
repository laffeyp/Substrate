"""code_evolution — the evolutionary loop's decisions (pure) + the topology wiring (integration).

The EA decisions (selection, terminate-at-budget, exhaust, stagnation) are a PURE function, tested
directly and exhaustively. The topology run is an outcome-deterministic smoke test (CI responders draft
a fixed correct genome; the loop must run its generations, select on cost, and reach a terminal) — the
real claim (does evolution lower cost vs best-of-N) needs real models and the assay, not this.
"""

import asyncio
import tempfile

from substrate import api
from substrate.topologies.code_evolution import (
    _ast_cost,
    _decide,
    ci_responders,
    code_evolution_topology,
)
from substrate.topologies.coding_flow.gate import parse_artifacts, sanitize_candidate_artifacts
from substrate.topologies.coding_flow.task import CodingTask

# ── the pure evolutionary decision ──


def test_decide_selects_lowest_cost_and_evolves_at_max_gens():
    pop = [
        {"gen": 1, "slot": 0, "code": "a", "correct": True, "cost": 50},
        {"gen": 1, "slot": 1, "code": "b", "correct": True, "cost": 30},
        {"gen": 2, "slot": 0, "code": "c", "correct": True, "cost": 20},
        {"gen": 2, "slot": 1, "code": "d", "correct": False, "cost": 10**9},
    ]
    kind, best = _decide(pop, 2, n=2, max_gens=2, select_k=2, patience=5)
    assert kind == "evolve" and best["cost"] == 20 and best["code"] == "c"


def test_decide_spawns_elite_parents_lowest_cost_first():
    pop = [
        {"gen": 1, "slot": 0, "code": "a", "correct": True, "cost": 50},
        {"gen": 1, "slot": 1, "code": "b", "correct": True, "cost": 30},
        {"gen": 1, "slot": 2, "code": "c", "correct": False, "cost": 10**9},
    ]
    kind, parents = _decide(pop, 1, n=3, max_gens=4, select_k=2, patience=5)
    assert kind == "spawn" and parents == ("b", "a")  # the two correct ones, lowest cost first


def test_decide_exhausts_when_no_correct_genome_within_budget():
    pop = [
        {"gen": 1, "slot": 0, "code": "x", "correct": False, "cost": 10**9},
        {"gen": 2, "slot": 0, "code": "y", "correct": False, "cost": 10**9},
    ]
    kind, payload = _decide(pop, 2, n=1, max_gens=2, select_k=2, patience=5)
    assert kind == "exhaust" and payload is None


def test_decide_stagnation_terminates_before_max_gens():
    # a correct genome at gen 1, NO cost improvement through gen 4; patience 2 -> stagnant by gen 4.
    pop = [
        {"gen": g, "slot": 0, "code": chr(96 + g), "correct": True, "cost": 30} for g in range(1, 5)
    ]
    kind, best = _decide(pop, 4, n=1, max_gens=10, select_k=1, patience=2)
    assert kind == "evolve" and best["cost"] == 30  # stopped early, not at max_gens=10


def test_decide_continues_while_cost_is_improving():
    # improving every generation -> NOT stagnant -> keep evolving (budget remains).
    pop = [
        {"gen": g, "slot": 0, "code": chr(96 + g), "correct": True, "cost": 60 - 10 * g}
        for g in range(1, 4)
    ]
    kind, _ = _decide(pop, 3, n=1, max_gens=10, select_k=1, patience=2)
    assert kind == "spawn"


def test_ast_cost_rewards_smaller_programs():
    terse = _ast_cost(
        parse_artifacts("# path: m.py\n```python\ndef f(x: int) -> int:\n    return x + 1\n```\n")
    )
    verbose = _ast_cost(
        parse_artifacts(
            "# path: m.py\n```python\ndef f(x: int) -> int:\n    y = x\n    z = 1\n    return y + z\n```\n"
        )
    )
    assert 0 < terse < verbose < 10**9
    assert _ast_cost(parse_artifacts("not a fenced block")) == 10**9  # no parseable module


# ── the topology wiring (outcome-deterministic) ──

_GENOME = "# path: inc.py\n```python\ndef f(x: int) -> int:\n    return x + 1\n```\n"
_TASK = CodingTask(
    name="inc",
    spec="Write `def f(x: int) -> int` in inc.py.",
    gate="ruff check . && mypy --strict . && python -m pytest -c /dev/null -q",
    fixtures={
        "test_dev.py": "from inc import f\n\n\ndef test_inc() -> None:\n    assert f(1) == 2\n"
    },
    ci_good="",
    ci_bad="",
)


def test_topology_runs_generations_and_reaches_evolved():
    topo = code_evolution_topology(
        _TASK, responders=ci_responders(_GENOME, 2), n=2, max_gens=2, patience=5, deterministic=True
    )
    d = tempfile.mkdtemp()
    asyncio.run(api.Runtime(d).run(topo))
    rec = list(api.read_record(d))
    evolved = [e for e in rec if e["kind"] == "Evolved"]
    assert len(evolved) == 1  # reached the success terminal
    expected = _ast_cost(sanitize_candidate_artifacts(parse_artifacts(_GENOME)))
    assert evolved[0]["payload"]["cost"] == expected  # selected the genome and scored its real cost
    # the loop actually advanced TWO generations (mutation is the model work; it metered).
    assert {int(e["payload"]["gen"]) for e in rec if e["kind"] == "Genome"} == {1, 2}
    assert any(e["kind"] == "ModelUsage" for e in rec)  # mutation metered onto the record
