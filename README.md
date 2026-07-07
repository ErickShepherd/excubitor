# agent-harness

**Safety fences for autonomous coding agents** — mechanical guards, loop discipline, and a
falsifiable intent-record system for letting an LLM agent work unattended without trusting it to
bless its own work.

Stdlib-only Python hooks + [Agent Skills](https://code.claude.com/docs/en/skills)-format capability
packets, with 130 tests and the design rationale that produced them. Built for and battle-tested
with Claude Code; the concepts (PreToolUse guards, frozen oracles, evidence tiers) port to any
agent runtime that can intercept tool calls.

## The problem: an agent cannot bless its own "done"

A productive agent workflow ends in an irreversible act — a merge, a branch delete, a push. If a
human reviews every step, fine. But run the agent in an **unattended loop** and a failure mode
opens up: the loop decides *for itself* that the work is complete, and then *acts* on that
judgment. LLMs have self-preference bias — a loop that writes its own completion evidence produces
*plausible-looking* proof of work that wasn't done, and any downstream check that trusts that
evidence is routed around by construction.

The fix is not "prompt it to be careful." The fix is **mechanical**: split the question into two
independent axes and enforce the answer outside the model —

- **Axis A — done-signal trust.** Is "done" decided by a *frozen, loop-immutable oracle* (a test
  suite's exit code the loop cannot edit — unforgeable), or by the LLM's own judgment (forgeable)?
- **Axis B — blast radius.** Is the act *reversible and internal* (a commit; a `--no-ff` merge
  into a non-default branch, undoable with `git revert -m 1`), or *irreversible/external* (push,
  hard-reset, branch delete, default-branch merge)?

An unattended agent may act on its own "done" **only** when the done-signal is unforgeable **and**
the act is reversible. Everything else is *stop-and-surface*: keep working, keep committing, then
stop and hand the irreversible tail to an out-of-loop reviewer or a human. This repo is that
policy, implemented as code you can read, test, and install.

## The four layers

| Layer | Component | What it enforces |
|---|---|---|
| 1. Declare intent | [`skills/telos/`](skills/telos/SKILL.md) | A repo's purpose as *falsifiable claims* — each with a decidable one-line `contract:`, a single `discharged-by: path::symbol`, and optionally an executable `verified-by:` witness whose exit code is trusted over the LLM. |
| 2. Audit against intent | [`skills/audit-telos/`](skills/audit-telos/SKILL.md) + [`telos_check.py`](skills/audit-telos/telos_check.py) | Read-only conformance audit with **evidence tiers**: a claim marked DISCHARGED without a backing witness is mechanically demoted to SUSPECT. The auditor deliberately has no write access to the record it audits. |
| 3. Fence the loop | [`hooks/`](hooks/) — three PreToolUse guards | `guard-default-branch.py`: no file mutations on `main`/`master` — branch first. `guard-loop-vc.py`: while `CLAUDE_LOOP_GUARD` is set, block the irreversible VC set (merge/push/branch-delete/hard-reset/`git clean`/worktree-remove/`gh pr merge`); in `=yolo` mode, additionally *allow* a `--no-ff` merge into a confirmed non-default branch (fail-deny on ambiguity). `guard-one-unit.py`: cap a headless loop worker at one unit of work per session, forcing a fresh-context re-read between units. |
| 4. Loop discipline + boundary | [`skills/ralph-loop/`](skills/ralph-loop/SKILL.md), [`skills/telos-loop/`](skills/telos-loop/SKILL.md), [`skills/leak-guard/`](skills/leak-guard/SKILL.md) | The unattended-loop recipes that use layers 1–3: charter-driven iteration, frozen-oracle verification (`check_oracle_frozen.py` proves the loop never edited the oracle that gates it), session-limit suspend, and a fail-closed guard for content crossing a private→public boundary. |

The design docs under [`docs/design/`](docs/design/) are not an afterthought — they are the
recorded deliberations (alternatives, rejected options, honest limits) behind each mechanism.
Start with [`loop-yolo-verifiable-autonomy.md`](docs/design/loop-yolo-verifiable-autonomy.md)
(the two-axis model above) and
[`loop-telos-anchor-deliberation.md`](docs/design/loop-telos-anchor-deliberation.md) (why a loop
must never discharge its own claims).

## What's in the box

```
hooks/                     # 3 stdlib-only PreToolUse guards + 30 tests
skills/
  telos/                   # intent-record authoring (write side)
  audit-telos/             # conformance audit (read side) + strict parser + 62 tests
  telos-loop/              # telos-anchored unattended loop recipe
  ralph-loop/              # charter-driven loop + oracle-freeze/suspend scripts + 38 tests
  leak-guard/              # private→public boundary guard
docs/design/               # 10 design/deliberation records
docs/telos/                # this repo's own intent record (audited by its own tooling)
scripts/install.sh         # symlink skills+hooks into ~/.claude, register the hooks
```

## Install

Requires Python 3.11+ and `git`. For Claude Code:

```bash
git clone <this-repo> && cd agent-harness
scripts/install.sh          # symlinks skills/* and hooks/* into ~/.claude, and idempotently
                            # registers the three guards in ~/.claude/settings.json
```

Or register the hooks by hand in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Edit|Write|NotebookEdit",
       "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/guard-default-branch.py", "timeout": 10}]},
      {"matcher": "Bash",
       "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/guard-loop-vc.py", "timeout": 10}]},
      {"matcher": "*",
       "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/guard-one-unit.py", "timeout": 10}]}
    ]
  }
}
```

All three guards are **opt-in or inert by default**: `guard-loop-vc.py` does nothing unless
`CLAUDE_LOOP_GUARD` is set in the loop's environment; `guard-one-unit.py` does nothing unless a
loop driver arms `ONE_UNIT_CAP_SCOPE` + `ONE_UNIT_CAP_BASELINE`; `guard-default-branch.py` can be
disabled per-repo with a `.claude/allow-default-branch` marker file or globally with
`CLAUDE_ALLOW_DEFAULT_BRANCH=1`. Interactive work is unaffected until you explicitly say "I'm
looping."

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/pytest -q        # 130 tests: 30 hooks, 62 audit-telos, 38 ralph-loop
                           # (127 pass; 3 audit-telos ledger round-trip tests skip — they
                           #  need a private sibling module that did not ship, see the extraction notes)
```

