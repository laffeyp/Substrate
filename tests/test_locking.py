# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Persistent-bus locking (technical §11) — conformance check 10 in miniature."""

import pytest

from substrate.errors import BusLockedError
from substrate.record.locking import acquire_lock, release_lock


def test_second_runtime_against_locked_root_fails_fast(tmp_path):
    fd = acquire_lock(tmp_path, start_time=1.0)
    try:
        with pytest.raises(BusLockedError) as ei:
            acquire_lock(tmp_path, start_time=2.0)
        # advisory contents identify the holder
        assert ei.value.advisory.get("pid") is not None
    finally:
        release_lock(fd)


def test_lock_is_reacquirable_after_release(tmp_path):
    fd = acquire_lock(tmp_path, start_time=1.0)
    release_lock(fd)
    fd2 = acquire_lock(tmp_path, start_time=2.0)  # must succeed now
    release_lock(fd2)
