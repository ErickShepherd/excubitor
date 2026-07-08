---
name: ralph-loop
description: >-
  Drive a self-paced `/loop` (Ralph-Wiggum style) against any repo, anchored on a durable spec re-read from
  disk every iteration so a fresh context can't drift. The anchor is PLUGGABLE: (a) telos — a `docs/telos/`
  claim ledger; (b) green-the-suite — a failing test set, loop until it exits 0; (c) checklist — a plan file
  (`- [ ]` items), loop until none remain. Use when asked to run a loop / Ralph loop / autonomous build
  against a repo, to "keep working until the suite is green", "autonomously make the tests pass", "work
  through the plan/TODO", or "keep working through the telos". One invocation = ONE iteration (re-read the
  spec, advance one unit, commit, surface) so `/loop` re-fires it with a fresh anchor each wake-up. By default
  stop-and-surface, never stop-and-act: it never merges, deletes a branch, or marks its own work done. An
  opt-in `--yolo` posture (under `CLAUDE_LOOP_GUARD=yolo`) lets it self-discharge and integrate ONLY work
  gated by a frozen, loop-immutable oracle. Generic; one per repo.
allowed-tools: [Read, Grep, Glob, Bash, Edit, Write, Skill]
metadata:
  version: 0.5.2
---

# ralph-loop

A **recipe**, not an engine. One invocation runs **one iteration** of a self-paced loop over a repo: re-read
a durable **anchor** from disk as the spec, advance the single next unit of work, commit on the loop's
branch, then either let `/loop` re-fire (more work remains) or **stop-and-surface** (done / stuck). There is
no bespoke halting machinery — the **anchor's own progress signal** is the stop signal, and the
`guard-loop-vc.py` seatbelt makes the act-fence mechanical. This skill just wires them into a loop.

The anchor is **pluggable**. The loop discipline below is **anchor-independent**; only two slots vary:

| slot | **telos** anchor | **green-the-suite** anchor | **checklist** anchor |
| --- | --- | --- | --- |
| **spec source** | `docs/telos/*.md` ledger (`audit-telos`) | a failing **suite command** (e.g. `pytest -q`) | a **plan file** (`- [ ]`/`- [x]` items) |
| **progress signal** | claim states + coverage | failing-test set / exit code | count of unchecked items |

A telos ledger is the *deep* anchor (claims + contracts + witnesses); a failing suite is a *thin-but-durable*
anchor (an exit code + a failing-test list re-derived from disk); a checklist is the *broadest* anchor (a
plan a human can write in any repo, no ledger/suite required) but the **prose/judgment** one — the loop ticks
its own boxes, so a checked box is a self-authored claim, not an oracle. All three kill drift the same way —
re-reading an out-of-context spec every pass — they differ in the depth of what is anchored and in whether the
done-signal is forgeable by the loop. Design + rationale: `docs/design/ralph-loop-green-the-suite.md`,
`docs/design/ralph-loop-checklist-anchor.md`, and `docs/design/loop-telos-anchor-deliberation.md`. The opt-in
**`--yolo`** posture is the one principled exception to never-act; its rationale is
`docs/design/loop-yolo-verifiable-autonomy.md`.

## When to use

- "Run a loop / Ralph loop against this repo", "autonomously build / grind on this", "keep going until X".
- **telos anchor:** "keep working through the telos", "discharge the undischarged claims". Requires the repo
  to have a `docs/telos/` ledger (`/telos bootstrap` first if it has none).
- **green-the-suite anchor:** "make the failing suite pass", "loop until the tests are green", on **any** repo
  with a test runner — no telos required.
- **checklist anchor:** "work through the plan", "grind through `IMPLEMENTATION_PLAN.md`", "keep going until
  the TODO is empty" — on **any** repo with a plan/checklist file. The canonical "Ralph Wiggum" form.

## Invocation (do this once, at session launch)

The seatbelt is read from the **harness process env**, so it must be set *before* the session starts —
**not** via `export` in a Bash tool call (that never reaches the hook):

```bash
CLAUDE_LOOP_GUARD=1 claude          # launch with the loop seatbelt armed (conservative, stop-and-surface)
CLAUDE_LOOP_GUARD=yolo claude       # verifiable-autonomy posture (only with a frozen oracle — see YOLO)
```

or persist it for a repo in `<repo>/.claude/settings.local.json` (`{ "env": { "CLAUDE_LOOP_GUARD": "1" } }`).

Then point `/loop` (self-paced — **no interval**, so the model paces itself) at this skill, **naming the
anchor**:

```
/loop /ralph-loop --anchor telos <repo>
/loop /ralph-loop --anchor green-the-suite --repo <repo> --suite "<suite command>" \
      --test-path tests/ --test-path conftest.py --test-path pytest.ini
/loop /ralph-loop --anchor checklist --repo <repo> [--plan IMPLEMENTATION_PLAN.md]
```

Each form may also take `--learnings <path>` (default `LOOP_LEARNINGS.md` at the repo root) — the append-only
learnings log (see *Append-only learnings log*). The **green-the-suite** form may also take `--decisions
<path>` (default `LOOP_DECISIONS.md`) — the lazily-created fork sidecar (see *Decision handling* → RECORD).
`/loop` re-fires the invocation verbatim each wake-up, so the
anchor arguments are the persisted out-of-context spec. **Confirm the guard is armed** at the top of the first
iteration
(`echo "$CLAUDE_LOOP_GUARD"` → `1` or `yolo`); if empty, stop and tell the user to relaunch — never run an
unguarded loop.

## The loop body (one iteration)

Let `R` = the repo path. The five beats are the same for every anchor; the **spec** and **progress** beats
dispatch to the anchor's section below.

