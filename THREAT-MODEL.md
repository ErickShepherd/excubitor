# Threat model

What excubitor defends, against whom, where they reach it, and — just as important — what it does
**not** defend. The guards are **seatbelts for the default path, not a sandbox**; a threat model that
overstated them would be the exact kind of forged safety claim this repo exists to refuse. This
document is the honest version. It pairs with [`KNOWN-BYPASSES.md`](KNOWN-BYPASSES.md) (the enumerated
ways past each control) and [`SECURITY.md`](SECURITY.md) (what counts as a bug).

## Assets — what we protect

1. **Integrity of the agent's completion / verification claims.** When an unattended loop says "done,"
   that claim must be *backed by something the model cannot forge* — a passing frozen oracle, a denied
   tool call — not by the model's own say-so. The primary asset is the trustworthiness of "done."
2. **The irreversibility boundary.** No **unattended** irreversible act — a merge into a shared branch,
   a `push`, a branch delete — may fire on a self-blessed "done." Reversible/internal acts (a commit; a
   `--no-ff` merge into a non-default branch, undoable with `git revert -m 1`) are permitted only under
   an unforgeable done-signal.
3. **The integrity of the guards themselves.** A guard the loop can disarm is not a guard. The ability
   to write a guard's kill-switch, or repoint the ref it trusts, is itself a protected asset.

Sensitivity: high but **bounded** — the blast radius is a *local* repository and its *local* history.
Excubitor is not defending secrets, a network service, or production infrastructure; it is defending a
developer's repo from an agent's unattended mistake or over-optimization. Reversibility is the saving
grace on most of the surface (git keeps reflogs; commits are cheap; only push/merge-to-shared/delete
cross into hard-to-undo), which is exactly why those few acts are the ones fenced.

## Adversaries — three tiers, increasing capability

The adversary is not a human attacker; it is **the agent loop itself**, modeled at three capability
tiers. Each tier is a strict superset of the one before.

### Tier 1 — the sloppy loop (accident, not intent)

A loop that isn't trying to escape anything but, through a bad plan or a hallucinated "all tests pass,"
drifts toward an unwarranted irreversible act — auto-merges half-finished work, force-pushes over a
teammate, `git clean`s a dirty tree it misread. No adversarial intent; the failure is *carelessness at
scale, unattended*. **This is the common case and the one the guards most fully cover.**

### Tier 2 — the optimizing loop (routes around an obstacle)

A capable model pursuing a goal treats a check between it and "done" as an obstacle to route around —
not from malice but from optimization pressure. It will retry a denied action a different way, write
its own passing test to satisfy a coverage gate, or bump a `last-grilled` date to dodge a staleness
re-grill. It does not craft novel exploits; it takes the *nearest available* path the guardrails
didn't close. **This is the tier the design most actively reasons about** — the whole two-axis model
(unforgeable done-signal × reversible blast radius) exists because a forgeable done-signal is precisely
what this tier forges.

### Tier 3 — the adversarial model (deliberate evasion)

A model that actively tries to defeat the guards: obfuscating a command to slip the parser, hiding a
dangerous verb in a shell expansion, spawning a subagent whose tool calls the parent's hooks don't
see, or building a forbidden path at runtime so no literal token matches. **Excubitor does not claim to
stop this tier** — and says so plainly. A string-parsing seatbelt cannot contain an adversary that
controls the string and the interpreter. The honest posture against Tier 3 is *defense in depth by
other means* (don't hand the loop the capability at all; run it in an actual sandbox/container; keep a
human on the irreversible tail) with excubitor as one layer, not the boundary. Every Tier-3 path we
know of is catalogued in [`KNOWN-BYPASSES.md`](KNOWN-BYPASSES.md).

## Attack surface — where the loop reaches the assets

