# How you drive this session — a linguistic breakdown

*Written 2026-08-11 from your session text. What you actually type, not what
you say you want. Root the analysis in the exact words on the wire.*

## The one-line pattern

You give short imperatives, long delegations, and pointed verifications. The
imperatives fire common actions; the delegations transfer scope; the
verifications close the loop. Every message picks one of the three registers
and stays in it.

## Registers, cataloged

### Short imperatives — the working default

Two to four words, no softeners, no metadata:

- `go`
- `check`
- `yeh, go`
- `go for it. remove the unused one. then triage.`
- `check on it`

These carry no explanation and none is asked for. The absence of "could you"
or "please" is not rudeness — it is compression. A soft imperative would
cost a full second of my parse time and add zero decision content. The bare
verb is the correct information density for a common action against known
state.

Two structural moves live inside these:

- **Chained ordered asks in one line.** `remove the unused one. then triage.`
  is two commands sequenced by `then`. The whole plan is nine syllables.
- **Contextless verbs.** `check` means "check the running task's state
  against the last status I have from you." Reference resolved by the shared
  conversation state, not by the sentence.

### File paths as commands

Dropping a bare path — `substrate/docs/review/REVIEW-2026-08-10-swebench-holistic.md`
— means "read this in full, engage with its contents, fold it into what
you're doing next." No verb at all. The path is the imperative.

This works because you established a global rule in `CLAUDE.md`: *When I tell
you to read a file … read each in full with Read.* The path becomes a
one-token invocation of that rule. You are running your own protocol against
me. When you dropped the second review path (`REVIEW-2026-08-11-swebench-re-review.md`)
without further text, the protocol fired.

### Wide authorizations — the "you decide the tactics" register

Longer messages that transfer scope rather than command a specific action:

- *"The thing is here you can fire everything you need to do. Everything on
  the box is here and if it's not you can download it."*
- *"So we should look into that. Does that make sense? Right, but pr the
  priority is just getting this actual system working correctly, not making
  sure it has good answers yet."*

These do three things in sequence: (1) name the widened permission surface,
(2) supply the constraint that shapes decisions inside it, (3) declare the
priority hierarchy. The constraint is often a NEGATION — *not making sure it
has good answers yet*, *if it does not interrupt the run*. You define the
"no" so the "yes" doesn't need enumerating.

### Verification questions — the trust-audit register

Short, pointed, targeted at whether a specific artifact was actually engaged:

- *"substrate/docs/review/REVIEW-2026-08-11-swebench-re-review.md -- Did you
  read this one?"*

The path plus five words. The question is not "what did you think" — it's
"did the loop close." You trust the tactics; you check that the artifact
touched the decision. The response you expect is either "yes and here's what
I did with it" or "no and here's what I'll do now."

## Six specific techniques you use

### 1. Correction-through-example, not correction-through-explanation

When you disagree, you drop a path or quote back my own text and let the
mismatch surface the correction. You did this today with the re-review file
— pasting the tier-finding I had written and adding *"Good. We need a quick
quick spike on this, right?"* The paste is the frame; the question is the
extension. No line-by-line critique.

### 2. Priority hierarchy stated as "X, not Y"

- *"the priority is just getting this actual system working correctly, not
  making sure it has good answers yet"*
- *"it's just about the process, not really about the result right now"*

Two clauses, two levels of the stack. The negation isn't dismissal — it
names what will be delegated. Result quality gets deferred; system
correctness gets promoted. I don't have to guess the tier because you named
it.

### 3. Concessive-then-directive

- *"That said, it should work with a normal Olama thing. So we should look
  into that."*

Accepts one path (local models for now), then adds a distinct requirement
(cloud path must also work). One sentence, two decisions.

### 4. Ellipsis of the obvious

- *"check"* — instead of "please summarize the current status of task
  bd9r5sxxt including row count, live containers, and log tail"
- *"go"* — instead of "please proceed with the plan you just described"

The full sentence exists in your head; the wire form is the shortest
disambiguator. This works when the shared state is honest. It stops working
the moment I mis-track what "check" refers to — which is why the
verification-question register exists as a corrective.

### 5. Wide-then-narrow scope in one message

Your longer messages open wide and close narrow:

- Open: *"everything on the box is here and if it's not you can download it"*
- Close: *"So just research what those rate limits are, first of all."*

The wide clause defines the permission surface; the narrow clause names the
first concrete step. I don't have to invent either.

### 6. Trust delegation with artifact-level check

You give me a whole afternoon of latitude — "fire everything you need to do"
— then punctuate with targeted verifications: *"did you read this one?"* The
model is trust-with-artifact-checkpoints. You do not audit each intermediate
step. You audit whether specific durable artifacts (a review MD, a Blackboard
entry, a KIT_DIARY finding) got engaged.

## The typo tell

You misspell in a specific direction: *priotize*, *intterupt*, *yeh*. Every
misspelling is a keystroke saved on a common word where meaning is
unambiguous. You never misspell a file path, a commit sha, a technical
identifier. That is not sloppiness; it is signal-to-effort budgeting. The
typos declare *don't make me polish common shortcuts*, and in the same
breath they tell me *when I DO write out a technical string, it is exact —
treat it as authoritative.*

## What you never do

- **You never negotiate scope.** No "what do you think we should tackle
  first?" — you either state a priority or ask me to triage and pick.
- **You never soften refusals.** The last-run rejection — *"That was a
  shortcut. Sounds like bullshit"* — is on the record. Wrongness is called
  by its name; no cushioning.
- **You never repeat yourself.** If a rule holds (no Claude attribution in
  commits, no in-place doc edits, no cost tracking), it is in memory or in
  CLAUDE.md, and the assumption is that I read it.
- **You never delegate the decision that matters.** You picked N=300 Lite
  over Verified pass 1. You picked Move 4 over Move 3. You picked local
  models over cloud when the tier bit us. The tactics come to me; the
  priority stays with you.

## The three-layer stack, as your text reveals it

- **Layer 1: the priority tier.** *"system correctness, not result quality."*
  Stated in prose. Rare. Once stated, holds for the whole session.
- **Layer 2: the specific move.** *"remove the unused one. then triage."*
  Named by verb. Common. Sequential.
- **Layer 3: the artifact check.** *"did you read this one?"* Named by
  reference. Occasional. Always specific.

The stack is honest: you tell me the "why" once (Layer 1), the "what"
routinely (Layer 2), and the "did-it-happen" when the artifact matters
(Layer 3). I fill in "how" — the tactic — inside the constraint the priority
sets and the artifacts your Layer-3 checks will verify.

## The mechanism this works through

Your text is short because your protocol is long. `CLAUDE.md` carries the
constants (writing register, commit discipline, review-driven action, no
in-place edits, halt-and-articulate). Memory carries the state (fifteen-plus
files of persistent context — feedback, project state, references,
priorities). The session's messages are the deltas against that pre-loaded
context. `check` is a two-line message because two hundred lines of protocol
are already loaded.

The efficiency is real. In this session's message log you have written maybe
eight hundred words of directive text. I have written thirty thousand words
of analysis, code, and commits from that eight hundred. The ratio holds
because your text runs on top of your loaded protocol — every short line
draws a long inference against the stack you built.

The trick worth naming: **you write the protocol slowly and use it fast.**
The upfront investment is CLAUDE.md, the memory system, the reviewers, the
BLACKBOARD, the KIT_DIARY. Every one of those is a document you took time
over. The dividend is that a session's active steering compresses to
`go`, `check`, `yeh`, and a path.