> **The load-bearing invariant: one invocation does ONE unit, then the turn ends.** "One iteration" is one
> worker turn *and* one unit of work — they must coincide (the file's other "one unit per iteration" phrasings
> mean exactly this coincident turn≡unit). The **loop** is realized by the **re-fire** (the `/loop` wake, or a
> driver re-spawning a fresh `claude -p` worker), and the re-fire is what supplies the **fresh context** that
> re-reads the spec from disk at beat 2 — the anti-drift property that is the recipe's entire purpose. A worker
> that stays in one turn and drains a *second* unit never gets that fresh re-read: it judges later units through
> a context polluted by the earlier ones, accumulating exactly the drift the loop exists to kill (and, on a long
> enough turn, degrading on plain long-context grounds). So: **do one unit, commit, end the turn — never begin
> another unit in the same session.** This binds beats 3–7; step 7's "continue" means *end this turn and let the
> re-fire start a fresh one*, never *keep going here*.
>
> **A headless / `claude -p`-driven realization must enforce this MECHANICALLY, not merely instruct it** — a
> free-running agent will not reliably stop on a soft "do one then stop" (it batch-drains a whole stage in a
> single multi-hour turn, silently defeating the fresh re-read). Enforce it with the family's allowed **tiny
> hook tweak**, **not** a supervising watcher (a process that monitors the worker and kills/re-spawns it is the
> daemon shape [`ralph-loop-halt-token.md`](../../docs/design/ralph-loop-halt-token.md) forbids): a
> **PreToolUse gate** (`guard-one-unit.py`, sibling of `guard-loop-vc.py`) that the driver arms per spawn (env
> `ONE_UNIT_CAP_SCOPE` + `ONE_UNIT_CAP_BASELINE`) and that **denies every tool call once the worker's one
> unit-advancing commit has landed** — so the worker, unable to act, ends its turn and the driver's *existing*
> re-fire spawns the fresh context. The deny fires on the first tool call *after* the commit, so step 6's commit
> completes and the capped worker's step-7 **stop-and-surface is model text** (no tools) — only unit #2 is
> prevented. (Step 7's *tool* paths — the suspend-gate's `suspend_verdict.py`/`ScheduleWakeup`, a SURFACE
> `AskUserQuestion` — belong to the **driver between spawns** or the interactive `/loop`, never the capped
> headless worker, so the cap does not eat them.) **Safety** is that the
> unit is **committed before the turn ends** on a durable branch (the recipe's existing property — *not* a
> signal handler; nothing is killed mid-unit), so a worker that ignores the deny merely collects denials and
> stops: bounded waste, never corruption. Scope-match the commit count (not a raw `HEAD` count) so a
> two-worker parallel stage doesn't cross-trip. Design + threat analysis:
> [`ralph-loop-one-unit-per-session.md`](../../docs/design/ralph-loop-one-unit-per-session.md). (This
> per-session cap is **re-fire harness, not bespoke halting** — the *stop* decision still belongs to the
> anchor's progress signal, per *Notes*; the cap only bounds how much one worker does *before* that signal is
> re-read.)

1. **Preconditions (fail fast).** Confirm `CLAUDE_LOOP_GUARD` is set. Confirm you are on a dedicated loop
   branch, **not** the default branch — `git -C "$R" switch -c loop/<anchor>-<date>` if needed. The seatbelt
   blocks merge/push/branch-delete/reset regardless; this is belt-and-suspenders.

2. **Re-read the spec** for the chosen anchor (its section below) — from disk, every iteration; never trust a
   remembered state from a prior pass. This re-read is the whole point: the anchor is the out-of-context spec
   that kills drift. **Also re-read the learnings log** (see *Append-only learnings log*) for *how-to* context
   — what a prior pass already tried and ruled out. It informs the approach only; it is **never** an input to
   the stop predicate or discharge, and the spec/code override it where they disagree. **Decision drift
   tripwire:** while re-reading, scan committed code for a fork-shaped choice (a library import, a sync/async
   signature) with no matching RED item — flag DRIFTED and surface (see *Decision handling* → DETECT).

3. **Pick the single next unit of work** — exactly one, per the anchor's priority rule. One unit per
   iteration keeps each commit focused and each re-read honest. **Then DETECT a fork** (see *Decision
   handling*): restate the intended choice as a one-line claim and grep the spec; if the spec
   under-determines it, this unit becomes **reify-as-fork** (RECORD), not implement.

4. **Do that one unit's work** on the loop branch. **Search before you write** — grep the codebase for an
   existing implementation, helper, or pattern *before* adding one (a fresh context's default failure is to
   *invent* a parallel version of code that already exists). Stay within the unit — do not opportunistically
   refactor unrelated surface (that defeats the focused commit and the stop signal). **If step 3 reified a
   fork, the unit's work is RECORD** (mint the RED item — `UNMET` claim / `- [ ] DECIDE:` item), not code.

5. **Discharge — route by work type (see *Discharge*). Do NOT self-bless.** **If the unit is a fork, route
   through CLASSIFY instead** (see *Decision handling*): oracle-elimination for an anticipated fork, else the
   reversibility rubric decides whether to defer — the loop never *chooses* a fork on judgment.

6. **Commit** one focused unit on the loop branch (`/conventional-commits` shape). Before committing,
   **append** (never rewrite) one dated entry to the learnings log capturing this iteration's dead ends,
   gotchas, and decisions-and-why; commit it alongside the unit. Never hand-edit a claim's `state:`/the test to
   fake the signal — the re-read recomputes it and will contradict you.

