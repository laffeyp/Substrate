# Sprint 184 — Mark PAPER as position doc, correct authority citations (closes external round-2 M2)

---

```yaml
---
id: 184
status: closed
phase: 0
pass_kind: docs
---
```

## scope

Round-2 review M2 named the paper `docs/review/PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` as a positioning document, not an engineering audit. Three specific reasons: title imports the adoption framing the user memory `feedback-no-market-framing-correctness-is-the-point` forbids; § 10 "What NOT to conclude" violates `feedback-writing-no-negative-examples-banned-schoolroom`; the natural-experiment argument doesn't control the variable (see round-2 R1 for the missing behavioral evidence). Plus two stale claims (§ 3.1 dead-vocabulary "still open" but element_localizer wired; § 3.2 BaseException catch but Sprint 169 narrowed it).

Sprint 184 does two things: adds a status note at the top of the paper naming its position status and pointing readers to the technical postmortem + audit + roadmap as authority, AND removes the paper from every doc that cited it as authority (currently roadmap v2). The paper's body stays as-is on disk per hard rule 12; the user's `feedback-no-in-place-edits-new-versions-only` says a rewrite would be a new dated file, not an edit — Sprint 184 does not attempt the rewrite here.

## files modified

- `docs/review/PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` — status note prepended above the existing abstract. Names the round-2 M2 finding, cites the two standing memory rules it violates, names the two stale claims, points to the three doc replacements for authority. Body preserved.
- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` — two edits:
  1. Companion-documents block at the top: paper replaced with postmortem + audit + halt. Sprint 184 attribution inline.
  2. Sources footer: paper removed from the list; Sprint 184 note appended.

## contracts

- Doc-only change.
- The paper is retained on disk per hard rule 12; the CI guard at `scripts/check_deprecated_preserved.sh` does not (yet) cover `docs/review/` deletions, but the status note itself is the audit-trail marker.
- Any new doc that cites the paper reads the status note and follows the pointer to the authoritative docs.

## what Sprint 184 does not do

- Does not rewrite the paper as a technical postmortem. That would be a new dated document (per `feedback-no-in-place-edits-new-versions-only`) titled per its actual content — e.g. `POSTMORTEM-2026-08-12-swebench-arc-divergence.md` — and is a substantial rewrite scope-appropriate for a separate sprint. Not queued yet.
- Does not delete or move the paper. The audit trail is the work.
- Does not touch every historical reference to the paper (the round-2 review itself cites it; the round-1 review does not; no other production doc cites it after roadmap v2's edit lands).

## done

Two files edited. The paper is on disk with an honest status note; no live document treats it as review authority. Round-2 M2's core concern (that the paper was being cited as diagnosis) is closed.
