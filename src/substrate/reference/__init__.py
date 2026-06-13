"""Reference topologies R-1/R-2/R-3 (product §8) — acceptance tests, not product features.

Dual-mode: CI mode (deterministic stand-in Producers, gated every commit) proves the wiring;
walkthrough mode (real local LLMs via the openai-compat adapter) proves the claim each
topology exists to demonstrate. These are topology-layer code — they import only
`substrate.api` (like the CLI), never kernel internals.
"""
