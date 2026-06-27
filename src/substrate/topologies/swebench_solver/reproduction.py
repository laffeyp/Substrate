"""Reproduction-test generation — the solver's own check that a patch fixes the issue (sprint 144).

A model call: from the issue, write a self-contained test that prints "Issue reproduced" when the bug is
present and "Issue resolved" when it's fixed. SELECT runs it against each candidate patch and prefers
patches that resolve the issue. The test is the solver's OWN artifact, generated from the issue text —
NOT the held-out FAIL_TO_PASS (firewall). If the model call fails, it emits an empty test rather than
crashing, so the run can't hang (KIT_DIARY 16).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from ...reference._models import Responder, call_responder_metered
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


def repro_generator_factory(responder: Responder, issue: str) -> _Factory:
    """The reproduction-test generator (one model call). Emits the metered usage then the ReproductionTest.
    If the model call fails, it emits an EMPTY ReproductionTest (SELECT then uses only the regression
    result) instead of crashing — same as the localizer and drafter (KIT_DIARY 16)."""

    async def generate(_inp: Any) -> AsyncIterator[Any]:
        try:
            response, usage = await call_responder_metered(responder, build_repro_prompt(issue))
            yield usage
            code = parse_repro_code(response)
        except Exception:  # noqa: BLE001 — a failed model call must not crash the producer (KIT_DIARY 16)
            code = ""
        yield ReproductionTest(code=code)

    return lambda: generate
