# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Reusable conversation instruments (Wave 13, lifted from the recursive_strategy_refinment
precursor's `instruments/`).

Composable application-level components that make the conversation topologies richer and
demonstrate composition: proper scoring rules (close the cheap-talk loop by paying for
calibration), and — as Producer+View+Route patterns — a confidence-claim grader, a repair
detector, and a common-ground extractor. Each is a small composition over substrate's public
primitives, not a runtime change. `scoring` is pure (no LLM, no I/O); the LLM-backed
instruments are non-load-bearing side Producers (a failure emits ProducerFailed and never
aborts the run — substrate gives that for free).
"""
