---
name: telos-loop
description: >-
  The telos-anchored mode of `ralph-loop` — a self-paced `/loop` (Ralph-Wiggum style) driven by a repo's
  `docs/telos/` claim ledger (`audit-telos` as both the spec and the progress signal). Use when asked to run
  a loop / autonomous build against a repo's telos, to "keep working through the telos", or to "discharge the
  undischarged claims". This is now a thin alias: the full recipe — one iteration per invocation, re-read the
  ledger each fire, advance one claim, stop-and-surface (never stop-and-act), the no-self-bless discharge
  split, and the opt-in `--yolo` posture — lives in `ralph-loop` under its **telos** anchor. Prefer invoking
  `ralph-loop --anchor telos` directly; this alias remains so existing "loop the telos" requests still fire.
allowed-tools: [Read, Grep, Glob, Bash, Edit, Write, Skill]
metadata:
  version: 0.3.0
---

# telos-loop

**This skill is an alias.** It is the **telos anchor** of [`ralph-loop`](../ralph-loop/SKILL.md) — the
generalized pluggable-anchor loop recipe. The loop discipline (fresh re-read each pass, one claim per
iteration, commit, no-self-bless, stop-and-surface, the `--yolo` verifiable-autonomy posture) is
**anchor-independent** and is stated once in `ralph-loop`; the telos-specific spec source (`docs/telos/`
ledger via `audit-telos`) and progress signal (claim states + coverage) are `ralph-loop`'s **Anchor: telos**
section.

## How to run

```
/loop /ralph-loop --anchor telos <repo>
```

Set the seatbelt **before** launching the session (`CLAUDE_LOOP_GUARD=1 claude`, or `=yolo` for the
verifiable-autonomy posture). Everything else — preconditions, the per-iteration loop body, the claim
priority order (`DRIFTED` > `UNMET`/`TODO`/`none` > failing-witness), the discharge split, stop-and-surface,
and the YOLO oracle gate (`check_oracle_frozen.py`) — is in
[`ralph-loop/SKILL.md`](../ralph-loop/SKILL.md). Read that.

## Why an alias and not a duplicate

`telos-loop` shipped first (2026-06-18) as the telos-only recipe; `ralph-loop` generalized it (2026-06-19) to
a pluggable anchor (telos + green-the-suite) so the same discipline serves repos with **no** telos ledger. To
avoid two copies of the load-bearing contract drifting apart, the recipe lives in `ralph-loop` and this name
forwards to it — the telos trigger phrasing is preserved here so "loop the telos" still resolves. Design:
`docs/design/ralph-loop-green-the-suite.md`.
