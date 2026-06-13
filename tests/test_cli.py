"""CLI tests (design §5; F-CLI-1..6, F-API-6).

Two jobs: (1) ENFORCE F-API-6 — `substrate.cli` may import only `substrate.api` among
substrate modules (the CLI is the standing existence proof that the public API suffices;
this is the import-lint rule PHASE1_PLAN S-0.INT calls for, run here under pytest with no
extra dependency). (2) Smoke-test the commands end-to-end over a real run record via Click's
CliRunner, asserting the documented output shapes + exit codes (§5.1)."""

import ast
from pathlib import Path

from click.testing import CliRunner
from msgspec import Struct

from substrate.api import Runtime, register_topology, threshold_count
from substrate.cli import (
    EXIT_CONFIG,
    EXIT_OK,
    main,
)


# ── F-API-6: the CLI imports only substrate.api among substrate modules ────────
def test_cli_imports_only_substrate_api():
    cli_path = Path(__file__).parent.parent / "src" / "substrate" / "cli.py"
    tree = ast.parse(cli_path.read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "substrate":
                # `from substrate import api` — the one allowed substrate import
                names = {a.name for a in node.names}
                if names - {"api"}:
                    offenders.append(f"from substrate import {sorted(names)}")
            elif mod.startswith("substrate.") and mod != "substrate.api":
                offenders.append(f"from {mod} import ...")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("substrate.") and a.name != "substrate.api":
                    offenders.append(f"import {a.name}")
    assert not offenders, f"cli.py imports non-api substrate modules (F-API-6): {offenders}"


# ── end-to-end smoke over a real record ────────────────────────────────────────
class CountReached(Struct, frozen=True):
    n: int


async def counter(_input):
    for n in range(1, 4):
        yield CountReached(n=n)


def _topo(b):
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


def _run_record(tmp_path):
    import asyncio

    root = tmp_path / "run"
    asyncio.run(Runtime(root).run(_topo))
    return root


def test_run_via_registry_prints_root_and_exits_zero(tmp_path):
    register_topology("cli_count", _topo)
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(main, ["run", "--topology", "cli_count", "--root", str(root)])
    assert res.exit_code == EXIT_OK
    assert str(root) in res.stdout  # the record root is the load-bearing stdout line


def test_run_missing_topology_is_config_error(tmp_path):
    runner = CliRunner()
    res = runner.invoke(main, ["run", "--root", str(tmp_path / "x")])
    assert res.exit_code == EXIT_CONFIG


def test_run_prints_root_on_config_error_when_root_known(tmp_path):
    # design §5.1: the record root is printed on every exit that contemplates a run — incl.
    # a topology-load failure (a known root, no record created).
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(
        main, ["run", "--topology-module", str(tmp_path / "nope.py") + ":x", "--root", str(root)]
    )
    assert res.exit_code == EXIT_CONFIG
    assert str(root) in res.stdout


def test_run_tail_streams_events(tmp_path):
    register_topology("cli_count_tail", _topo)
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(
        main, ["run", "--topology", "cli_count_tail", "--root", str(root), "--tail"]
    )
    assert res.exit_code == EXIT_OK
    assert str(root) in res.stdout  # data on stdout
    # --tail streams application events to stderr (default: no substrate.* without --verbose)
    assert "CountReached" in res.stderr


def test_run_tail_verbose_includes_lifecycle(tmp_path):
    register_topology("cli_count_tailv", _topo)
    runner = CliRunner()
    root = tmp_path / "out"
    res = runner.invoke(
        main,
        ["run", "--topology", "cli_count_tailv", "--root", str(root), "--tail", "--verbose"],
    )
    assert res.exit_code == EXIT_OK
    assert "substrate.RunFinalised" in res.stderr  # lifecycle streamed with --verbose


def test_tail_aligned_and_jsonl(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    aligned = runner.invoke(main, ["tail", str(root)])
    assert aligned.exit_code == 0
    assert "seq=0" in aligned.stdout and "substrate.RunStarted" in aligned.stdout
    assert "CountReached" in aligned.stdout
    jsonl = runner.invoke(main, ["tail", str(root), "--format", "jsonl"])
    assert '"kind":"substrate.RunStarted"' in jsonl.stdout.replace(" ", "")


def test_tail_filters_compose(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["tail", str(root), "--kind", "CountReached"])
    assert res.exit_code == 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    assert lines and all("CountReached" in ln for ln in lines)


def test_inspect_why_cites_seq(tmp_path):
    root = _run_record(tmp_path)
    # find the counter instance
    from substrate.api import read_record

    started = next(e for e in read_record(root) if e["kind"] == "substrate.ProducerStarted")
    inst = started["payload"]["producer"]["instance"]
    runner = CliRunner()
    res = runner.invoke(main, ["inspect", str(root), "--producer", f"counter[{inst}]", "--why"])
    assert res.exit_code == 0
    assert "caused_by:" in res.stdout
    assert "RunStarted" in res.stdout  # initial producer attributes to the run open


def test_replay_level2_ok(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["replay", str(root), "--level", "2"])
    assert res.exit_code == 0
    assert "[OK] Level 2 replay successful." in res.stdout


def test_replay_level3b_is_deferred_not_silent(tmp_path):
    root = _run_record(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["replay", str(root), "--level", "3b"])
    # deferred surfaces as a non-zero exit with a [deferred] message, never a false green
    assert res.exit_code != 0
    assert "deferred" in (res.stdout + res.stderr).lower()


def test_validate_module(tmp_path):
    # write a tiny topology module and validate it via the path:func form
    mod = tmp_path / "topo.py"
    mod.write_text(
        "from msgspec import Struct\n"
        "from substrate.api import threshold_count\n"
        "class E(Struct, frozen=True):\n    n: int\n"
        "async def p(_):\n    yield E(n=1)\n"
        "def topo(b):\n"
        "    b.producer_kind('p', schemas=[E], schema_version=1, factory=lambda: p)\n"
        "    b.initial('p', input=None)\n"
        "    b.termination(threshold_count('substrate.ProducerCompleted', 1))\n"
    )
    runner = CliRunner()
    res = runner.invoke(main, ["validate", "--topology-module", f"{mod}:topo"])
    assert res.exit_code == 0
    assert "[OK] Topology validates." in res.stdout


def test_conformance_reports_not_wired_not_false_green(tmp_path):
    # the harness is Wave 9; the command must NOT print a false green
    runner = CliRunner()
    res = runner.invoke(main, ["conformance"])
    assert res.exit_code == EXIT_CONFIG  # honest "not yet wired", not exit 0


def test_stats_reads_writer_stats_sidecar(tmp_path):
    import asyncio

    root = tmp_path / "run"
    asyncio.run(Runtime(root, writer_stats=True).run(_topo))
    runner = CliRunner()
    res = runner.invoke(main, ["stats", str(root), "--sidecar", "writer_stats"])
    assert res.exit_code == 0
    assert "writer_stats:" in res.stdout
