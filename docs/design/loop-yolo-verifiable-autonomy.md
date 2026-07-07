# Loop YOLO-mode — verifiable autonomy — Design

**Date:** 2026-06-19
**Status:** shipped — Phases 0–3 built 2026-06-19 (see the status note at the end of this doc; the
header previously read "design (unbuilt)" and was corrected at extraction)
**Extends:** [`loop-telos-anchor-deliberation.md`](loop-telos-anchor-deliberation.md) — builds on that doc's
brainstorm **finalist #2, the "frozen external oracle"** (telos `verified-by:`, exit-code-trusted-over-LLM
as the affirmative done-signal for test-expressible claims). That oracle was scoped there to *checking* the
loop's work; this doc lets it also *permit the loop to act*. (Distinct from the related "external unforgeable
halt token" wildcard, which is a *halt* mechanism, not a permit-to-act one.)

## Context / problem

The shipped loop containment — [`guard-loop-vc.py`](../../hooks/guard-loop-vc.py) plus
telos-loop's "stop-and-surface, never stop-and-act" — treats *never-act* as a **universal** rule. It is
not. Its justification (per the prior deliberation) is **LLM self-preference bias**: a loop can't trust
its own "done," because a loop that writes its own witnesses produces *backed* `DISCHARGED` claims that
route around telos's `SUSPECT`-demotion guard.

That argument only covers **judgment / prose** claims. For a **test-expressible** claim gated by a
**frozen, loop-immutable oracle**, "done" is an *unforgeable external signal* (an exit code trusted over
the LLM), **not** the LLM judging itself — so the self-preference argument evaporates. On that branch the
universal never-act rule is **belt-and-suspenders, not load-bearing**, and it is over-broad: it stops the
loop from autonomously completing *and integrating* verifiable work, which is a primary power of LLM-driven
development. We want a **YOLO-mode**: the loop may act through to a verifiable Definition of Done, fenced
only against genuinely destructive / irreversible / external acts.

## Goals & non-goals

**Goals**
- A third trust posture on the ralph/telos loop where the loop **may act** (including integrate) to a
  machine-verifiable DoD, when that DoD is gated by a **loop-immutable** oracle.
- Re-key the guard from "block all VC mutation" to "block destructive / irreversible / external acts" —
  splitting git operations *across* the reversibility line instead of parking them all on the deny side.
- Make the frozen-oracle property **mechanical** — the loop cannot author or edit the oracle that gates it.

**Non-goals**
- *Not* lifting never-act for **judgment / prose** claims — no unforgeable signal exists there; they stay
  stop-and-surface.
- *Not* permitting push-to-remote, force-push, default-branch mutation, outward sends (email/IM/HTTP POST),
  deploys, DB drops, or money — denied **regardless** of DoD verifiability.
- *Not* a bespoke loop engine — still recipes over the built-in `/loop` + PreToolUse hooks.
- *Not* changing the default. YOLO is opt-in; absent the posture, behavior is exactly today's
  stop-and-surface (backward compatible).

## Approach

Two **orthogonal** axes decide whether a loop may act on its own "done":

**Axis A — done-signal trust**
- *Verifiable* — frozen, loop-immutable oracle (exit code), trusted over the LLM → loop **may** trust "done."
- *Judgment* — LLM / prose → self-preference bias is live → loop may **not** trust "done."

**Axis B — act blast radius**
- *Reversible & internal* — commit; a **`--no-ff`** merge into a *non-default* branch; branch ops on a
  non-default branch. The `--no-ff` merge is durably reversible via `git revert -m 1` — a forward, in-history
  undo that does **not** depend on reflog; a fast-forward merge leaves no merge commit to revert and is
  therefore *excluded* (the allowed merge is `--no-ff` only). The **commit / branch-op** cases instead
  recover via **reflog**, which is *local mutable* state that **expires** (gc / `git reflog expire`) — so for
  those, "reversible" means "recoverable for a bounded window on this host," not "undoable forever."
- *Irreversible | external* — push (all forms, incl. force-push); default-branch mutation; `reset --hard`;
  **`clean -fdx`** (deletes untracked files with **no reflog** — strictly worse than `reset --hard`); outward
  sends; deploys; DB drops; money → unrecoverable or externally observable.

> **YOLO permission = (Axis A = verifiable) AND (Axis B = reversible & internal).**
> The loop runs to a green oracle and integrates **within the reversible fence**; anything in the
> irreversible-or-external quadrant stays denied and is surfaced for an out-of-loop actor.

This is the precise correction to the prior framing: the fence is **reversibility + external-side-effect**,
*not* the git/non-git boundary. `git merge` into a throwaway branch in a local repo is VC-mutating but
**reversible**; sending a Telegram message is **not VC at all** but irreversible+external. They belong on
opposite sides of the fence.

