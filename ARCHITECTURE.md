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
         scripts/run_frozen_oracle.py  returns the witness verdict from a baseline-bound,
                                       frozen surface (anchor + base pin → executable trust →
                                       precheck → snapshot → shell-less sanitized run → recheck;
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

2. **Model ↔ VC irreversibility.** The four guards are now thin Claude Code adapters over a
   **model-blind policy core** (`excubitor/core/`: the `loop-vc`, `default-branch`, `one-unit`, and
   `self-integrity` policies + a read-only git boundary + a deny-precedence dispatcher, all stdlib-only
   and free of host I/O); `runtime/spec_adapter.py` drives the *same* core from a generic
   `excubitor.pre_tool.v1` envelope, so the decision is identical whichever adapter runs (the
   differential suites prove it). The full contract is [`SPEC.md`](SPEC.md); only Claude Code is a
   *supported* runtime today (other hosts are designed, not built — no live-host claims). The hooks run
   *outside* the model, in the runtime's PreToolUse interception. Deny decisions are emitted as JSON on
   stdout with exit 0 (the process contract is
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

3. **Loop ↔ its own oracle.** YOLO mode's permit-to-act is only sound if the loop cannot author
   what gates it. `run_frozen_oracle.py` is that gate: the witness command must be
   baseline-authored (verbatim in the anchor file's base-tree blob, with the base pinned to the
   default branch), the executable must be trusted (tracked in-repo and frozen, or non-user-writable
   outside — the untracked `.venv/bin/python` class refuses), verdict-affecting companions
   (conftest, runner config, `-m` shadowing) join the surface, and only then does the envelope run:
   validate the full oracle surface (lexical paths, symlink-chain hops, resolved targets) against
   the baseline, snapshot it, run the witness without a shell under a sanitized environment, and
   recheck the snapshot before returning the verdict — an exit code produced by frozen,
   baseline-bound bytes, not a promise. Stated precisely: git proves *committed* baseline/final
   state, never that an unobserved worktree edit didn't happen earlier; the runner's envelope is
   what binds the checked bytes to the exit code. Accepted residuals: a mid-run edit restored
   before the recheck, and the gate binds authorship/bytes, not semantics (see KNOWN-BYPASSES.md).
   `check_oracle_frozen.py` remains the check-only diagnostic and performs none of the bindings.

4. **Private ↔ public.** `leak-guard` gates content crossing outward, fail-closed, with explicit
   (never silent) whitelisting.

## Layout

```
excubitor/core/           # the model-blind policy core (stdlib only; no host I/O):
                          #   events.py (PreToolEvent / Decision(pass|deny)), git_state.py (read-only
                          #   git boundary), policies/{loop_vc,default_branch,one_unit,self_integrity}.py,
                          #   dispatch.py (deny precedence) + tests under excubitor/tests/
excubitor/adapters/       # per-runtime adapters: claude_code.py (shared PreToolUse envelope glue)
excubitor/cli.py          # the `excubitor` console entry point (a thin argparse dispatcher)
excubitor/config.py       # neutral .excubitor/policy.toml + EXCUBITOR_* precedence (host I/O; not core)
excubitor/commands/       # CLI subcommands: install, uninstall, status, print-config, doctor
excubitor/installers/     # the transactional installer foundation (Campaign 2):
                          #   runtime.py (Claude Code profile + discovery), plan.py (write-nothing
                          #   dry-run), validate.py (nested config validation), receipts.py (exact,
                          #   hash-bound ownership), transaction.py (atomic stage/register/rollback/
                          #   recover + uninstall), status.py, doctor.py
excubitor/probe.py        # the harmless-denial probe framework (disposable sandbox + marker)
hooks/                    # the four Claude Code guard entry points — thin adapters over the core —
                          # + _denial_log.py telemetry helper + tests/ (the differential oracles)
runtime/spec_adapter.py   # the generic excubitor.pre_tool.v1 adapter (JSON CLI) + tests/
skills/<name>/SKILL.md    # open Agent Skills format: frontmatter trigger + instructions
skills/<name>/scripts/    # executable helpers (ralph-loop's oracle/suite/suspend checks)
skills/<name>/tests/      # per-component pytest suites
pyproject.toml            # package metadata (excubitor console script; stdlib-only, no runtime deps)
packaging/build.py        # stdlib-only, byte-reproducible wheel/sdist/pyz builder (+ tests/)
docs/design/              # the deliberation records behind each mechanism
docs/telos/               # this repo's own claims, audited by its own audit-telos
scripts/install.sh        # legacy symlink + settings.json registration (superseded by `excubitor install`)
```

## The installer foundation (Campaign 2)

The package ships an `excubitor` CLI whose `install`/`uninstall`/`status`/`print-config`/`doctor`
subcommands drive a **transactional** installer over a runtime's config. Its spine:

- **Discover → validate → plan** are read-only; `install --dry-run` writes nothing (proven by a
  byte-for-byte filesystem snapshot). Validation rejects a malformed settings structure or an unknown
  policy version *before* any mutation.
- **Stage → register → receipt** run as one journalled transaction: artifacts are staged atomically
  (temp + `os.replace`, hash-verified), the exact-tuple hooks are merged while unrelated entries survive
  byte-for-byte, and a **hash-bound receipt** records exactly what the install owns. Any failure rolls
  back the exact prior state; a leftover journal (a crash) is recovered on the next run.
- **Ownership is never a substring.** Upgrade/uninstall touch only what the receipt records by exact
  path+SHA-256 (files) and exact tuple (registrations); a file edited since install is preserved.
- **Protection is earned, not assumed.** `status`/`doctor` never infer "protected" from file presence —
  only a real host harmless-denial probe does, and absent a real runtime-dispatch witness they report
  `needs-probe`. Only Claude Code is a supported runtime; other hosts are reported designed-not-built.

Components are deliberately decoupled: the hooks are thin entry points that import only the model-blind
`excubitor` package (never the skills); the skills' scripts import nothing from the hooks; the only
vendored code is `claude_usage.py` (next to the one script that needs it). One core, many adapters — the
policy logic lives once in `excubitor/core/` and every adapter shares it verbatim, so a decision can
never fork between hosts. Together they form the four-layer harness described in the README.
