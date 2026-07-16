# Architecture

Four layers, one trust story: **the model's judgment is never load-bearing for an irreversible
act** — and the guards enforcing that are themselves fenced against the loop that would disarm
them. Every arrow below that crosses toward "irreversible" passes through something the model
cannot forge — a strict parser, an exit code, a denied tool call, or a human.

```
                 ┌────────────────────────────────────────────────────┐
                 │  docs/telos/  — intent record (falsifiable claims) │
                 └───────▲────────────────────────────┬───────────────┘
   writes (grill-gated,  │                            │  reads (no Write tool)
   validated, committed) │                            ▼
        ┌────────────────┴───┐              ┌────────────────────────┐
        │  skills/telos      │              │  skills/audit-telos    │
        │  (write side)      │              │  telos_check.py        │
        └────────────────────┘              │  strict parse → state  │
                                            │  recompute → evidence  │
                                            │  tier (unbacked        │
                                            │  DISCHARGED → SUSPECT) │
                                            └───────────┬────────────┘
                                                        │ findings (read-only)
                                                        ▼
   agent session ──tool calls──► PreToolUse guards ──deny/defer──► runtime
                                 ├─ guard-default-branch.py   (Edit|Write|NotebookEdit)
                                 ├─ guard-loop-vc.py          (Bash: git/gh VC mutations)
                                 ├─ guard-one-unit.py         (*: post-commit cap)
                                 └─ guard-self-integrity.py   (armed loop: no writes to the
                                                               guards' own kill-switches)
                                 └──every deny──► ~/.claude/excubitor/denials.jsonl
                                                  (_denial_log.py: telemetry, best-effort
                                                   after the decision; NOT evidence)
                                                        ▲
                                                        │ armed by env markers
   unattended loop (skills/ralph-loop, skills/telos-loop)
     CLAUDE_LOOP_GUARD=1    → work + commit only; stop-and-surface
     CLAUDE_LOOP_GUARD=yolo → + --no-ff merge into non-default branch, IFF
         scripts/run_frozen_oracle.py  returns the witness verdict from a frozen surface
                                       (precheck → snapshot → shell-less run → recheck;
                                        check_oracle_frozen.py = check-only diagnostic)
         scripts/check_suite_frozen.py proves the suite wasn't weakened
         scripts/suspend_verdict.py    suspends before the session limit

   private content ──► skills/leak-guard ──block-on-hit──► public artifact
```

## Trust boundaries

1. **Model ↔ intent record.** Only the `telos` skill writes `docs/telos/`; `audit-telos` audits it
   with no Write tool. The strict parser (`telos_check.py parse`) refuses malformed records, so the
   record can't drift into unauditable prose. State is *recomputed* by the audit — a hand-asserted
   `state: DISCHARGED` is contradicted, and one with no `verified-by:` witness is demoted to
   SUSPECT rather than trusted.

2. **Model ↔ VC irreversibility.** The hooks run *outside* the model, in the runtime's PreToolUse
   interception. Deny decisions are emitted as JSON on stdout with exit 0 (the process contract is
   fail-open — a guard bug must never wedge the tool — while the YOLO merge *decision* fails deny:
   an undeterminable branch blocks the merge). `guard-self-integrity.py` closes the reflexive hole:
   while a loop guard is armed, the loop may not write the guards' own kill-switches (the
   allow-default-branch marker, the hook scripts, the settings.json hooks block) — a judge the
   model can rewrite is not a judge. Every deny is also appended to a local JSONL telemetry log
   (`hooks/_denial_log.py`) strictly *after* the decision is flushed to the runtime, strictly
   best-effort, and time-bounded (a hung write is abandoned, not waited on) — neither a faulting
   nor a blocking telemetry write can change or outlast a decision. The log is observability, not
   evidence: it is deliberately not a fenced kill-switch (see KNOWN-BYPASSES.md) and nothing in
   the trust story reads it.

3. **Loop ↔ its own oracle.** YOLO mode's permit-to-act is only sound if the loop cannot edit the
   oracle that gates it. `run_frozen_oracle.py` is that gate: it validates the full oracle surface
   (lexical paths, symlink-chain hops, resolved targets) against the loop's baseline, snapshots it,
   runs the witness without a shell, and rechecks the snapshot before returning the verdict — an
   exit code produced by frozen bytes, not a promise. Stated precisely: git proves *committed*
   baseline/final state, never that an unobserved worktree edit didn't happen earlier; the runner's
   envelope is what binds the checked bytes to the exit code (accepted residual: a mid-run edit
   restored before the recheck). `check_oracle_frozen.py` remains the check-only diagnostic.

4. **Private ↔ public.** `leak-guard` gates content crossing outward, fail-closed, with explicit
   (never silent) whitelisting.

## Layout

```
hooks/                    # the guards + _denial_log.py telemetry helper + tests/ (stdlib only;
                          # no imports across components — the helper is within-component)
skills/<name>/SKILL.md    # open Agent Skills format: frontmatter trigger + instructions
skills/<name>/scripts/    # executable helpers (ralph-loop's oracle/suite/suspend checks)
skills/<name>/tests/      # per-component pytest suites
docs/design/              # the deliberation records behind each mechanism
docs/telos/               # this repo's own claims, audited by its own audit-telos
scripts/install.sh        # symlinks + idempotent settings.json hook registration
```

Components are deliberately decoupled: the hooks import nothing from the skills, the skills'
scripts import nothing from the hooks, and the only vendored code is `claude_usage.py` (next to
the one script that needs it). Any piece is usable without the rest; together they form the
four-layer harness described in the README.
