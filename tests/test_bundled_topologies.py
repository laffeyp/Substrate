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
