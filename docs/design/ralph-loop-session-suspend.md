# ralph-loop — session-limit suspend (auto-continuation) — Design

**Date:** 2026-06-24
**Status:** PROPOSED 2026-06-24 (local-only; pending opus pre-merge-review). Prompted by a request to let a
long Ralph loop **safely continue** across a usage-window pause instead of stalling for a human to relaunch.
**Touches:** the anchor-independent core of [`ralph-loop`](../../skills/ralph-loop/SKILL.md) (step 7 + a new
*Session-limit suspend* section + `scripts/suspend_verdict.py`). Reuses `check-usage` (a private sibling skill; its `claude_usage.py` reader is vendored here).
Sibling to [`ralph-loop-learnings-log.md`](ralph-loop-learnings-log.md),
[`ralph-loop-checklist-anchor.md`](ralph-loop-checklist-anchor.md),
[`ralph-loop-green-the-suite.md`](ralph-loop-green-the-suite.md),
[`loop-telos-anchor-deliberation.md`](loop-telos-anchor-deliberation.md), and
[`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md).

## Context / problem

A self-paced Ralph loop can run for many iterations. On the Max plan there are two **rolling-window usage
caps** — a **5-hour** window (resets in minutes-to-hours) and a **7-day** window (resets days away). A long
loop can exhaust the 5h window mid-run; the session is then forced to pause until the window resets. The
shipped recipe says nothing about this, so the loop simply **stalls**, and a human has to notice and relaunch
`/loop /ralph-loop …`. The ask: handle this **safely and automatically**.

## Key realisation: the loop is already resume-safe; the gap is narrow

The whole anti-drift design is also a crash/resume design. Every iteration re-reads the anchor **from disk**
(never trusts in-context state), commits each unit on a durable branch (step 6), and re-reads the append-only
learnings log. So "resume" is already free: relaunching the **verbatim** `/loop` invocation continues from
committed branch state. The missing pieces are therefore small:

1. **A third iteration outcome.** Today step 7 is binary — *continue* (re-fire) or *stop-and-surface*
   (terminal). A usage-cap pause is neither: the loop is **healthy and work remains** (not a stop), but it
   **cannot do a unit now** (not a continue). Name it **suspend**.
2. **A verdict.** Detect the condition and decide suspend-vs-surface from the live windows.
3. **A poll-for-reset wake-up.** Re-fire after the window resets.

## The load-bearing invariant: a suspend is unreachable from a stop

This is the whole safety argument. If `suspend` could fire from a *stop* condition (done, or **stuck** /
no-progress), auto-continuation would silently convert a **spin** into an **indefinite poll** — defeating the
ratchet that is the recipe's entire halting mechanism. So step 7 **evaluates the anchor's stop predicate
first**: a done or stuck loop **still terminates**, unchanged. Only a loop that *would have continued* (made
progress AND work remains) is allowed to consult the session-limit gate and downgrade `continue → suspend`.
Suspend is a strictly-narrower outcome carved out of *continue*, never out of *stop*.

## The policy: 5h auto-resumes, 7d surfaces

Chosen (over "auto-resume both" and "detect & surface only") to balance unattended progress against not
silently parking a branch open for days:

| binding window | reset horizon | outcome |
| --- | --- | --- |
| **5-hour** at/over threshold | minutes–hours | **SUSPEND** — leave a clean tree, poll for the reset, auto-resume |
| **7-day** at/over threshold | days | **SURFACE** — stop-and-surface for a human (note the reset time) |

**7d takes precedence over 5h** when both are over: there is no point suspending for a near-term 5h reset
when the days-away 7d wall will block the loop again immediately. A short 5h gap self-heals; a multi-day 7d
wait should go back to a human rather than hold the loop open.

## Mechanism (recipe, not engine)

Consistent with the skill's "recipe, not an engine" rule, this wires two existing primitives together rather
than building a runner:

- **`check-usage`** already reads the OAuth `oauth/usage` endpoint
  (token stays OS-side, never in context) and returns 5h/7d **utilization %** + **reset times**. A new thin
  helper, [`scripts/suspend_verdict.py`](../../skills/ralph-loop/scripts/suspend_verdict.py), wraps that
  reader plus the fixed policy into one machine-readable verdict + exit code (`PROCEED` 0 / `SUSPEND` 10 /
  `SURFACE` 20), with a **clamped `next_poll_seconds`** for the wake-up.
- **`ScheduleWakeup`** (the `/loop` self-pacing primitive) clamps a delay to ≤3600s. A 5h reset can be
  farther out than one wake-up, so SUSPEND is a **heartbeat poll**: schedule `next_poll_seconds` ahead, and
  each fire re-runs the gate, resuming the loop the first time it returns `PROCEED`.

### Clean-checkpoint requirement

Before pausing, SUSPEND confirms a **clean working tree** (`git status --porcelain` empty). Each unit is
already committed at step 6, so this is normally already true; making it explicit guarantees a
kill-at-the-limit leaves **no half-applied edit** for a resume to double-apply. (Even a mid-unit kill is
recoverable — the next pass re-reads the anchor, sees the unit not done, and redoes it idempotently — but the
clean-tree guarantee removes the double-apply hazard entirely.)

### Fail-open (deliberately opposite to the YOLO checks)

If usage can't be read (endpoint down, missing reader), the verdict is **`PROCEED`** (exit 1, with a
warning). A usage blip must never wedge a healthy loop into an indefinite **false** suspend. The worst case is
one iteration that tries and is throttled — recoverable on the next re-read — and a real hard cap still
surfaces as an actual harness pause. This is the **inverse** of `check_oracle_frozen.py` /
`check_suite_frozen.py`, which **fail-deny**: those gate an irreversible *act* (a YOLO integration), so
ambiguity must refuse; this gate only chooses *reschedule vs. surface*, where the safe default on ambiguity is
to keep working.

## What is unchanged (the act-fence)

A suspend **never** merges, pushes, or marks work done; `CLAUDE_LOOP_GUARD` stays armed across the pause.
Auto-continuation adds unattended **runtime**, not a new **act** — so it does not weaken the
stop-and-surface posture (it does raise the value of keeping the guard armed for a longer-running loop). The
session-limit gate is **orthogonal to the YOLO posture**: it runs before any YOLO per-unit gate and changes
nothing about it. The no-self-bless split, the one-unit-per-iteration rule, and re-read-from-disk are all
untouched.

## Alternatives considered

- **Auto-resume both 5h and 7d.** Rejected as the default: a 7d wait can hold a loop branch open for days
  with no human in the loop. (A future `--max-suspend-hours` knob could opt into it; not built.)
- **Detect & surface only (no auto-resume).** The most conservative option — make the stall graceful and
  resumable, but require a human to relaunch. Rejected as the default because the explicit ask was *auto*-
  continuation; the 5h auto / 7d surface split keeps the short, self-healing case unattended while still
  surfacing the long one.
- **A bespoke loop-runner/daemon that watches usage.** Rejected — violates "recipe, not an engine"; the
  `ScheduleWakeup` heartbeat + `check-usage` reader already cover it with no new long-lived process.

## Honest limits

- The threshold (default 90%) is a heuristic on **headroom**, not a guarantee a unit fits — a single large
  unit could still trip a hard cap mid-work. That is recoverable (clean checkpoint + idempotent re-read), and
  the one-small-unit-per-iteration rule keeps the exposure small.
- Like the rest of the recipe, the loop's *obedience* to the verdict is recipe-level; the guard hook cannot
  enforce "you must suspend here." But suspend grants **no act**, so a skipped suspend is at worst a stall,
  not an unsafe action.
- The 7d check reads only the **aggregate** `seven_day` window, not the per-model `seven_day_opus` /
  `seven_day_sonnet` windows the endpoint also exposes. A loop on one model could exhaust its per-model 7d cap
  while the aggregate still shows headroom, so the gate returns `PROCEED` and the real cap is caught only by
  the actual harness pause. This is **intentionally out of scope** and degrades to the documented worst case
  (one throttled iteration, then the harness pause — the fail-open net), not an unsafe act.
