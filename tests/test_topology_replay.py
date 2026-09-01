# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Level-2 replay verification for the bundled Phase-2 topologies (S-11 tail).

Each topology's CI-mode record replays at Level 2 — every substrate.TriggerFired's recorded
resolved input re-hashes to its recorded input_sha256 (D-5). Level 3(b) byte-identity is the
deferred A1.1 item (replay(level="3b") raises NotImplementedError, conformance check 6); these
topologies ship the same tier the runtime ships: Level 1/2 + 3(a) precondition.
"""

import pytest

from substrate.api import Runtime, assert_replayable, replay
from substrate.reference._models import DeterministicResponder
from substrate.topologies.code_review import DEFAULT_ROLES, code_review_topology
from substrate.topologies.pair_coding import pair_coding_topology
from substrate.topologies.recursive_decomposition import recursive_decomposition_topology


def _code_review():
    return code_review_topology(
        "def f(x):\n    return x / 0\n",
        responders={r: DeterministicResponder(seed=i) for i, r in enumerate(DEFAULT_ROLES)},
        judge=DeterministicResponder(seed=99),
        quorum=3,
    )


def _pair_coding():
    return pair_coding_topology(
        "write solve()",
        driver_model=DeterministicResponder(seed=1),
        navigator_model=DeterministicResponder(seed=2),
        chunks=["def solve(x):\n", "    y = x + 1\n", "    return y\n"],
    )


def _recursive():
    return recursive_decomposition_topology(
        "build a feature",
        solver_model=DeterministicResponder(seed=3),
        max_depth=2,
        fanout=2,
    )


@pytest.mark.timeout(15)
@pytest.mark.parametrize(
    "name,thunk",
    [("code_review", _code_review), ("pair_coding", _pair_coding), ("recursive", _recursive)],
)
async def test_ci_record_replays_level_2(tmp_path, name, thunk):
    root = tmp_path / name
    await Runtime(root).run(thunk())
    # Level 2: every recorded decision's input hash re-verifies (D-5); raises on any mismatch.
    result = assert_replayable(root, "2")
    assert result.level == "2"
    assert result.decisions_verified > 0  # the topology made recorded Trigger decisions
    assert not result.mismatches
    # Level 3(b) is honestly refused (the deferred A1.1 item), never faked as success.
    with pytest.raises(NotImplementedError):
        replay(root, "3b")
