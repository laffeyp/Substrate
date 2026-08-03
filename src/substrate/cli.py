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

# Narration only; data goes to stdout via click.echo (unwrapped). markup=False is load-bearing:
# the narration lines start with literal tags like [config]/[lock]/[deferred]/[FAIL], which rich
# would otherwise parse as console-markup style tags and SILENTLY EAT (e.g. "[config] ..." would
# print as " ..."). This channel never uses markup, so disable it.
_err = Console(stderr=True, markup=False)


# ── topology loading (a CLI concern; uses only public Runtime/TopologyBuilder) ──
def _load_topology(spec: str) -> Callable[[Any], None]:
    """Resolve a topology factory. `spec` is either a bundled-registry name or a
    `path/to/module.py:func` reference. The module path is executed with the user's
    privileges — no sandbox (technical §17); this is documented, not silent."""
    if ":" in spec and spec.split(":", 1)[0].endswith(".py"):
        return _load_attr(spec)
    # bundled registry name. Populate the bundled registry on demand via a DYNAMIC import, so the
    # CLI's STATIC import surface stays substrate.api-only (F-API-6; import-linter checks static
    # imports, not a runtime importlib call). If the bundled package is unavailable, fall through
    # to whatever is already registered.
    try:
        importlib.import_module("substrate.topologies.bundled").register_all()
    except Exception:  # noqa: BLE001 - bundled topologies are optional; never block a real run
        pass
    try:
        return api.get_topology(spec)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc


