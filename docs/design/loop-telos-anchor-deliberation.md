# Deliberation — telos/motive as anchor + halting oracle for a self-paced `/loop`

**Date:** 2026-06-17
**Skill:** `/deliberate`
**Run group:** `loop-telos-anchor-2026-06-17`
**Rung:** full 4-lens panel (stakes read: reversible guidance, low blast radius — panel
seated over the pair floor because the value sought was the divergent angles).
**Roster (toward:caution = 2:2, balanced):** Advocate, Ambition (toward) · Skeptic, Risk
(caution) · Synthesizer (opus, leanings-blind).

## Framing

- **D1** — Should internal-toolkit guidance state that a repo/app/feature's **telos** (or a
  **motive** statement for small scopes) be used as the anchoring spec AND halting oracle for
  a self-paced "Ralph Wiggum" loop (the `/loop` skill, run with no interval so the model
  self-paces)? Or is it premature / wrong / better left unstated?
- **D2** (conditional) — What **form**? Proposed = cross-link note in `loop` + reciprocal
  pointers from `telos`/`audit-telos`, with a caveat that the verification leg stays
  independent (loop writes witnesses but does not self-bless). Alternatives surfaced: do
  nothing; a worked recipe; a guardrail/constraint-only note; a heavier scripted halting
  mechanism; a new dedicated skill.

The Synthesizer found D1 and D2 **coupled** — the *form* IS the decision (an encouraging
recipe and a guardrail restraint are different verdicts, not one verdict at two resolutions).

## Verified facts the panel reasoned from

- `/loop` self-paces via scheduled wakeups; `telos`/`audit-telos` exist (per-repo claim
  ledger with discharge+witness criteria; coverage/orphan surfacing). All already ship.
- telos evidence-tier demotes **unbacked** `DISCHARGED` → `SUSPECT` at parse time.
- KNOWN HAZARD: telos discharge is surface/claim-based, NOT a correctness guarantee; an
  independent pre-merge-review once falsified a self-reported discharge.
- VC norm: on review SIGN-OFF, work auto-merges (`--no-ff`) and **deletes the branch**
  (human gate is up-front).
- UNVERIFIED: no measured instance of a Ralph loop drifting/declaring premature victory in
  this user's practice; no evidence loops are being run against telos repos yet; telos
  coverage ~18–29% (most repos/claims have no telos); current `loop`/`telos` SKILL.md
  contents not re-read; whether "motive" is a formalized artifact or ad-hoc prose.

## Positions (steelmanned)

- **Advocate** — Adopt. Telos gives a self-paced loop what an ad-hoc prompt can't: a durable
  out-of-context anchor (kills drift) and a checkable stop predicate via audit-telos coverage
  (kills premature victory). Cross-link fits the "don't absorb" norm; reversible; positive-EV
  even under unverified premises. *R2: conceded the SUSPECT-routing point below; pivoted to a
  harder shape (stop-and-surface), not nothing.*
- **Ambition** — Under-building is the real risk: a self-paced loop without a durable anchor
  is a blind autonomous agent that fails silently. A bare pointer is too timid — it names the
  hazard without giving the seam. Ship a worked recipe (halt = audit-telos coverage, not
  self-assessment; discharge-judging = a different invocation). *R2: converged with Risk
  (stop-and-surface); conceded in-loop independence is impossible — recipe must forbid in-loop
  discharge; pointer-only or nothing.*
- **Skeptic** — No. Problem unwitnessed; addressable population possibly empty (coverage
  18–29% ∩ being-looped). Worse, telos discharge is surface-not-correctness → anchoring an
  unsupervised loop's halt on it is a Goodhart engine; "independent verification" is
  unenforceable by a note; "motive" fallback is vapor. *R2: moved partway — still rejects the
  affirmative recommendation, but a guardrail-only restraint clears its bar (EV scales with
  blast radius, not frequency).*
