"""The `substrate` CLI (design §5; F-CLI-1..6, F-API-6).

The CLI is the standing existence proof that the public API is sufficient to build a
reader/runner on public surfaces alone (principle 8). It therefore imports ONLY
`substrate.api` (F-API-6) — never a private module. (Enforced by import-linter in CI; the
single allowed non-api imports are stdlib + click + rich, none of which are substrate
internals.) Output is structured: typed fields, sequence numbers everywhere identification
happens, the eight-word vocabulary, no anthropomorphic synonyms, no emoji. stdout carries
data (the record root, JSONL); stderr carries narration. Exit codes are a contract (§5.1).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

import click
from rich.console import Console

from substrate import api

# ── exit codes (design §5.1) ───────────────────────────────────────────────────
EXIT_OK = 0  # run finalised normally
EXIT_FAILED = 1  # run failed (view raised, writer crashed)
EXIT_PAUSED = 2  # run paused awaiting input (pause-await-input)
EXIT_CONFIG = 64  # configuration error (CLI args, topology import, registration)
EXIT_LOCKED = 65  # persistent-bus lock contention
EXIT_SIGINT = 130  # user interrupted

_err = Console(stderr=True)  # narration only; data goes to stdout via click.echo (unwrapped)


# ── topology loading (a CLI concern; uses only public Runtime/TopologyBuilder) ──
def _load_topology(spec: str) -> Callable[[Any], None]:
    """Resolve a topology factory. `spec` is either a bundled-registry name or a
    `path/to/module.py:func` reference. The module path is executed with the user's
    privileges — no sandbox (technical §17); this is documented, not silent."""
    if ":" in spec and spec.split(":", 1)[0].endswith(".py"):
        path_str, func_name = spec.split(":", 1)
        path = Path(path_str)
        if not path.exists():
            raise click.ClickException(f"topology module not found: {path}")
        mod_spec = importlib.util.spec_from_file_location(
            f"_substrate_topo_{uuid.uuid4().hex}", path
        )
        if mod_spec is None or mod_spec.loader is None:
            raise click.ClickException(f"cannot load module: {path}")
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)
        if not hasattr(module, func_name):
            raise click.ClickException(f"module {path} has no attribute {func_name!r}")
        return getattr(module, func_name)  # type: ignore[no-any-return]
    # bundled registry name
    try:
        return api.get_topology(spec)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc


def _producer_label(ref: dict[str, Any] | None) -> str:
    if not isinstance(ref, dict):
        return ""
    kind = ref.get("kind", "?")
    inst = ref.get("instance")
    return f"{kind}[{inst}]" if inst else str(kind)


def _format_event_line(env: dict[str, Any]) -> str:
    """One aligned human-readable line for `tail` (design §5.2 default format)."""
    seq = env.get("seq")
    kind = str(env.get("kind", ""))
    payload = env.get("payload") or {}
    ref = env.get("producer")
    bits: list[str] = []
    if ref:
        bits.append(f"producer={_producer_label(ref)}")
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in ("topology", "schemas", "baseline"):  # large; elide in the aligned view
                continue
            bits.append(f"{k}={v}")
    return f"seq={seq:<5} {kind:<34} {'  '.join(bits)}"


async def _run_maybe_tailing(
    rt: Any, topology: Any, record_root: Path, tail_live: bool, verbose: bool
) -> Any:
    """Run the topology; when `tail_live`, concurrently stream its events to stderr over a
    read-only follower as the run progresses (design §5.1 `--tail`/`--verbose`). The
    follower is the same F-PERS-4 read-only attach path — it observes the record, never the
    runtime's internals. The follower task is cancelled once the run task completes (and one
    final drain catches the tail)."""
    if not tail_live:
        return await rt.run(topology)

    run_task = asyncio.ensure_future(rt.run(topology))
    live = api.attach(record_root, poll_ms=20)  # one follower, cursor shared across drains

    def _drain() -> None:
        for env in live.read_new():
            if not verbose and str(env.get("kind", "")).startswith("substrate."):
                continue
            _err.print(_format_event_line(env))

    async def _stream() -> None:
        while True:
            _drain()
            await asyncio.sleep(0.02)

    stream_task = asyncio.ensure_future(_stream())
    try:
        result = await run_task
    finally:
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass
        _drain()  # final drain: emit anything written between the last poll and run end
    return result


# ── the command group ──────────────────────────────────────────────────────────
@click.group()
@click.version_option(message="substrate %(version)s")
def main() -> None:
    """Substrate — a concurrent streaming dataflow runtime. Read the run record; never the
    runtime's mind. Every command cites sequence numbers."""


