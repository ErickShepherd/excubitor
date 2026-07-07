# ralph-loop — pluggable-anchor loop + green-the-suite anchor — Design

**Date:** 2026-06-19
**Status:** SHIPPED 2026-06-19 (green-the-suite anchor; local-only, opus pre-merge-review). The build-gate
override is recorded below. *(Update: the **checklist** anchor — the third and last — shipped 2026-06-19 too;
see [`ralph-loop-checklist-anchor.md`](ralph-loop-checklist-anchor.md). All three anchors now ship.)*
**Generalizes:** [`loop-telos-anchor-deliberation.md`](loop-telos-anchor-deliberation.md) (the original
loop deliberation — its roadmap item is *this* generalization) and the shipped
[`telos-loop`](../../skills/telos-loop/SKILL.md). Pairs with
[`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md) (the YOLO posture this anchor leans on).

## Context / problem

`telos-loop` is the shipped *telos-anchored* recipe for a self-paced "Ralph Wiggum" `/loop`: one
invocation = one iteration (re-read the ledger → advance one claim → commit → stop-and-surface, or let
`/loop` re-fire). Its reusable discipline — **fresh re-read each pass, one unit per iteration, commit,
no-self-bless, stop-and-surface** — is **anchor-independent**; only the *spec source* and *progress
signal* vary. But telos-loop is a no-op on the majority of repos: those with no `docs/telos/` ledger
(telos coverage is low; most repos have none). Its anchor is too narrow.

This builds **`ralph-loop`**: the same recipe with a **pluggable anchor**, and adds the
**green-the-suite** anchor — loop until a failing test set exits 0. green-the-suite pairs directly with
the just-shipped YOLO posture: a failing suite *is* a frozen, loop-immutable oracle (its exit code), so
`ralph-loop` green-the-suite + `CLAUDE_LOOP_GUARD=yolo` = "autonomously make the suite pass and integrate
within the reversible fence."

### Gate-override (recorded honestly, as prior overrides were)

The roadmap deferred this generalization "until the first real need to loop a repo *without* a telos." **No
such instance was witnessed.** Erick chose to proceed anyway (2026-06-19) because the YOLO work made
green-the-suite the compelling, highest-value anchor — the same pattern by which `telos-loop` and each YOLO
phase were built ahead of their gate. This is a deliberate build-gate override, not a witnessed trigger.
The **checklist** anchor (`PLAN.md`/TODO) stays gated — still a near-empty population; build it when a real
instance appears.

### The design fork this commits to

Building green-the-suite picks **"support telos-less loops"** over "make every looped repo get a telos
first." telos-loop leaned the latter ("a loop with no anchor is just a blind agent"). The resolution that
makes both coherent: **a green-the-suite anchor *is* a durable, out-of-context anchor — just shallower than
a telos ledger.** A telos ledger is claims + contracts + witnesses; a green-the-suite anchor is the failing
suite itself, re-derived from disk each pass. **Reach = broad** (any repo with tests), **anchor = thin**
(an exit code + a failing-test list, no intent model). Both kill drift the same way — by re-reading an
out-of-context spec from disk every iteration — they differ only in the *depth* of what is anchored.

## Goals & non-goals

**Goals**
- `ralph-loop`: one recipe, a **pluggable anchor**. Ship two modes: **telos** (the existing recipe, now a
  mode) and **green-the-suite** (new). The anchor-independent discipline is stated **once**, shared.
- The green-the-suite anchor: spec = a failing suite command; progress = its failing-test set / exit code;
  stop = green (or stuck). Works on **any** repo with a test runner.
- A **suite-immutability** check for the YOLO posture (the main new design question, below): assert the loop
  did **not** weaken/skip/delete tests to force green — mechanically, fail-deny, mirroring
  `check_oracle_frozen.py`.
- Re-key `telos-loop` to be the **telos mode of `ralph-loop`** (Erick's chosen topology: ralph-loop parent,
  telos-loop a thin alias).

**Non-goals**
- *Not* the **checklist** anchor — deferred (gated; near-empty population).
- *Not* a bespoke loop engine — still a recipe over the built-in `/loop` + `ScheduleWakeup` + the
  `guard-loop-vc.py` seatbelt. The suite's exit code is the stop signal; the guard is the no-act fence.
- *Not* touching `guard-loop-vc.py` — it already supports `=1` and `=yolo` mechanically; ralph-loop just
  runs under it like telos-loop does.
- *Not* lifting never-act for judgment work — green-the-suite is test-expressible by definition, but the
  no-self-bless / stop-and-surface default is unchanged; YOLO is the opt-in narrow exception.
- *Not* changing telos-loop's behavior — its trigger still fires; it redirects into ralph-loop's telos mode.

## Approach

### The pluggable-anchor shape

A ralph-loop iteration is the same five-beat loop regardless of anchor; only two slots are anchor-specific:

| Beat                | telos anchor                              | green-the-suite anchor                         |
|---------------------|-------------------------------------------|------------------------------------------------|
| **Spec source**     | `docs/telos/*.md` ledger (`audit-telos`)  | a failing suite command (e.g. `pytest -q`)     |
| **Progress signal** | claim states + coverage                   | failing-test set / exit code                   |
| Pick one unit       | next actionable claim (DRIFTED>UNMET>…)   | one failing test (or one root-cause cluster)   |
| Do the work         | fulfil the `discharged-by` symbol         | fix the code so that test passes               |
| Discharge / stop    | claim-type split; stop-and-surface        | exit 0 = green; stop-and-surface (or YOLO)     |

The **anchor-independent core** (preconditions, re-read-from-disk, one-unit-per-iteration, no-self-bless,
commit, continue-or-stop, stop-and-surface, the YOLO posture) is written once and shared by both modes.

### green-the-suite, concretely

- **Spec source / invocation.** The loop is launched with the **suite command** (how to invoke the failing
  tests) and the repo. `/loop` re-fires the invocation verbatim each wake-up, so the suite command is the
  persisted out-of-context anchor (the analog of the ledger path). Each iteration **re-runs the suite from
  disk** — never trusts a remembered failure list.
- **Progress signal.** The suite's **failing-test set** (and its exit code). Pick one failing test (or one
  cluster sharing a root cause), fix the *production* code so it passes, commit, re-fire.
- **Stop predicate.** `ratchet-not-resolve`, generalized from telos-loop's "no progress → stop":
  - **Green** (exit 0, zero failing tests) → stop-and-surface (success).
  - **Stuck** (an iteration fails to *reduce* the failing-test count) → stop-and-surface (can't advance).
  - Otherwise (count dropped, tests remain) → re-fire.
  The number of failing tests is a monotone-decreasing ratchet; "suite green" is the terminal. We do **not**
  use coverage-100% (Goodhart-able). Under YOLO the suite-immutability check (below) prevents the loop from
  faking the ratchet by deleting tests.

### Suite-immutability for YOLO (the main new design question)

`check_oracle_frozen.py` freezes a *named* oracle file. For green-the-suite the "oracle" is the **whole
suite** (many files), so the immutability story differs: how do we assert the loop didn't weaken/skip/delete
tests to force green?

**Decision: the YOLO green-the-suite act is legal only if the loop touched ZERO test-surface files on its
branch.** If no test file changed, green came purely from *production* changes — exactly "fix the code, not
the test." This is the strongest *simple* guarantee, it is hermetic (pure `git diff`, no test execution),
and it mirrors `check_oracle_frozen.py`'s style. We reject the count/nodeid ratchet *as the primary gate*
(see Alternatives) — but the recipe still observes the failing-count ratchet as the *progress* signal.

**Why file-frozen beats count-ratchet here.** If a test file legitimately *must* change, the loop is doing
**test-authoring** work — which is exactly the self-bless hazard (loop writes a test, loop declares it
green). That work must **stop-and-surface**, not run under YOLO. So "no test file changed" is not just
simpler than a count ratchet; it is the *more correct* fence for the YOLO posture.

**`check_suite_frozen.py`** — new, sibling to `check_oracle_frozen.py`:
- Inputs: `--repo`, `--base` (the loop branch's base / default branch), and one-or-more `--test-path`
  **git pathspecs** naming the frozen verdict surface (test dirs/globs **and** any runner-config that affects
  collection — `pytest.ini`, the `[tool.pytest]` table's file, `conftest.py`, `tox.ini`, etc.).
- Surface-exists check (fail-deny on typos): each `--test-path` must match ≥1 tracked file **at `base`**,
  checked by diffing the **empty tree** against `base` limited to the pathspec
  (`git diff --name-only <empty-tree> <base> -- <pathspec>`). This uses git's SAME pathspec engine as the
  tamper check, so directories, exact files, and `*` globs resolve identically — `git ls-tree` is *not* used
  here because it does **not** honour wildcard pathspecs (a glob surface would wrongly match nothing). A
  pathspec matching nothing means the author froze a surface that doesn't exist → refuse (exit 1). This
  closes the "typo'd pathspec → vacuous FROZEN" hole.
- Tamper check: `git diff --name-only <base>...HEAD -- <pathspecs…>` must be **empty**. Any test-surface
  file added/edited/deleted on the loop branch → NOT-FROZEN (exit 1). Letting git do pathspec matching keeps
  us in git's exact diff space (the same lesson `check_oracle_frozen` learned about path normalization) and
  catches deletions (they appear in `--name-only`).
- **FAIL-DENY** everywhere: no `--test-path` given, git error, ambiguity → exit 1. Exit 0 only when the
  surface provably exists at base **and** is untouched on the branch.
- Exit codes mirror `check_oracle_frozen.py`: `0` = frozen (safe to act); `1` = not frozen / unverifiable;
  `2` = usage error.

**Accepted, named residual (pushed onto the DoD author — same bargain as oracle incompleteness, decision 5
of the YOLO doc).** The check freezes exactly the pathspecs it is given. If a verdict-affecting path is
*not* listed (e.g. a `pyproject.toml` `addopts = "--ignore=tests/slow"` the author forgot to freeze), a loop
could weaken the suite via that path without tripping the check. So **enumerating the complete verdict
surface is the recipe author's responsibility**, exactly as enumerating a *complete* oracle is the DoD
author's. The check makes the *freeze* mechanical; it cannot know which files constitute "the suite."

## Key decisions

1. **One recipe, pluggable anchor; the discipline is stated once.** telos and green-the-suite share the
   anchor-independent core verbatim. (Generalizes the roadmap item.)
2. **Topology: ralph-loop is the parent skill; telos-loop is a thin alias** into ralph-loop's telos mode.
   Chosen by Erick (AskUserQuestion, 2026-06-19), reversing his earlier "telos-loop is its own skill" call —
   recorded as his decision.
3. **green-the-suite anchor = the failing suite on disk**; progress = failing-test count (ratchet), stop =
   green or stuck. Not coverage (Goodhart-able).
4. **YOLO suite-immutability = "zero test-surface files changed on the branch"**, checked mechanically and
   fail-deny by `check_suite_frozen.py`. A suite that *must* change → test-authoring → stop-and-surface, not
   YOLO.
5. **Verdict-surface completeness is the DoD author's responsibility** — the same accepted Goodhart bargain
   as oracle incompleteness; the check freezes what it is told to freeze, no more.
6. **Build green-the-suite only.** checklist stays gated; the gate-override is recorded above.

## Alternatives considered

- **Count/nodeid ratchet as the YOLO primary gate** (collected test count must not drop). *Rejected as
  primary.* It permits test files to change (only the *count* is pinned), which is precisely the
  loop-writes-its-own-test self-bless hazard; it requires executing collection at two revisions (heavier,
  language-specific) where a pure `git diff` suffices; and a renamed/replaced test keeps the count while
  weakening coverage. Kept only as the *progress* signal ("failing count must drop"), not as the immutability
  fence.
- **Freeze the suite via a hash-pin manifest of every test file.** Rejected for the same reason
  `check_oracle_frozen` rejected it — a manifest to maintain and forge; `git diff <base>...HEAD` already
  answers "did the loop touch this surface" without new schema.
- **Keep telos-loop standalone, add ralph-loop as a sibling sharing a core doc** (the precedent-respecting
  topology). *Not chosen* — Erick selected the parent/alias topology; recorded as decision 2.
- **Build checklist too** while here. Rejected — scope discipline; near-empty population; the gate stands.
- **A bespoke loop runner that scripts the halt.** Rejected (consistent with the prior deliberation): the
  suite exit code is the stop signal and the guard is the no-act fence; a scripted *acting* halt is the
  catastrophe being guarded against.

## Risks

Security-relevant (a loop that may *act* under YOLO) → `threat-model` lens; most controls are inherited from
[`loop-yolo-verifiable-autonomy.md`](loop-yolo-verifiable-autonomy.md).

- **Asset:** repo integrity + the irreversible/external action surface (unchanged from the YOLO doc).
- **Suite reward-hacking (weaken/skip/delete a test to force green).** *Control:* `check_suite_frozen.py` —
  no test-surface file may change on the branch; fail-deny. **Closed for the enumerated surface.**
- **Incomplete verdict-surface enumeration.** A verdict-affecting config path the author forgot to freeze.
  *Control:* author discipline (decision 5). **Residual** — named, pushed onto the DoD author.
- **Oracle/suite Goodhart (green-but-wrong).** A passing suite that doesn't capture the real intent. *Control:*
  suite-authorship discipline; **mitigated, not eliminated.** **Residual.**
- **Guard bypass / seatbelt-not-sandbox / in-fence git-hook side effects.** All inherited unchanged from the
  YOLO doc — ralph-loop adds no new guard surface and presumes a hook-clean working copy under YOLO.
- **Anchor confusion** (wrong anchor selected, or green-the-suite run on a repo whose "suite" is a no-op that
  trivially exits 0). *Control:* the recipe asserts the suite is **red at the start** before looping — a
  green-at-launch suite is a no-op anchor and must stop-and-surface ("nothing to do / suspicious"), not
  declare instant victory.

## Open questions

*(Resolved during this build; kept as the decision record.)*

- **Suite-immutability mechanism** — RESOLVED: file-frozen (`check_suite_frozen.py`), not count-ratchet.
- **Stop predicate** — RESOLVED: failing-count ratchet + "green or stuck", not coverage.
- **Topology** — RESOLVED: parent/alias (decision 2).
- **checklist anchor** — was DEFERRED (gated); has since SHIPPED 2026-06-19 as the prose/judgment anchor —
  see [`ralph-loop-checklist-anchor.md`](ralph-loop-checklist-anchor.md).

## Rollout / migration

- **Phase 1 ✅** — design doc (this file).
- **Phase 2 ✅** — `check_suite_frozen.py` + 15 stdlib tests (hermetic temp git repos, fail-deny), sibling to
  `check_oracle_frozen.py`.
- **Phase 3 ✅** — `ralph-loop/SKILL.md`: shared core + telos anchor + green-the-suite anchor; moved the
  telos-mode oracle check (`check_oracle_frozen.py` + tests) under `skills/ralph-loop/`.
- **Phase 4 ✅** — `telos-loop/SKILL.md` reduced to a thin alias into ralph-loop's telos anchor (v0.3.0).
- **Phase 5 ✅** — `scripts/validate.py` green (42 skills); all affected suites green (suite-frozen 15,
  oracle-frozen 11, guard 15); `ROADMAP.md` + the YOLO design record updated.
- **Phase 6** — independent `/pre-merge-review` → merge `--no-ff` (local-only, never push).
- **Default unchanged** — omitting `--yolo` / the posture = stop-and-surface, fully backward compatible.
