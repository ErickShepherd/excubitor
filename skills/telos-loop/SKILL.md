---
name: telos-loop
description: >-
  Start an Excubitor Ralph job from a repository's telos claims and acceptance
  witnesses. Use when asked to loop the telos or work through unmet claims.
  An alias of ralph-loop using the same launcher, limits and review rules.
allowed-tools: [Read, Grep, Glob, Bash, Edit, Write, Skill]
metadata:
  version: 0.4.0
---

# Telos-backed Ralph job

Read the sibling [ralph-loop skill](../ralph-loop/SKILL.md) and use its launcher
workflow. Read the project's `docs/telos/` record, identify the requested unmet
behavior and its witnesses, and translate them into the job goal and frozen
acceptance checks. Use `audit-telos` if available and useful for assessing drift.
If no record exists, surface that missing anchor or use another anchor the user
has already authorized; do not invent claims as completion evidence.

The launcher runs all agreed units with bounded helpers and one final writer.
Reuse the user's scope and limits. A successful job does not authorize the worker
to certify its own telos claims or change the ledger's acceptance criteria.
Ledger changes require the separate telos-authoring workflow when available.

Do not wrap the launcher in `/loop`, set legacy guard environment variables, or
enable automatic integration. This alias adds no CLI `--anchor` argument: the
anchor informs planning, while the executable uses the commands in `ralph-loop`.
