"""Bundled topology registry — the newcomer's `substrate run --topology <name>` works (review
#16 HAT B). Each bundled name resolves, runs to a record, and exits 0 — no network, no config.
"""

import pytest
from click.testing import CliRunner

from substrate.cli import EXIT_OK, main
from substrate.topologies.bundled import names


@pytest.mark.timeout(30)
@pytest.mark.parametrize("name", names())
def test_run_bundled_topology_via_cli(tmp_path, name):
    res = CliRunner().invoke(main, ["run", "--topology", name, "--root", str(tmp_path / name)])
    assert res.exit_code == EXIT_OK, f"{name}: {res.output}\n{res.exception!r}"
    # the run printed its record root (the load-bearing stdout line) and the record finalised
    assert (tmp_path / name).exists()


def test_unknown_topology_still_errors_cleanly():
    res = CliRunner().invoke(main, ["run", "--topology", "nonesuch", "--root", "/tmp/x_nonesuch"])
    assert res.exit_code != EXIT_OK
    assert "unknown topology" in res.output and "nonesuch" in res.output


def test_topology_list_enumerates_the_registry():
    res = CliRunner().invoke(main, ["topology", "list"])
    assert res.exit_code == EXIT_OK, res.output
    listed = set(res.output.split())
    assert set(names()) <= listed  # every bundled topology is discoverable
    assert "code_review" in listed and "natural_conversation" in listed


def test_demo_replay_committed_record():
    res = CliRunner().invoke(main, ["demo", "replay", "code_review"])
    assert res.exit_code == EXIT_OK, res.output
    assert "RunStarted" in res.output and "RunFinalised" in res.output


def test_demo_replay_unknown_errors():
    res = CliRunner().invoke(main, ["demo", "replay", "nonesuch"])
    assert res.exit_code != EXIT_OK
    assert "no committed record" in res.output


def test_demo_run_live(tmp_path):
    res = CliRunner().invoke(main, ["demo", "run", "debate", "--root", str(tmp_path / "d")])
    assert res.exit_code == EXIT_OK, res.output


@pytest.mark.timeout(60)
@pytest.mark.parametrize("name", names())
async def test_committed_record_is_current(tmp_path, name):
    # CURRENCY GATE (review #51 finding 1): the committed CI record must REGENERATE byte-identically
    # from HEAD, not merely replay. A schema change (e.g. a Struct field's type) moves
    # RunStarted.topology and silently strands the record, while Level-2 replay — which checks the
    # record against ITSELF — still passes. So replay alone cannot catch staleness; a fresh run vs
    # the committed record can. (int->Any on ToolResult.output stranded tool_loop's record until regen.)
    from substrate.api import Runtime, first_divergence, read_record
    from substrate.topologies import bundled

    await Runtime(tmp_path / name).run(bundled.BUNDLED[name]())
    # GUARD (review #52): only an all-deterministic topology can regenerate byte-identically. Skip —
    # LOUDLY, with a named reason — a non-deterministic bundled topology, so the gate never mistakes
    # non-determinism for a stale record (a false-fail). Every BUNDLED entry is deterministic today;
    # this keeps that invariant explicit rather than implicit.
    rs = next(e for e in read_record(tmp_path / name) if e["kind"] == "substrate.RunStarted")
    nondet = [pk["kind"] for pk in rs["payload"]["topology"]["producer_kinds"] if not pk["deterministic"]]
    if nondet:
        pytest.skip(f"{name}: non-deterministic producers {nondet} — not byte-reproducible, currency gate N/A")
    div = first_divergence(bundled.record_path(name), tmp_path / name)
    assert div is None, (
        f"{name}: committed record is STALE — a fresh run diverges from it. "
        f"Regenerate via `uv run python scripts/gen_topology_records.py` ({div})"
    )