**Mechanics (sketch)**
- **Posture is explicit.** A `--yolo` posture (or trust-level) on telos-loop / ralph-loop; the guard reads a
  mode value (e.g. `CLAUDE_LOOP_GUARD=yolo` vs. the current `1`). Default = conservative stop-and-surface.
- **Guard becomes two-mode.** `1` keeps today's deny set unchanged. `yolo` swaps to a **destructive-only**
  deny set that **keeps** today's denials — `push` (all forms; the current guard blocks every `git push`, so
  no separate `--force` parsing is needed), `reset --hard`, `worktree remove`, `gh pr merge` — and **adds**
  default-branch merge and `git clean -fd[x]`. It then **allows** a `--no-ff` merge into a non-default
  *local* branch.
  - ⚠ **`clean` is NOT in today's deny set** — [`guard-loop-vc.py`](../../hooks/guard-loop-vc.py)
    `_classify()` never inspects it. YOLO must *add* it, not inherit it; otherwise widening the allow set
    ships an open irreversible hole.
- **Oracle-immutability precondition.** Before YOLO acts, verify the gating oracle is unwriteable by the loop
  (out-of-tree, or hash-pinned and checked). If the loop touched the oracle this iteration → YOLO refuses,
  falls back to stop-and-surface.
- **Claim-type refusal.** YOLO is legal only on **test-expressible** claims with a frozen `verified-by:`
  oracle. Prose / judgment claims **hard-refuse** YOLO, no override.

## Key decisions

1. **Never-act is scope-specific, not universal** — keyed on *done-signal trust*, not on "is this a VC op."
   This reverses the implicit universal framing in the shipped guard's docstring.
2. **The fence is reversibility + external-side-effect**, not the git/non-git boundary; git operations split
   across it.
3. **Oracle immutability is mechanical, not conventional.** Today's "may run, not edit" is enforced by the
   out-of-loop human's attention; YOLO removes that human, so reward-hacking the oracle must be closed
   *mechanically* (out-of-tree / hash-pin + refuse-if-touched).
4. **YOLO is opt-in and posture-explicit; the default is unchanged.** Two guard modes; omitting the posture
   is today's behavior.
5. **Goodhart on oracle incompleteness is an accepted, named bargain** pushed onto the DoD author — exactly
   the "provided that definition is verifiable" condition. The DoD's *completeness* is the human's
   responsibility; YOLO does not pretend to verify the verifier.

## Alternatives considered

- **Keep universal never-act (status quo).** Rejected — over-broad; cripples verifiable autonomy for a
  self-preference reason that doesn't apply to frozen-oracle claims.
- **Lift the guard entirely under YOLO (true "yolo").** Rejected — destructive/external acts are
  irreversible *regardless* of DoD verifiability. The value sought is autonomous *work + integrate*, not
  autonomous *destruction*.
- **Convention-only oracle freeze** (the loop "shouldn't" edit its gating test). Rejected — without the
  human reviewer, an unconstrained loop can weaken/delete the oracle to force green. Must be mechanical.
- **Per-step approval ramp only** (the "Loop Training Mode → flip OFF" pattern from the source video).
  *Partial.* The ON state is a fine *interactive training* ramp, but its terminal "fully autonomous OFF" has
  **no** oracle / immutability / blast-radius fence — it is the *unsafe* version of this design. YOLO is the
  principled terminal state that ramp should graduate **into**.
- **New bespoke loop engine with scripted halting.** Rejected — consistent with the prior deliberation: it
  duplicates ledger semantics, and a scripted *acting* halt is the catastrophe we're guarding against.

## Risks

Security-relevant → `threat-model` lens.

- **Asset:** repo integrity + the irreversible/external action surface.
- **Oracle incompleteness (Goodhart)** — green-but-wrong DoD → loop integrates bad work. *Control:* DoD
  authorship discipline; **mitigated, not eliminated** — the accepted bargain (decision 5). **Residual.**
- **Oracle tampering (reward hacking)** — loop weakens/deletes the gating test. *Control:* mechanical
  immutability (out-of-tree / hash-pin) + refuse-if-touched. Closes the route convention left open.
- **Guard bypass** — Bash string-parsing is a **seatbelt, not a sandbox** (raw git via script/alias/odd
  spelling). Inherited limit. YOLO *widens* the allow set, so a **misclassified default branch** could pass
  a bad merge → default-branch detection must **fail toward deny** on ambiguity.
- **Mode confusion** — `=yolo` set when conservative was meant → unexpected acting. *Control:* loud explicit
  value; telos-loop preflight **echoes the active posture** before any act.
- **Blast-radius misclassification** — an op that looks reversible but isn't (e.g. merge into a branch that
  auto-deploys on push via CI). *Control:* external-side-effect is its **own** deny axis, and push-to-remote
  stays denied, so *push-triggered* CI can't fire from inside the fence — **but only absent a repo-side hook
  (see next bullet)**, which can push from a process the guard never sees.
