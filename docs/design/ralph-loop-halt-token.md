# ralph-loop — external unforgeable halt token — Design

**Date:** 2026-06-19
**Status:** design (spec only). **Recommendation: DEFER — documented wildcard, do not build yet.** This is a
spec pass, not a build: Erick authorized *the spec* (2026-06-19); the *build* stays gated and is not
recommended by this doc. The "if/when it ever becomes worth building" shape is recorded in full below so the
analysis survives.
**Closes the spec gap on:** the last design-doc'd-but-unbuilt wildcard of the [`ralph-loop`](../../skills/ralph-loop/SKILL.md)
loop family — the *external unforgeable halt token*, framed once in
[`loop-telos-anchor-deliberation.md`](loop-telos-anchor-deliberation.md) (line 227) and named as a *halt*
mechanism (not a permit-to-act one) in [`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md)
(line 9). Sibling to the three shipped-anchor design records
([`ralph-loop-green-the-suite.md`](ralph-loop-green-the-suite.md),
[`ralph-loop-checklist-anchor.md`](ralph-loop-checklist-anchor.md)) and the **mirror** of the YOLO doc — that
one is *permit-to-act*; this one is *halt*.

## Context / problem

Every shipped piece of the loop family stops the same way: **stop-and-surface.** The loop computes a
"done / stuck" signal each iteration by re-reading a durable, out-of-context spec from disk (telos coverage,
the suite's exit code, the unchecked-box count), and on "done" or "no progress" it *terminates itself* —
omitting the next `ScheduleWakeup` and presenting the branch for an out-of-loop reviewer. The
[`guard-loop-vc.py`](../../hooks/guard-loop-vc.py) seatbelt separately prevents the loop from
*acting* (merge/push/branch-delete) on that judgment.

The **external unforgeable halt token** *inverts* the termination decision. Today the loop forms the
done-judgment (even if mechanically) and surfaces it. The halt-token posture removes the loop's ability to
evaluate "done" **at all**: an out-of-loop actor (a human, or a separate process) holds a signal, and the
loop runs — committing work on its branch each iteration — until that *external* signal says halt. It is the
strongest form of no-self-bless: not "the loop judges done but can't *act*" (stop-and-surface) and not "the
loop may act on a verifiable oracle" (YOLO) — it is **"the loop cannot even form the done-judgment."** Its
original framing is the **default-run / never-quiesce** loop: *the loop never self-evaluates; an external
unforgeable token halts it* (`loop-telos-anchor-deliberation.md:227`).

**The problem this doc solves is the *decision*, not the build:** is that inversion **meaningfully distinct**
from stop-and-surface + the seatbelt + ordinary process control — and does the marginal value clear the build
bar? The honest answer, worked below, is **no** — and the reason is a clean asymmetry that is worth recording
precisely, because it is *not* obvious going in (the handoff itself flagged "unforgeable is the whole game").

## Goals & non-goals

**Goals**
- **Resolve the crux** up front: is the halt token distinct from what already ships, and is it worth building?
- If it is *not* (the finding): record **why**, so the wildcard is closed as "analyzed and deferred," not
  left as an open 💡 that invites a re-spec.
- Record the **if/when-built shape** in enough detail that a future build is a lookup, not a re-derivation:
  the candidate token shapes weighed, the recipe-not-engine form, and the threat surface.

**Non-goals**
- *Not* a build. No SKILL.md change, no guard change, no new script lands from this doc. (See Rollout.)
- *Not* a new skill, and — if ever built — *not* a new skill either: it would be a **posture/section** in
  `ralph-loop/SKILL.md` alongside stop-and-surface and YOLO (the family's chosen topology), unless a future
  build argues otherwise with reason.
- *Not* a re-open of `ratchet-not-resolve` — that is **already built** (the stop predicate inside
  green-the-suite + checklist). It is not an open item and is out of scope here.
- *Not* an engine. Whatever the halt token is, it must fit "recipes over the built-in `/loop` +
  `ScheduleWakeup` + the opt-in seatbelt" — a recipe rule (and at most a tiny guard/hook tweak), **never** a
  long-running watcher/daemon. A design that starts requiring a watcher is a red flag, surfaced not accepted.

## Approach — the crux, worked

### Three postures on one axis, and what each actually governs

| Posture | Who decides **termination** | Who decides **acting** (merge) | Trust placed in the loop |
|---|---|---|---|
| **stop-and-surface** (shipped default) | the loop (mechanical re-read signal) | **nobody in-loop** — out-of-loop reviewer | may judge done, may **not** act |
| **YOLO** (shipped, opt-in) | the loop, gated by a **frozen external oracle** | the loop, within a reversible fence | may act **iff** an unforgeable oracle backs it |
| **halt token** (this doc) | an **external actor only**; the loop cannot evaluate done | unchanged — still stop-and-surface / seatbelt | may **not even judge** done |

The halt token moves left-column control from the loop to an external actor. Crucially, it leaves the
*acting* column **unchanged** — it is explicitly a **halt** mechanism, not a permit-to-act one
(`loop-yolo-verifiable-autonomy.md:9`). So the question is narrow: **is moving the *termination* decision out
of the loop worth a mechanism?**

### Finding 1 — termination is the *fail-safe* direction; the no-self-bless rule does not bite here

The entire loop-containment design exists to stop one thing: the loop **acting** on a false "done" (a
self-blessed `DISCHARGED` → an unattended bad `--no-ff` merge + branch-delete). The dangerous direction is a
**false-positive done → act**. Stop-and-surface already severs the act, and the seatbelt enforces it
mechanically.

A loop that *stops* — correctly or incorrectly — is not *free*: a premature stop **leaves incomplete work on
the table**, a real cost. But that cost is **lost progress, not corruption** — the branch is surfaced
intact, nothing is mis-merged or destroyed, and the remedy is **cheap and already in hand: re-fire the loop**
(it re-reads the spec from disk and resumes). This is the load-bearing distinction: the entire containment
design — and the bar a new mechanism must clear — is about preventing **irreversible corruption** (an
unattended bad merge), *not* about maximizing completion. A false-positive *done* costs a relaunch; a
false-positive *act* costs an irreversible merge. They are not the same axis, and only the second is what the
machinery is for. So **removing the loop's ability to decide to stop does not close any safety hole** — at
most it trades a re-launchable under-completion for making the loop run *longer*, which is a cost / resource
tradeoff, not an integrity one.

Crucially, the halt token is also **not the right fix for the under-completion cost it would target.** A loop
that falsely reads "done" today is caught by the surface step — a human (or out-of-loop reviewer) sees the
branch and relaunches if work remains; and a loop that stops because it is genuinely *stuck* (the ratchet) is
stopping *correctly* and should not be forced onward. So the cure for "stopped with work left" is to re-fire,
not to build an unforgeable token so the loop can never stop on its own — which would also cost the **stuck**
auto-stop (Finding 5).

This is the first half of the verdict: the halt token's headline property ("the loop can't self-evaluate
done") guards a *cost* axis (under-completion, cheaply recoverable), not the *integrity* axis the no-self-bless
machinery exists for — and it isn't even the cheapest remedy on that cost axis.

### Finding 2 — the safety of a *halt* token is the mirror-image of a *permit* token, and the mirror is asymmetric

YOLO's permit-to-act oracle **must** be unforgeable: if the loop could mint its own "done," it would merge on
a false signal — catastrophe. That is why `check_oracle_frozen.py` / `check_suite_frozen.py` exist and why
the handoff calls unforgeability "the whole game."

The halt token is the mirror, but **safety is not mirror-symmetric**, because the failure directions invert:

- **Forge a permit** ("I'm done, merge") → the loop acts on a false done → **bad merge. Catastrophic.**
  Unforgeability is load-bearing.
- **Forge a halt** ("stop now") → the loop stops early → **surfaces a branch. Fail-safe** (no corruption — it
  costs lost progress, recoverable by re-firing; see Finding 1 — never an irreversible act).
- **Ignore / fail to receive a halt** (the only adversarial direction for a halt token) → the loop **keeps
  running** → bounded entirely by **process control**: a human can always kill the session, stop the cron, or
  decline the next wake-up. The seatbelt still forbids it to merge/push, so a runaway loop pollutes only its
  own branch and burns budget — it cannot corrupt the repo.

So the property the handoff worried was "the hard part" — making the token un-mintable by the loop — is
**not load-bearing for a halt token.** Minting a halt early is fail-safe; the dangerous direction (refusing to
halt) is already capped by the human's ultimate, un-forgeable, zero-mechanism halt: **kill the process.** The
loop cannot prevent its own kill.

### Finding 3 — the external halt already exists, for free, and the marginal delta is merely *graceful-vs-abrupt*

A self-paced `/loop` only continues because each iteration schedules the next wake-up (and, for a cron
variant, because the schedule still exists). The human therefore **already holds an unforgeable external halt
by default**: don't answer the wake, stop the routine, or kill the session. No token, no mechanism, no guard
change. This is the `CLAUDE_LOOP_GUARD` precedent's deeper point — the strongest "the loop can't set this
itself" signal is one that lives in the *environment / process*, which the loop genuinely cannot reach from a
Bash `export`; the **process lifecycle itself is exactly such a signal**, and it is already wired.

What a built halt-token feature would add over "just kill it" is **graceful** termination: the loop notices
the halt at an iteration boundary, finishes committing the in-flight unit, writes its stop-and-surface
summary, then stops — instead of being killed mid-unit with a half-done working tree and no summary. That is a
**real but minor ergonomic delta**, not a safety primitive. And it is buyable, *if ever wanted*, as a
one-line recipe rule with **no new mechanism** (see the if/when shape).

### Verdict

The halt token is **not meaningfully distinct on the safety axis** from stop-and-surface + the seatbelt + the
human's existing process-control halt. Its only genuine marginal value is the small ergonomic one (a graceful
in-band halt for a never-quiesce loop), which does **not** clear the build bar — and which, if it ever did,
costs a single recipe sentence rather than a mechanism. **Recommendation: DEFER, documented.** Build only if a
real *never-quiesce* loop appears (Finding 4 below) *and* the graceful-halt ergonomics are felt to matter.

### Finding 4 — the one shape that is genuinely distinct (and still doesn't need an unforgeable token)

There is exactly one loop *topology* the three shipped anchors don't model: a **never-quiesce** loop whose
work has **no computable terminal** — continuous improvement ("keep finding and fixing", "keep tightening
toward a quality bar with no end state"). The three anchors all have a terminal (coverage / green / zero
unchecked); a never-quiesce loop has none, so it *can't* self-evaluate "done" — not because we forbid it, but
because there is nothing to compute. For that shape an external actor must decide "enough."

But even here the unforgeable token is unnecessary: the external "enough" is again **process control + the
out-of-loop review cadence** (the human reviews the accumulating branch and, when satisfied, halts the loop
and merges). The only thing missing is graceful in-band halt — the same minor ergonomic delta. **And** a pure
"loop can't evaluate anything" never-quiesce loop is actively *worse* than today, because it would discard the
**stuck** auto-stop (Finding 5): you want a never-quiesce loop to still self-halt when it can no longer make
progress, so it doesn't spin burning budget. So even the never-quiesce shape should keep self-evaluating
*stuck* — it only drops self-evaluating *done*. That further shrinks the feature to "don't stop on done (there
is none); do still stop on stuck; a human halts on enough" — which is, again, a recipe rule.

### Finding 5 — a pure halt token would *delete* a safety feature

Today the **stuck** ratchet (an iteration that fails to reduce the progress count → stop-and-surface) is the
loop's automatic protection against spinning. A literal "the loop can't self-evaluate doneness at all" posture
that also removed self-evaluation of *stuck* would let a wedged loop commit useless or harmful churn to its
branch indefinitely, until a human notices. So the maximalist framing is not just low-value — it is mildly
*negative*. The correct never-quiesce posture **keeps** the stuck auto-stop; it only lacks a *done* terminal.
This is decisive: the feature's own logic pulls it back toward "a recipe rule on top of the existing
stop-and-surface core," never a from-scratch posture that strips self-evaluation.

## Key decisions

1. **DEFER — do not build; close the wildcard as analyzed.** The marginal value over stop-and-surface + the
   seatbelt + process control is essentially nil on the safety axis (Findings 1–3) and small-and-recipe-shaped
   on the ergonomic axis. (This matches the prior gate-override honesty: a clean "defer, here's the design
   if/when" is a legitimate outcome, and here it is the *correct* one — unlike telos-loop / green-the-suite /
   checklist, where Erick chose to override the gate, this doc *recommends* the gate hold.)
2. **The "unforgeable" property is NOT load-bearing for a halt token.** Safety is asymmetric: forging a
   *permit* is catastrophic (YOLO), forging a *halt* is fail-safe; the only adversarial direction (ignoring a
   halt) is capped by process control + the unchanged seatbelt. This *retires* the handoff's central worry
   ("unforgeability is the whole game") for the halt direction — it was true for the YOLO mirror, not here.
3. **Halt stays distinct from permit-to-act in the record.** This doc is the mirror of the YOLO doc and must
   not blur into it; the asymmetry in decision 2 is precisely *why* they stay separate.
4. **If ever built: a recipe rule + an out-of-band flag, never an engine.** The cheapest sufficient form is a
   human-only halt file checked at each iteration boundary (below). No watcher, no daemon, no new skill, no
   guard change — consistent with the family's "recipes over `/loop` + `ScheduleWakeup` + seatbelt" posture.
5. **A never-quiesce loop keeps self-evaluating *stuck*; it only drops the *done* terminal.** (Finding 5.) Any
   future build must not strip the stuck auto-stop — doing so removes a safety feature.

### The if/when-built shape (recorded, not built)

Should a real never-quiesce loop appear *and* graceful halt be wanted, the **entire** feature is:

- **Recipe rule (in `ralph-loop/SKILL.md`, a short "never-quiesce / external halt" note under the
  stop-and-surface section):** "If launched in never-quiesce mode, the loop has no *done* terminal — it does
  not stop on a done-signal. At the **start of each iteration**, check for a human-written halt flag
  (default `<repo>/.loop-halt`, or env `CLAUDE_LOOP_HALT`); if present, finish nothing new, write the
  stop-and-surface summary, and stop (omit the wake-up reschedule). The **stuck** ratchet auto-stop is
  unchanged. The seatbelt and no-self-bless / no-act rules are unchanged."
- **Token shape:** the **out-of-band flag** — a file only a human writes, or an env var the loop can't
  `export` (the `CLAUDE_LOOP_GUARD` precedent) — is the right model, *not* for unforgeability (decision 2) but
  for **clarity and discoverability**: a human writes it, the loop reads it, no schema. No guard enforcement is
  needed because halting is fail-safe.
- **No new script, no guard change, no new skill.** This is why the build bar isn't cleared by "it'd be a lot
  of work" — it wouldn't; it isn't cleared because the value is near-zero until the never-quiesce shape is
  real, and trivially recoverable when it is.

## Alternatives considered

- **Do nothing — stop-and-surface + the seatbelt + process control already cover it.** **CHOSEN** (as the
  recommendation). The loop already cannot act on a false done; the human already holds an unforgeable
  process-level halt; the only gap (graceful in-band halt for a never-quiesce loop) is small and recipe-shaped.
- **Build the halt token now as a first-class posture** (a third section mirroring YOLO, with a guard-enforced
  unforgeable token). *Rejected.* Findings 1–3: it guards the fail-safe direction, its headline property isn't
  load-bearing, and the dangerous direction is already capped — so a guard-enforced token is mechanism without
  a matching hazard. Also risks pulling in a watcher (engine), which the family forbids.
- **An env-var halt token enforced by `guard-loop-vc.py`** (mirror the `CLAUDE_LOOP_GUARD` precedent
  literally). *Rejected.* The guard exists to deny *acts*; a halt isn't an act. There is nothing for the guard
  to deny — refusing to halt is not a Bash command it can intercept, and stopping needs no permission. Wrong
  tool; adds guard surface for no safety gain. (And the seatbelt is a Bash-string seatbelt, not a sandbox —
  the same honest limit the existing guard discloses — so even *wanting* it to enforce a halt would inherit
  that limit for zero benefit.)
- **An external service / queue signal** (the loop long-polls a queue for a halt). *Rejected.* That is an
  engine / long-running integration — the exact red flag the family's no-engine rule names. Process control +
  a file flag deliver the same outcome with no infrastructure.
- **A pure "loop evaluates nothing" never-quiesce posture** (drop *both* done and stuck self-evaluation).
  *Rejected (Finding 5)* — strips the stuck auto-stop, a net safety loss; lets a wedged loop churn its branch
  indefinitely.
- **Leave the wildcard open (status quo: a one-line 💡 on the roadmap).** *Rejected* — an open 💡 invites a
  periodic re-spec of a question that has now been answered. Closing it as "analyzed → deferred, here's the
  if/when shape" is the higher-value terminal state, exactly like the deep-analysis records elsewhere.

## Risks

Security-relevant (it concerns an autonomous loop's containment) → `threat-model` lens. The asset is **repo
integrity + the no-self-bless guarantee** (unchanged from the YOLO / checklist docs). The notable result of
the threat model is that **almost every controlled risk here is controlled by mechanisms that already ship**;
the feature adds essentially no new attack surface *because it isn't built*, and wouldn't add much if it were.

- **Asset:** repo integrity + the no-self-bless / no-act guarantee + bounded compute/budget.
- **(Modeled, deferred) Loop ignores / forges a halt and runs away.** The only adversarial direction for a
  halt token. *Control (already shipping):* the seatbelt forbids push / branch-delete / `gh pr merge` /
  default-branch merge regardless (and *all* merges in conservative mode; YOLO permits only a revertable
  `--no-ff` merge into a non-default branch), so a runaway pollutes only its own non-default branch;
  **process control** (kill the session /
  stop the routine / decline the wake) is the un-forgeable, zero-mechanism backstop. *Residual:* wasted
  compute + branch churn until a human notices — a **cost** risk, not an integrity one. This is why
  unforgeability isn't load-bearing (decision 2).
- **(Modeled, deferred) Forged / premature halt** (something trips the halt early). *Control:* none needed —
  **fail-safe**; the loop stops and surfaces, the safe response to any uncertain "done." It costs lost
  progress (recovered by re-firing the loop, Finding 1), not corruption — no irreversible act occurs.
- **Seatbelt-not-sandbox** (inherited, honest limit). The `guard-loop-vc.py` seatbelt parses Bash strings and
  is not airtight; a `post-commit`/`post-merge` git hook or a filesystem watcher can fire a side effect it
  never sees. This limit is **unchanged** by this doc — the halt token adds no guard surface (decision 4) and,
  recommended-deferred, adds none at all. Stated for completeness because the if/when build must not pretend
  the seatbelt is a sandbox.
- **Scope creep into an engine.** *Control:* decision 4 fences any future build to a recipe rule + a flag; a
  watcher/queue design is a red flag to surface, not accept.
- **Wedged never-quiesce loop churns its branch** (Finding 5). *Control:* keep the **stuck** auto-stop even in
  a never-quiesce build; never adopt the "evaluate nothing" maximalist framing.

## Open questions

*(Resolved during this spec; kept as the decision record.)*

- **Is the halt token meaningfully distinct from stop-and-surface + the seatbelt?** RESOLVED: **no, on the
  safety axis** (Findings 1–3); only a small *ergonomic* (graceful-halt) delta exists, and only for the
  never-quiesce shape. → defer.
- **Is "unforgeable" achievable within the recipe-not-sandbox posture, and is it needed?** RESOLVED: **not
  needed** for a halt token (decision 2 — safety is asymmetric); the process-lifecycle halt is already
  un-forgeable by the loop, for free.
- **Does any genuinely distinct shape need it?** RESOLVED: the **never-quiesce** loop is the one distinct
  topology (Finding 4), and it *still* doesn't need an unforgeable token — only a graceful in-band halt, which
  is a recipe rule keeping the stuck auto-stop (Finding 5).
- **If built, where does it live?** RESOLVED: a short **posture/section** in `ralph-loop/SKILL.md` (the
  family topology), not a new skill, not a guard change, not a script. (decision 4)

## Rollout / migration

- **Phase 1 ✅** — this design doc (the deliverable). Records the DEFER recommendation + the if/when shape.
- **Phase 2** — `ROADMAP.md`: change the lone remaining halt-token 💡 from "unbuilt wildcard" to
  **"design-doc'd → DEFER (analyzed; build only if a real never-quiesce loop appears)"**, linking this doc.
  This closes the loop family's open-item list: all three anchors ship, and the last wildcard is now
  *resolved-as-deferred* rather than *unbuilt-and-open*.
- **Phase 3** — independent `/pre-merge-review` → merge `--no-ff` (local-only, **never push**). Expect the
  reviewer to press the redundancy-vs-stop-and-surface question; Findings 1–5 are the answer of record.
- **No SKILL.md / guard / script change.** Default behavior is **unchanged** — this is a doc-only, deferral
  pass. The build stays gated pending a fresh, explicit go-ahead from Erick.
