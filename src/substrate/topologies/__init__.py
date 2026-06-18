"""Bundled application topologies (Phase 2 — the runtime made visible).

Each topology is a small, self-contained demonstration built ONLY on the public
`substrate.api` surface (the same surface a third-party topology author has). They are
dual-mode like the §8 reference topologies: a CI mode with deterministic stand-in
Producers (proves the wiring, runs every commit, no network) and a walkthrough mode with
real local LLMs (proves the claim). The model seam is `substrate.reference._models.Responder`.

Sprint 140 formalizes a registry + entry-point discovery; until then, import topologies
directly (e.g. `from substrate.topologies.code_review import code_review_topology`).
"""
