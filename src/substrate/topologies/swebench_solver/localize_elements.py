"""Element-level localizer — sprint 157a (Group E of the close-the-loop roadmap).

The file-level localizer at `localize.py` names the SUSPECT FILES; this module reads those files
and enumerates their AST elements (top-level functions + methods on classes), so the Repairer's
`edit_context` can be trimmed from "the whole suspect file" to "just the classes/functions the
model might need to touch" (Agentless-style, per docs/swebench-solver-design.md §5). Additive
alongside the file-level path — the roadmap card scopes it as an ablation arm, not a replacement.
The existing `SuspectElements` record (records.py:51-55) has been defined-but-unemitted since
sprint 138; this module is what emits it.

Two entrypoints:
  - `extract_elements(source: str) -> list[str]` — pure, deterministic, takes Python source text
    and returns qualified element names in file order (`ClassName.method`, `top_level_function`).
    A syntax error yields an empty list rather than raising — a repo with a partially-parseable
    file is normal, and the file-level localizer's suspect set stays useful.
  - `element_localizer_factory(responder, issue, repo_skeleton, base_checkout, known_files, ...)`
    — a producer that fires the file-level LLM call (same prompt as `localizer_factory`) and
    additionally reads each suspect file from `base_checkout`, extracts its elements, and emits
    one `SuspectElements` per file. EditLocations then carries `file::element` targets that the
    Repairer's `_build_edit_context` (assemble.py) can trim to.

Non-Python files (docs, config, JSON) go through as-is: no elements extracted, the file itself
stays in EditLocations. That means a mixed-language patch (e.g. flask changes a `.py` AND a
`.cfg`) still routes both files through — element trimming is a Python-only affordance today,
not a filter that would drop non-Python targets.
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from ...adapters import Responder, call_responder_metered
from .localize import build_localize_prompt, parse_suspect_files
from .records import EditLocations, SuspectElements, SuspectFiles

_Factory = Callable[[], Any]


def extract_elements(source: str) -> list[str]:
    """Enumerate qualified AST elements (top-level functions + class methods) from Python source
    text in file order. Returns names like `top_fn`, `MyClass.method`, `MyClass.other_method`.
    Nested functions and async variants both included; nested classes render as `Outer.Inner`
    (methods on Outer.Inner render as `Outer.Inner.method`).

    Syntax errors → `[]` — a partially-parseable file is a normal repo state (an unfinished
    edit, a Python 2 remnant, a generated stub). The file-level localizer's suspect set stays
    useful even when element extraction can't kick in for that file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[str] = []

    def walk(node: ast.AST, prefix: str) -> None:
        # Iterate direct children of `node`. A function child gets emitted with `prefix`; a
        # class child gets its methods qualified as `prefix + class_name.method_name` — done by
        # recursing INTO the class with a new prefix. Nested classes render as
        # `Outer.Inner.method`. Recursion covers all nesting depths; no manual grandchild loop.
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                out.append(f"{prefix}{child.name}")

    walk(tree, "")
    return out


def _extract_from_file(base_checkout: Path, file_path: str) -> tuple[str, ...]:
    """Read a file from the checkout and extract its elements. Non-Python paths + unreadable
    files return `()` — the file itself stays in EditLocations (see module docstring) so a
    non-Python patch target isn't dropped. Reads with UTF-8 + `errors="replace"` because a repo
    may have latin-1 legacy files that block full extraction but are still legitimate patch
    targets."""
    if not file_path.endswith(".py"):
        return ()
    p = base_checkout / file_path
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return ()
    return tuple(extract_elements(text))


def element_localizer_factory(
    responder: Responder,
    issue: str,
    repo_skeleton: str,
    base_checkout: str,
    known_files: set[str],
    *,
    top_k: int = 5,
) -> _Factory:
    """The element-level localizer producer. Same first step as `localizer_factory`: one LLM call
    to pick suspect files from the issue + repo skeleton. Then a deterministic AST pass over the
    top-k suspect files reads elements out of the checkout on disk, emits one `SuspectElements`
    per file, and composes `EditLocations` at `file::element` granularity — so the Repairer's
    `edit_context` can be trimmed to just the classes/functions the model might need to touch.

    Death-resilience matches the file-level localizer (KIT_DIARY 16): the LLM call is wrapped;
    if it dies, emit an empty SuspectFiles + no SuspectElements + empty EditLocations, so the
    seed trigger still fires with a blank slate and the loop reaches a clean Exhausted rather
    than wedging the whole instance."""
    checkout = Path(base_checkout)

    async def localize(_inp: Any) -> AsyncIterator[Any]:
        try:
            response, usage = await call_responder_metered(
                responder, build_localize_prompt(issue, repo_skeleton)
            )
            yield usage
            files = parse_suspect_files(response, known_files)[:top_k]
        except Exception:  # noqa: BLE001 — see localizer_factory's rationale (KIT_DIARY 16).
            files = []

        yield SuspectFiles(files=tuple(files))

        targets: list[str] = []
        for file_path in files:
            elements = _extract_from_file(checkout, file_path)
            if elements:
                yield SuspectElements(file=file_path, elements=elements)
                targets.extend(f"{file_path}::{e}" for e in elements)
            else:
                # Non-Python file, unreadable, or syntax-error: the file stays as a whole-file
                # target so the Repairer can still route to it. NOT a silent drop.
                targets.append(file_path)

        yield EditLocations(targets=tuple(targets))

    return lambda: localize


__all__ = ["element_localizer_factory", "extract_elements"]
