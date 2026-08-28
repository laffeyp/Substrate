"""Tiny home-rolled interpolator for the Mad Lib bundle wizard.

TECH-SPEC §9 line 57-60 asks for `{{slot_name}}` substitution and
`{% if slot_name %}...{% endif %}` conditionals — no jinja, no
sandbox concerns. This module ships that in ~40 lines.

Grammar:
  - `{{ slot_name }}` (whitespace optional) inserts the slot value.
  - `{% if slot_name %}<body>{% endif %}` includes `<body>` iff the
    slot value is truthy. Non-nested. A nested `{% if %}` inside
    `<body>` is not supported; the template parser refuses one
    at render time with `TemplateError`.
  - Missing slot in `values` is treated as empty string / falsy.
  - `slots:` YAML-fenced header block is parsed by
    `parse_template_header` — the caller reads slot declarations
    for the wizard prompt loop; the rest of the template is fed to
    `render`.
"""

from __future__ import annotations

import re
from typing import Any


class TemplateError(Exception):
    """Malformed template — missing endif, nested if, unknown syntax."""


_SLOT_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_IF_PATTERN = re.compile(
    r"\{%\s*if\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*%\}(.*?)\{%\s*endif\s*%\}",
    re.DOTALL,
)


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return bool(value)


def render(template: str, values: dict[str, Any]) -> str:
    """Substitute `{{slot}}` and evaluate `{% if slot %}...{% endif %}`.

    Order matters: conditionals expand first so a `{{slot}}` inside a
    conditional body still expands.
    """
    if "{% if" in template:
        outer_ifs = _find_all_ifs(template)
        for start, end, slot, body in reversed(outer_ifs):
            if "{% if" in body:
                raise TemplateError("nested {% if %} not supported; flatten the template")
            replacement = body if _truthy(values.get(slot)) else ""
            template = template[:start] + replacement + template[end:]

    def _substitute(match: re.Match[str]) -> str:
        slot = match.group(1)
        value = values.get(slot, "")
        return "" if value is None else str(value)

    return _SLOT_PATTERN.sub(_substitute, template)


def _find_all_ifs(template: str) -> list[tuple[int, int, str, str]]:
    """Return every (start, end, slot, body) tuple for `{% if %}...{% endif %}`
    blocks. `end` is one past the closing `{% endif %}` sentinel so a
    caller can splice with `template[:start] + replacement + template[end:]`."""
    result: list[tuple[int, int, str, str]] = []
    for match in _IF_PATTERN.finditer(template):
        result.append((match.start(), match.end(), match.group(1), match.group(2)))
    return result


def parse_template_header(source: str) -> tuple[dict[str, Any], str]:
    """A Mad Lib template starts with a YAML-fenced `slots:` block:

        ---
        slots:
          - name: rubric
            kind: text_paragraph
            prompt: "The review rubric this bundle should apply"
          - name: security_posture
            kind: bool
            prompt: "Flag unsafe patterns on every turn?"
        ---
        <template body>

    Returns `({"slots": [...]}, template_body_without_header)`. Missing
    header is an error — a Mad Lib without slot declarations is a plain
    string.
    """
    stripped = source.lstrip()
    if not stripped.startswith("---"):
        raise TemplateError("template missing YAML `slots:` header block")
    lines = stripped.splitlines(keepends=True)
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise TemplateError("template YAML header not closed with `---`")
    header_text = "".join(lines[1:end_index])
    body = "".join(lines[end_index + 1 :])
    slots = _parse_slots_yaml(header_text)
    return {"slots": slots}, body


def _parse_slots_yaml(text: str) -> list[dict[str, Any]]:
    """Minimal YAML subset: only the `slots:` list of `{name, kind,
    prompt, choices?}` dicts. Avoids a runtime PyYAML dependency for
    this small surface."""
    slots: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("slots:"):
            continue
        if line.startswith("  - "):
            if current is not None:
                slots.append(current)
            current = {}
            key, _, value = line[4:].partition(":")
            current[key.strip()] = value.strip().strip('"')
        elif line.startswith("    ") and current is not None:
            key, _, value = line[4:].partition(":")
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                current[key] = [v.strip().strip('"') for v in value[1:-1].split(",") if v.strip()]
            else:
                current[key] = value.strip('"')
    if current is not None:
        slots.append(current)
    return slots


__all__ = ["TemplateError", "parse_template_header", "render"]
