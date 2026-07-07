# ralph-loop — checklist anchor — Design

**Date:** 2026-06-19
**Status:** SHIPPED 2026-06-19 (local-only, opus pre-merge-review). The build-gate override is recorded below.
**Completes:** the third and final anchor of [`ralph-loop`](../../skills/ralph-loop/SKILL.md). Sibling to
[`ralph-loop-green-the-suite.md`](ralph-loop-green-the-suite.md) (the prior anchor + the pluggable-anchor
shape) and [`loop-telos-anchor-deliberation.md`](loop-telos-anchor-deliberation.md) (the original loop
deliberation). Pairs with [`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md) (the YOLO
posture — whose boundary this anchor sits squarely *outside* of by default).

## Context / problem

`ralph-loop` is the shipped pluggable-anchor recipe for a self-paced "Ralph Wiggum" `/loop`: one invocation =
one iteration (re-read a durable, out-of-context spec from disk → advance one unit → commit → stop-and-surface,
or let `/loop` re-fire). Two anchors ship: **telos** (the claim ledger) and **green-the-suite** (a failing
test set). This adds the third and final anchor, **checklist** — drive the loop from a **plan/checklist file**
(markdown `- [ ]`/`- [x]` items), with **items-remaining** as the progress signal.

This is the **canonical, origin "Ralph Wiggum" form** (Geoffrey Huntley's `fix_plan.md`/`PROMPT.md` loop): a
prioritized plan file, "do only one thing per loop," re-read the plan each pass. It is also the broadest
anchor — it needs neither a telos ledger nor a red test suite, only a plan a human can write in any repo.

### Gate-override (recorded honestly, as prior overrides were)

The roadmap gated checklist "until the first real need to loop a repo with a plain checklist." **No such
instance was witnessed.** Erick authorized the research + this build anyway (2026-06-19) — the same pattern by
which `telos-loop`, `ralph-loop`/green-the-suite, and each YOLO phase were built ahead of their gate. This is
a deliberate build-gate override, not a witnessed trigger. With it, **all three anchors ship**; only the
design-doc'd-but-unbuilt *external-unforgeable-halt-token* wildcard remains (the `ratchet-not-resolve` stop
predicate is already realized inside the green-the-suite and checklist anchors, so it is not an open item).
This matches the accounting in `ROADMAP.md` and the YOLO design record.

## Goals & non-goals

**Goals**
- A **checklist** anchor section in `ralph-loop/SKILL.md`, mirroring `## Anchor: telos` / `## Anchor:
  green-the-suite`: spec = a plan file; pick = the highest-priority unchecked item; progress = unchecked-count
  ratchet; stop = zero unchecked (success) or no-progress (stuck).
- Reuse the existing anchor-independent core verbatim (fresh re-read, one-unit-per-iteration, commit,
  no-self-bless, stop-and-surface, the `--yolo` posture). The checklist anchor adds **no new core**.
- A **per-item `verify:` unifier**: a checklist item MAY carry its own command. A bare-prose item is
  judgment work (no YOLO); an item with a *frozen* `verify:` oracle degrades into a test-expressible unit
  dischargeable/YOLO-able via the **existing** `check_oracle_frozen.py`. This unifies all three anchors.

**Non-goals**
- *Not* a new skill — checklist is an anchor *section* inside `ralph-loop` (Erick's chosen parent/alias
  topology; mirrors how telos and green-the-suite live).
- *Not* a new freeze script. A checklist has **no freezable surface** — the loop is *meant* to edit the plan
  file (it ticks its own boxes). "Freezing the plan" is incoherent. Per-item `verify:` oracles reuse
  `check_oracle_frozen.py`; nothing new is needed. (This is the load-bearing scope call — see Key decisions.)
- *Not* a bespoke checklist parser/engine. The loop reads the plan file itself; we do **not** build a
  `- [ ]` counter (KISS / "don't build a loop runner"). See the Open questions resolution.
- *Not* lifting never-act for prose. A ticked box is a **claim, not an oracle** — the checklist anchor
  **hard-refuses blanket YOLO** by default (see below).
- *Not* touching `guard-loop-vc.py` — checklist inherits `=1` stop-and-surface and the `=yolo` mechanics
  unchanged.

## Approach

### The anchor slots (filling the pluggable shape)

| Beat                | checklist anchor                                                        |
|---------------------|-------------------------------------------------------------------------|
| **Spec source**     | a plan file (default `IMPLEMENTATION_PLAN.md`; `--plan <path>` to override), re-read from disk each pass |
| **Progress signal** | count of unchecked (`- [ ]`) items — a monotone-decreasing ratchet      |
| Pick one unit       | the highest-priority (top-most) unchecked item — exactly one per loop   |
| Do the work         | implement that item on the loop branch                                  |
| Discharge / stop    | per-item: prose (out-of-loop falsifier) or frozen `verify:` oracle; stop at 0 unchecked (success) or no-progress (stuck) |

The anchor-independent core is untouched; only these two slots are new.

### checklist, concretely

- **Spec source / invocation.** The loop is launched with the repo and (optionally) the plan path. `/loop`
  re-fires the invocation verbatim, so the plan path is the persisted out-of-context anchor (the analog of
  the ledger path / suite command). Each iteration **re-reads the plan from disk** — never trusts a
  remembered item list. **Reconcile plan-vs-code each fire** ("search the codebase, don't assume an item is
  un-done just because its box is unchecked") — this is the anti-drift discipline the origin and snarktank
  both stress.
- **Pick.** The highest-priority unchecked item — top-most in a priority-ordered plan — exactly one per
  iteration ("only one thing per loop").
- **Progress signal / stop predicate** (`ratchet-not-resolve`, the same generalization as green-the-suite):
  - **Done** — zero unchecked items → stop-and-surface (success).
  - **Stuck** — an iteration fails to *reduce* the unchecked count → stop-and-surface (can't advance).
  - Otherwise (count dropped, items remain) → re-fire.
  **Do NOT** use "the loop says it's done" as the predicate — the unchecked count, computed by re-reading the
  file, is the signal. We **deliberately do not adopt a `--max-iterations` cap** (Anthropic's plugin makes it
  the *only* guard): the recipe is stateless across fires (each re-reads from disk and remembers nothing), so
  a fresh context has no place to keep a fire-counter, and building one violates the no-engine rule. The
  ratchet already terminates a spinning loop on its next no-progress iteration, so the cap would be redundant
  machinery — and neither the telos nor green-the-suite anchor has one. (See Alternatives.)

### The crux: checklist is the PROSE / JUDGMENT member of the anchor trio

This is the load-bearing finding. Contrast the three anchors by *who authors the done-signal*:

- **green-the-suite** — the done-signal is a **suite exit code**: an unforgeable external oracle the loop
  cannot author (and `check_suite_frozen.py` proves it didn't edit the suite). → YOLO-able.
- **telos** — per-claim: a `verified-by:` test is an oracle (YOLO-able, gated by `check_oracle_frozen.py`); a
  bare prose claim is judgment (stop-and-surface).
- **checklist** — the done-signal is **"all boxes ticked," and the loop ticks its own boxes.** The plan file
  is loop-writable by design. A checked box is therefore a **self-authored claim**, *exactly* the proxy
  signal that OpenAI's `/goal` design names as the deepest LLM-agent failure mode, and exactly the
  self-preference hazard the no-self-bless rule exists to fence. Huntley (the origin) independently lands
  here: he explicitly *distrusts the agent's self-assessment*, leans the real stop on the test suite + human
  review of the plan, and periodically regenerates the TODO to fight drift.

So checklist **inherits telos-loop's prose treatment by default**: stop-and-surface, never self-bless, and
**HARD-REFUSE blanket YOLO**. A ticked box does not permit the loop to act.

### The per-item `verify:` unifier (the one YOLO path)

A checklist item MAY carry its own verification command — the convention several real Ralph variants adopt
(snarktank runs quality checks before flipping `passes:true`; Huntley leans on passing tests). We adopt this
as the *single* graceful escalation:

- **Bare-prose item** (`- [ ] Refactor the auth flow`) → judgment work → stop-and-surface; **no YOLO**.
- **Item with a frozen `verify:` oracle** (`- [ ] Add retry … verify: pytest tests/test_retry.py`) →
  degrades into a **test-expressible unit**, dischargeable/YOLO-able through the **existing**
  `check_oracle_frozen.py` (freeze the `verify:` command's file at base; require it green) — *identical* to a
  telos claim with a `verified-by:`. No new mechanism.

This unifies all three anchors under one rule: **an item/claim is YOLO-able iff it is gated by a frozen,
loop-immutable oracle the loop cannot author.** checklist is prose by default, test-expressible per-item when
a frozen `verify:` command is attached.

## Key decisions

1. **checklist is an anchor *section* in `ralph-loop`, not a new skill.** Mirrors telos / green-the-suite
   (Erick's parent/alias topology, decided 2026-06-19).
2. **checklist is the prose/judgment anchor: stop-and-surface, hard-refuse blanket YOLO.** A ticked box is a
   loop-authored claim, not an oracle. This is the *correct* application of the YOLO doc's boundary (decision
   5: oracle/DoD completeness is the author's responsibility), not a limitation.
3. **No new freeze script.** A plan file the loop is *meant* to edit has no freezable surface; "freezing" it
   is incoherent. Safety = refusing to trust the loop-written signal (the existing no-self-bless contract),
   not a new immutability mechanism. The build is **doc-only** (+ the per-item `verify:` reuse).
4. **Per-item `verify:` unifier = the single YOLO path.** A frozen per-item oracle reuses
   `check_oracle_frozen.py`, identical to a telos `verified-by:`. Bare-prose items never YOLO.
5. **No checklist-counter helper.** The loop reads the plan and counts `- [ ]` itself; building a parser
   violates "don't build a loop runner" and KISS. (Revisit only if a reviewer calls the ratchet
   unverifiable — it isn't: re-reading and counting is a one-line `grep -c`.)
6. **Stop = unchecked-count ratchet** (done-at-0 / stuck-on-no-progress), never "the loop says done." Same
   `ratchet-not-resolve` shape as green-the-suite. **No `--max-iterations` cap** — the recipe is stateless
   across fires (no place for a fire-counter without an engine), the ratchet already halts a spinning loop,
   and neither sibling anchor has one.
7. **Default plan path `IMPLEMENTATION_PLAN.md`, `--plan` to override.** A canonical wild name (alongside
   `fix_plan.md` / `PLAN.md`); explicit and discoverable. The flag keeps it portable.

## Alternatives considered

- **Make checklist YOLO-able like green-the-suite** (treat "all boxes ticked" as the done oracle). *Rejected
  — the central error.* The loop authors the boxes; "all checked" is a self-blessed proxy, the exact
  self-preference hazard YOLO was scoped to *exclude*. Only a per-item *frozen external* oracle escapes this.
- **Build a `check_plan_frozen.py`** mirroring `check_suite_frozen.py`. *Rejected* — incoherent: the plan
  file is the thing the loop edits. There is no surface to freeze. Safety comes from distrust of the signal,
  not from pinning the file.
- **Build a `- [ ]`/`- [x]` counter/parser helper** to make the ratchet mechanical. *Rejected (KISS)* — the
  loop re-reads the file and counts unchecked boxes itself; a parser is an engine the recipe forbids. The
  ratchet is already mechanical (`grep -c '^[[:space:]]*- \[ \]'`).
- **Adopt Anthropic's `ralph-wiggum` plugin shape** (loop *in-session* via a Stop hook; exact-string
  completion promise; `--max-iterations` the only guard; no anti-premature-completion). *Rejected — recorded
  as a deliberate divergence.* In-session looping is the **context-overflow failure** the canonical Ralph
  warns against, and it discards our fresh-re-read anti-drift property. Our `/loop` fresh-context +
  no-self-bless contract is strictly more conservative and matches the origin's discipline. We also **reject
  its `--max-iterations`-as-sole-guard** model: a stateless recipe can't keep a fire-counter without the
  engine we refuse to build, and the unchecked-count ratchet already terminates a non-advancing loop.
- **A new skill `checklist-loop`** paralleling the old telos-loop split. *Rejected* — the parent/alias
  topology (decision 1) puts anchors as sections; a fourth skill would re-fragment the recipe.

## Risks

Security-relevant (a loop that could act under a mis-applied YOLO) → `threat-model` lens; controls inherited
from [`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md).

