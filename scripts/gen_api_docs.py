"""Generate docs/api.md from the live `substrate.api.__all__` and the symbols' docstrings.

The API reference is GENERATED, never hand-written, so it cannot drift from the code. Run
`uv run python scripts/gen_api_docs.py` after any change to the public surface (`api.__all__`)
or a public docstring. The grouping below must cover `__all__` exactly — the script asserts
it (a new public symbol that isn't grouped fails loudly, so the doc is never silently
incomplete).
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import substrate.api as api

# Symbol groups, mirroring the section comments in api.py's __all__. MUST partition __all__.
GROUPS: dict[str, list[str]] = {
    "Data types": ["Event", "BlobRef", "ProducerRef", "Subscription"],
    "Primitives & protocols": [
        "Producer",
        "View",
        "BufferView",
        "KindBuffer",
        "KindCount",
        "PerKindLatest",
        "StartedCompletedCounts",
        "Once",
        "PerEvent",
        "PerKey",
        "WhileTrue",
        "Logical",
        "WallClock",
        "TerminationPolicy",
        "Decision",
    ],
    "Termination recipes": [
        "threshold_count",
        "all_completed",
        "quiescence_with_watchdog",
        "pause_await_input",
        "cancel_all_others",
        "let_finish",
        "any_of",
        "all_of",
    ],
    "Topology & execution": [
        "TopologyBuilder",
        "register_topology",
        "get_topology",
        "Runtime",
        "RunResult",
    ],
    "Records & encoding": [
        "read_record",
        "recover_open_segment",
        "Interval",
        "Always",
        "NoFsync",
        "canonical_bytes",
        "content_hash",
    ],
    "Live attach (technical §13)": ["attach", "LiveRecord"],
    "Off-bus sidecars (technical §3.8 / §6.4)": ["read_sidecar"],
    "Composition (technical §20)": ["embedded_substrate", "EmbeddedRunFailed"],
    "Conformance suite (product §7)": [
        "run_conformance",
        "ConformanceReport",
        "CheckResult",
        "Status",
    ],
    "Replay (technical §12)": ["replay", "assert_replayable", "ReplayResult", "HashMismatch"],
    "Inspection / provenance / divergence (technical §14)": [
        "explain_producer",
        "trace_ancestry",
        "view_at",
        "decisions_between",
        "first_divergence",
        "Explanation",
        "Divergence",
    ],
    "Test helpers (technical §15)": ["assert_event", "assert_no_event", "assert_sequence"],
    "Exceptions (design §6.3)": [
        "SubstrateError",
        "BusLockedError",
        "RegistrationError",
        "UnsupportedPlatformError",
        "FsyncError",
        "ProducerNotFound",
        "SequenceOutOfRange",
        "InputTypeError",
        "ReplayError",
        "RecordIncompleteError",
    ],
}

_METHODS_FOR = {"Runtime", "TopologyBuilder", "LiveRecord"}  # classes whose methods to list


def _signature(obj: object) -> str:
    try:
        return str(inspect.signature(obj)) if callable(obj) else ""
    except (ValueError, TypeError):
        return ""


def _own_doc(obj: object) -> str:
    """The symbol's OWN docstring only — never an inherited base-class docstring. `inspect.getdoc`
    walks the MRO, so a class with no docstring of its own (e.g. an msgspec.Struct or an Enum
    subclass) would otherwise pick up the base class's example docstring as slop. We read
    `__doc__` directly (which is per-class / per-object, not inherited for classes) and clean its
    indentation. A symbol with no own docstring renders as "_(no docstring)_"."""
    doc = getattr(obj, "__doc__", None)
    return inspect.cleandoc(doc).strip() if doc else "_(no docstring)_"


def _summary(own: str) -> str:
    """A one-line method-list summary: the first SENTENCE of the first paragraph, with source
    line-wraps collapsed (not the first physical line, which would trail off mid-sentence). The
    sentence boundary requires the terminator to be followed by whitespace + a capital/`(` or
    end-of-string (so it never cuts at a qualified name like `msgspec.Struct` or `§4.2`), and a
    negative lookbehind exempts the common lowercase abbreviations `e.g.` / `i.e.` / `etc.`."""
    if own == "_(no docstring)_":
        return ""
    para = " ".join(own.split("\n\n")[0].split())  # first paragraph, whitespace collapsed
    m = re.match(r"(.+?[.!?])(?<!e\.g\.)(?<!i\.e\.)(?<!etc\.)(?=\s+[A-Z(]|\s*$)", para)
    return m.group(1) if m else para


def generate() -> str:
    grouped = {n for names in GROUPS.values() for n in names}
    missing = set(api.__all__) - grouped
    extra = grouped - set(api.__all__)
    if missing or extra:
        raise SystemExit(
            f"gen_api_docs: groups do not match api.__all__ — missing {missing}, extra {extra}"
        )

    out: list[str] = [
        "# API reference — `substrate.api`",
        "",
        "The complete public surface (F-API-1). Everything else is private; the CLI imports only",
        "this module (F-API-6). **This page is GENERATED from the live `substrate.api.__all__` and",
        "the symbols' own docstrings** (`scripts/gen_api_docs.py`) so it cannot drift from the",
        "code. Regenerate (`uv run python scripts/gen_api_docs.py`) after any public-surface change.",
        "",
    ]
    for title, names in GROUPS.items():
        out += [f"## {title}", ""]
        for name in names:
            obj = getattr(api, name)
            sig = _signature(obj)
            out.append(f"### `{name}{sig}`" if sig else f"### `{name}`")
            out.append("")
            out.append(_own_doc(obj))
            out.append("")
            if isinstance(obj, type) and name in _METHODS_FOR:
                for m, mo in inspect.getmembers(obj, predicate=inspect.isfunction):
                    if m.startswith("_"):
                        continue
                    out.append(f"- `{m}{_signature(mo)}` — {_summary(_own_doc(mo))}")
                out.append("")
    return "\n".join(out) + "\n"


def main() -> None:
    target = Path(__file__).resolve().parent.parent / "docs" / "api.md"
    target.write_text(generate())
    print(f"wrote {target} ({len(api.__all__)} symbols across {len(GROUPS)} groups)")


if __name__ == "__main__":
    main()
