# Claude Code project guidance

## Excubitor roadmap work

When asked to implement, continue, loop over, or assess the outstanding review, model-agnostic, or
multi-runtime distribution work, read these files before changing code:

1. the build checklist — the
   executable checklist and current sequencing authority.
2. the review notes
   — reproduced defects, required fixes, and Phase 0 exit criteria.
3. [`docs/design/model-agnostic-runtime.md`](docs/design/model-agnostic-runtime.md) — shared-core and runtime
   adapter design.
4. [`docs/design/installable-multi-runtime-distribution.md`](docs/design/installable-multi-runtime-distribution.md)
   — packaging, installation, host conformance, and layered enforcement plan.
5. [`skills/ralph-loop/SKILL.md`](skills/ralph-loop/SKILL.md) — loop mechanics and stop/surface rules.

Treat the checklist as a `ralph-loop --anchor checklist` anchor. Work from the first unchecked item,
complete exactly one unit and one focused commit per iteration, then end the turn so the next invocation
re-reads the plan. Do not batch-drain a phase.

Phase 0 must run conservatively with `CLAUDE_LOOP_GUARD=1`. Do not use `yolo` while R-01 through R-05 are
open: the review found defects in the VC guard, default-branch path handling, oracle gate, and telos
validation. A `verify:` command is evidence in conservative mode, not permission to merge, push, publish,
or mark a human/external gate complete.

Never resolve an open `DECIDE:` item by guessing. Never mark live-host trust, marketplace publication,
remote repository policy, credentials, administrator configuration, cross-platform evidence, or final
security sign-off complete without the named external evidence. Stop and surface those items.

If Claude Opus 4.8 is required, launch Claude Code with the exact model ID rather than the moving `opus`
alias:

```bash
CLAUDE_LOOP_GUARD=1 claude --model claude-opus-4-8
```

Then start the repo plan from the Claude Code session:

```text
/loop /ralph-loop --anchor checklist --repo /path/to/excubitor \
  --plan the build checklist
```

The loop may commit on its dedicated implementation branch. It must not merge to the default branch,
push, publish packages/plugins, change remote protection, or delete branches.
