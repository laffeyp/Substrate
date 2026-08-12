"""The SWE-bench Adapter + Suite — wire substrate topologies as Arms over real SWE-bench instances.

The assay harness (suite.py / run.py / report.py / oracle.py) is generic and already proven by the
firewalled coding benchmark (coding.py). This is the SWE-bench analog: a `Case` per instance, an Arm
matrix of topologies, and the record-grading `swebench_record_oracle`. The Adapter does the per-case
setup the session's `scripts/solve_instance.py` did by hand — clone the repo at base_commit, discover the
canonical test modules, build the firewall-clean regression command, and run the base suite ONCE for the
passed-at-base set — and packs PRIMITIVES into `Case.payload` so each Arm's `build(case)` reconstructs the
runner + regression planner without redoing the I/O. Every Arm on a Case consumes the IDENTICAL payload
(the Wave-0-carry discipline); the firewall lives here (the held-out test_patch/FAIL_TO_PASS never enter
the payload — `exclude` carries only test_patch FILE PATHS, used to drop issue-related tests, disclosed).

THE ARM CONTRACT: a topology is a valid SWE-bench Arm iff `build(case)` returns a topology that emits a
`SelectedPatch` carrying its model_patch (what `model_patch_from_record` reads). The pipeline arm built
here (`swebench_solver_arm`) does; other topologies (a tool agent, an ensemble) provide their own arm
builder over the same payload.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NotRequired, TypedDict, cast

from ..topologies.swebench_solver.assemble import swebench_solver_topology_with_test_selection
from ..topologies.swebench_solver.select_docker import (
    DockerTestRunner,
    build_regression_command,
    instance_image,
    repo_test_spec,
)
from ..topologies.swebench_solver.select_exec import passed_tests
from ..topologies.swebench_solver.select_regression import (
    discover_test_modules,
    make_regression_planner,
)
from .suite import ABLATION, BASELINE, FULL, Arm, Case, Suite, Topology
from .swebench import swebench_record_oracle


class PreparedPayload(TypedDict):
    """Sprint 143 — typed shape of a SWE-bench `Case.payload` produced by `prepare_swebench_case`.

    The generic assay `Case.payload` is `dict[str, Any]` by the harness contract; this TypedDict
    types the SWE-bench-specific fields so a caller hand-rolling a payload for
    `solver_topology_from_payload` fails mypy unless every required key is present with the right
    type. No runtime cost — the object at runtime is still a `dict`. The type is the wall that
    keeps future code from opening a second door around `prepare_swebench_case`.
    """

    base_checkout: str
    repo_skeleton: str
    known_files: list[str]
    regression_files: list[str]
    exclude: list[str]
    spec: dict[str, Any]
    passed_at_base: list[str]
    image: str
    issue: str
    # 2026-08-09: when True, the solver SELECT falls back to the whole-run
    # `regression_passed` bool instead of the scoped `regression_held` filter.
    # `prepare_swebench_case(skip_base_pytest=True)` sets this and leaves
    # `passed_at_base` as `[]`. Verified is human-curated to eliminate the
    # flask-class "warnings-as-errors → 133 pre-existing base failures" case
    # (select_exec.py:66-69) — the base-pytest exists as a defense against a
    # class of noise that Verified was built to preclude, so skipping it cuts
    # ~day of prep wall on Verified without changing the honest verdict. On
    # Lite the default stays False; the caller opts in with the confirmatory
    # runner's `SWEBENCH_SKIP_BASE_PYTEST=1`.
    skip_base_pytest: NotRequired[bool]


def safe_case_id(instance_id: str) -> str:
    """A filesystem-safe Case.case_id from a SWE-bench instance_id. The harness forbids `__` in a case_id
    (it is the `{arm}__{case}__t{trial}` run-root separator), but SWE-bench ids contain it
    (`pallets__flask-4045`). Map `__`->`_1776_` (swebench's own TestSpec convention). The REAL instance_id
    stays in `Case.ground_truth` — this is only the path-safe label, never the grade key."""
    return instance_id.replace("__", "_1776_")


def _added_files(diff: str) -> set[str]:
    return {ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"}


# 2026-08-09 wall-clock reshape (item 3 of the review at
# docs/review/REVIEW-2026-08-09-swebench-runner-shape-and-walltime.md and the mother-clone
# rescue that hit right after re-firing pass 1 with skip_base_pytest ON): the pre-fix `_clone_at`
# ran `git clone https://github.com/{repo}` per instance. Verified spans 500 instances across
# ~12 unique repos; at CONCURRENCY=8 the prep runner regularly grabbed 8 astropy instances
# simultaneously and cloned astropy (~700 MB) 8 times in parallel over one pipe — GitHub throttled
# and the clones fought for bandwidth, so 10 min in the runner had prepped zero cases.
#
# Fix: one bare "mother" clone per repo under `~/.cache/substrate/swe-mothers/<owner__repo>.git`,
# then `git clone --local` per instance (hardlinked objects, essentially instant). Two concurrent
# workers hitting the same missing repo serialize on `fcntl.flock` of a per-repo `.lock` file, so
# a fresh cache never triggers two parallel bare-clones of the same repo. On subsequent runs the
# mother is reused as-is — SWE-bench base_commits are years old, so no `git fetch` is needed for
# cache hits. Cross-process safe (the flock survives a runner restart mid-clone).
_MOTHER_CACHE_ROOT = Path.home() / ".cache" / "substrate" / "swe-mothers"


def _mother_clone(repo: str) -> Path:
    """Bare mother clone for `repo` under `~/.cache/substrate/swe-mothers/`, created on first miss
    under a per-repo `fcntl.flock` so two concurrent workers can't both bare-clone the same missing
    repo. Returns the mother path. Idempotent."""
    import fcntl

    _MOTHER_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    safe = repo.replace("/", "__")
    mother = _MOTHER_CACHE_ROOT / f"{safe}.git"
    lock_path = _MOTHER_CACHE_ROOT / f"{safe}.lock"
    with open(lock_path, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            if not mother.exists():
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--bare",
                        "--quiet",
                        f"https://github.com/{repo}",
                        str(mother),
                    ],
                    check=True,
                )
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return mother


def _clone_at(repo: str, base_commit: str) -> str:
    """A per-instance checkout at `base_commit`, cheaply produced from the on-disk mother clone.
    `git clone --local` hardlinks objects — essentially instant even for a 700 MB repo like
    astropy. Origin is removed so the solver's derived clones (`repair_validate_factory` at
    topologies/swebench_solver/repair.py:98 clones this dir again) can't `git fetch` a fix from
    GitHub via origin — the pre-mother `_clone_at` left origin pointing at github.com, a
    pre-existing contamination hole closed here as a side benefit. (The solver still has the
    mother's objects available through the local-clone hardlinks; the container backend at
    swebench_container.py:78-87 does the fuller ref/reflog neuter for the executing-agent path.)"""
    mother = _mother_clone(repo)
    d = tempfile.mkdtemp(prefix="assay-swe-")
    subprocess.run(["git", "clone", "--quiet", "--local", str(mother), d], check=True)
    subprocess.run(["git", "-C", d, "checkout", "--quiet", base_commit], check=True)
    subprocess.run(["git", "-C", d, "remote", "remove", "origin"], capture_output=True, check=False)
    return d


def prepare_swebench_case(
    instance: dict[str, Any],
    *,
    namespace: str = "swebench",
    timeout: int = 1800,
    skip_base_pytest: bool = False,
) -> Case:
    """ENV-GATED (git + Docker). The Adapter's per-case setup: clone at base_commit, discover
    canonical test modules, build the regression command, and optionally run it once at base for
    the passed-at-base set. Returns a `Case` whose `payload` holds PRIMITIVES every Arm
    reconstructs from; `ground_truth` is the instance (the Oracle reads its instance_id).

    2026-08-09 halt-on-error rewrite: no firewall pre-filter. SWE-bench Verified is human-audited
    clean, so a firewall violation on Verified is a data bug in the benchmark and deserves to
    halt the sweep, not silently exclude. Callers using Lite (which does carry leaky instances)
    can call `firewall_check` themselves and skip the leaky ones upstream — that's a benchmark
    choice, not a substrate design.

    2026-08-09 wall-clock reshape: `skip_base_pytest=True` skips the base-repo pytest run — the
    dominant prep bottleneck (astropy/django/sympy: 15-40 min each; 500 instances × 30 min /
    CONCURRENCY=4 ≈ 60h prep). SELECT then falls back to whole-run `regression_passed` at
    select_exec.py:61-76 instead of the scoped `regression_held`. The `passed_at_base` filter
    exists to guard the flask-class "warnings-as-errors → 133 pre-existing base failures" case
    documented at select_exec.py:66-69, which Princeton/OpenAI/Anthropic curated OUT of SWE-bench
    Verified. The choice is stamped in the payload (`skip_base_pytest: True`) and hashed into
    the confirmatory runner's config fingerprint, so the record self-describes the trade.
    """
    base = _clone_at(instance["repo"], instance["base_commit"])
    repo_files = subprocess.run(
        ["git", "-C", base, "ls-files"], capture_output=True, text=True
    ).stdout.split()
    repo_tests = discover_test_modules(repo_files)
    exclude = _added_files(
        instance["test_patch"]
    )  # held-out test_patch file PATHS (firewall-disclosed)
    spec = dict(repo_test_spec(instance["repo"], instance["version"]))

    image = instance_image(instance["instance_id"], namespace=namespace)
    if skip_base_pytest:
        passed_at_base: list[str] = []
    else:
        runner = DockerTestRunner(image, timeout=timeout)
        full_reg = build_regression_command(spec, [t for t in repo_tests if t not in exclude])
        _, base_out = runner.run("", full_reg)  # empty patch -> run on base_commit
        passed_at_base = sorted(passed_tests(base_out))

    payload: PreparedPayload = {
        "base_checkout": base,
        "repo_skeleton": "\n".join(repo_files),
        "known_files": repo_files,
        "regression_files": repo_tests,
        "exclude": sorted(exclude),
        "spec": spec,
        "passed_at_base": passed_at_base,
        "image": image,
        "issue": instance["problem_statement"],
        "skip_base_pytest": skip_base_pytest,
    }
    return Case(
        case_id=safe_case_id(instance["instance_id"]), payload=dict(payload), ground_truth=instance
    )


def solver_topology_from_payload(
    payload: PreparedPayload,
    responders: list[Any],
    *,
    n: int,
    max_rounds: int,
    repro_k: int = 1,
) -> Topology:
    """Reconstruct the swebench_solver topology for a prepared Case payload — the runner + the
    per-candidate firewall-clean regression planner + passed-at-base, with the given responders. Pure
    (no I/O): the runner runs only when the topology runs. This is the Arm's `build` body.
    `repro_k` (F4 fix, review 2026-08-08) samples K reproduction scripts in parallel and combines
    them into ONE runner per Docker invocation — K > 1 is a mechanism upgrade, K = 1 is
    identical to the pre-F4 wire."""
    runner = DockerTestRunner(str(payload["image"]))
    planner = make_regression_planner(
        payload["spec"], list(payload["regression_files"]), exclude=set(payload["exclude"])
    )
    # 2026-08-09 wall-clock reshape: when the case was prepared with
    # `skip_base_pytest=True`, `passed_at_base` is `[]` and we pass `None` so SELECT
    # routes through `regression_passed` (the whole-run bool) rather than
    # `regression_held({}, ...)`, which would treat an empty base-passing set as
    # "no base evidence" and refuse every regression signal. See PreparedPayload
    # docstring for the Verified-vs-Lite rationale.
    passed_at_base: frozenset[str] | None
    if payload.get("skip_base_pytest", False):
        passed_at_base = None
    else:
        passed_at_base = frozenset(payload["passed_at_base"])
    return swebench_solver_topology_with_test_selection(
        responders=responders,
        base_checkout=str(payload["base_checkout"]),
        issue=str(payload["issue"]),
        repo_skeleton=str(payload["repo_skeleton"]),
        known_files=set(payload["known_files"]),
        runner=runner,
        regression_command=planner,
        passed_at_base=passed_at_base,
        n=n,
        max_rounds=max_rounds,
        repro_k=repro_k,
        watchdog_seconds=2400.0,
    )


def swebench_solver_arm(
    name: str,
    role: str,
    *,
    models: Sequence[str],
    n: int | None = None,
    max_rounds: int = 2,
    max_tokens: int = 2048,
) -> Arm:
    """A pipeline (localize→repair→select) Arm over the given producer models. `build(case)` wires the
    swebench_solver topology from the prepared payload with one OllamaResponder per slot. `n` defaults to
    len(models). The producers are interchangeable — this arm uses Ollama responders; the CLI/agent seam
    is a drop-in once built (no model-tier distinction — just producers)."""
    slots = n if n is not None else len(models)

    def build(case: Case) -> Topology:
        # Rate-limit shim wraps every responder so concurrent in-flight calls to the same
        # model share one semaphore capped at the tier limit (design DESIGN-2026-08-11).
        from .swebench_matrix import _ollama_quota_from_env, _wrap_ollama

        quota = _ollama_quota_from_env()
        responders = [
            _wrap_ollama(models[i % len(models)], quota, max_tokens) for i in range(slots)
        ]
        # The cast is the Adapter's promise: this Case was built by `prepare_swebench_case`, so its
        # payload matches PreparedPayload. Any callsite that constructs a Case without going through
        # the Adapter loses the type refinement, which is exactly the door we want closed at check time.
        payload = cast(PreparedPayload, case.payload)
        return solver_topology_from_payload(payload, responders, n=slots, max_rounds=max_rounds)

    return Arm(name=name, role=role, build=build)


def swebench_suite(
    cases: Sequence[Case],
    arms: Sequence[Arm],
    *,
    report_root: Path | str,
    dataset_name: str,
    control_arm: str,
    name: str = "swebench",
    version: str = "0.1",
    primary_metric: str = "resolved",
    null_rule: str = (
        "the primary endpoint is instances resolved (held-out FAIL_TO_PASS + PASS_TO_PASS all pass, "
        "all-or-nothing). A control Arm must appear on the log; equivalence is claimed only if the paired "
        "delta CI sits inside the pre-registered margin, never from non-significance alone."
    ),
    equivalence_margin: float = 0.1,
    pass_k: int = 1,
) -> Suite:
    """Assemble the pre-registered SWE-bench Suite: the prepared Cases, the Arm matrix, and the
    record-grading Docker Oracle. `report_root` is where the harness writes per-instance grade reports."""
    return Suite(
        name=name,
        version=version,
        cases=tuple(cases),
        arms=tuple(arms),
        oracle=swebench_record_oracle(report_root=report_root, dataset_name=dataset_name),
        control_arm=control_arm,
        primary_metric=primary_metric,
        null_rule=null_rule,
        equivalence_margin=equivalence_margin,
        pass_k=pass_k,
    )


__all__ = [
    "safe_case_id",
    "prepare_swebench_case",
    "solver_topology_from_payload",
    "swebench_solver_arm",
    "swebench_suite",
    "ABLATION",
    "BASELINE",
    "FULL",
]