- **Asset:** repo integrity + the irreversible/external action surface (unchanged from the YOLO doc).
- **Self-blessed completion (the loop ticks its own box and calls it done).** *Control:* checklist is prose
  by default — stop-and-surface, hard-refuse blanket YOLO; the stop predicate is the re-read unchecked count,
  not the loop's say-so; out-of-loop falsification at the merge gate. **This is the primary risk and it is
  the reason for the prose treatment.**
- **Placeholder / shallow "done" (box ticked, work not real).** *Control:* reconcile-plan-vs-code each fire;
  the box ≠ the work; independent out-of-loop falsifier confirms. **Mitigated, not eliminated** — the named
  residual of any judgment anchor (~40% gap on subtle non-verifiable items, per the no-self-bless note).
- **Plan drift (plan and code diverge; stale or fabricated items).** *Control:* re-read + reconcile each
  pass; optional periodic plan regeneration (origin practice). **Residual** — author discipline.
- **Per-item `verify:` Goodhart (oracle green-but-wrong, or incomplete).** *Control:* `check_oracle_frozen.py`
  + oracle-authorship discipline — the same accepted bargain as telos `verified-by:` (YOLO doc decision 5).
  **Residual, pushed onto the item author.**
- **Guard bypass / seatbelt-not-sandbox / git-hook side effects.** Inherited unchanged from the YOLO doc;
  checklist adds no new guard surface.

