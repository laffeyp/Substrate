"""Generate the committed CI-mode run records for R-1/R-2/R-3 under docs/walkthroughs/records/.

These records are DETERMINISTIC (deterministic stand-in Producers, no network) and small, so
they can be committed and read back from a fresh checkout — they ARE the durable, replayable
artifact the product is about. `docs/walkthroughs/README.md` points `substrate tail` / `inspect`
/ `replay` at them. Regenerate with `uv run python scripts/gen_walkthrough_records.py` after a
reference-topology change that alters the recorded event shape.

Note: each record's wall-clock `t` field varies per generation (it is excluded from D-8
log-equivalence); the EVENT SEQUENCE is what is stable and asserted by tests/test_reference.py.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from substrate.api import Runtime
from substrate.reference._models import DeterministicResponder
from substrate.reference.r1_ensemble import ensemble_topology
from substrate.reference.r2_pipeline import operator_override, pipeline_topology
from substrate.reference.r3_codesynth import codesynth_composed_topology

RECORDS = Path(__file__).resolve().parent.parent / "docs" / "walkthroughs" / "records"


async def _gen_r1(root: Path) -> None:
    members = {
        f"m{i}": DeterministicResponder(seed=i, menu=["Paris", "Lyon", "Nice"]) for i in range(5)
    }
    topo = ensemble_topology(
        "Capital of France?",
        members=members,
        adjudicator=DeterministicResponder(seed=99, menu=["m0", "m1", "m2"]),
        quorum=3,
        deterministic=True,
    )
    await Runtime(root).run(topo)


async def _gen_r2(root: Path) -> None:
    topo = pipeline_topology(
        ["alpha", "beta", "gamma", "delta"],
        transform_model=DeterministicResponder(seed=0),
        fault_row=1,
        hard_fault_row=2,
        malformed_row=3,
        deterministic=True,
    )
    await Runtime(root, persistent=True).run(topo)  # runs to the pause
    await Runtime(root, persistent=True).resume(topo, resume_event=operator_override(row=2))


async def _gen_r3(outer: Path, inner: Path) -> None:
    chunks = ["def add(a, b):\n", "    return a + b\n", "def mul(a, b):\n    return a * b\n"]
    topo = codesynth_composed_topology(chunks, str(inner), deterministic=True)
    await Runtime(outer).run(topo)


async def main() -> None:
    if RECORDS.exists():
        shutil.rmtree(RECORDS)
    RECORDS.mkdir(parents=True)
    await _gen_r1(RECORDS / "r1")
    await _gen_r2(RECORDS / "r2")
    await _gen_r3(RECORDS / "r3", RECORDS / "r3-inner")
    # The persistent-mode r2 run leaves a .lock file (an exclusive-lock marker for a LIVE run);
    # it is runtime state, not part of the durable record, so drop it from the committed set.
    for lock in RECORDS.rglob(".lock"):
        lock.unlink()
    print(f"wrote CI-mode records under {RECORDS}")


if __name__ == "__main__":
    asyncio.run(main())
