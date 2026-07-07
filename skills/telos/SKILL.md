---
name: telos
description: >-
  Author and maintain a repo's living intent record (docs/telos/) — the motive, the telos (purpose it
  must fulfil), and the falsifiable claims the audit-telos audit checks code against. Use to write a new
  purpose claim, to bootstrap an intent record for a repo that has none, to forward-spec a greenfield
  repo's intended invariants before the code exists (telos-first, with TODO discharge pointers), to AMEND a claim whose stated
  purpose went out of date (the remediation amend-fork), to retire/supersede a claim, to promote a
  checkable CLAUDE.md boundary into a claim, or to turn an audit-telos orphan finding into a claim. Every
  claim is grill-gated to a decidable one-line contract before it is written, and every mutation is a
  reviewable commit. This is the ONLY skill that writes the record; audit-telos can only read it.
argument-hint: "<repo> [new <intent> | amend <TELOS-NNN> | retire <TELOS-NNN> | bootstrap | promote | from-orphan <target>]"
allowed-tools: [Read, Grep, Glob, Bash, Write, Edit]
metadata:
  version: 0.1.1
---

# telos

Owns the **write** side of the purpose-conformance pair (`audit-telos` is the read side). A claim is a
*falsifiable hypothesis about purpose* — `### TELOS-NNN — <title>` + `- key: value` lines — not decorative
prose. The strict parser in `telos_check.py` is the contract; **validate every mutation through it before
committing**, and never let the audit pass write here.

Two gates, both required (orthogonal):
- **grill-me = the quality gate.** Before writing/amending a claim, run the grill discipline (one question
  at a time) until the intent is a *decidable* one-line `contract:` resolvable against a single
  `discharged-by: path::symbol`. If you can't state what would falsify it, it isn't a claim yet.
- **git = the deliberateness gate.** Every `docs/telos/` mutation is its own attributable commit.

## When to use

- "Write/record a purpose claim", "what is this app's telos", "bootstrap a telos record".
- **Forward-spec a greenfield repo (telos-first).** Author the intended invariants as claims *before* the
  code exists — each `discharged-by: TODO` (or `none`) — then discharge them as you build. The audit
  recomputes `state:`, so an unbuilt claim honestly reads as undischarged and never masquerades as
  DISCHARGED — making the telos the build's spec, not a retrofit. Still grill-gated: a forward-spec claim
  must already state its decidable `contract:` and the symbol it *will* be discharged by.
- **Amend** a claim after `audit-telos` flagged DRIFTED *and the code is right, the purpose was outdated*
  (the `audit-remediate` amend-fork routes here).
- **Retire/supersede** a claim (a real rename/replacement — IDs are immutable, so this mints a new one).
- **Promote** a checkable CLAUDE.md hard boundary into a claim.
- **from-orphan**: turn an `audit-telos` `[telos-orphan]` "should-be-claimed" finding into a claim.

## The claim block

```markdown
### TELOS-NNN — <reword-tolerant title>
- state: DISCHARGED            # last-known; the audit recomputes it — informational here
- intent: <why this must hold; what's worse if it doesn't>
- discharged-by: <path::symbol>   # a SINGLE function/class/method qualname (or `none`/`TODO` if unbuilt)
- contract: <the one-line falsifiable assertion the audit judges fulfilment against>
- verified-by: <test-id-or-command>   # optional executable witness; exit!=0 ⇒ DRIFTED, trusted over the LLM
- source: CLAUDE.md#<anchor>   # optional provenance (e.g. a promoted boundary)
- last-grilled: <YYYY-MM-DD>
- anchor: none                 # or an opt-in content-hash for a high-stakes stable contract
- superseded-by: TELOS-NNN     # set ONLY when retiring; the audit then skips it (history preserved)
```

`TELOS-NNN` is **opaque, mint-once, immutable.** Reword the title freely; **never edit the ID.** If a
claim needs several symbols, split it into atomic claims (or use `covers:`) rather than listing them.

