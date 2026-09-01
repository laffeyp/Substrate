# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The persistence layer — the segmented run record (writer / reader / torn-tail recovery), CRC
framing, the content-addressed blob store, segment sealing, the single-writer lock, off-bus sidecars."""
