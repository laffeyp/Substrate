# REVIEW — Piece B red-team close (2026-08-28)

**Reviewer:** Claude, session 2026-08-28.
**Scope:** the red-team correction that closed piece B on 2026-08-28.
Companion to REVIEW-2026-08-26-piece-b-fold-and-215-216-red-team.md;
this doc closes the correction thread the earlier fold opened, per
sdd-kit-2 rule 12 (audit trail is the work) — REVIEW-2026-08-28
F8 named the missing dated closure doc.

## What the red-team pass produced

A drift found and corrected mid-session. The agent had claimed piece B
carried five open items:

1. Missing `POST /api/topology/<name>/run` endpoint.
2. Missing `GET /api/topology/<name>/status?run_id=<id>` endpoint.
3. Missing `GET /api/applications` endpoint.
4. Missing `POST /api/bundle` endpoint.
5. Missing `GET /api/bundle` endpoint.

The Architect challenged the framing. On re-reading TECH-SPEC-2026-08-25
-round6 §7 line 144-146, three of the five (`POST /api/topology/*/run`,
`GET /api/topology/*/status`, `GET /api/applications`) are explicitly
scoped to piece E; the two `/api/bundle` endpoints are scoped to piece H
under the same parenthetical-cluster convention. Piece B's scope is
session endpoints only, and every one shipped: `POST /api/session`,
`POST /api/session/<id>/turn`, `POST /api/session/<id>/interrupt`,
`POST /api/session/<id>/end`, `GET /api/session/<id>/events`,
`GET /api/session`, `GET /api/session/by-name/<name>`,
`PATCH /api/session/<id>`, `DELETE /api/session/<id>`. Nine endpoints.
Piece B owed zero of the five the agent had listed.

## The four KIT_DIARY findings the correction folded

The BLACKBOARD 2026-08-28 head entry ("PIECE B CLOSED, red-team-
corrected") names the closure; the doctrine landed in KIT_DIARY findings
64-67:

- **KD 64 — endpoint scope inference from a parenthetical.** The agent
  read spec line 144's parenthetical `(piece E)` as applying to only
  one endpoint in the cluster. Round-6's convention is that the
  parenthetical applies to the whole visually-adjacent block; the
  cluster reads together. Doctrine: on any parenthetical scope tag,
  read the whole cluster the tag opens, not just the line the tag sits
  on.

- **KD 65 — "still open" needs a source, not an inference.** The
  agent's "5 still open" claim rested on grep-hits for endpoints not on
  the wire; it did not verify against the piece-B scope declaration.
  Doctrine: an "open" claim cites the scope doc (spec or roadmap) that
  makes it open, not the absence-of-implementation grep.

- **KD 66 — prescribing endpoint work before writing sprint cards.**
  The agent proposed shipping the five missing endpoints inline in the
  same session. Discipline requires a sprint card per concept; the
  wrong shape is "just add the endpoints and move on." Doctrine:
  every additive endpoint gets a card first; agent has zero right to
  ship endpoint work off-card, even for pieces that look adjacent.

- **KD 67 — piece boundaries hold across arcs.** Piece B closes when
  its own scope closes, not when an adjacent piece's endpoints happen
  to be missing. Doctrine: never fold work into piece X because piece
  Y needs it eventually; write piece Y's card and land it under piece
  Y's arc.

## What actually closed piece B

Sprints landed in this order across 2026-08-26 and 2026-08-27:

- 214a, 214b, 214c: session create + turn + list + by-name + events + delete.
- 215a: POST /end.
- 215b: HALTED on `substrate_primitive_missing` (no in-loop
  targeted-producer cancel on Runtime).
- 215c: PATCH driver + name.
- 215d: SIGTERM graceful shutdown.
- 216: per-session turn-queue cap + 410 on ended session.
- 217a: daemon composes `Runtime.run` for turn 1 + `Runtime.resume`
  for turn 2+ (closed finding 16 from piece-B fold review).
- 217c: `Runtime.cancel_producer(instance, cause=, caller=)` kernel
  primitive + `substrate.ProducerCancelled` payload gains `cause` and
  `caller` (v0.3 vocabulary bump, additive).
- 217d: daemon interrupt endpoint rewires onto 217c's primitive.
- 217e: daemon extensions for piece D — PATCH tools + POST /turn
  context + UDS bind.

Nine session endpoints on the wire. `Runtime.cancel_producer` added
additively per the v0.3 vocabulary evolution pipeline. SIGTERM
graceful shutdown. Per-session queue cap. 410 semantics on ended /
deleted sessions.

## Open items on piece B at close

Two decision items, not code work, both surfaced by the piece-B fold
review (2026-08-26):

- Finding 10: `_session_events` reimplements `LiveRecord.follow(
  until_finalised=True)` at `server.py:975-1163`. Accept-as-is or
  write a card to swap the seam. Not affecting behavior; noted for
  a future hygiene pass.
- Finding 11 (F11): SSE endpoint sends no keep-alive comment during
  idle. Accept-as-is or write a card to add the heartbeat. Reverse
  proxies with idle timeouts might close idle streams; not affecting
  the shipped daemon behavior against a direct client.

Neither blocks piece D or downstream.

## Verification

- 175/175 substrate-ui tests pass at piece-B close.
- 951 substrate tests pass (5 skipped, 1 real-model timeout on
  `test_realmodel_demos.py::test_instrument_ablation_delta` — unrelated
  to piece-B code paths).
- Zero legacy session records exist on disk under
  `~/.substrate/sessions/` (grep for `s_*` returned zero at close);
  every existing directory is `adhoc-*` or `sess-*` from earlier
  schemes with no `manifest.json` — the 214a-216 legacy-shape debt is
  theoretical, no migration owed.

## Closure verdict

Piece B is closed under the corrected scope. The correction thread is
now on file as this doc; future readers searching "piece B closure"
land here first. The four KIT_DIARY doctrines (64-67) apply forward.

*REVIEW-2026-08-28-piece-b-red-team-close.md. Author: Claude session
2026-08-28. Closes the correction opened by
REVIEW-2026-08-26-piece-b-fold-and-215-216-red-team.md via KIT_DIARY
findings 64-67.*
