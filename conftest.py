"""Pytest session hygiene — clear stale bytecode before collection.

An editable install plus repeated cross-session runs can leave stale `.pyc` that SHADOWS edited
source (an old compiled function body runs while the source reads correct), producing PHANTOM
test failures — review #22 (Lens 5) found this nearly caused two false bug reports, including a
spurious "HIGH" one. Clearing `__pycache__` under the package before the session, and not writing
new bytecode for the run, keeps "green means green".
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def pytest_configure(config: object) -> None:
    """Clear the package's compiled bytecode and stop writing more for this session."""
    del config  # unused; pytest passes the Config object by name
    sys.dont_write_bytecode = True
    pkg = Path(__file__).parent / "src" / "substrate"
    for pycache in pkg.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)