- **Risk** — Yes, but the hazard is under-stated: a witness-writing loop produces **backed**
  claims, so the SUSPECT demotion (fires only on *unbacked*) is routed around by construction;
  "independent" is unenforceable when the loop is the only agent awake; blast radius =
  unattended auto-merge/branch-delete on a false "all discharged." Mandate stop-and-surface,
  never stop-and-act, or ship nothing. *R2: conceded stop-and-surface relocates Goodhart onto
  the reviewer's attention rather than eliminating it — say so explicitly; ship the constraint,
  defer the inviting recipe.*

## The real crux vs. vocabulary disputes

- **Resolved (not real):** cross-link vs. recipe (all agree a *bare* pointer under-builds);
  "independence" (all agree in-loop independence is impossible — the writer can't self-check
  that backed ≠ correct).
- **The one real crux:** does writing this guidance **recommend** a near-empty, unobserved
  workflow (fails the premature-guidance bar), or **constrain** a hazardous capability that
  already ships (`/loop` + telos + auto-merge)? — Resolved **toward constraint**: all four
  lenses ended in the same cell (adopt a guardrail, defer the recipe).

## Verdict (D1+D2, coupled): Adopt as a guardrail/restraint, NOT an encouraging recipe

Ship a constraint note, cross-linked between `loop` and `telos`/`audit-telos`, whose
load-bearing content is a **behavioral contract**:

1. **A self-paced loop CANNOT discharge its own halt.** Reading the telos ledger as durable
   anchoring spec (re-read each iteration, outside compacting context) is the one affirmative
   thing worth saying. The loop's only legal terminal state is *"stopped, surfaced, awaiting
   an out-of-loop actor."*
2. **Stop-and-surface, never stop-and-act.** Name the prohibited actions: never auto-merge,
   never delete a branch, never mark a claim discharged on the loop's own witnesses.
3. **Anti-self-bless callout, stated honestly:** because the loop *writes* witnesses, the
   `SUSPECT` demotion (unbacked-only) is routed around by construction; discharge-judging is a
   *different invocation* (audit-telos / pre-merge-review) by a different actor. The guardrail
   makes failure non-catastrophic and human-legible — it does **not** make it absent.
4. **The "motive" fallback is the most exposed path** (no discharge criteria). Don't build
   affirmatively on it; mention only to warn.

