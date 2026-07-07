# ralph-loop — learnings log — Design

**Date:** 2026-06-23
**Status:** PROPOSED 2026-06-23 (local-only; pending opus pre-merge-review). Prompted by a re-examination of
`ralph-loop` against Matt Pocock's "Ralph Wiggum" walkthrough (YouTube `_IK18goX4X8`), which surfaces
Anthropic's "effective harnesses for long-running agents" recommendation of an append-only progress log.
**Touches:** the anchor-independent core of [`ralph-loop`](../../skills/ralph-loop/SKILL.md). Sibling to
[`ralph-loop-checklist-anchor.md`](ralph-loop-checklist-anchor.md),
[`ralph-loop-green-the-suite.md`](ralph-loop-green-the-suite.md),
[`loop-telos-anchor-deliberation.md`](loop-telos-anchor-deliberation.md), and
[`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md).

## Context / problem

`ralph-loop` is the shipped pluggable-anchor recipe for a self-paced "Ralph Wiggum" `/loop`: one invocation =
one iteration (re-read a durable, out-of-context spec from disk → advance one unit → commit → stop-and-surface,
or let `/loop` re-fire). It is dogmatic — correctly — that **remembered progress is untrusted**: the done-signal
must be recomputed from disk every pass (the anchor's progress signal), and the loop may never confirm its own
discharge (the no-self-bless split). That dogma defends the **stop/discharge** decision.

It leaves a different need unmet. A fresh context each iteration has **no memory of what was already tried and
failed**. So the loop can rediscover the same dead end every pass: re-attempt a flaky approach, re-investigate
a library that doesn't work, re-derive a decision already reasoned through and discarded. Git commit messages
record *what changed*, not *what was tried that didn't work and why* — and the latter is the high-value,
non-reconstructible part.

Both Matt Pocock's walkthrough and the Anthropic harness guidance it cites solve this with an **append-only,
free-text `progress.txt`** the agent writes its learnings into each pass and re-reads at the start of the next —
"a note for the next person working in your codebase." Matt is explicit that it must be **append**, not update
("if you tell it to update, it rewrites the whole file"), and that the agent re-reads it plus git history for
cross-iteration context.

This is **fully consistent with our anti-drift principle**, because it is *also re-read from disk* — it is
durable on-disk memory, not trusted in-context state. The distinction this design draws is the load-bearing
one:

- **Trusting remembered progress to decide stop/done** — forbidden, and unchanged. This is how loops fake
  completion.
- **Reading an on-disk log of what was already tried** — *adopted here*. It informs *how* to do the next unit;
  it never decides *whether* work is complete.

## Goals & non-goals

**Goals**
- An **append-only learnings log** in the anchor-independent core: re-read at the start of each iteration
  (alongside the spec re-read), appended to at the end (alongside the commit). One file per loop, on disk in
  the repo.
- Make it **memory, never an oracle**: explicit invariant that nothing in the log gates a stop, a discharge,
  or a YOLO act. The stop signal stays the anchor's progress signal; discharge stays the no-self-bless split.
- Make it **append-only** in instruction (mirroring Matt's update-vs-append point) so the loop accumulates
  rather than rewrites — each entry is dated and scoped to one iteration.
- A **YOLO carve-out**: the log is loop-mutable by design, so it is explicitly *outside* every frozen-oracle
  immutability surface (`check_oracle_frozen.py` / `check_suite_frozen.py`) — writing to it never trips, and
  it is never part of, an immutability check.

**Non-goals**
- *Not* a new anchor, a new skill, or a new script. This is an addition to the five-beat core, shared by all
  three anchors. No parser, no log-rotation engine (KISS / "don't build a loop runner").
- *Not* a second progress signal. The unchecked-count / failing-test / claim-state ratchets are untouched; the
  log is orthogonal to them. A line in the log saying "done" means nothing to the stop predicate.
- *Not* a discharge surface. A learning is a note, never evidence. The no-self-bless split is unchanged: a
  learning the loop wrote can never confirm the loop's own work.
- *Not* a YOLO-eligible artifact. It cannot be frozen (the loop is meant to write it), so it can never be the
  thing a `verify:`/`verified-by:` oracle checks. It lives strictly outside the gate.
- *Not* mandatory state. The recipe stays stateless on the **decision**; the log is advisory enrichment. A
  loop with an empty/absent log behaves exactly as today.

## Approach

### The artifact

A single append-only markdown file per loop, default `LOOP_LEARNINGS.md` at the repo root
(`--learnings <path>` to override). Each iteration appends one dated, scoped entry:

```markdown
## 2026-06-23 — iteration on <unit id / short name>
- Tried X; failed because <reason> — don't retry without <precondition>.
- <library/approach> doesn't work here: <one-line why>.
- Decided <decision> over <alternative> because <reason>; revisit if <condition>.
- Gotcha for next pass: <thing the fresh context won't know>.
```

It is *learnings*, not a status mirror — do not restate the spec or the ratchet count (those are re-read from
their own sources). It captures only what a fresh context would otherwise have to rediscover.

### Wiring into the five beats

The two core beats gain a companion read/write; the decision beats are untouched.

- **Step 2 (re-read the spec):** also re-read the learnings log from disk. It is *context for how to do the
  next unit*, never an input to the stop predicate. Treat it as advice from a prior self that may be stale —
  it does not override what the spec/code say now.
- **Step 6 (commit):** before committing, **append** (never rewrite) one dated entry recording this
  iteration's learnings — dead ends, gotchas, decisions-and-why. Commit it alongside the unit (it is part of
  the focused commit, like the PRD/box tick is). If the iteration learned nothing worth carrying, append
  nothing.

Everything else — the spec re-read as the source of truth, one-unit-per-iteration, the ratchet stop, the
no-self-bless discharge, stop-and-surface — is unchanged.

### Why this doesn't reintroduce the drift it was built to kill

The hazard `ralph-loop` exists to prevent is a loop that *trusts a remembered state to declare itself done*.
The learnings log is firewalled from that hazard by construction:

1. It feeds only the **how**, not the **whether**. The stop predicate and discharge routing never read it.
2. It is **re-read from disk** like the spec — it is not in-context memory carried across the boundary.
3. It is **append-only** — the loop can add a wrong note but cannot quietly erase the record (and a wrong note
   can mislead the *approach*, costing an iteration, but never corrupt the *done-signal*, which is recomputed
   independently).

The residual risk is a *bad* learning misleading a later pass into a worse approach — lost progress on one
iteration, recoverable by re-firing. That is the same failure class as a bad commit, not a new corruption
surface (cf. the halt-token analysis: lost progress, not corruption).

### YOLO interaction

Under `=yolo`, the log changes nothing about the gate:
- It is **never** a frozen surface. `check_oracle_frozen.py` / `check_suite_frozen.py` check the *oracle* /
  *test surface*; the learnings file is neither and must not be listed as one. The loop writing to it on a
  YOLO pass does not affect the immutability verdict.
- It is **never** the thing a `verify:`/`verified-by:` oracle asserts on. A learning is not evidence.

So the YOLO act remains backed solely by the frozen green oracle; the log is just advisory context the loop
read on its way there.

## Key decisions

- **One file, append-only, repo root, overridable path** — mirrors Matt's `progress.txt` and the checklist
  anchor's `--plan` override. No per-iteration files, no rotation.
- **Memory ≠ oracle is the whole point** — stated as an invariant in the skill, not left implicit. This is the
  line that keeps the addition consistent with the no-self-bless dogma.
- **Advisory, not mandatory** — the recipe stays decision-stateless. The log enriches; it never gates. A loop
  ignoring it is a degraded loop, not a broken one.
- **No script** — appending a markdown section is a one-liner the model already does for the checklist tick;
  building a logging engine would violate "this is a recipe, not an engine."

## Alternatives considered

- **Do nothing (status quo).** Rejected: the rediscovered-dead-end cost is real and the fix is cheap and
  invariant-safe. The reason we hadn't adopted it was an over-broad reading of "remembered state is untrusted"
  — which is about the *done-signal*, not about *how-to* context.
- **Put learnings in git commit messages only.** Rejected: commit messages record what changed, are awkward to
  scan as accumulated cross-iteration memory, and bury the "what didn't work" under "what did." A dedicated
  append-only log is what both Matt and the Anthropic guidance land on.
- **Let it also carry a status/done summary.** Rejected hard: that is exactly the forgeable self-blessed
  done-signal the recipe is built to exclude. The log is learnings only; status is recomputed from the anchor.
- **A `progress.txt`-style free-text blob with no structure.** Partially adopted: free-text is the point, but
  we date and scope each entry so a fresh context can tell stale notes from fresh and attribute them to a unit.

## Plan

1. Add an **"Append-only learnings log"** subsection to the anchor-independent core of `ralph-loop/SKILL.md`,
   between the loop-body beats and the discharge section, stating: the artifact, the read (step 2) and append
   (step 6) wiring, and the **memory-not-oracle** invariant.
2. Add the read/append companions to **steps 2 and 6** of "The loop body."
3. Add the **YOLO carve-out** sentence to the YOLO section's "Unchanged under YOLO" note (log is never a frozen
   surface / never evidence).
4. Add `--learnings <path>` to the invocation examples (default `LOOP_LEARNINGS.md`).
5. Cross-reference this design doc from the Notes section.
6. `scripts/validate.py` green; **re-check the `ralph-loop` description length** (it is near the cap — the new
   feature should be documented in the body, not crammed into `description`).
7. Bump `metadata.version` (0.2.0 → 0.3.0; additive feature).
8. Out-of-loop **opus `/pre-merge-review`**, then `--no-ff` merge, local-only (no push — standing rule).

## Falsifier (ATDD-style headline)

The addition is correct iff: (a) a loop re-reads the log at step 2 and appends (never rewrites) at step 6;
(b) no stop predicate, discharge route, or YOLO gate reads the log; (c) the log is never listed as a frozen
oracle/suite surface. (a) is a prompt-instruction property (reviewed, not unit-testable); (b)/(c) are
guaranteed structurally because the existing ratchet/discharge/freeze machinery is untouched and the log is
introduced as read-only-advisory input — the review confirms no beat was rewired to consult it for a decision.