def _load_attr(spec: str) -> Callable[..., Any]:
    """Resolve a `path/to/module.py:attr` reference to the named attribute (a callable).
    The module path is executed with the user's privileges — no sandbox (technical §17);
    documented, not silent. Shared by topology loading and resume-event loading."""
    path_str, attr_name = spec.split(":", 1)
    path = Path(path_str)
    if not path.exists():
        raise click.ClickException(f"module not found: {path}")
    mod_spec = importlib.util.spec_from_file_location(f"_substrate_mod_{uuid.uuid4().hex}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise click.ClickException(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(mod_spec)
    try:
        mod_spec.loader.exec_module(module)
    except Exception as exc:
        # Importing/executing the user module failed (ImportError, SyntaxError, a raise at module
        # scope, ...). Surface it as a clean config error (-> EXIT_CONFIG) naming the cause, not a
        # raw traceback escaping the CLI.
        raise click.ClickException(f"failed to import {path}: {type(exc).__name__}: {exc}") from exc
    if not hasattr(module, attr_name):
        raise click.ClickException(f"module {path} has no attribute {attr_name!r}")
    return getattr(module, attr_name)  # type: ignore[no-any-return]


_FAILURE_KINDS = (
    "substrate.ProducerFailed",
    "substrate.InputBuildFailed",
    "substrate.PredicateQuarantined",
    "substrate.ProducerEmittedInvalidEvent",
)


def _failure_summary(root: Path) -> tuple[dict[str, int], int]:
    """Count the authoring-failure events on a record, so a run that finalised but silently did
    nothing is surfaced to the AUTHOR (not merely honest on the record). Returns (counts, total)."""
    counts: dict[str, int] = {}
    for env in api.read_record(root):
        kind = str(env.get("kind", ""))
        if kind in _FAILURE_KINDS:
            short = kind.removeprefix("substrate.")
            counts[short] = counts.get(short, 0) + 1
    return counts, sum(counts.values())


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
    return await _drive_maybe_tailing(rt.run(topology), record_root, tail_live, verbose)


async def _resume_maybe_tailing(
    rt: Any, topology: Any, resume_event: Any, record_root: Path, tail_live: bool, verbose: bool
) -> Any:
    return await _drive_maybe_tailing(
        rt.resume(topology, resume_event=resume_event), record_root, tail_live, verbose
    )


async def _drive_maybe_tailing(coro: Any, record_root: Path, tail_live: bool, verbose: bool) -> Any:
    """Drive a run/resume coroutine; when `tail_live`, concurrently stream its events to
    stderr over a read-only follower as it progresses (design §5.1 `--tail`/`--verbose`).
    The follower is the same F-PERS-4 read-only attach path — it observes the record, never
    the runtime's internals. The follower task is cancelled once the drive task completes
    (and one final drain catches the tail)."""
    if not tail_live:
        return await coro

    run_task = asyncio.ensure_future(coro)
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
def _resolve_version() -> str:
    # resolved locally (not imported from the package top level) to keep the F-API-6 boundary — cli
    # imports only substrate.api. click's default --version lookup infers the dist from the import name
    # ("substrate"), but the dist is "substrate-kernel", so the default raised a traceback (review C-4).
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _dist_version

    try:
        return _dist_version("substrate-kernel")
    except PackageNotFoundError:  # pragma: no cover — bare source tree, no installed metadata
        return "0.0.0"


@click.group()
@click.version_option(version=_resolve_version(), message="substrate %(version)s")
def main() -> None:
    """Substrate — a concurrent streaming dataflow runtime. Read the run record; never the
    runtime's mind. Every command cites sequence numbers."""


@main.command()
@click.option("--topology", "topology_name", help="bundled topology name")
@click.option(
    "--topology-module",
    "topology_module",
    help="path/to/module.py:func — EXECUTES that module as code with your privileges "
    "(no sandbox); only point it at code you trust",
)
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
@click.option(
    "--strict", is_flag=True, help="exit nonzero if any Producer/input/predicate failure occurred"
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
    strict: bool,
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
    # Surface authoring failures: a run can finalise while Producers/inputs/predicates FAILED (the
    # failures are honestly on the record, but a newcomer's eye is on this status line — make a
    # broken run LOOK broken). --strict turns any such failure into a nonzero exit.
    fail_counts, fail_total = _failure_summary(record_root)
    if fail_total:
        summary = ", ".join(f"{n} {k}" for k, n in sorted(fail_counts.items()))
        _err.print(f"[{result.status}] {result.record_root}  WARNING: {summary} (read the record)")
        if strict and code == EXIT_OK:
            code = EXIT_FAILED
    else:
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
        try:
            chain = list(api.trace_ancestry(root, producer))
        except (api.ProducerNotFound, api.SequenceOutOfRange) as exc:
            _err.print(f"[config] {exc}")  # a bad producer ref is a config error, not a traceback
            sys.exit(EXIT_CONFIG)
        for exp in chain:
            click.echo(
                f"{exp.kind}[{exp.instance}]  caused_by {exp.cause} at seq={exp.at_seq}"
                + (f" (trigger={exp.trigger_id})" if exp.trigger_id else "")
            )
        return
    if producer is not None and why:
        try:
            exp = api.explain_producer(root, producer)
        except (api.ProducerNotFound, api.SequenceOutOfRange) as exc:
            _err.print(f"[config] {exc}")  # clean error, consistent with run's [config] shape
            sys.exit(EXIT_CONFIG)
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
@click.option(
    "--lifecycle",
    is_flag=True,
    help="include the producer-lifecycle bracketing (Started/Completed/Injection) beats",
)
@click.option(
    "--summary",
    is_flag=True,
    help="emit a one-paragraph digest (counts + finalisation) instead of per-event prose",
)
def narrate(root: str, lifecycle: bool, summary: bool) -> None:
    """Narrate a record as a legible prose account — the plot of the run (Wave 14).

    A read-only projection over the log (no run, no network): the substrate.* causal beats
    in prose (a TriggerFired as "starts X", terminations, finalisation, and every authoring
    failure) interleaved with the application events (the work). Lifecycle bracketing is
    suppressed by default; --lifecycle restores the every-frame account. Every line cites a
    seq. --summary prints a digest instead."""
    if summary:
        s = api.narration_summary(api.read_record(root))
        fails = (
            s.producers_failed
            + s.input_build_failures
            + s.predicate_quarantines
            + s.invalid_emissions
        )
        # The HEADER must answer "did my run work?" at a glance (review #26): a finalised run
        # with failures is NOT a green run — say so on line 1, not line 3 ("finalised" alone
        # reads green and buries the alarm). This closes the #19 "finalised != worked" thread
        # in the layer best positioned to answer it.
        if not s.finalised:
            head = "Run NOT finalised (incomplete record)"
        elif fails:
            head = f"Run finalised WITH {fails} FAILURE{'S' if fails != 1 else ''}"
        elif s.final_reason:
            head = f"Run finalised ({s.final_reason})"
        else:
            head = "Run finalised"
        click.echo(f"{head}: {s.total_events} events.")
        click.echo(
            f"  producers: {s.producers_started} started, {s.producers_completed} completed, "
            f"{s.producers_cancelled} cancelled, {s.producers_failed} failed"
        )
        if fails:
            click.echo(
                f"  failures: {s.producers_failed} ProducerFailed, "
                f"{s.input_build_failures} InputBuildFailed, "
                f"{s.predicate_quarantines} PredicateQuarantined, "
                f"{s.invalid_emissions} ProducerEmittedInvalidEvent (read the record)"
            )
        if s.application_events:
            work = ", ".join(f"{k}={n}" for k, n in sorted(s.application_events.items()))
            click.echo(f"  work: {work}")
        return
    # Default mode: stream the plot, tallying authoring-failure beats so a long run's failures
    # (which can scroll past inline) get a footer pointing at the digest (review #26, optional).
    fail_lines = 0
    for line in api.narrate(api.read_record(root), lifecycle=lifecycle):
        click.echo(f"seq {line.seq:>5}  {line.text}")
        if line.kind in _FAILURE_KINDS:
            fail_lines += 1
    if fail_lines:
        _err.print(
            f"[warning] {fail_lines} authoring failure(s) above "
            f"-- run `substrate narrate {root} --summary` for the tally"
        )


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
    if level == "3a":
        # Level 3(a) gate-checks the re-execution PRECONDITIONS (replay ceiling 3a + every
        # Producer kind author-deterministic) and re-verifies the Level-2 input hashes; it does
        # NOT itself re-execute the Producers (re-execution is the Runtime's job, against the
        # same record). Say so plainly rather than implying a re-run happened.
        click.echo("[OK] Level 3(a) preconditions verified (re-execution NOT performed).")
    else:
        click.echo(f"[OK] Level {level} replay successful.")
    click.echo(f"Frames replayed: {result.frame_count}")
    if level in ("2", "3a"):
        click.echo(f"Decisions verified: {result.decisions_verified} (all inputs verified by hash)")


@main.command()
@click.option("--topology-module", "topology_module", required=True, help="path/to/module.py:func")
def validate(topology_module: str) -> None:
    """Static topology lint (F-CLI-3): registration, plus undeclared event-kind references, a
    missing TerminationPolicy, wall-clock cooldown flags, and a counts summary. Runs nothing.
    Exit 0 (clean) / 64 (registration error or a lint failure)."""
    try:
        topology = _load_topology(topology_module)
        builder = api.TopologyBuilder()
        topology(builder)
        reg = builder.build()
    except click.ClickException as exc:
        _err.print(f"[FAIL] {exc.message}")
        sys.exit(EXIT_CONFIG)
    except Exception as exc:
        _err.print(f"[FAIL] {type(exc).__name__}: {exc}")
        sys.exit(EXIT_CONFIG)

    # the set of every event kind some Producer can emit; a Predicate/Route subscribing to a kind
    # outside this set (and outside the reserved substrate.* lifecycle namespace) is a dead reference.
    declared = {kind for pk in reg.producer_kinds.values() for kind in pk.schemas}
    failures: list[str] = []
    for t in reg.triggers:
        for kind in sorted(t.subscription.kinds):
            if not kind.startswith("substrate.") and kind not in declared:
                failures.append(
                    f"trigger {t.id!r} subscribes to kind {kind!r}, which no Producer declares"
                )
    for r in reg.routes:
        for kind in sorted(r.subscription.kinds):
            if not kind.startswith("substrate.") and kind not in declared:
                failures.append(
                    f"route {r.id!r} subscribes to kind {kind!r}, which no Producer declares"
                )

    click.echo(
        f"{len(reg.producer_kinds)} Producer kinds, {len(reg.triggers)} Triggers, "
        f"{len(reg.routes)} Routes, {len(reg.views)} Views, "
        f"{1 if reg.termination is not None else 0} TerminationPolicy."
    )
    if reg.has_wall_clock_cooldown:
        click.echo('1+ WallClock cooldown registered -> replay ceiling = "3b".')
    if reg.termination is None:
        click.echo(
            "note: no TerminationPolicy registered -> the run defaults to quiescence-with-watchdog."
        )

    if failures:
        _err.print(f"[FAIL] {len(failures)} issue(s):")
        for f in failures:
            _err.print(f"  - {f}")
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
        # show the detail for any non-PASS, AND always for the perf check (operators want the
        # measured appends/sec number even when it PASSES the floor).
        if r.status.value != "PASS" or r.number == 15:
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
@click.option("--topology", "topology_name", help="bundled topology name")
@click.option(
    "--topology-module",
    "topology_module",
    help="path/to/module.py:func — EXECUTES that module as code with your privileges "
    "(no sandbox); only point it at code you trust",
)
@click.option(
    "--input",
    "input_spec",
    required=True,
    help="resume event factory: path/to/module.py:func (zero-arg callable -> the external "
    "resume event Struct a resume Trigger subscribes to)",
)
@click.option(
    "--tail", "tail_live", is_flag=True, help="stream events to stderr while the run progresses"
)
@click.option(
    "--verbose", is_flag=True, help="with --tail, also stream substrate.* lifecycle events"
)
def resume(
    root: str,
    topology_name: str | None,
    topology_module: str | None,
    input_spec: str,
    tail_live: bool,
    verbose: bool,
) -> None:
    """Resume a paused persistent-bus run (F-TERM-3 / F-CLI; design §6).

    Reattaches to the EXISTING record at <root> (re-acquires the exclusive lock, restores
    next_seq from the log tail, refolds the registered Views over the record), appends the
    external resume event so the resume Trigger fires the continuation Producer, and drives
    to the next terminal — appending on the SAME seq sequence as the paused run.

    The topology is re-resolved fresh (same factory the paused run used). Exit: 0 finalised,
    1 failed, 2 paused (paused again), 64 config, 65 lock contention, 130 SIGINT."""
    record_root = Path(root)
    spec = topology_module or topology_name
    if not spec:
        _err.print("[config] one of --topology or --topology-module is required")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)
    try:
        topology = _load_topology(spec)
        event_factory = _load_attr(input_spec) if ":" in input_spec else None
        if event_factory is None:
            raise click.ClickException(
                f"--input must be a path/to/module.py:func reference, got {input_spec!r}"
            )
        resume_event = event_factory()
    except click.ClickException as exc:
        _err.print(f"[config] {exc.message}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)

    # resume is a persistent-bus operation by construction (it reattaches to an existing,
    # lock-guarded record) — the runtime enforces persistent=True for resume().
    rt = api.Runtime(record_root, persistent=True)
    try:
        result = asyncio.run(
            _resume_maybe_tailing(rt, topology, resume_event, record_root, tail_live, verbose)
        )
    except KeyboardInterrupt:
        click.echo(str(record_root))
        sys.exit(EXIT_SIGINT)
    except api.BusLockedError as exc:
        _err.print(f"[lock] {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_LOCKED)
    except (api.RegistrationError, api.UnsupportedPlatformError) as exc:
        _err.print(f"[config] {type(exc).__name__}: {exc}")
        click.echo(str(record_root))
        sys.exit(EXIT_CONFIG)
    click.echo(result.record_root)
    code = {"finalised": EXIT_OK, "failed": EXIT_FAILED, "paused": EXIT_PAUSED}[result.status]
    _err.print(f"[{result.status}] {result.record_root}")
    sys.exit(code)


@main.group()
def topology() -> None:
    """The bundled topology registry (runnable via `substrate run --topology <name>`)."""


@topology.command("list")
def topology_list() -> None:
    """List bundled topology names, one per line. Discoverability for the --topology flag."""
    names: list[str]
    try:
        # dynamic import keeps the CLI's static surface substrate.api-only (F-API-6).
        names = importlib.import_module("substrate.topologies.bundled").names()
    except Exception:  # noqa: BLE001 - bundled topologies are optional
        names = []
    for name in names:
        click.echo(name)


@main.group()
def demo() -> None:
    """Run or replay a bundled demonstration topology (the one-command on-ramp)."""


@demo.command("replay")
@click.argument("name")
@click.pass_context
def demo_replay(ctx: click.Context, name: str) -> None:
    """Replay a bundled topology's committed CI record — tail it (no run, no network)."""
    record = importlib.import_module("substrate.topologies.bundled").record_path(name)
    if not record.exists():
        _err.print(
            f"[config] no committed record for {name!r}. Try `substrate topology list`, "
            f"or `substrate demo run {name}` to run it live."
        )
        sys.exit(EXIT_CONFIG)
    ctx.invoke(
        tail, root=str(record), kinds=None, producer=None, since=None, fmt="aligned", follow=False
    )


@demo.command("run")
@click.argument("name")
@click.option("--root", "root", default=None, help="record root (default: ./runs/<run-id>)")
@click.pass_context
def demo_run(ctx: click.Context, name: str, root: str | None) -> None:
    """Run a bundled topology live (CI-default, deterministic) and stream it to stderr."""
    ctx.invoke(
        run,
        topology_name=name,
        topology_module=None,
        root=root,
        persistent=False,
        writer_stats=False,
        diagnostics=False,
        tail_live=True,
        verbose=False,
        strict=False,
    )


@main.command()
@click.argument("root", type=click.Path(exists=True))
@click.option("--rule", "rule_name", default="brier", help="brier | log_loss | spherical")
def score(root: str, rule_name: str) -> None:
    """Score a record's Grade events under a proper rule — the calibration PAYOFF (lower is
    better). Turns 'calibration pays, confident-sounding doesn't' from raw Grade rows into a
    per-speaker result. Closes the cheap-talk loop the grader instrument opens."""
    grades = [e["payload"] for e in api.read_record(Path(root)) if e.get("kind") == "Grade"]
    if not grades:
        _err.print("[config] no Grade events here; run a topology with scoring on first")
        sys.exit(EXIT_CONFIG)
    # dynamic import keeps the CLI's static surface substrate.api-only (F-API-6).
    scoring = importlib.import_module("substrate.topologies.instruments.scoring")
    grader = importlib.import_module("substrate.topologies.instruments.grader")
    try:
        rule = scoring.select_scoring_rule(rule_name)
    except Exception as exc:  # noqa: BLE001 - unknown rule -> clean config error
        _err.print(f"[config] {exc}")
        sys.exit(EXIT_CONFIG)
    try:
        # record payload fields are attacker-controllable; a malformed Grade (non-numeric /
        # out-of-range confidence) is a clean config error, not an uncaught traceback (review #20).
        losses = grader.score_grades(grades, rule)
    except Exception as exc:  # noqa: BLE001 - any malformed Grade payload -> clean [config]
        _err.print(f"[config] malformed Grade payload in record: {exc}")
        sys.exit(EXIT_CONFIG)
    by_speaker: dict[str, list[float]] = {}
    for claim, loss in losses.items():
        by_speaker.setdefault(str(claim).split("-", 1)[0], []).append(float(loss))
    click.echo(f"calibration loss ({rule_name}, lower is better):")
    for spk in sorted(by_speaker):
        vals = by_speaker[spk]
        click.echo(f"  {spk}: mean={sum(vals) / len(vals):.4f}  n={len(vals)}")


if __name__ == "__main__":
    main()