- **Tool calls** — the `Bash`, `Edit`/`Write`/`NotebookEdit` calls the loop makes. This is the primary
  surface, and where the PreToolUse guards intercept. It is **command-string parsing**, not shell
  execution — so it sees literal tokens, not what the shell will expand them into.
- **The intent record** (`docs/telos/*.md`) — a loop that authors its own telos claims and witnesses
  can produce *backed* DISCHARGED claims. The audit's evidence tier catches *unbacked* overclaims; it
  cannot judge a backed-but-weak witness (an always-pass test). See the residual below.
- **The guards' own kill-switches** — the `.claude/allow-default-branch` marker, the hook scripts, the
  `settings.json` hooks block, and the `origin/HEAD` ref the default-branch detection trusts.
- **The host runtime** — the layer excubitor's hooks run *in*. This is the surface excubitor **cannot
  reach past**, and it matters (next section).

## The host-runtime enforcement gap (why a hook layer is not a boundary)

Excubitor's guards are PreToolUse hooks. They are only as strong as the runtime's hook dispatch, and
that dispatch has documented gaps. These are not excubitor bugs — they are the **substrate** excubitor
inherits, and an honest threat model names them rather than implying the hooks are airtight:

- **Hooks don't fire on subagent (Task) tool calls.** A PreToolUse hook configured in the parent's
  settings has not been enforced on the tool calls a subagent makes — so a loop that spawns a subagent
  can perform, *through the subagent*, an act the parent's guard would deny. Documented as a security
  issue in Claude Code (`anthropics/claude-code#21460`; closed — resolution state may vary by version).
  The structural point outlives any single fix: **hook coverage that varies by invocation path means a
  guard is only as complete as the paths it is dispatched on.**
- **Hooks cannot reach prompt assembly.** Claude Code's hook events fire around tool calls and a few
  lifecycle points; none fires during assembly of the model's context. `UserPromptSubmit` sees the raw
  user message and can *inject* context, but cannot read or rewrite the assembled system/context. So a
  guard cannot vet *what the model was told*, only *what it then tries to do* — excubitor is a control
  on **actions, never on cognition**.
- **The runtime's own denylist has been bypassed.** Claude Code's permission `deny` rules have been
  defeated by command chaining past a parser threshold (`anthropics/claude-code#4956`) and by symbolic
  links (advisory `GHSA-4q92-rfm6-2cqx`), among others — several since addressed. The lesson excubitor
  takes: a command-string denylist (which `guard-loop-vc.py` also is) is a seatbelt, and the same
  parser-evasion class applies to it too — which is why it is *documented*, not claimed away.

The takeaway is not "excubitor is broken." It is: **a hook-layer guard is a proportional control for
Tiers 1–2 and a speed bump for Tier 3, on a substrate that is itself not a sandbox.** Anyone relying on
it for Tier 3 must add a real boundary (container/VM isolation, capability restriction) beneath it.

## Controls — matched to the tiers, not gold-plated

The four guards' decision logic now lives in a shared **model-blind core** (`excubitor/core/`); the
shipped `hooks/guard-*.py` are thin Claude Code adapters over it, and a generic adapter
(`runtime/spec_adapter.py`) reaches the same core. This extraction is **behavior-preserving** — the
differential test suites are the oracle — so the threat surface, the tiers, and every control and
residual below are unchanged by it. What the core *adds* is reach, not enforcement: the policies are
now reachable from a neutral `excubitor.pre_tool.v1` envelope, but the only runtime with real shipped
enforcement is still the Claude Code hooks (other hosts are designed, not built — see
[`SPEC.md`](SPEC.md)). "Model-blind" widens the *contract*, not the *proven substrate*.

