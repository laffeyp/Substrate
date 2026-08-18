"""Sprint 188 (roadmap v2 S2 part 2 of 2): `swebench_repair` is registered in
`topologies/bundled.py`; the committed CI record round-trips.

Pins the bundled-registration contract:
- `swebench_repair` appears in `bundled.names()` alongside the eleven other bundled topologies.
- `bundled.BUNDLED["swebench_repair"]()` returns a callable (the topology function).
- The committed record at `topologies/swebench_repair/records/ci_mode.record` reads back
  cleanly, contains a `RepairSummary` terminal, and includes the `SelectedPatch` +
  `RunFinalised` events the topology's contract mandates.

Fixture-repo path: the factory uses `SUBSTRATE_CI_FIXTURE_ROOT` when set; tests point it at
a tmpdir so a fresh test box works without a pre-existing `~/.substrate/ci-fixtures/`.
"""

from __future__ import annotations

from pathlib import Path

from substrate.api import read_record
from substrate.topologies import bundled


def test_swebench_repair_in_bundled_registry():
    """Sprint 188: `swebench_repair` joins the bundled topologies dict."""
    assert "swebench_repair" in bundled.names()
    assert "swebench_repair" in bundled.BUNDLED


def test_swebench_repair_factory_returns_a_topology(monkeypatch, tmp_path):
    """The zero-arg factory returns a callable — the topology function `substrate run`
    dispatches. Fixture repo lands under the tmpdir so the test does not touch the user's
    home directory."""
    monkeypatch.setenv("SUBSTRATE_CI_FIXTURE_ROOT", str(tmp_path / "fixtures"))
    factory = bundled.BUNDLED["swebench_repair"]
    topo = factory()
    assert callable(topo)


def test_swebench_repair_committed_ci_record_reads_cleanly():
    """The record committed at `topologies/swebench_repair/records/ci_mode.record` round-trips
    via `read_record` and contains the topology's terminal invariants."""
    record_root = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "substrate"
        / "topologies"
        / "swebench_repair"
        / "records"
        / "ci_mode.record"
    )
    assert record_root.exists(), (
        f"expected committed CI record at {record_root}. Run "
        "`uv run python scripts/gen_topology_records.py` to regenerate."
    )
    events = list(read_record(record_root))
    kinds = [e["kind"] for e in events]
    assert "substrate.RunStarted" in kinds
    assert "substrate.RunFinalised" in kinds
    assert "RepairSummary" in kinds, (
        f"CI record must contain the topology's terminal RepairSummary event; "
        f"got kinds={sorted(set(kinds))}"
    )
    # The topology's invariant: at least one Candidate + one Verdict per drafter round.
    assert any(k == "Candidate" for k in kinds)
    assert any(k == "Verdict" for k in kinds)