## Steps

Let `R` = the repo; `SKILL_DIR` = this skill's dir; `CHECK` = `$SKILL_DIR/../audit-telos/telos_check.py`.

1. **Locate / create the record.** `R/docs/telos/app.md` holds Motive + Telos + Claims. Per-feature
   `R/docs/telos/<feature>.md` is spawned **lazily** — never pre-create empty files. For **bootstrap**,
   write Motive + Telos first (grill the user for the real *why*, not a restatement of what it does).

2. **Grill the claim** (one question at a time, grill-me discipline) until you have: a decidable
   `contract:`, a single `discharged-by` symbol that exists (or `none`/`TODO` if intentionally unbuilt),
   and an `intent:` that says why it matters. Set `last-grilled:` to today.

3. **Mint the ID** for a NEW claim: scan all `R/docs/telos/*.md` for `### TELOS-NNN`, take `max(NNN)+1`,
   zero-padded to 3. Never reuse a retired ID.

4. **Write the block** (Write/Edit) into the right file under the `## Claims` section.

5. **Validate before committing — non-negotiable:**
   ```bash
   python3 "$CHECK" parse "$R" >/dev/null || { echo "record invalid — fix before commit"; exit 1; }
   ```
   The strict parser refuses unknown keys, bad states, malformed pointers, dup keys/IDs. A failure here
   means the record is broken; fix it, don't commit it.

6. **Commit the mutation** on a branch (never the default branch): one focused commit per claim, e.g.
   `git -C "$R" commit -m "telos(TELOS-007): claim export redacts PII before write"`.

## Operation specifics

- **Amend** (`amend <ID>`): code is right, the stated purpose drifted. Re-grill the *new* intent, edit the
  claim's `intent`/`contract` (NEVER the ID), bump `last-grilled`. The commit IS the gate that lets
  `audit-remediate` mark the finding `(disp: AMENDED)` — an amend with no commit stays PENDING.
- **Retire/supersede** (`retire <ID>`): set `superseded-by: <new-ID>` on the old claim (the audit skips it,
  history preserved) and author the replacement as a new claim. Do **not** delete the old block — that's
  what loses the history the opaque-ID design exists to protect.
- **Promote** (`promote`): find a CLAUDE.md hard boundary that is *checkable against code*; author a claim
  carrying `source: CLAUDE.md#<anchor>`. Leave the human sentence in CLAUDE.md — link, don't move.
- **from-orphan** (`from-orphan <target>`): an `audit-telos` candidate the LLM judged "should be claimed".
  Grill it into a real claim with `discharged-by:` = that symbol.

## Notes

- **Never** write the record from the audit pass; `audit-telos` has no Write tool by design.
- A new claim's `state:` is informational — the audit recomputes it. Don't hand-assert DISCHARGED to dodge
  a finding; the audit will contradict you, loudly.
- Disputed spirit-of-requirement → the human runs `/deliberate --run-id=<claim-ID>`; record the ruling's
  outcome in the claim (re-grill + bump `last-grilled`), not an automated escalation.
- Run `/audit-telos <repo>` after a batch of authoring to confirm the new claims resolve as intended.
- **A telos can anchor a self-paced `/loop` (Ralph-style) — but the loop may not discharge its own claims.**
  A loop that writes its own witnesses produces *backed* `DISCHARGED` claims, routing around the
  SUSPECT-demotion guard, so its self-judgment can't be trusted to halt-and-merge. A loop is
  stop-and-surface, never stop-and-act: run it with `CLAUDE_LOOP_GUARD=1` (the `guard-loop-vc.py` hook
  blocks in-loop merge/push/branch-delete) and let an out-of-loop reviewer (`pre-merge-review`) or a human
  confirm discharge. The runnable recipe is the `telos-loop` skill (`/loop /telos-loop <repo>`); design +
  rationale: `docs/design/loop-telos-anchor-deliberation.md`.
