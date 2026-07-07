# ralph-loop — one-unit-per-session cap (hook-gate) — Design

**Date:** 2026-06-30 · **Status: BUILD** (Erick authorized 2026-06-30; mechanism = **hook-gate**, chosen over a
timeout backstop and over reopening the no-watcher deferral).
**Touches:** [`ralph-loop/SKILL.md`](../../skills/ralph-loop/SKILL.md) (the invariant + mechanism),
[`hooks/guard-one-unit.py`](../../hooks/guard-one-unit.py) (new, the tiny gate), the
driver that realizes the loop (e.g. downstream-repo `tools/loop-driver-pipeline.sh`). Sibling to the act-fence
guard [`guard-loop-vc.py`](../../hooks/guard-loop-vc.py).

## Problem

A headless `claude -p "/<skill>"` worker is a **free-running agent**. The recipe's "one unit per iteration" is
a *soft* instruction, and "iteration" was never bound to "the worker's turn." Observed 2026-06-30: a single
`bulk-content-review` worker stayed in ONE turn for **2h41m and drained ~51 units**, committing each. That
defeats the per-iteration **fresh-context re-read** that is the recipe's entire anti-drift purpose — later
units are judged through a context polluted by the earlier ones (and degrade on plain long-context grounds; the
dominant fix, "over-edit a draft," risks becoming a reflexive pattern rather than a fresh judgment). The
driver's outer loop only re-spawns a fresh context **when the worker exits** — and a worker that internally
loops never exits, so the fresh re-read silently degrades from "per unit" to "per multi-hour batch."

## Constraint from the family — no watcher/daemon

[`ralph-loop-halt-token.md`](ralph-loop-halt-token.md) (reaffirmed in `ralph-loop-green-the-suite.md` and the
session-suspend doc) fixes the family's allowed shape: *"recipes over the built-in `/loop` + `ScheduleWakeup` +
the opt-in seatbelt — a recipe rule (and at most a **tiny guard/hook tweak**), **never** a long-running
watcher/daemon. A design that starts requiring a watcher is a red flag."* So the cap may **not** be a
supervising process that monitors the worker's commits and kills/re-spawns it (the first-draft mechanism — it
was the forbidden shape, and it also killed the worker *at the commit*, pre-empting step 7's stop/surface
logic). It must be a **recipe rule + a tiny hook tweak**.

## Mechanism — a PreToolUse hook gate (the allowed tiny hook tweak)

New PreToolUse hook `guard-one-unit.py`, a sibling of `guard-loop-vc.py`, **opt-in via env the driver sets per
worker spawn** (so interactive sessions and `/loop` wakes — each already a fresh session — are untouched):

- `ONE_UNIT_CAP_SCOPE` — the conventional-commit **scope** the worker's unit commits carry (the driver derives
  it from the skill: `${skill#bulk-}` → `content-review` / `stage-a` / `stage-b` / …).
- `ONE_UNIT_CAP_BASELINE` — the count of scope-matched commits on the branch **at spawn time**.

On **every** tool call: if the env is unset → no-op (allow). Else recompute the scoped commit count — the
number of commits whose **subject** carries `(<scope>)`, via `git log --format=%s HEAD` counted for the
literal `(<scope>)`. **Not** `git rev-list --grep`: that matches the whole commit *message* (subject **and
body**), so a worker whose commit body merely mentions a sibling stage's scope would inflate that stage's
count and cross-trip the parallel guarantee below — subject-only keeps the attribution exact. If the count is
**greater than the baseline**, the session has already landed its one unit → **DENY** (PreToolUse
`permissionDecision="deny"`) with a message telling the worker to end its turn. Denied of any further action,
the worker ends the turn; the driver's existing re-fire then re-spawns a **fresh** process — which *is* the
anti-drift re-read.

