# ralph-loop — decision handling (under-determined forks) — Design

**Date:** 2026-06-24
**Status:** PROPOSED 2026-06-24 (local-only; pending opus pre-merge-review). Prompted by the question
"does the Ralph loop have any logic for how to handle decisions raised by any instance?" — it does not, as a
first-class mechanism (see *Context*). Framing widened with a scoped `/brainstorm` (4 lenses + opus
Shortlister, 2026-06-24); this doc resolves the field into a recipe.
**Touches:** the anchor-independent core of [`ralph-loop`](../../skills/ralph-loop/SKILL.md). Reuses
[`telos`](../../skills/telos/SKILL.md) / [`audit-telos`](../../skills/audit-telos/SKILL.md) (the binding
ledger), `design-doc` (the up-front gate; a private sibling skill not shipped here),
[`check_oracle_frozen.py`](../../skills/ralph-loop/scripts/check_oracle_frozen.py) (the no-self-bless gate),
and `AskUserQuestion` (the surface). Sibling to
[`ralph-loop-learnings-log.md`](ralph-loop-learnings-log.md),
[`ralph-loop-session-suspend.md`](ralph-loop-session-suspend.md),
[`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md).

## Context / problem

A Ralph loop runs as a series of **fresh-context iterations**: each re-reads a durable on-disk **anchor**
(the spec) from disk, advances ONE unit, commits, then re-fires or stop-and-surfaces. The recipe is
dogmatic about *progress* (re-read the spec; never trust in-context memory; never self-bless the
done-signal) — but it has **no first-class mechanism for a decision an instance raises**: an
**under-determined fork** where the anchor's preimage is not a singleton (multiple implementations all
satisfy the spec — which library, sync vs async, an API shape, a robustness-vs-effort tradeoff).

Three structural facts make this dangerous in *this* loop specifically (from the first-principles lens):

1. **A fork the spec under-determines is invisible to the anchor's progress signal** — both branches pass,
   so the ratchet can't even detect a choice was made.
2. **Self-preference bias is perplexity-driven**, so a fresh context won't just re-decide — it re-decides
   *toward whatever the already-committed code implies*. The first commit on a fork becomes a
   self-fulfilling prophecy; the decision is "locked in" by the **path-dependence of the codebase**, not by
   any deliberate ledger.
3. **Statelessness makes "I'll remember to ask at the end" impossible** — there is no end-of-run context.
   The only thing that survives is disk, so every escalation must be a durable artifact a future fresh pass
   re-discovers and is forced to route on — identical to how the anchor itself works.

Today such a fork falls into one of: the loop silently decides it (drift), shoehorns it into "stuck" and
halts, or drops a note in the **advisory, overridable** learnings log (which is firewalled from the
done-signal by design, so it can't bind a future instance). None is a real answer.

## Goals & non-goals

**Goals.** A recipe (prose + thin reuse, no bespoke engine) by which a fresh-context iteration can
(a) **detect** it is at an under-determined fork, (b) **record** it as durable, *binding* on-disk state,
(c) **classify** whether it may resolve it autonomously or must defer, and (d) **surface** the result to a
human — all without breaking the four invariants (anti-drift, no-self-bless, stop-and-surface by default,
the narrow reversible/oracle-backed YOLO act).

**Non-goals.** A new bespoke decision-ledger file format (we reuse telos — see Decision 2). A mid-loop
human-in-the-loop interrupt (surfacing stays **batched at run-end**, per the existing no-per-unit-review
discipline). Eliminating *all* mid-run forks (the up-front gate only reduces them). Cross-repo decisions
(one loop, one repo, as ever).

## Approach

Decompose decision-handling into **four separable stages**; a complete recipe picks one mechanism per
stage. Plus an **up-front gate** that front-loads anticipated forks into the binding spec before launch.

| Stage | Question | Mechanism |
| --- | --- | --- |
| **0. Anticipate** (pre-launch gate) | Which forks can we resolve before running? | `/design-doc` `## Open questions` → `## Key decisions`, **anchor-conditional** |
| **DETECT** | Is this unit actually an under-determined fork? | cheap **preimage probe** (default) → **cross-context disagreement probe** (suspected/high-stakes) → **drift tripwire** (backstop) |
| **RECORD** | Where does the open fork durably live, bindingly? | a **telos claim**, `discharged-by: none` → surfaces as `UNMET` (no new ledger) |
| **CLASSIFY** | May the loop resolve it autonomously, or defer? | **composed**: oracle-elimination for anticipated forks; reversibility rubric decides *whether to defer* the rest |
| **SURFACE** | How/when does the human see it? | **RED anchor item** (structural stall) + **batched `AskUserQuestion`** at run-end |

The stages map onto the user's original three-rule proposal and **correct one tension in it** (Decision 4):
the up-front gate is stage 0; "record in a binding ledger" is RECORD; "decide reversible autonomously /
defer irreversible / lean robust" is CLASSIFY; "raise at the end" is SURFACE. The new, previously-absent
capability is **DETECT** — nothing in the baseline let an instance *know* it was at a fork.

## Key decisions

**1. Decompose into DETECT / RECORD / CLASSIFY / SURFACE.** The brainstorm field looked broad but was mostly
*cross-stage overlap*: ideas that seemed to compete were answering different sub-questions. Splitting them
makes the recipe a clear one-pick-per-stage, and localizes the only real judgment call to CLASSIFY.

**2. RECORD reuses the telos ledger — no new decision-ledger file.** An under-determined fork **is** an
undischarged claim awaiting a verdict. Mint a `TELOS-NNN` whose `contract:` states the decision criterion,
with `discharged-by: none` — which `audit-telos` computes as state **`UNMET`** (an unbuilt, actionable
claim; `needs_judgment` is a *different*, audit-computed bucket — a boolean flag, not a member of the state
set — for a pointed-but-unwitnessed claim, and is not author-writable; so the fork is recorded as UNMET, not
`needs_judgment`). This already has the exact
firewall a *binding* ledger needs: `audit-telos` recomputes the claim's `state` from disk every pass
(anti-drift), the evidence `tier` is **tool-written, never author-written ("so it can't be forged")**, and
the strict parser **demotes an unbacked `DISCHARGED`→`SUSPECT` at parse time** — so the loop cannot
self-bless a decision into "settled."
The binding-vs-advisory split the user asked for **already exists** as `docs/telos/` (binding, recomputed,
non-forgeable) vs `LOOP_LEARNINGS.md` (advisory, firewalled). A third store would duplicate it for no gain.

**3. SURFACE makes the stall structural, then batches to the human.** Recording the fork as a **RED anchor
item** — an open `- [ ] DECIDE: <fork>` (checklist) or the `UNMET` claim (telos) — means the
anchor's own done-predicate (zero unchecked items / no actionable claim remains) **cannot reach "done" while
a fork is open**. Stop-and-surface stops being a behavior the loop must choose to honor and becomes a
**ratchet invariant**. At run-end, the deferred forks are already enumerable (the `UNMET` claims / open
items); batch them into **one** `AskUserQuestion` (forks-taken → confirm; forks-deferred → rule) — reusing
the existing "batch falsification at the merge gate, don't review per-unit" discipline. Degrades safely: no
answer → the claims stay `UNMET`, loop stays stopped.

**4. CLASSIFY is composed — and that composition *corrects* the user's rule #1.** The user's fallback rule
#1 ("make the call autonomously, raise at the end") is, as written, **stop-and-act**, which conflicts with
no-self-bless. The fix: rule #3 (defer irreversible) is not parallel to #1 — it is the **gate on** it, and
the gate must be **mechanical**, not a self-classification the loop is trusted to make honestly. So:
   - **Anticipated forks → oracle-elimination.** Each carries frozen `forbid:` predicates (an exit-code
     check per option). The loop may only *rule options out*; one survivor → oracle-backed resolution
     (YOLO-eligible, no self-bless, reuses `check_oracle_frozen.py` unchanged — the per-option `forbid:`
     predicate format is a build-time open question); >1 survivor → defer. The loop
     **never chooses on judgment, only eliminates** — which is what makes autonomy here invariant-safe.
   - **Everything else → the reversibility rubric decides *whether to defer*** (reuse `deliberate`'s
     `--reversible / --blast-radius / --cost-to-get-wrong` triad — the *same* axis the YOLO posture already
     gates on). `reversible=yes` + internal blast radius is the only class the loop may resolve-and-record
     autonomously; `no`/`partial` → defer. Rule #2 (lean robust) is the within-class tie-breaker, unchanged.

   This makes "decide autonomously" the decision-analog of the act YOLO *already* permits (reversible /
   internal blast radius), and never a self-blessed consequential judgment.

**5. DETECT is a cost ladder, piloted cheapest-first (the crux is test-settleable).** Whether a probe
actually catches the repo's real fork population is a *measurement*, not a judgment — so adopt the cheapest
rung that empirically works before adding cost:
   - **Preimage-Collapse probe (default, cheap):** at *pick* time, restate the intended choice as a one-line
     claim and check it against the spec text grepped from disk; under-determination flips the unit from
     "implement" to "reify-as-fork" **before** a self-blessed commit locks the path in.
   - **Cross-context disagreement probe (suspected / high-stakes):** sample the fork from *k* independent
     fresh contexts; convergence → proceed under CLASSIFY; **divergence → stop-and-surface**. It turns
     Ralph's defining property (fresh context per pass) into a detector and is invariant-clean by
     construction — **divergence can only HALT, never upgrade confidence** (so it cannot self-bless).
   - **Path-dependence tripwire (backstop):** at re-read, grep committed code for fork-shaped choices (the
     library imported, the sync/async signature) lacking a ledger entry → flag DRIFTED and surface, so
     merely committing can never silently ratify a fork.

**6. The up-front gate (stage 0) is anchor-conditional and a *reducer*.** Reuse the design-doc's
`## Open questions` (must be resolved/empty) and `## Key decisions` sections — no new artifact; resolved
forks migrate Open→Key, and the loop re-reads it each pass. Require it for **telos** and **checklist**
anchors; keep it **opt-in for green-the-suite**, whose entire value is "any repo, a failing suite, zero
ceremony" — forcing a design-doc there breaks the anchor. It shrinks but cannot eliminate mid-run forks,
which is why DETECT/RECORD/CLASSIFY/SURFACE must exist.

## Alternatives considered

- **A new bespoke binding decision-ledger file** (the literal reading of the user's rule #3). *Rejected* —
  duplicates the telos ledger's non-forgeable `judged`-receipt firewall and re-introduces a binding/advisory
  split that already exists (Decision 2); two decision stores invites drift.
- **CLASSIFY by reversibility rubric alone** (one-way/two-way doors + "lean robust"). *Rejected as the whole
  answer* — it relies on the loop to *self-classify* "reversible," which is exactly the self-assessment
  no-self-bless distrusts. Kept only as the *whether-to-defer* half, gating the mechanical oracle-elimination
  half (Decision 4).
- **CLASSIFY by oracle-elimination alone.** *Rejected as the whole answer* — it presumes forks are
  pre-enumerable with frozen `forbid:` predicates; a novel/unanticipated fork has no predicate, so the loop
  would be stuck. Composition (oracle for anticipated, defer the rest) covers both.
- **Mid-loop human interrupt** (LangGraph-style breakpoint, ask-on-the-spot). *Rejected* — violates the
  batched-surface discipline and the unattended premise of a loop; SURFACE stays run-end-batched.
- **Spike + Last-Responsible-Moment, keep working around the fork** (D4). *Deferred, not rejected* — it
  preserves throughput (scoped stall vs the global stall of a RED item) but adds real complexity and a
  global-vs-scoped-stall choice; revisit if global stalls prove too blunt in practice (Open questions).

## Risks

- **Under-determination may not be greppable** (Decision 5, preimage probe — the field's weakest premise). A
  *semantic* fork may leave no one-line signature against the spec text. Mitigation: the preimage probe is a
  **floor**, not a ceiling — the cross-context probe (D3) catches forks it misses; and the drift tripwire is
  the post-hoc backstop. Worst case is a missed fork that surfaces later as drift, not an unsafe act.
- **Cross-context probe is blind when all *k* samples share the same wrong answer** (stated by the research
  lens). Mitigation: it is used **only** to *trip escalation*, never to upgrade confidence — so its blind
  spot can only *miss* a fork, never bless one. And it is cost-gated (run only on suspected/high-stakes
  forks), since *k* fresh contexts per pass is expensive.
- **Oracle-expressibility assumption** (Decision 4): autonomous resolution presumes enough real forks ship a
  frozen `forbid:`/`verify:` predicate. If few do, almost everything defers and the loop stalls often —
  acceptable (a stall is the safe degradation), but it caps the autonomy win. The DoD/spec author owns
  predicate quality (same bargain as oracle-incompleteness in the YOLO doc).
- **green-the-suite has no plan file or ledger to host a RED item** (see Open questions) — **resolved at
  build time (2026-06-24) toward a lazily-created `LOOP_DECISIONS.md` sidecar**, not the degrade-to-immediate-
  stop-and-surface this bullet originally proposed. The sidecar is created only on the first detected fork, so
  the anchor stays ceremony-free until a fork appears; it then hosts a `- [ ] DECIDE:` RED item (reusing the
  checklist count) and the stop predicate becomes *suite green AND zero open sidecar items*, letting the bare
  anchor run CLASSIFY autonomously on a reversible fork instead of always deferring.
- This is a **governance** change (it authorizes a *new autonomous act* — resolving a reversible fork). The
  act-fence is unchanged (the seatbelt still blocks merge/push/branch-delete; the YOLO oracle-frozen check
  still gates), but the surface area of "things a loop may do unattended" grows; the up-front gate + the
  mechanical CLASSIFY are the proportional controls.

## Open questions

- **CLASSIFY composition boundary:** exactly when does a fork count as "anticipated" (has a usable
  `forbid:` predicate) vs. "fall through to the rubric"? Likely a per-fork annotation, but the syntax and
  where it lives (the design-doc? the telos `contract:`?) needs settling at build time.
  **RESOLVED (Phase-1 build, 2026-06-24):** the `forbid:` predicates are **executable command annotations in
  the design-doc `## Key decisions` entry** for the fork (one `forbid: <command>` per option), reused by the
  telos and checklist anchors; a checklist/sidecar `- [ ] DECIDE:` item MAY also carry them inline (parallel
  to the existing `verify:` annotation). **Not** a telos `forbid:` key — `telos_check.py`'s `CLAIM_KEYS` is a
  closed, strict set that rejects unknown keys, so a new key would be new code (out of Phase-1 reuse-only
  scope); and **not** the telos `contract:` (a one-line falsifiable assertion, not a runnable command — it
  would break the `check_oracle_frozen.py` reuse). The loop runs `check_oracle_frozen.py` on each predicate
  to confirm immutability, then runs it to rule an option out.
- **green-the-suite hosting:** confirm the degraded "immediate stop-and-surface, no autonomous resolution"
  is the intended behavior for the thin anchor, or whether a minimal sidecar decision file is worth it
  (leaning no — keep the anchor ceremony-free).
  **RESOLVED (Phase-1 build, 2026-06-24): sidecar, NOT degrade.** Erick chose the **minimal sidecar** so the
  bare anchor can run CLASSIFY (and the rule-#2 robustness tie-breaker) autonomously on a reversible fork
  rather than always deferring to the human. It is a **lazily-created** `LOOP_DECISIONS.md` (default; created
  only on the first detected fork, so the anchor stays zero-ceremony until a fork actually appears) that hosts
  a `- [ ] DECIDE:` RED item using the checklist count verbatim. Derived consequence: the green-the-suite stop
  predicate becomes **suite exits 0 AND zero open sidecar `- [ ] DECIDE:` items** (so the RED item makes the
  stall *structural*, per Decision 3 — a green suite with an open fork is not "done").
- **Build the reversibility-depth fuse (B2)?** The only mechanism modeling that reversibility *decays* (a
  two-way door hardens into one-way after N dependent commits). Valuable on long runs; deferred until a real
  long run shows a two-way door hardening unnoticed.
- **DETECT cost threshold:** what utilization / stakes signal promotes a fork from the cheap preimage probe
  to the *k*-sample cross-context probe? (Composes with the session-suspend `check-usage` read.)

## Rollout / migration

Phased, cheapest-and-safest first; each phase is its own reviewed branch (the standard workflow):

1. **Recipe-only, reuse-only (no new code):** the up-front gate (stage 0, design-doc sections), RECORD via
   telos `UNMET` claims, SURFACE via RED anchor item + run-end `AskUserQuestion`, and the **cheap preimage
   probe** for DETECT. Plus the CLASSIFY prose (oracle-elimination + reversibility-rubric-to-defer, reusing
   `check_oracle_frozen.py` and `deliberate`'s triad). This is the whole spine with zero bespoke machinery.
2. **Pilot DETECT:** measure whether the preimage probe catches real forks on one repo; add the
   cross-context disagreement probe only if it misses material cases (it's the expensive rung).
3. **Deferred:** the depth-fuse (B2) and the spike/Last-Responsible-Moment throughput path (D4) — build only
   if practice shows the global-stall RED item is too blunt or two-way doors harden unnoticed.

No data migration. The change is additive to the recipe; an existing loop with none of this behaves exactly
as today.
