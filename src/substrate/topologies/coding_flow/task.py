# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The coding task the flow builds + validates. A task is shape-agnostic: a spec for the drafters, a
free-form GATE command, a set of fixed `fixtures` always written into the sandbox (here the test
file the candidate is validated against), and — for CI — canned good/buggy candidate responses so
the deterministic mode exercises a REAL gate run without a model.

The demo task: a small multi-file Python module — an in-memory key-value store (`store.py`) plus a
command router (`router.py`) — validated by `ruff check . && mypy . && pytest`. Multi-file, a real
multi-check gate, in-ecosystem (no extra toolchain).
"""

from __future__ import annotations

from msgspec import Struct


class CodingTask(Struct, frozen=True):
    """A unit of work for the flow. `spec` instructs the drafters; `gate` validates a candidate;
    `fixtures` are files always present in the sandbox (the tests); `ci_good`/`ci_bad` are canned
    drafter responses (model-output format) so CI runs a real gate deterministically."""

    name: str
    spec: str
    gate: str
    fixtures: dict[str, str]
    ci_good: str
    ci_bad: str


_SPEC = """\
Build a tiny in-memory key-value store as TWO files.

# path: store.py
A `Store` class: `get(key: str) -> str | None`, `set(key: str, value: str) -> None`,
`delete(key: str) -> bool` (True iff the key existed). Back it with a `dict[str, str]`.

# path: router.py
A `handle(store: Store, command: str) -> str` function dispatching whitespace-split commands:
  - `SET <k> <v>` -> store the value, return "OK"
  - `GET <k>`     -> return the value, or "NIL" if absent
  - `DEL <k>`     -> return "OK" if it existed, else "NIL"
  - anything else -> "ERR"

Hard constraints (the gate is `ruff check` + `mypy --strict` + `pytest`):
  - `router.py` MUST do `from store import Store` and use the Store CLASS (not a dict alias).
  - Add NO import you don't use (ruff F401 fails the build).
  - Every function fully type-annotated.
Output ONLY the two files, each as a `# path: <name>` line then a fenced ```python block. No prose.
"""

_TESTS = """\
from router import handle
from store import Store


def test_set_then_get() -> None:
    s = Store()
    assert handle(s, "SET a 1") == "OK"
    assert handle(s, "GET a") == "1"


def test_get_missing() -> None:
    assert handle(Store(), "GET nope") == "NIL"


def test_delete() -> None:
    s = Store()
    handle(s, "SET a 1")
    assert handle(s, "DEL a") == "OK"
    assert handle(s, "GET a") == "NIL"
    assert handle(s, "DEL a") == "NIL"


def test_unknown_command() -> None:
    assert handle(Store(), "FOO bar") == "ERR"
"""

# A correct candidate, in the drafter's output format. Passes ruff + mypy --strict + all four tests.
_GOOD = """\
Here is the implementation.

# path: store.py
```python
class Store:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False
```

# path: router.py
```python
from store import Store


def handle(store: Store, command: str) -> str:
    parts = command.split()
    if not parts:
        return "ERR"
    op = parts[0]
    if op == "SET" and len(parts) == 3:
        store.set(parts[1], parts[2])
        return "OK"
    if op == "GET" and len(parts) == 2:
        value = store.get(parts[1])
        return value if value is not None else "NIL"
    if op == "DEL" and len(parts) == 2:
        return "OK" if store.delete(parts[1]) else "NIL"
    return "ERR"
```
"""

# A buggy candidate: an unknown command falls through to "OK" instead of "ERR" (fails
# test_unknown_command) and GET of a missing key returns "" instead of "NIL" (fails test_get_missing).
# ruff/mypy-clean but behaviourally wrong — exactly the case build-validation must catch.
_BAD = """\
# path: store.py
```python
class Store:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def delete(self, key: str) -> bool:
        existed = key in self._data
        self._data.pop(key, None)
        return existed
```

# path: router.py
```python
from store import Store


def handle(store: Store, command: str) -> str:
    parts = command.split()
    op = parts[0] if parts else ""
    if op == "SET":
        store.set(parts[1], parts[2])
        return "OK"
    if op == "GET":
        return store.get(parts[1]) or ""
    if op == "DEL":
        return "OK" if store.delete(parts[1]) else "NIL"
    return "OK"
```
"""


def kvstore_task() -> CodingTask:
    """The demo task: a two-file in-memory key-value store + router, gated by ruff + mypy + pytest."""
    return CodingTask(
        name="kvstore",
        spec=_SPEC,
        gate="ruff check . && mypy --strict . && python -m pytest -q",
        fixtures={"test_kvstore.py": _TESTS},
        ci_good=_GOOD,
        ci_bad=_BAD,
    )