## Open questions

*(Resolved during this build; kept as the decision record.)*

- **Does checklist get ANY YOLO?** RESOLVED: **none by default** (prose); only a checklist item carrying its
  own *frozen* `verify:` oracle may act, via the existing `check_oracle_frozen.py`. (decisions 2, 4)
- **Build a checkbox-counter helper?** RESOLVED: **no** (KISS; the loop counts the file itself). (decision 5)
- **Default plan path / format?** RESOLVED: `IMPLEMENTATION_PLAN.md` default, `--plan` override; markdown
  `- [ ]`/`- [x]`, optional per-item `verify:`. (decision 7)
- **A new freeze script?** RESOLVED: **no** — incoherent for a loop-edited file. (decision 3)

## Rollout / migration

- **Phase 1 ✅** — design doc (this file).
- **Phase 2 ✅** — `ralph-loop/SKILL.md`: add `## Anchor: checklist`; update the pluggable-anchor table +
  "When to use"; remove the "checklist anchor — deferred" callout; extend the YOLO per-unit gate with the
  checklist case (prose → hard-refuse; per-item frozen `verify:` → existing `check_oracle_frozen.py`).
- **Phase 3 ✅** — `scripts/validate.py` green; re-check the (near-cap) `ralph-loop` description length.
- **Phase 4 ✅** — `ROADMAP.md`: flip checklist to shipped, update the header status; cross-link this doc from
  the green-the-suite + YOLO design records.
- **Phase 5** — independent `/pre-merge-review` → merge `--no-ff` (local-only, never push).
- **Default unchanged** — no behavior change to telos / green-the-suite; checklist is purely additive.
- **No new script, no new test surface** — the per-item `verify:` path reuses `check_oracle_frozen.py` (and
  its existing tests) verbatim.