7. **Decide: continue, stop, or suspend.** Evaluate the anchor's **stop predicate first** — done/stuck is
   terminal and is *never* reachable from a suspend (see *Session-limit suspend*). **An open fork keeps the
   stop predicate from reaching "done":** a RED item (an `UNMET` claim / open `- [ ] DECIDE:`) blocks the
   anchor's done-predicate, so a run with open forks stops-and-surfaces with the run-end batched
   `AskUserQuestion` (see *Decision handling* → SURFACE) — it can never silently finish.
   - **No work remains, OR this iteration could not advance ("no progress")** → **stop-and-surface**. Do not
     reschedule a spinning loop.
   - **Progress made this iteration AND work remains** → the loop *would* continue. Now consult the
     **session-limit gate** (below): on `PROCEED`, end the iteration and `/loop` re-fires; on `SUSPEND`,
     pause and poll for the 5h reset; on `SURFACE`, stop-and-surface (7d cap).

## Append-only learnings log

A fresh context each iteration has **no memory of what was already tried and failed**, so without help the loop
re-discovers the same dead ends (re-attempts a flaky approach, re-investigates a library that doesn't work,
re-derives a discarded decision). Git messages record *what changed*, not *what was tried that didn't work*.
The fix — recommended by Anthropic's long-running-agent harness guidance — is one **append-only, free-text**
log per loop (default `LOOP_LEARNINGS.md` at the repo root; `--learnings <path>` to override) that the loop
re-reads at step 2 and appends to at step 6. It is durable on-disk memory, so it is *also re-read from disk* —
fully consistent with the anti-drift rule, which is about not trusting *in-context* state across the boundary.

**The load-bearing invariant: the log is memory, never an oracle.** It feeds the *how* (the approach for the
next unit), never the *whether* (whether work is done). **No stop predicate, no discharge route, and no YOLO
gate ever reads it.** A line in the log saying "done" means nothing — the stop signal is recomputed from the
anchor's progress signal, and discharge stays the no-self-bless split. This firewall is what keeps the log from
re-introducing the self-blessed done-signal the recipe exists to exclude.

- **Append, never update.** Add a dated, unit-scoped entry each pass; do not rewrite the file (rewriting loses
  the accumulated record and tempts a status-mirror). If a pass learned nothing worth carrying, append nothing.
- **Learnings only, not a status mirror.** Don't restate the spec or the ratchet count (those are re-read from
  their own sources). Capture only what a fresh context would otherwise have to rediscover — dead ends with the
  reason, gotchas, decisions-and-why with a revisit condition.
- **Advisory, not authoritative.** Treat it as advice from a prior self that may be stale; the spec and the
  code override it. A loop with an empty/absent log behaves exactly as a loop without this feature.
- **Worst case is lost progress, not corruption.** A *wrong* note can mislead one iteration's approach
  (recoverable by re-firing); it can never corrupt the done-signal, which is computed independently.

## Reduce invention: searchable spec linkage

The learnings log fights *re-trying* a dead end; this fights *re-inventing* existing code. A fresh context
each iteration only knows what it can re-derive from disk, so the cheapest lever on output quality is making
the **search tool** find the right context fast — the more it finds, the less it invents. Two complementary
habits, both optional but high-leverage:

- **Keep the spec index search-friendly, not just human-readable.** If the repo has a spec/plan index
  (a `specs/README.md`, a doc map, the plan file's headings), enrich each entry with the **alternate terms a
  search would use** (e.g. an "authn / login / session / credentials" entry for the auth spec). This is a
  recall aid for grep, not prose for a person — it raises the hit-rate of the loop's own searches against its
  own codebase.
- **Link plan items to where the work lands.** A plan/checklist item should **cite the spec section and the
  source file(s)** it touches (down to a line range / hunk when you know it), so step 4 starts anchored to
  real locations instead of a blank-page guess. This generalizes the checklist anchor's "reconcile
  plan-vs-code" rule from *don't redo done work* to *don't reinvent existing code*.

Both are ordinary repo hygiene, not loop machinery — there is no new artifact the loop must maintain and no
new stop/discharge surface (this is search-recall, never a done-signal). A loop without them just searches
harder by hand.

## Anchor: telos

- **Spec source (step 2):** read `R/docs/telos/*.md` and run `/audit-telos <repo>`. Use its per-claim output
  (`state`, `needs_judgment`, `tier`, coverage, orphans) as the anchor + progress signal.
- **Pick (step 3):** exactly one claim, in priority order — `DRIFTED` (a regression beats new work) >
  `UNMET` / `discharged-by: TODO` / `discharged-by: none` > a claim whose `verified-by:` witness is failing.
  Ties → lowest `TELOS-NNN`.
- **Do (step 4):** write/fix the code so the `discharged-by` symbol fulfils the `contract`.
- **Stop predicate (step 7):** no actionable claim remains (coverage "complete" is a *trigger* to
  stop-and-surface, not a license to halt-and-merge), or an iteration made no progress.
- **Fork (decision handling):** RECORD an under-determined fork as a new claim with `discharged-by: none` →
  `UNMET` (the decision criterion in `contract:`); the `UNMET` blocks the stop predicate until it is resolved.
  Up-front gate (`## Key decisions`) **required** here. CLASSIFY per *Decision handling*.

> The **`motive` fallback** (a free-text motive with no discharge criteria) has no oracle and no falsifiable
> contract — never build a loop's "done" on a motive. If the repo only has a motive and no claims, stop and
> ask for `/telos` claims first.

## Anchor: green-the-suite

- **Spec source (step 2):** run the `--suite` command in `R` from a clean state and read its **failing-test
  set** (and exit code). This is re-derived from disk every iteration — never carry a remembered failure list.
  - **Guard against a no-op anchor:** if the suite is **already green** at the very first iteration, there is
    nothing to do — **stop-and-surface** ("suite green at launch — nothing to loop / verify the suite is
    real"), do not declare instant victory.
- **Pick (step 3):** one failing test, or one cluster of failures sharing a single root cause. Lowest-level /
  most-depended-on failure first when they're independent.
- **Do (step 4):** fix the **production** code so that test passes. **Do not edit the tests** — a suite the
  loop rewrites is a suite the loop can fake. If a failing test is itself *wrong* (a bad assertion, a stale
  fixture), that is **test-authoring** work: do **not** fix it inside the loop — flag it and **stop-and-surface**
  for an out-of-loop actor. (Editing tests also forfeits the YOLO posture; see below.)
- **Stop predicate (step 7):**
  - **Green** — suite exits 0, zero failing tests → stop-and-surface (success).
  - **Stuck** — an iteration fails to *reduce* the failing-test count → stop-and-surface (can't advance).
  - Otherwise (count dropped, tests remain) → re-fire.
  The failing-test count is a monotone-decreasing **ratchet**; "suite green" is the terminal. Do **not** use
  coverage-100% as the predicate (Goodhart-able).
- **Fork (decision handling):** the bare anchor has no plan/ledger, so RECORD a fork in a **lazily-created
  sidecar** (default `LOOP_DECISIONS.md` at the repo root; `--decisions <path>` to override) as a
  `- [ ] DECIDE: <fork>` item (reusing the checklist `- [ ]` count verbatim — created **only on the first
  fork**, so the anchor stays zero-ceremony until then). The stop predicate then becomes **suite exits 0 *AND*
  zero open sidecar `- [ ] DECIDE:` items** — a green suite alone is no longer "done". Up-front gate is
  **opt-in** here (keep it ceremony-free). CLASSIFY per *Decision handling*.

## Anchor: checklist

The canonical "Ralph Wiggum" form: a plan file is the spec, items-remaining is the progress signal. It is the
broadest anchor (no ledger/suite required) but the **prose/judgment** one — the loop ticks its own boxes.

- **Spec source (step 2):** read the plan file under `R` (default `IMPLEMENTATION_PLAN.md` at the repo root;
  `--plan <path>` to override) from disk every iteration. A markdown checklist of `- [ ]` (open) / `- [x]` (done) items,
  priority-ordered top-to-bottom; an item MAY carry a trailing `verify: <command>` annotation (see YOLO).
  Count the open items — `grep -c '^[[:space:]]*- \[ \]' <plan>` — that count is the anchor + progress signal.
  **Reconcile plan-vs-code:** before treating an unchecked item as un-done, *search the codebase* — an item
  may already be implemented (the box just wasn't ticked). Don't redo work; tick the box and move on.
- **Pick (step 3):** the **highest-priority (top-most) unchecked item** — exactly one per iteration ("only
  one thing per loop"). One item keeps each commit focused and each re-read honest.
- **Do (step 4):** implement that one item on the loop branch.
- **Discharge (step 5):** the box is **prose by default** — ticking it is a *claim*, not proof. Route to the
  **prose/judgment** split (independent out-of-loop falsifier; never self-bless). **Exception:** an item with
  a frozen `verify:` oracle is test-expressible — see the YOLO per-unit gate. Tick `- [ ]` → `- [x]` to record
  the claim, but the *stop signal* is the re-read count, never your say-so.
  - **For UI / end-to-end items, the falsifier should drive the running app, not just read code.** Anthropic's
    long-running-agent harness finding: a coding loop tends to mark a UI feature "done" without ever exercising
    it, and does markedly better when *explicitly* told to verify end-to-end as a real user would — e.g. via a
    browser-automation MCP (Playwright). So the out-of-loop falsifier for a UI item should exercise the
    behavior in the running app, not rubber-stamp the diff. Note this is **context-expensive** (driving a
    browser + reading screenshots burns budget), which reinforces the one-small-item-per-iteration rule: keep
    units small enough that the falsifier still has the budget to actually poke the app. A standing `verify:`
    command that runs the e2e check turns this from prose into a *test-expressible* item that, if its oracle is
    frozen / loop-immutable, becomes YOLO-eligible — see the gate.
- **Stop predicate (step 7):**
  - **Done** — zero unchecked items → stop-and-surface (success).
  - **Stuck** — an iteration fails to *reduce* the unchecked count → stop-and-surface (can't advance).
  - Otherwise (count dropped, items remain) → re-fire.
  The unchecked count is a monotone-decreasing **ratchet**; "zero unchecked" is the terminal. The ratchet is
  the whole stop — a spinning loop trips "stuck" on its very next no-progress iteration (no fire-counter is
  needed or kept; like every anchor, this one re-reads from disk and never remembers a prior pass). Do **not**
  use "the loop says it's done" as the predicate — re-read the file and count.
- **Fork (decision handling):** RECORD a fork as a `- [ ] DECIDE: <fork>` item in the plan file (with an
  optional inline `forbid: <command>` per option for an anticipated fork — see *Decision handling* →
  CLASSIFY). It counts in the unchecked ratchet, so it blocks the stop predicate until resolved. Up-front gate
  **required** here. CLASSIFY per *Decision handling*.

> **Why the box is never the oracle.** Unlike a suite exit code (green-the-suite) or a `verified-by:` test
> (telos), the checklist's done-signal is *authored by the loop itself* — the loop both does the work and
> ticks the box. "All boxes checked" is therefore the self-blessed proxy signal that is the deepest LLM-agent
> failure mode. So the checklist anchor **inherits the prose treatment and hard-refuses blanket YOLO**: a
> ticked box does not permit the loop to act. Only a per-item *frozen, loop-immutable* `verify:` oracle can —
> see below. Don't try to "freeze the plan file"; the loop is *meant* to edit it, so there is no surface to
> freeze (this is why there is no `check_plan_frozen.py`).

## Discharge — split by work type (the no-self-bless rule)

A loop that authors its own evidence produces *backed* "done" that routes **around** the normal checks. A
fresh same-model context does **not** escape LLM self-preference bias (it is perplexity-driven, not
memory-driven). So the loop can never be the actor that confirms its own discharge. Split:

- **Test-expressible work → a frozen oracle the loop didn't author.** For telos, the `verified-by:` command
  whose exit code `audit-telos` trusts over the LLM; for green-the-suite, the suite itself. The loop **may
  run** the oracle to check its work, but must **not author or edit** it in the same pass that discharges the
  work — a loop-written test that the loop declares passing is circular. A missing/needed witness or a
  wrong test is **out-of-loop work to surface**, not something to self-write-then-pass.
- **Prose / judgment work → an independent out-of-loop falsifier.** Cannot be discharged inside the loop at
  all. Do the work and commit it, but leave confirmation to a **separate spawn** (`/pre-merge-review`,
  `/grill-me`, `/re-audit-repo`) run by a different actor — **ideally a different model or differently
  prompted**. Honest residual: even two fresh falsifiers leave a ~40% gap on subtle non-verifiable claims.

This falsification step is the **expensive** part — it is **out-of-loop and batched**: surface the worked
units and let one review pass falsify them all at the merge gate; do **not** spawn a reviewer per unit per
iteration inside the loop.

## Decision handling (under-determined forks)

The anchor pins *progress*, but it can leave a **fork** under-determined — a unit where several
implementations all satisfy the spec (which library, sync vs async, an API shape, a robustness-vs-effort
tradeoff). A fork is **invisible to the progress signal** (both branches pass), and a fresh context re-decides
*toward whatever is already committed* — so the first commit on a fork silently locks the path in. Handling a
fork is a four-stage spine — **DETECT / RECORD / CLASSIFY / SURFACE** — plus an up-front gate (stage 0) that
front-loads anticipated forks into the spec before launch. It is **recipe, not engine**: every stage reuses an
existing primitive — there is **no new decision-ledger file and no new script**. Design + rationale:
`docs/design/ralph-loop-decision-handling.md`.

The four invariants are unchanged and decision-handling rides *on* them: anti-drift (every signal re-read from
disk), no-self-bless (the loop never confirms its own judgment), stop-and-surface by default, and the narrow
reversible/oracle-backed YOLO act-fence. **The loop never *chooses* a fork on judgment — it only *eliminates*
options by a frozen oracle, or *defers*.**

**Stage 0 — anticipate (pre-launch gate).** Before launch, resolve the forks you can. Reuse the design-doc's
`## Open questions` (resolve to empty) → `## Key decisions` sections (`/design-doc`); a resolved fork migrates
Open→Key and the loop re-reads it each pass. **Required for telos and checklist anchors; opt-in for
green-the-suite** (forcing a design-doc on the bare anchor breaks its "any repo, zero ceremony" value). The
gate *reduces* mid-run forks; it cannot eliminate them, which is why the four stages exist.

**DETECT — the cheap preimage probe (at *pick*, step 3), with a drift tripwire backstop (at re-read, step 2).**
- **Preimage probe (default, cheap):** before treating the picked unit as "implement", restate the intended
  choice as a **one-line claim** and grep the spec from disk for it. Spec pins it → implement as normal. Spec
  **under-determines** it (the preimage is not a singleton) → **flip the unit from "implement" to
  "reify-as-fork"**: its work this iteration is RECORD, not code. Probing at *pick* time is what catches the
  fork **before** a self-blessed commit locks the path in. This is a **recipe step, not a helper — do not
  script it.**
- **Drift tripwire (backstop, at re-read):** while re-reading, scan committed code for a fork-shaped choice (a
  library import, a sync/async signature) with **no matching RED item** → flag **DRIFTED** and surface, so
  merely committing can never silently ratify a fork the preimage probe missed.
- Honest floor: a purely *semantic* fork may leave no greppable signature; the tripwire and an out-of-loop
  reviewer catch what the preimage probe misses. **Worst case is a fork that surfaces later as drift, never an
  unsafe act.** (The expensive *k*-sample cross-context disagreement probe for suspected/high-stakes forks is
  **deferred to a later phase** — Phase 1 is the cheap probe + tripwire.)

**RECORD — a RED anchor item, reusing the existing ledger (no new decision file).** A fork **is** an
undischarged claim awaiting a verdict, so record it where the anchor already carries undone work:
- **telos:** mint a `TELOS-NNN` whose `contract:` states the decision criterion, with `discharged-by: none` —
  which `audit-telos` computes as state **`UNMET`** (an actionable, undischarged claim). It is **not**
  `needs_judgment`: that is a *different*, audit-computed boolean for a *pointed-but-unwitnessed* claim and is
  **not author-writable** (`audit-telos/telos_check.py`). Record a fork as `UNMET`; never hand-set a judgment
  flag.
- **checklist:** add a `- [ ] DECIDE: <fork>` item to the plan file (with any anticipated-fork `forbid:`
  annotations inline — see CLASSIFY). It counts in the unchecked ratchet.
- **green-the-suite:** the bare anchor has no plan/ledger, so **lazily create a sidecar decision file** (default
  `LOOP_DECISIONS.md` at the repo root; `--decisions <path>` to override) and add the same `- [ ] DECIDE:
  <fork>` item. The file is created **only on the first detected fork** — no fork, no file, the anchor stays
  zero-ceremony. It **reuses the checklist RED-item mechanism verbatim** (the `- [ ]` count), not a new format.

The telos ledger already has the exact firewall a *binding* record needs: `audit-telos` recomputes `state`
from disk every pass (anti-drift), the evidence `tier` is **tool-written, never author-written**, and the
parser **demotes an unbacked `DISCHARGED`→`SUSPECT`** — so the loop cannot self-bless a fork into "settled".
The advisory `LOOP_LEARNINGS.md` is the **wrong** home for the open-fork item (it is firewalled *out* of the
done-signal by design, so it can't bind a future pass) — keep the *why* of a fork in the learnings log, but the
**binding open-fork item** in the ledger / checklist / sidecar.

**CLASSIFY — may the loop resolve the fork, or must it defer?** The load-bearing judgment, and it is
**mechanically gated — never a self-classification the loop is trusted to report honestly.** Two composed
paths:
- **Anticipated fork (carries `forbid:` predicates) → oracle-elimination.** An anticipated fork carries, in its
  `## Key decisions` entry (or inline on a checklist/sidecar `- [ ] DECIDE:` item), **one `forbid: <command>`
  predicate per option** — an exit-code check that *rules that option out*. For each option's predicate,
  confirm it is **frozen / loop-immutable** (reuse `check_oracle_frozen.py` **unchanged**:
  `python3 ~/.claude/skills/ralph-loop/scripts/check_oracle_frozen.py --repo "$R" --base <default-branch> --verified-by "<the forbid command>"`,
  require exit 0), then run it. The loop may only **rule options out**. **Exactly one survivor →
  oracle-backed resolution** (no self-bless — an exit code, not the LLM judging itself; YOLO-eligible under the
  usual act-fence). **More than one survivor, or any predicate not frozen → defer.**
- **Everything else → the reversibility rubric decides *whether to defer* (it does NOT pick the fork).** Reuse
  `deliberate`'s `--reversible / --blast-radius / --cost-to-get-wrong` triad — the *same* axis the YOLO
  act-fence already gates on. **`reversible=yes` + internal blast radius is the ONLY class the loop may
  resolve-and-record autonomously;** `no` / `partial`, or any external reach → **defer** (RECORD + SURFACE).
  When the loop *does* resolve a reversible fork, **the lean-robust within-class tie-breaker** applies —
  prefer the more robust survivor. This makes "decide autonomously" the decision-analog of the act YOLO already
  permits (reversible / internal blast radius), and never a self-blessed consequential judgment.

> **The correction this encodes.** A fork is *not* "make the call autonomously, raise at the end" — that is
> **stop-and-act**, which violates no-self-bless. Deferring the irreversible is the **gate on** acting, and the
> gate is **mechanical** (a frozen oracle eliminates, or the reversibility class defers), not a classification
> the loop is trusted to self-report. Drift back toward "the loop decided the fork because it judged it fine"
> is the one regression a reviewer should falsify hardest.

**SURFACE — structural stall, then a batched ask (no mid-loop interrupt).** Because the fork is a RED item (an
open `- [ ]` / an `UNMET` claim), the anchor's own **done-predicate cannot fire while the fork is open**: telos
"no actionable claim remains" can't hold with an `UNMET`; checklist & green-the-suite "zero open items" can't
hold with an open `- [ ] DECIDE:` (for green-the-suite the stop predicate becomes **suite green *AND* zero open
sidecar DECIDE items** — the suite passing is no longer sufficient). Stop-and-surface stops being a behavior
the loop must choose to honor and becomes a **ratchet invariant**. At **run-end** the deferred forks are
already enumerable (the open items / `UNMET` claims); batch them into **one** `AskUserQuestion` — confirm the
forks the loop *took* (oracle-backed), and ask the human to rule the forks it *deferred*. Reuses the existing
"batch falsification at the merge gate, don't review per-unit" discipline. Degrades safely: no answer → the
items stay open, the loop stays stopped.

## Stop-and-surface (the default terminal state)

When step 7 says stop, the default terminal state is **"stopped, surfaced, awaiting an out-of-loop actor"** —
never "merged" or "done". (The opt-in `--yolo` posture below is the one narrow exception.) Concretely:

- **Never** `git merge`, `git push`, `git branch -d/-D`, `git reset --hard`, `git worktree remove`,
  `git clean`, or `gh pr merge`. The `guard-loop-vc.py` seatbelt blocks these while `CLAUDE_LOOP_GUARD` is
  armed, but the recipe forbids them regardless — the guard is a Bash-string seatbelt, not a sandbox. (Under
  `=yolo` the guard allows exactly one — a `--no-ff` merge into a non-default branch — see YOLO.)
- **Never** mark work done on the loop's own evidence (above). *(YOLO exception: test-expressible work whose
  frozen, loop-immutable oracle is green — its signal is unforgeable, not self-blessed.)*
- **Surface**: write a short summary — units advanced this run, units still pending (`UNMET`/`DRIFTED`, or
  still-failing tests), witnesses/tests that need authoring, and prose work pending independent falsification
  — and present the loop branch for an out-of-loop reviewer (`/pre-merge-review`) or a human to confirm +
  merge. Then **stop the loop** (omit the wake-up reschedule).

## Session-limit suspend (auto-continuation across a usage-window pause)

A long loop can exhaust the plan's rolling-window usage caps mid-run — a **5-hour** window (resets in
minutes-to-hours) and a **7-day** window (resets days away). A forced pause at a cap is a **third**
iteration outcome, distinct from both *continue* and *stop*: the loop is **healthy and work remains** (not a
*stop*), but it cannot safely do a unit right now (not a *continue*). Handling it is pure recipe — no new
engine: the loop is **already resume-safe by construction** (it re-reads the anchor from disk and commits
each unit, so relaunching the verbatim `/loop` invocation continues from committed branch state). The only
additions are a clean checkpoint, a verdict, and a poll-for-reset wake-up.

**The load-bearing invariant: a suspend is unreachable from a stop.** Step 7 evaluates the anchor's stop
predicate **first** — a done or *stuck* (no-progress) loop **still terminates**, exactly as before. Only a
loop that *would have continued* may consult the session-limit gate and downgrade continue → suspend. If
suspend could fire from a stop condition, auto-continuation would silently mask a spin into an indefinite
poll — the precise failure the ratchet exists to catch.

**The gate (only when step 7 already decided "continue"):** run

```
python3 ~/.claude/skills/ralph-loop/scripts/suspend_verdict.py   # [--threshold 90] [--max-poll-seconds 1800]
```

a thin wrapper over the vendored `claude_usage.py` reader (the OAuth token stays OS-side). It prints a
`verdict=` line and exits:

- **`PROCEED` (exit 0)** — headroom remains. End the iteration normally; `/loop` re-fires.
- **`SUSPEND` (exit 10)** — the **5h** window is at/over the threshold. **Do not pick a new unit.** Confirm a
  **clean working tree** first (the prior unit was already committed at step 6 — `git -C "$R" status
  --porcelain` must be empty; the clean checkpoint is what makes a kill-at-the-limit safe to resume). Then
  reschedule a wake-up `next_poll_seconds` ahead (the helper clamps it to ≤ `--max-poll-seconds` **and** to
  `ScheduleWakeup`'s 3600s ceiling, so it is always a valid delay) with a reason like *"suspended: 5h window
  at 94%, polling for reset at HH:MM"*.
  Each fire re-runs the gate; resume the loop the first time it returns `PROCEED`. This is a **heartbeat
  poll**, because a 5h reset can be farther out than one wake-up's max.
- **`SURFACE` (exit 20)** — the **7d** window is the binding limit (reset days away). Do **not** hold the
  loop open for days: **stop-and-surface** for a human, exactly like a normal terminal stop, noting the 7d
  reset time in the summary.

**Fail-open, by design.** If usage can't be read (endpoint down, missing reader), the verdict is `PROCEED`
(exit 1, with a warning) — a usage blip must never wedge a healthy loop into an indefinite *false* suspend. A
real hard cap still surfaces as an actual harness pause; the worst case is one iteration that tries and is
throttled, recoverable on the next re-read. This is the **opposite** of the YOLO immutability checks (which
fail-*deny*): those gate an irreversible *act*, this only gates a reschedule.

**The act-fence is unchanged.** A suspend **never** merges, pushes, or marks work done, and `CLAUDE_LOOP_GUARD`
stays armed across the pause. Auto-continuation adds unattended **runtime**, not a new **act** — so it does
not weaken stop-and-surface (it does raise the value of keeping the guard armed for a longer-running loop).
The session-limit gate is **orthogonal to the YOLO posture**: it runs before any YOLO act gate and changes
nothing about it.

## YOLO posture (verifiable autonomy — opt-in, narrow)

By default this recipe never acts. The `--yolo` posture relaxes that for **one case only**: test-expressible
work whose oracle is an **unforgeable external signal the loop cannot edit**. "Done" is then an exit code,
not the LLM judging itself, so the self-preference objection evaporates and the loop may *act*: self-discharge
and integrate within the reversible/internal fence. Rationale: `docs/design/loop-yolo-verifiable-autonomy.md`.

**Run-level preconditions — assert ALL before any YOLO act; if any fails, run the whole loop conservatively
(stop-and-surface):**
1. `CLAUDE_LOOP_GUARD=yolo` (`echo "$CLAUDE_LOOP_GUARD"` → `yolo`). The guard then mechanically permits a
   `--no-ff` merge into a non-default branch while still blocking push / default-branch merge / `git clean` /
   reset / branch-delete / `gh pr merge` / fast-forward merge.
2. **Hook-clean working copy.** `git -C "$R" config --get core.hooksPath` is empty AND `"$R"/.git/hooks/`
   holds no non-`.sample` files, and no filesystem watcher is running — a `post-commit`/`post-merge` hook can
   fire an external side effect (push/deploy) the guard never sees. Hooks present → YOLO is unsafe → conservative.
3. You are on a dedicated **non-default** loop branch (loop body step 1).

**Per-unit gate — in step 5, for THIS unit only, replace the discharge routing iff ALL hold. Prose / judgment
work hard-refuses YOLO — no override — and routes to the normal out-of-loop falsifier.**

- **telos unit:**
  - the claim has an executable `verified-by:` oracle (test-expressible);
  - the oracle is **frozen / loop-immutable** —
    `python3 ~/.claude/skills/ralph-loop/scripts/check_oracle_frozen.py --repo "$R" --base <default-branch> --verified-by "<the claim's verified-by command>"`
    exits 0 (non-zero → the loop edited its oracle, or none is extractable → refuse, surface);
  - the oracle is **green** — run the `verified-by:` command, require exit 0.
- **green-the-suite unit:**
  - the loop touched **zero test-surface files** on its branch —
    `python3 ~/.claude/skills/ralph-loop/scripts/check_suite_frozen.py --repo "$R" --base <default-branch> --test-path <each test/config pathspec>`
    exits 0 (non-zero → the loop weakened/added/deleted a test or runner config, or named a non-existent
    surface → refuse, surface). **List every verdict-affecting path** (test dirs/globs **and** runner config
    — `pytest.ini`, the `[tool.pytest]` file, `conftest.py`, …); an unlisted path is an immutability hole the
    DoD author owns;
  - the suite is **green** — run the `--suite` command, require exit 0.
- **checklist unit:**
  - a **bare-prose item HARD-REFUSES YOLO — no override.** A ticked box is a loop-authored claim, not an
    oracle, so it routes to the normal out-of-loop falsifier (stop-and-surface). This is the default.
  - an item with a frozen `verify:` oracle is **test-expressible** and degrades to the **telos-unit gate
    verbatim**: extract the item's `verify:` command, require it **frozen / loop-immutable** —
    `python3 ~/.claude/skills/ralph-loop/scripts/check_oracle_frozen.py --repo "$R" --base <default-branch> --verified-by "<the item's verify command>"`
    exits 0 (non-zero → the loop edited its oracle, or none is extractable → refuse, surface) — **and**
    green (run the `verify:` command, require exit 0). No new mechanism: a `verify:` item *is* a `verified-by:`
    claim.

**The YOLO act (only after the gate passes):** mark the unit done (its frozen green oracle backs it) and you
MAY integrate via `git merge --no-ff` into a **non-default** integration branch. Never the default branch,
never push (the guard blocks both); the final default-branch merge stays a human / out-of-loop step.

**Unchanged under YOLO:** prose/judgment work (still stop-and-surface); the no-author-then-pass rule
(`check_oracle_frozen` / `check_suite_frozen` enforce it mechanically); the merge-to-default and push
prohibitions; one-unit-per-iteration; re-read the spec each fire. The **learnings log** is also unchanged
under YOLO: it is loop-mutable by design, so it is **never** a frozen surface (never list it as an oracle/suite
path — writing to it must not affect any immutability verdict) and **never** the thing a `verify:`/`verified-by:`
oracle asserts on. The YOLO act stays backed solely by the frozen green oracle; the log is only advisory
context the loop read on the way there.

> **Honest limit.** The immutability *check* is mechanical and the default-branch-merge prohibition is
> mechanical, but a misbehaving loop could skip the check — the guard can't know which files are "the
> oracle"/"the suite". YOLO *narrows* the trust placed in the loop; it does not eliminate it, and it presumes
> the DoD oracle is a *true*, *complete* definition (oracle/suite incompleteness — Goodhart — is the DoD
> author's responsibility, not something YOLO can verify).

## Notes

- **This is a recipe, not an engine.** Don't build bespoke halting code — the anchor's progress signal is the
  stop signal, the seatbelt is the no-act enforcement. If you find yourself scripting a loop runner, stop.
  - **The one-unit-per-session cap is the exception that proves the rule — it is a re-fire *gate*, not
    halting.** Bounding a `claude -p` worker to a single unit (the `guard-one-unit.py` PreToolUse gate that
    denies further tools once the unit commit lands; see *The loop body*'s invariant) is **not** the forbidden
    "loop runner" / watcher: it is an event-driven hook (fires per tool call, like `guard-loop-vc.py`), it does
    not decide *whether the work is done* (the anchor still does), and it monitors/kills nothing — it just makes
    the worker end its turn so the driver's existing re-fire supplies the fresh context. Without it the
    anti-drift re-read silently degrades to "once per worker turn," so a driver-backed loop **must** arm this
    gate; an interactive `/loop` gets it for free (each wake is a fresh session). Don't skip it on the grounds
    of "no engine."
- **Per-repo, not cross-repo.** One anchor, one repo per loop — a loop's anchor, progress signal, act-fence,
  and pre-merge-review are all scoped to a single repo. Aim a separate loop at each repo.
  - **Multi-repo work = ordered per-repo charters, not one cross-repo loop.** A task that spans repos (e.g. a
    tool repo whose output a second repo consumes) does **not** become one loop. Decompose it into one charter
    **per repo**, sequenced by their dependency, each its own plan/anchor/branch. Put the cross-repo dependency
    as a **precondition at the top of the downstream charter's plan** — so a fresh context re-reads it every
    pass and won't start before the upstream is ready (e.g. *"do not begin until <upstream repo> has
    stop-and-surfaced, passed `/pre-merge-review`, and LANDED — this repo builds against its merged output, not
    an unmerged branch"*). Run them in order: loop the upstream to stop-and-surface → out-of-loop
    `/pre-merge-review` + `--no-ff` local-only merge → **then** launch the downstream loop. The cross-repo
    boundary is **one designed handoff at a real dependency seam** (a good place to confirm the upstream
    foundation landed), **not** a mid-plan stop — and it is **not** an under-determined fork: don't record it as
    a `DECIDE:` item, it's a sequencing edge between charters, not a choice the loop resolves. (A symptom you got
    this wrong: a single loop that finishes its items for one repo then asks to be switched to another repo —
    split that plan in two.) Automating away even this one handoff is a separate, unbuilt feature (a sequencing
    parent touching the merge-ordering + act-fence) — don't improvise it inside the loop.
- **Non-Python telos repos** run `audit-telos` in degraded grep-existence mode (drift/unmet work; orphan +
  coverage skipped) — lean harder on `verified-by:` witnesses for the signal.
- Reciprocal pointers: `skills/telos-loop/SKILL.md` (the telos-anchor alias into this skill),
  `skills/telos/SKILL.md` (telos write side), `skills/audit-telos/SKILL.md` (telos read/stop signal),
  `hooks/guard-loop-vc.py` (the act-fence seatbelt; `=yolo` mode),
  `hooks/guard-one-unit.py` (the one-unit-per-session PreToolUse gate — *The loop body*'s
  invariant), `skills/ralph-loop/scripts/check_oracle_frozen.py` + `skills/ralph-loop/scripts/check_suite_frozen.py`
  (the YOLO immutability checks — reused as-is by a checklist item's `verify:` oracle),
  `skills/ralph-loop/scripts/suspend_verdict.py` (the session-limit suspend/surface/proceed verdict, over
  the vendored `claude_usage.py`), and the design records: `docs/design/ralph-loop-green-the-suite.md`,
  `docs/design/ralph-loop-checklist-anchor.md`, `docs/design/loop-telos-anchor-deliberation.md`,
  `docs/design/loop-yolo-verifiable-autonomy.md`, `docs/design/ralph-loop-learnings-log.md` (the append-only
  learnings log), `docs/design/ralph-loop-session-suspend.md` (session-limit auto-continuation),
  `docs/design/ralph-loop-decision-handling.md` (under-determined-fork handling — the *Decision handling*
  section above), and `docs/design/ralph-loop-one-unit-per-session.md` (the one-unit-per-session cap + the
  `guard-one-unit.py` hook-gate — the invariant in *The loop body*).