**Ship teeth or ship nothing** — a defanged "see also" launders endorsement onto a hazard.
Rejected: do-nothing (hazard already exists); encouraging recipe as primary framing (invites
an unobserved workflow); soft caveat/bare pointer (can't encode the contract); scripted halt /
new skill (duplicates ledger semantics; a scripted *acting* halt is the catastrophe itself).

**Deferred sub-decision:** the encouraging worked recipe — defer until ≥1 real self-paced loop
run against a telos-bearing repo is observed.

## Preserved dissent

Residual disagreement is a **dial, not a fork**: how much *affirmative* "you may use the ledger
as your re-read anchor" to include. Skeptic wants near-zero affirmative content; Ambition/
Advocate want the *safe* wiring shown. Both agree the spine is the prohibition.

## Prediction blocks

### D1+D2 (coupled)
- **crux:** recommendation of an unobserved workflow vs. constraint on an already-shipping
  hazard — resolved toward constraint.
- **tip-condition:** if, after shipping, a self-paced loop is observed to reach an *acting*
  terminal state (auto-merge / branch-delete / self-marked-discharge) against a telos repo
  despite the guardrail (prohibition proves unenforceable-by-prose), the verdict flips toward a
  **scripted/mechanical** stop-gate.
- **testable-claim:** a guardrail note ("a self-paced loop must stop-and-surface and may never
  self-bless/merge/delete on its own telos witnesses") prevents the catastrophic
  auto-merge-on-false-discharge path at near-zero cost without recommending an unobserved
  workflow.

### Deferred recipe
- **crux:** is there a real, recurring population of `/loop` runs against telos-bearing repos?
- **tip-condition:** ≥1 actual self-paced loop run against a telos repo where read-spec /
  stop-and-surface wiring would have helped → upgrade restraint to a worked recipe, re-run D2.
- **testable-claim:** until such an instance exists, an encouraging recipe addresses a
  near-empty population and is correctly deferred.

### Honesty note (flagged, no verdict)
- **crux:** even a perfect stop-and-surface loop relocates Goodhart pressure onto the
  reviewer's attention budget (machine-scale plausibly-backed-but-possibly-wrong witnesses).
- **tip-condition:** if out-of-loop reviewers begin rubber-stamping loop-generated witnesses
  (review attention saturates), an upstream throttle on loop witness-volume becomes warranted.
- **testable-claim:** the guardrail makes loop failure non-catastrophic and human-legible; it
  does not make it absent — and the note must say so.

## Bottom line

Adopt — ship the **anti-self-bless restraint** (cross-linked, named prohibited actions, honest
"SUSPECT is routed around" callout), **not** an encouraging recipe; defer the recipe until a
real looped-telos instance exists; ship nothing if the note can't carry teeth.

---

# Addendum — brainstorm re-widening + premise spike (2026-06-17)

After the verdict was deferred, a `/brainstorm` re-widened the option space ("how should a
self-paced loop know it's done and trust completion without self-blessing?"), then the three
load-bearing premises were spiked before any further debate.

## Shortlist the brainstorm produced (3 finalists, which turned out to *compose*, not compete)

1. **Containment floor** — a PreToolUse merge-gate + "loop can't invoke merge" → the substrate.
2. **Frozen external oracle** — telos `verified-by:` (executable, exit-code-trusted-over-LLM) as
   the affirmative done-signal for *test-expressible* claims.
3. **Falsification budget** — a fresh, independent reviewer must fail to break "done" → the
   affirmative signal for *non-test-expressible* claims (plugs the BACKED-but-bogus hole).

Preserved outlier (a finding, not an idea): LLM self-preference bias is **perplexity-driven**, so
a fresh-*context* same-model Ralph iteration does **not** escape it — independence needs a
*separate* spawn (ideally different model / differently prompted), not just a fresh context.

## Spike results (the probe-first rung)

- **P3 — is every merge route hookable? PARTIAL.** The only existing PreToolUse hook matched
  `Edit|Write|NotebookEdit`, not `Bash`; git VC actions ran un-hooked. A Bash-matcher gate is
  buildable (and now built) but string-parsing is not airtight (raw `git`, `gh`, scripts can
  bypass) → seatbelt, not sandbox.
- **P1 — is a discharge probe authorable up-front? YES for test-expressible claims, NO for prose.**
  telos `verified-by:` already provides an executable, loop-unauthored oracle whose exit code is
  trusted over the LLM, and it is in active use (downstream-repo pytest suites; live telos records
  in other private repos). It does not extend to judgment/prose claims — the RLVR floor, confirmed.
- **P2 — do fresh falsifiers catch a BACKED-but-bogus witness? SUPPORTED (2/2).** Two independent
  fresh reviewers both FALSIFIED a green-but-vacuous witness (a passing test that never exercised
  the claimed invariant), each naming the code gap and the test gap. Caveat: catchable case; the
  RLVR ~40% gap still applies to subtler/non-verifiable claims; this does not refute the
  self-preference finding (that is about a *self*-judging agent, not a fresh spawn).

**Net:** the spike dissolved the layer-2 crux — the finalists partition by claim type rather than
competing, so a `/deliberate` on layer 2 would likely return a non-decision. The one surviving
judgment is still the empty-population call → build the cheap floor now, defer the rest.

## What was BUILT (layer 1 — the containment floor), 2026-06-17

- **`~/.claude/hooks/guard-loop-vc.py`** — a PreToolUse `Bash` guard, **opt-in via
  `CLAUDE_LOOP_GUARD`**. While set, it blocks `git merge`/`push`/`branch -d|-D`/`reset --hard`/`worktree remove` and
  `gh pr merge` (allows `commit`, `log --merges`, `merge-base`, `branch --merged`, `switch -c`).
  Fails open on any parse/IO fault (never wedges the tool), same contract as `guard-default-branch.py`.
- **Registered** in `~/.claude/settings.json` (new `Bash` PreToolUse matcher) and **wired into
  `scripts/install.sh`** so a fresh host symlinks the hook and ensures the registration idempotently
  (the pre-merge review caught that the installer would otherwise leave the hook inert).
- **Tested** — `hooks/tests/test_guard_loop_vc.py` pins the deny set (incl. compound `&&`,
  background `&`, and env-prefix bypasses), the safe-read allow set (`merge-base`, `log --merges`,
  `branch --merged`, `gh pr view/checkout/list`), the opt-in gate, and the fail-open contract.
- **Documented** in the global CLAUDE.md VC section ("Autonomous loops are stop-and-surface, never
  stop-and-act") + reciprocal pointers in the `telos` and `audit-telos` skills + the hooks' install notes.
- `/loop` is a **built-in** skill (not an editable SKILL.md) and sets no loop-context marker, so the
  guard is deliberately opt-in rather than auto-detected. Limit: Bash string-parsing → seatbelt, not
  sandbox; prefer also not granting an unattended loop a merge capability.

## BUILT (layer 2 — the recipe), 2026-06-18

The generative half is now shipped as the **`telos-loop` skill** (`skills/telos-loop/SKILL.md`), the
runnable answer to the original question. It is a *recipe, not an engine* — one invocation = one loop
iteration (re-read the ledger → advance one actionable claim → commit on the loop branch → stop-and-surface
or let `/loop` re-fire), driven by `/loop /telos-loop <repo>` under `CLAUDE_LOOP_GUARD=1`. It encodes the
layer-1 contract (stop-and-surface, never stop-and-act) and the claim-type split below (frozen `verified-by`
oracle for test-expressible claims vs. independent out-of-loop falsifier for prose/judgment claims; the loop
never authors-then-self-passes a witness). No bespoke halting machinery was added — `audit-telos` supplies
the progress signal and `guard-loop-vc.py` enforces no-act. Cross-linked reciprocally from `telos` and
`audit-telos`. The original deferral (below) was lifted by an explicit build request; the
spec it laid out is what was built.

### The spec it was built to (was: DEFERRED until a real looped-telos instance exists)

1. **Code/test-expressible claims → frozen `verified-by` oracle.** Require the discharge witness to
   be an executable `verified-by:` authored *before* the loop ran (or by a separate up-front pass),
   re-run in a clean checkout the loop didn't author; disagreement ⇒ FALSIFIED, not SUSPECT. Mostly
   already exists — the work is enforcing "loop may run but not author/edit the witness."
2. **Prose/judgment claims → falsification budget.** Before a claim flips to discharged, K fresh
   *independent* reviewers (separate spawns; prefer different model / differently-prompted, per the
   perplexity-bias finding) must each fail to name remaining/incorrect work. Reuse
   `pre-merge-review` / `grill-me` / `re-audit-repo`. Honest residual: ~40% gap on subtle cases.
3. **Both ride on the layer-1 floor** — the loop never acts; it surfaces, and (1)/(2) run out-of-loop.

Wildcards kept on the table: default-run/external-halt (loop never self-evaluates; an external
unforgeable token halts it); ratchet-not-resolve (halt when the loop can't *name* real remaining
work); quiescence as a stop-and-surface *trigger*, never a verdict.

---

# See also — verifiable-autonomy ("YOLO") posture (2026-06-19)

The **frozen external oracle** (brainstorm finalist #2 above) is developed into a third trust posture in
[`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md) — extending it from *checking* the
loop's work to *permitting the loop to act* (distinct from the "external unforgeable halt token" wildcard,
which only *halts*). There the never-act rule is
**scope-specific, not universal** — load-bearing for *judgment/prose* claims (self-preference bias),
but only belt-and-suspenders for *test-expressible* claims gated by a **frozen, loop-immutable**
oracle, where "done" is an unforgeable external signal rather than the LLM judging itself. That doc
re-keys the guard fence from "all VC mutation" to **reversibility + external-side-effect**, so a loop
may autonomously complete *and integrate* verifiable work while destructive/irreversible/external acts
stay denied.
