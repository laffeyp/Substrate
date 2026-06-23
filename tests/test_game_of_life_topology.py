"""Game of Life — CI structural + determinism tests (Wave 15).

The blinker is a period-2 oscillator (vertical -> horizontal -> vertical), so a two-generation
run must return to its starting grid, having genuinely changed in between — and every cell of a
generation must have computed concurrently against the shared world-state.
"""

import pytest

from substrate.api import Runtime, first_divergence, read_record
from substrate.topologies.game_of_life import blinker, game_of_life_topology


@pytest.mark.timeout(20)
async def test_blinker_oscillates(tmp_path):
    result = await Runtime(tmp_path / "run").run(game_of_life_topology())
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    gens = sorted(
        (e["payload"] for e in envs if e["kind"] == "Generation"), key=lambda p: p["tick"]
    )
    assert [g["tick"] for g in gens] == [0, 1, 2]
    g0, g1, g2 = (g["grid"] for g in gens)
    # the blinker: vertical bar -> horizontal bar -> vertical bar (period 2).
    assert g0 == blinker()  # starts as the seeded vertical blinker
    assert g0[1][2] == g0[2][2] == g0[3][2] == 1
    assert g1[2][1] == g1[2][2] == g1[2][3] == 1  # rotated to horizontal
    assert g1 != g0  # it actually changed
    assert g2 == g0  # and returned — period-2 oscillation
    # every cell of each advancing generation computed (concurrently) against the shared grid.
    for tick in (0, 1):
        nexts = [e for e in envs if e["kind"] == "CellNext" and e["payload"]["tick"] == tick]
        assert len(nexts) == 25  # 5x5
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(20)
async def test_game_of_life_is_deterministic(tmp_path):
    await Runtime(tmp_path / "a").run(game_of_life_topology())
    await Runtime(tmp_path / "b").run(game_of_life_topology())
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None