| Control | What it is | Tier it addresses | Honest limit |
|---|---|---|---|
| `guard-default-branch.py` | deny the direct file-edit tools (Edit/Write/NotebookEdit) on `main`/`master` — branch first | 1 (mostly), 2 | registration boundary: Bash mutations bypass (R-06, accepted — see KNOWN-BYPASSES); disarmable marker → now fenced by self-integrity |
| `guard-loop-vc.py` (`=1`) | deny the irreversible VC set while looping | 1, 2 | literal-token parse; shell-expansion evades (Tier 3) |
| `guard-loop-vc.py` (`=yolo`) | permit only a revertable `--no-ff` merge into a non-default branch, fail-deny on ambiguity | 1, 2 | presumes a hook-clean working copy |
| `guard-one-unit.py` | cap a headless worker at one unit/session (fresh-context re-read) | 1, 2 | opt-in; a determined loop can be re-armed |
| `guard-self-integrity.py` | while armed, deny writes to the guards' own kill-switches | 2, and Tier-3 *default paths* | literal-token parse; same expansion residual |
| `audit-telos` evidence tier | demote an unbacked DISCHARGED to SUSPECT; trust witness exit codes over the LLM | 1, 2 | cannot judge a *backed-but-weak* witness |
| `run_frozen_oracle.py` (+ `check_oracle_frozen.py` / `check_suite_frozen.py` diagnostics) | bind the witness verdict to baseline-authored, trusted state: the command must appear in the anchor's base-tree blob as a whole authored line / `verify:` suffix, never a substring (`--anchor`, base pinned to the **remote-tracking** default `refs/remotes/origin/<name>` — the highest-bar in-repo anchor; a local-only default is trivially loop-movable and fail-denies), the executable must be tracked-in-repo or non-user-writable (the untracked `.venv/bin/python` class refuses; a resolved symlink target outside the repo is writability-checked too), conftest/runner-config/module-shadow companions join the frozen surface, then precheck vs base, snapshot, shell-less sanitized-env run, recheck | 2 (forged done-signal) | binds authorship and bytes, not semantics (a baseline-authored vacuous/delegating command is the DoD author's risk); proves start==end state, not *adequate*; a mid-run edit restored before the recheck remains; the base OID is defense-in-depth not absolute — a `git fetch` refspec or direct `.git/refs` write can move even the remote-tracking ref, so true baseline immutability is the driver's (loop isolation / out-of-band `--base`); system site-packages content and direct-script sys.path shadowing are outside the surface |

The proportionality logic: **the assets are high-value but reversible-except-at-a-few-edges, and the
realistic adversary is Tiers 1–2.** So the controls concentrate on those few irreversible edges
(merge/push/branch-delete) and on the one thing that makes a done-signal forgeable (the model grading
its own work), and they *decline* to chase completeness against Tier 3 — which would be theater on this
substrate. That declared scope is the design's spine, recorded across `docs/design/`.

## Residual risks (accepted, documented, and where pinned)

- **Shell-expansion evasion of the command parsers** (glob/brace/`$VAR`/quoted substitution) — Tier 3.
  Accepted; pinned in both hooks' `TestAcceptedResiduals`. `KNOWN-BYPASSES.md`.
- **Dangerous git verbs outside the fenced set** (`update-ref -d`, `reflog expire`, `filter-branch`, …)
  — lose local/recoverable state; not the integration/publication set. Pinned in `TestUnhandledGitVerbs`.
- **A backed-but-weak telos witness** (`verified-by: true`) — the audit trusts exit codes, not witness
  quality. By design; catching it is an out-of-loop reviewer's or a frozen oracle's job. Pinned in
  `skills/audit-telos/tests/test_adversarial_records.py`.
- **Subagent/Task hook non-coverage and other host-runtime gaps** — inherited from the substrate, above.
  Not closable from within a hook; the mitigation is a real sandbox beneath excubitor for Tier 3.
- **Out-of-band side effects** (`post-commit` git hooks, filesystem watchers, git wrappers) — the guard
  never sees them; YOLO mode presumes a hook-clean working copy.

None of these is hidden. That is the whole point: an enumerated limit is an honest control boundary; a
concealed one is a forged safety claim — the very thing the harness exists to refuse.