- **In-fence side effects the guard cannot see (git hooks / watchers)** — the *allowed* `commit` and
  `--no-ff` merge invoke local git hooks (`post-commit`, `post-merge`), and filesystem watchers fire on the
  loop's writes; any of these can `push` / deploy / send **without the guard ever seeing a denied command**
  (the hook fires inside another process). So "push-triggered CI can't fire" holds only for a **hook-clean**
  repo. *Control:* YOLO **presumes a hook-clean working copy** — the preflight should assert no active
  `.git/hooks/*` (or core.hooksPath) and no watcher before permitting the posture. **Residual** where that
  can't be fully verified.
- **Recovery is bounded for the non-merge cases** — the `--no-ff` merge itself is durably undoable via
  `git revert -m 1` (in-history, not reflog-dependent), which is why fast-forward is excluded. But the
  *commit / branch-op* cases rely on **reflog**, which expires (`gc`), is host-local, and is itself
  loop-writable. *Control:* allow only `--no-ff` merges (revertable) and accept reflog as the
  bounded-window net for the rest. **Residual:** for the non-merge cases, recoverability is bounded-window,
  not permanent.

## Open questions

*(Resolved during the Phase 1–3 build, 2026-06-19; kept here as the decision record.)*

- **Default-branch detection** — RESOLVED: `_default_branch()` prefers `symbolic-ref origin/HEAD`, else the
  sole local `main`/`master` (disambiguated by `init.defaultBranch` when both exist), else `None` →
  **fail-deny**. `_yolo_merge_reason` *also* always protects the literal `main`/`master` names.
- **Branch-provenance** — RESOLVED: dropped from the guard (stateless per-command parser can't know it).
  Provenance lives at the recipe layer, which knows the branch it created.
- **Immutability mechanism** — RESOLVED: neither out-of-tree nor a hash-pin manifest, but a **git-diff
  check** — `scripts/check_oracle_frozen.py` confirms no file referenced by the claim's `verified-by:`
  appears in `git diff <base>...HEAD` (the loop didn't edit its own gate). No new schema; fail-deny when no
  oracle file is extractable.
- **Branch cleanup** — RESOLVED (KISS): YOLO allows merge only; `branch -d` stays denied / out-of-loop.
- **Posture surface** — RESOLVED: the **env-var value** `CLAUDE_LOOP_GUARD=yolo` selects the guard mode (no
  new guard surface); the telos-loop recipe carries a `--yolo` posture and asserts the oracle is frozen via
  `check_oracle_frozen.py`.
- **Sequencing** — RESOLVED: shipped on telos-loop's test-expressible claims; the ralph-loop generalization
  stays separately build-gated (it never blocked this).

## Rollout / migration

*Status: Phases 0–3 SHIPPED 2026-06-19 (local-only, each gated by independent opus pre-merge-review). The
build-gate was overridden by an explicit build request — recorded honestly here, as telos-loop itself once was.*

- **Phase 0 ✅** — this doc + cross-link from the prior deliberation record (merged `aeb9797`).
- **Phase 1 ✅** — guard two-mode refactor (`1` unchanged + new `git clean` denial; `yolo` = destructive-only,
  allowing only a `--no-ff` merge into a confirmed non-default branch; default-branch detection fails deny).
  Merged `4b3f33c` (4 review rounds — three caught real `git clean` dry-run bypasses: `-e<pattern>`, the `--`
  separator, `--end-of-options`). `hooks/guard-loop-vc.py` + 15 tests.
- **Phase 2 ✅** — oracle-immutability check `check_oracle_frozen.py` (git-diff based; fail-deny) + 11 tests.
  *(Now lives at `skills/ralph-loop/scripts/check_oracle_frozen.py` after the 2026-06-19 ralph-loop
  generalization moved the telos mode under ralph-loop.)*
- **Phase 3 ✅** — telos-loop `--yolo` posture: legal only on test-expressible + frozen-oracle claims;
  preconditions echo the posture, require a hook-clean copy, and hard-refuse judgment claims or a mutable
  oracle (`check_oracle_frozen` exit 0). `skills/telos-loop/SKILL.md` v0.2.0 *(the posture is now stated in
  `ralph-loop`'s YOLO section; telos-loop is a thin alias as of 2026-06-19)*.
- **Build-gate (for what remains)** — the **ralph-loop generalization** SHIPPED its **green-the-suite** anchor
  2026-06-19 (`docs/design/ralph-loop-green-the-suite.md`); the **checklist** anchor SHIPPED 2026-06-19 too
  (`docs/design/ralph-loop-checklist-anchor.md`) — and is the **clean application of decision 5's boundary**:
  a ticked box is a loop-authored claim, not an oracle, so checklist hard-refuses blanket YOLO; only a
  per-item frozen `verify:` oracle (reusing `check_oracle_frozen.py`) may act. All three anchors now ship.
- **Default unchanged** — omitting the posture = stop-and-surface. Fully backward compatible.
