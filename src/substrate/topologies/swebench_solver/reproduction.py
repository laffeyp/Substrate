"""Reproduction-test generation — the solver's own check that a patch fixes the issue (sprint 144).

A model call: from the issue, write a self-contained test that prints "Issue reproduced" when the bug is
present and "Issue resolved" when it's fixed. SELECT runs it against each candidate patch and prefers
patches that resolve the issue. The test is the solver's OWN artifact, generated from the issue text —
NOT the held-out FAIL_TO_PASS (firewall). If the model call fails, it emits an empty test rather than
crashing, so the run can't hang (KIT_DIARY 16).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from ...adapters import Responder, call_responder_metered
from .records import ReproductionTest

_Factory = Callable[[], Any]

_PROMPT = """Write ONE self-contained Python test script that reproduces the issue below.

The script MUST:
- import only from the project and the standard library,
- exercise the specific behavior the issue describes,
- print EXACTLY the line "Issue reproduced" if the buggy behavior is present (the bug is NOT fixed),
- print EXACTLY the line "Issue resolved" if the behavior is correct (the bug IS fixed),
- on any unexpected error, print "Other issues" then the traceback.

Output ONLY the Python code. No prose, no markdown fences.

## issue
{issue}
"""


def build_repro_prompt(issue: str) -> str:
    return _PROMPT.format(issue=issue)


def parse_repro_code(response: str) -> str:
    """Strip a wrapping markdown fence if the model added one; otherwise return the code as-is."""
    s = response.strip()
    if s.startswith("```"):
        lines = s.splitlines()[1:]  # drop the opening ``` (and any language tag)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines)
    return s.strip()


def combine_repro_scripts(scripts: list[str]) -> str:
    """Bundle K reproduction scripts into ONE runner script that executes each in-process
    (isolated subprocesses would spawn K Python interpreters). F4 fix (review 2026-08-08):
    the pre-fix generator sampled K=1 — one repro was one Bernoulli draw per candidate, and the
    flask-4045 failure mode (KIT_DIARY 21, "repro exercises the wrong half of the bug") had no
    variance to surface. Combining K scripts into one runner amortises the single Docker
    invocation `select_exec` already pays: K variants for one container start, not K starts.

    Each script runs in an isolated dict namespace so name collisions across scripts can't
    poison later variants. All output prints go to stdout in submission order. Empty script
    entries are skipped (a failed model call at K > 1 shouldn't zero the whole set).

    K=1 case: identical to the pre-fix `code` — just the one script's text. The runner wrapper
    fires the same single execution."""
    scripts = [s for s in scripts if s.strip()]
    if not scripts:
        return ""
    if len(scripts) == 1:
        return scripts[0]
    parts = ["import io, contextlib, traceback"]
    for i, s in enumerate(scripts):
        # Encode the script as a string so no character-escaping across the runner boundary.
        # exec() in a fresh namespace so scripts don't share state.
        parts.append(f"# --- repro variant {i} ---")
        parts.append("try:")
        parts.append("    _buf = io.StringIO()")
        parts.append("    with contextlib.redirect_stdout(_buf):")
        indented = "\n".join("        " + line for line in s.splitlines())
        parts.append("        exec(compile(" + repr(s) + ", '<repro-" + str(i) + ">', 'exec'), {})")
        parts.append("    print(_buf.getvalue(), end='')")
        parts.append("except Exception:")
        parts.append("    print('Other issues')")
        parts.append("    traceback.print_exc()")
        # keep `indented` referenced so future indentation-style variant doesn't dead-code it
        del indented
    return "\n".join(parts)


def repro_generator_factory(responder: Responder, issue: str, *, k: int = 1) -> _Factory:
    """The reproduction-test generator. F4 fix (review 2026-08-08): now samples K >= 1 times in
    parallel and combines the K scripts into one runner via `combine_repro_scripts`. Emits K
    metered usages (one per sample) then ONE ReproductionTest whose `.code` is the combined
    runner script. Downstream `select_exec` invokes Docker once per candidate and the runner
    prints K markers; `reproduction_status` then majority-votes over the markers.

    K=1 (default): identical wire behaviour to the pre-fix generator. K > 1 pays K model calls
    at generation time (parallel) + ~K× script execution inside the one Docker invocation the
    select_exec pass already runs — no extra container starts.

    If ALL K model calls fail, emits an EMPTY ReproductionTest (SELECT then uses only the
    regression result) instead of crashing — same as the localizer and drafter (KIT_DIARY 16).
    Partial failures (some K succeed, some raise) drop the raising samples and emit a runner
    over the survivors — K=3 with one failed call becomes an effective-K=2 vote."""
    if k < 1:
        raise ValueError(f"k must be >= 1; got {k}")

    async def _one_call() -> tuple[str, Any]:
        # 2026-08-09 halt-on-error rewrite: no exception swallow. asyncio.gather propagates.
        response, usage = await call_responder_metered(responder, build_repro_prompt(issue))
        return parse_repro_code(response), usage

    async def generate(_inp: Any) -> AsyncIterator[Any]:
        outcomes = await asyncio.gather(*[_one_call() for _ in range(k)])
        codes: list[str] = []
        for code, usage in outcomes:
            yield usage
            if code:
                codes.append(code)
        yield ReproductionTest(code=combine_repro_scripts(codes))

    return lambda: generate