**Why scope-matched, not a raw HEAD count.** In the `stage-a ∥ stage-b` parallel stage two workers commit to the
**same branch**; a raw, un-scoped HEAD count would let the *sibling's* commit trip my cap before I commit my
own unit (livelock risk). Disjoint conventional-commit scopes (`feat(stage-a)` vs `feat(stage-b)` vs
`feat(content-review)`) attribute each commit to its own worker → parallel-safe. **Contract for the driver
branch:** the driver computes `ONE_UNIT_CAP_BASELINE` and the hook computes the runtime count with the
**identical** subject-only invocation (`git log --format=%s HEAD`, counting the literal `(<scope>)`); they
**must** match — a divergent invocation (e.g. the driver using `rev-list --grep` while the hook counts
subjects) makes baseline and count disagree the moment any commit body mentions a sibling scope, re-opening
the cross-trip. Both count subjects only.

## Why this is NOT the forbidden watcher

- **No process monitors the worker; nothing is killed or supervised.** The hook is event-driven — it fires on a
  tool call, exactly like `guard-loop-vc.py`, and is stateless between calls (it recomputes from git each time).
  The family explicitly permits "a tiny guard/hook tweak"; this is one.
- **The loop is still the driver's existing re-fire** (re-spawn on the worker's *natural* exit). The hook only
  makes the worker *exit after one unit* (by denying further actions) instead of free-running. It does **not**
  decide done/stop — the anchor's progress gate still does, in the driver, between spawns (`halt-token`'s
  no-self-bless line is untouched).
- **No step-7 timing bug.** The deny fires on the first tool call *after* the unit commit. Step 6 (the commit)
  already landed; step 7 (surface) is model **text**, not a tool, so it runs fine. The worker simply can't
  *start* unit #2.

## Safety

Durability comes from the unit being **committed at step 6** on a durable branch *before* the turn ends — the
recipe's existing property, **not** a signal handler (the first draft wrongly claimed the worker "checkpoints on
signal"; it does not). The hook never acts mid-unit: it denies a *post-commit* tool call, after the commit has
landed. A worker that ignores the deny and keeps trying tools just collects repeated denials → does no work →
ends the turn (bounded waste, never corruption). **Fail-open:** any hook error → allow, never wedge the tool
(same process contract as `guard-loop-vc.py`; we never exit non-zero).

## Preconditions / honest limits

- **One focused commit per unit** (learnings appended *alongside* it, per recipe step 6). A worker that makes a
  separate mid-unit checkpoint commit would trip the cap early — the hardened charter instructs a *single*
  unit+learnings commit, so this holds. If a worker uses an unexpected commit scope, the cap simply **doesn't
  trip** (graceful degradation to today's free-running behavior; the charter's one-unit instruction still
  applies). The cap *tightens* the common case; it never corrupts.
- **String/scope coupling.** Like `guard-loop-vc.py`'s command parsing, this leans on a convention (the unit
  commit's scope). It is a seatbelt for the default path, not a sandbox.

## Rollout

- **internal-toolkit** (this branch): the hook + its test, this doc, the SKILL.md invariant + mechanism rewrite,
  a version bump, a Notes pointer, **and the `scripts/install.sh` wiring** (symlink loop + the matcher-`*`
  settings.json registration block) so the hook deploys through the documented install path; README updated.
- **`~/.claude`** (live, opt-in): `install.sh` symlinks the hook into `~/.claude/hooks/` and registers it in
  `~/.claude/settings.json` `PreToolUse` (matcher `*`), merged in idempotently. Inert until a driver sets the
  env, so zero effect on ordinary interactive work.
- **downstream-repo** (separate branch): `run_iteration` exports `ONE_UNIT_CAP_SCOPE` + `ONE_UNIT_CAP_BASELINE`
  per spawn; the bulk-* charters say "do **one** unit, make a **single** commit, then **STOP** — end your turn."

## Non-goals

Not a supervisor / daemon / watcher; not a kill-and-respawn loop; not a change to the stop/done decision (the
anchor owns it); not active for interactive or `/loop` sessions.