CI runs the same suite on a stock GitHub runner (`.github/workflows/ci.yml`), plus this repo's
own telos audit — the six claims in [`docs/telos/app.md`](docs/telos/app.md) must all resolve
DISCHARGED at the `witness` evidence tier, i.e. every safety claim this README makes about the
guards is re-proven by an executed test on every CI run.

## The workflow these fences assume

Branch-first: never edit or commit on the default branch — create a branch, commit in focused
units as you go, and gate integration on an independent fresh-context review. The guards enforce
the mechanical edges of that workflow (layer 3 above); the review itself is a process convention
(see `pre-merge-review` in the glossary). Unattended loops get the stricter posture: with
`CLAUDE_LOOP_GUARD=1` the loop can work and commit but never integrate; with
`CLAUDE_LOOP_GUARD=yolo` it may integrate reversibly **only** when a frozen oracle — not the
model — says the work is done.

## Honest limits

These are **seatbelts for the default path, not a sandbox** — the hooks' own docstrings say so,
and mean it:

- `guard-loop-vc.py` parses Bash command strings. A script that calls git indirectly, a shell
  alias, or a `post-commit` hook firing an external side effect can slip past. Where possible,
  also simply don't hand the loop a merge capability.
- On a local-only repo with both `main` and `master` (or a non-standard trunk), default-branch
  detection is a best-effort heuristic; YOLO mode compensates by always protecting the literal
  `main`/`master` names and failing deny on ambiguity, and the residual exposure is bounded to a
  revertable `--no-ff` merge.
- The evidence-tier demotion (layer 2) catches *unbacked* claims of completion. A loop that
  authors its own witnesses produces *backed* claims — which is exactly why layers 3–4 sever the
  loop's ability to act, rather than trusting any audit of its output.

## Glossary — referenced but not included

This library is extracted from a larger private skill set; the shipped files occasionally
reference siblings that did not ship. One line each, so nothing dangles:

- **`pre-merge-review`** — spawns a fresh-context, read-only, highest-capability reviewer over a
  completed branch's full diff; merges only on its explicit sign-off (fail-closed).
- **`grill-me`** — one-question-at-a-time interrogation discipline used to sharpen a vague intent
  into a decidable contract before it is written down.
- **`deliberate`** — structured multi-perspective deliberation for contested decisions.
- **`audit-repo` / `audit-remediate`** — whole-repo audit sweep and its serial remediation
  counterpart (audit-telos is the purpose-conformance member of that family).
- **`threat-model`** — assets/attack-surface/proportional-controls reasoning; leak-guard defers to
  it for how hard to guard.
- **`automated-testing`, `logging`, `handoff`** — testing, no-secrets-in-logs, and
  session-handoff conventions referenced in passing.
- **`check-usage`** — subscription usage reader; its 87-line `claude_usage.py` module is vendored
  at `skills/ralph-loop/scripts/` so the session-limit suspend gate works standalone.

## Provenance

This repo is a **curated extraction** of the agent-governance subset of a private library, with a
fresh history. the extraction notes records the source commit, the per-file origins,
and every edit made during extraction. The private library remains the upstream; this snapshot is
re-published manually when upstream changes materially. It describes what the harness looked like
as of the recorded commit — a claim that stays true — rather than pretending to be a live mirror.

## License

To be finalized before first publish (tracked as an open decision in the extraction design doc).