@main.command()
@click.option("--topology", "topology_name", help="bundled topology name")
@click.option("--topology-module", "topology_module", help="path/to/module.py:func")
@click.option("--root", "root", default=None, help="record root (default: ./runs/<run-id>)")
@click.option("--persistent", is_flag=True, help="persistent-bus mode (exclusive lock)")
@click.option("--writer-stats", is_flag=True, help="emit the off-bus writer_stats sidecar")
@click.option("--diagnostics", is_flag=True, help="emit the off-bus diagnostics sidecar")
@click.option(
    "--tail", "tail_live", is_flag=True, help="stream events to stderr while the run progresses"
)
@click.option(
    "--verbose", is_flag=True, help="with --tail, also stream substrate.* lifecycle events"
)
def run(
    topology_name: str | None,
    topology_module: str | None,
    root: str | None,
    persistent: bool,
    writer_stats: bool,
    diagnostics: bool,
    tail_live: bool,
    verbose: bool,
) -> None:
    """Run a topology to a run record (F-CLI-1). Prints the record root to stdout on every
    exit. Exit: 0 finalised, 1 failed, 2 paused, 64 config, 65 lock contention, 130 SIGINT.

    --tail streams events to stderr as the run progresses (default: application events
    only; add --verbose for substrate.* lifecycle events too) over the read-only attach
    follower (F-PERS-4) — the run record is the source of truth, never the runtime's
    internals."""
    spec = topology_module or topology_name
    if not spec:
        # an arg error before any run is contemplated — no record root exists to print.
        _err.print("[config] one of --topology or --topology-module is required")
        sys.exit(EXIT_CONFIG)
    # Compute the record root up front so it can be printed on EVERY exit that contemplates
    # a run (design §5.1: "the record root path is printed to stdout on every exit"), incl.
    # the topology-load / registration / lock failure paths below.
    record_root = Path(root) if root else Path("runs") / str(uuid.uuid4())
    try:
        topology = _load_topology(spec)
    except click.ClickException as exc:
        _err.print(f"[config] {exc.message}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)

    rt = api.Runtime(
        record_root, persistent=persistent, writer_stats=writer_stats, diagnostics=diagnostics
    )
    try:
        result = asyncio.run(_run_maybe_tailing(rt, topology, record_root, tail_live, verbose))
    except KeyboardInterrupt:
        click.echo(str(record_root))
        sys.exit(EXIT_SIGINT)
    except api.BusLockedError as exc:  # by TYPE via the public api surface, not string-match
        _err.print(f"[lock] {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_LOCKED)
    except (api.RegistrationError, api.UnsupportedPlatformError) as exc:
        _err.print(f"[config] {type(exc).__name__}: {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)
    # the record root is the load-bearing stdout line (shell-pipeable)
    click.echo(result.record_root)
    code = {"finalised": EXIT_OK, "failed": EXIT_FAILED, "paused": EXIT_PAUSED}[result.status]
    _err.print(f"[{result.status}] {result.record_root}")
    sys.exit(code)


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--kind", "kinds", default=None, help="comma-separated kinds (AND with others)")
@click.option("--producer", "producer", default=None, help="producer kind prefix or full ref")
@click.option("--since", "since", type=int, default=None, help="only seq >= this")
@click.option("--format", "fmt", type=click.Choice(["aligned", "jsonl"]), default="aligned")
@click.option("--follow/--no-follow", default=False, help="stay attached past current end")
def tail(
    root: str,
    kinds: str | None,
    producer: str | None,
    since: int | None,
    fmt: str,
    follow: bool,
) -> None:
    """Stream events from a live or closed record (F-CLI-5). Filters compose with AND."""
    import json as _json

    kind_set = set(kinds.split(",")) if kinds else None

    def _passes(env: dict[str, Any]) -> bool:
        if kind_set is not None and str(env.get("kind")) not in kind_set:
            return False
        if since is not None and int(env.get("seq", -1)) < since:
            return False
        if producer is not None:
            ref = env.get("producer")
            if not isinstance(ref, dict):
                return False
            label = _producer_label(ref)  # "kind[instance]"
            kind = str(ref.get("kind", ""))
            # design §5.2 / F-CLI-5: `--producer` accepts a KIND PREFIX (matches all
            # instances) OR a full producer ref. A full ref matches exactly; otherwise the
            # arg is a prefix of the kind.
            if not (label == producer or kind == producer or kind.startswith(producer)):
                return False
        return True

    def _emit(env: dict[str, Any]) -> None:
        if not _passes(env):
            return
        if fmt == "jsonl":
            click.echo(_json.dumps(env, sort_keys=True, separators=(",", ":")))
        else:
            click.echo(_format_event_line(env))

    if follow:
        live = api.attach(root)
        try:
            for env in live.follow(until_finalised=True):
                _emit(env)
        except KeyboardInterrupt:
            sys.exit(EXIT_SIGINT)
    else:
        for env in api.read_record(root):
            _emit(env)


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--producer", "producer", default=None, help="a producer ref kind[instance]")
@click.option("--why", is_flag=True, help="proximate cause (one firing / RunStarted)")
@click.option("--ancestry", is_flag=True, help="full causal chain to RunStarted")
@click.option("--seq", "seq", type=int, default=None, help="the event at seq N")
@click.option("--between", "between", nargs=2, type=int, default=None, help="substrate.* in [A,B]")
@click.option("--diff", "diff_root", type=click.Path(exists=True), default=None)
def inspect(
    root: str,
    producer: str | None,
    why: bool,
    ancestry: bool,
    seq: int | None,
    between: tuple[int, int] | None,
    diff_root: str | None,
) -> None:
    """Deterministic queries over a record (design §5.3). Every output cites seq numbers."""
    if diff_root is not None:
        div = api.first_divergence(root, diff_root)
        if div is None:
            click.echo("equivalent under D-8 (no divergence)")
        else:
            click.echo(f"first divergence at index {div.index} (seq={div.seq}):")
            click.echo(f"  a: kind={div.kind_a} hash={div.hash_a}")
            click.echo(f"  b: kind={div.kind_b} hash={div.hash_b}")
        return
    if producer is not None and ancestry:
        for exp in api.trace_ancestry(root, producer):
            click.echo(
                f"{exp.kind}[{exp.instance}]  caused_by {exp.cause} at seq={exp.at_seq}"
                + (f" (trigger={exp.trigger_id})" if exp.trigger_id else "")
            )
        return
    if producer is not None and why:
        exp = api.explain_producer(root, producer)
        click.echo(f"producer={exp.kind}[{exp.instance}]")
        click.echo(f"parent={exp.parent}")
        click.echo("caused_by:")
        click.echo(f"  seq={exp.at_seq}  {exp.cause}")
        click.echo(f"    trigger={exp.trigger_id}")
        click.echo(f"    firing_key={exp.firing_key}")
        click.echo(f"    input_sha256={exp.input_sha256}")
        return
    if between is not None:
        for ev in api.decisions_between(root, between[0], between[1]):
            click.echo(f"seq={ev.seq:<5} {ev.kind}")
        return
    if seq is not None:
        for env in api.read_record(root):
            if int(env.get("seq", -1)) == seq:
                click.echo(_format_event_line(env))
                return
        raise click.ClickException(f"no event at seq {seq}")
    raise click.ClickException("inspect needs one of --why/--ancestry/--seq/--between/--diff")


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--level", type=click.Choice(["1", "2", "3a", "3b"]), default="1")
@click.option("--diff", "diff_root", type=click.Path(exists=True), default=None)
def replay(root: str, level: str, diff_root: str | None) -> None:
    """Replay a record at an honesty tier (F-CLI-2). Exit 0 on success, non-zero on failure
    or on a refused/deferred tier."""
    if diff_root is not None:
        div = api.first_divergence(root, diff_root)
        if div is None:
            click.echo("equivalent under D-8 (no divergence)")
        else:
            click.echo(f"first divergence at index {div.index} (seq={div.seq})")
        return
    try:
        result = api.replay(root, level=level)  # type: ignore[arg-type]
    except NotImplementedError as exc:
        # Level 3(b) is a documented deferral (spec amendment A1.1), surfaced as a distinct
        # message, NOT a silent pass and NOT an opaque crash.
        _err.print(f"[deferred] {exc}")
        sys.exit(EXIT_FAILED)
    if result.mismatches:
        _err.print(f"[FAIL] level {level}: {len(result.mismatches)} input-hash mismatch(es)")
        for m in result.mismatches:
            _err.print(f"  seq={m.seq} trigger={m.trigger_id} recorded={m.recorded}")
        sys.exit(EXIT_FAILED)
    if level == "3a" and result.preconditions_ok is False:
        _err.print(f"[FAIL] Level 3(a) refused: {result.refusal_reason}")
        sys.exit(EXIT_FAILED)
    click.echo(f"[OK] Level {level} replay successful.")
    click.echo(f"Frames replayed: {result.frame_count}")
    if level in ("2", "3a"):
        click.echo(f"Decisions verified: {result.decisions_verified} (all inputs verified by hash)")


@main.command()
@click.option("--topology-module", "topology_module", required=True, help="path/to/module.py:func")
def validate(topology_module: str) -> None:
    """Static topology lint (F-CLI-3). Exercises registration; runs nothing. Exit 0/64."""
    try:
        topology = _load_topology(topology_module)
        builder = api.TopologyBuilder()
        topology(builder)
        builder.build()
    except click.ClickException as exc:
        _err.print(f"[FAIL] {exc.message}")
        sys.exit(EXIT_CONFIG)
    except Exception as exc:
        _err.print(f"[FAIL] {type(exc).__name__}: {exc}")
        sys.exit(EXIT_CONFIG)
    click.echo("[OK] Topology validates.")


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option(
    "--sidecar", type=click.Choice(["writer_stats", "diagnostics"]), default="writer_stats"
)
def stats(root: str, sidecar: str) -> None:
    """Read an off-bus sidecar (writer_stats / diagnostics) from a record (§6.4 / §3.8)."""
    path = Path(root) / "sidecar" / f"{sidecar}.jsonl"
    records = api.read_sidecar(path)
    if not records:
        _err.print(f"[empty] no {sidecar} sidecar at {path}")
        return
    click.echo(f"{sidecar}: {len(records)} record(s)")
    for r in records[-10:]:
        click.echo("  " + "  ".join(f"{k}={v}" for k, v in sorted(r.items())))


@main.command()
@click.option("--no-perf", is_flag=True, help="skip the perf-floor probe (check 15)")
def conformance(no_perf: bool) -> None:
    """Run the 17-check conformance suite — the v1.0 release gate (F-CLI-4, product §7).

    Each check prints PASS / FAIL / DEFERRED / SKIPPED, four DISTINCT states. DEFERRED
    (check 6, Level-3b byte-identity — spec amendment A1.1) is a ruled "not shippable in
    v1.0"; SKIPPED is a run-time skip (e.g. check 15 under --no-perf) and is NOT spec-amended.
    Neither prints green; neither is a pass. Exit: 0 iff no check FAILED, 1 if any FAILED.
    Run WITHOUT --no-perf in CI so the N-PERF-1 floor miss cannot be masked."""
    report = asyncio.run(api.run_conformance(include_perf=not no_perf))
    n = len(report.results)
    _err.print(f"Running {n} conformance checks (product §7)...")
    tags = {
        "PASS": "PASS",
        "FAIL": "FAIL",
        "DEFERRED": "DEFERRED (spec-amended A1.1)",
        "SKIPPED": "SKIPPED (--no-perf; not spec-amended)",
    }
    for r in report.results:
        click.echo(f"  [{r.number:02d}/17] {r.name:<32} ... {tags[r.status.value]}")
        if r.status.value != "PASS":
            _err.print(f"         {r.detail}")
    summary = (
        f"{report.passed} passed, {report.failed} failed, "
        f"{report.deferred} deferred, {report.skipped} skipped"
    )
    if report.all_non_failing:
        click.echo(f"\n{summary}. No check FAILED.")
        if report.deferred:
            _err.print(
                f"NOTE: {report.deferred} check(s) DEFERRED (spec-amended, A1.1) — distinct "
                f"from pass; v1.0 ships with these deferred. NOT a green pass."
            )
        if report.skipped:
            _err.print(
                f"NOTE: {report.skipped} check(s) SKIPPED on this invocation (e.g. --no-perf) "
                f"— run the default `substrate conformance` (no flags) to exercise them."
            )
        sys.exit(EXIT_OK)
    click.echo(f"\n{summary}. {report.failed} FAILED — release gate not met.")
    sys.exit(EXIT_FAILED)


@main.command()
@click.argument("root", type=click.Path(exists=True))
def resume(root: str) -> None:
    """Resume a paused persistent-bus run (F-CLI; design §6). Wired with the pause/resume
    persistence path in a later wave; reports the not-yet-wired status honestly."""
    _err.print("[config] resume is wired with the persistent-bus pause/resume path (later wave).")
    sys.exit(EXIT_CONFIG)


if __name__ == "__main__":
    main()
