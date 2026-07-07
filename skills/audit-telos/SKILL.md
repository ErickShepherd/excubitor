---
name: audit-telos
description: >-
  Audit whether an app still serves the purpose it was built for — a read-only conformance audit of a
  repo's living intent record (docs/telos/) against its actual code. Reports claims that have DRIFTED
  (code no longer serves the stated intent), are UNMET (promised but never built), are SUSPECT (the
  record's own honesty is in doubt), and code that is ORPHAN (significant surface serving no stated
  purpose) — plus a coverage figure. Use to check purpose-conformance / intent-drift / "does this still
  do what it was for", to bootstrap an intent record for a claimless repo, or when asked to run
  /audit-telos. It never writes the record (that is the `telos` skill); it only emits a findings ledger.
argument-hint: "<repo or dir to audit> [--no-witnesses to skip verified-by execution on untrusted repos]"
allowed-tools: [Read, Grep, Glob, Bash]
metadata:
  version: 0.2.0
---

# audit-telos

A **read-only** purpose-conformance audit. It composes with `audit-repo` (which checks *well-built* and
*safe*); this checks whether the code still serves its **declared intent**. The deterministic spine is
`telos_check.py` (sibling script); this skill adds the two irreducible LLM judgments on top and emits a
ledger in the exact `audit-repo` worklist format, so it scores through the unmodified `audit_accuracy.py`.

**It cannot mutate the intent record.** No `Write` tool; `docs/telos/` is owned by the `telos` skill.
Authoring, amending, and accepting proposed claims all route there. This pass only *reads* and *reports*.

## When to use

- "Has this app drifted from its purpose?", "does this still do what it was built for?", intent/telos/
  purpose-conformance review, or an explicit `/audit-telos <repo>`.
- To **bootstrap** an intent record: pointed at a repo with no `docs/telos/`, the audit aborts loudly; the
  record-free `bootstrap` subcommand (step 5) then surfaces the significant surface as candidate claims to
  hand to `telos`.
- As the *periodic, deep* arm of anti-rot. The *per-change* arm is `pre-merge-review` — don't duplicate it.

## Steps

Let `SKILL_DIR` = this skill's directory; `R` = the repo path; `DATE` = today (`YYYY-MM-DD`).

1. **Run the deterministic pass** and capture its JSON:
   ```bash
   RESULT=$(mktemp); J=$(mktemp); LEDGER="$R/docs/audits/$(basename "$R")-telos-$DATE.md"
   python3 "$SKILL_DIR/telos_check.py" audit "$R" --date "$DATE" > "$RESULT" || { cat "$RESULT"; exit 2; }
   ```
   A non-zero exit is an **ABORT** (absent/empty/malformed record, or zero claims) — surface it, do **not**
   fabricate a clean verdict. An abort on a claimless repo is the bootstrap entry point (step 5).

2. **Read `$RESULT`.** It carries, per claim: a deterministic `state` (UNMET / SUSPECT / DISCHARGED-via-
   witness / DRIFTED-via-witness) **or** `needs_judgment: true`; an audit-computed evidence `tier`
   (`witness` / `judged` / `cache` / `unproven` — never author-written, so it can't be forged); plus the
   candidate-orphan list, the coverage figure, and a `low coverage` flag. A `needs_judgment` claim also carries `neighbors` (its 1-hop
   callees as `path::symbol` pointers — the evidence window) and `neighbors_truncated`. The script already
   ran any `verified-by:` witnesses and trusted their exit codes — **do not second-guess a mechanical
   witness result.**

3. **Make ONLY the two LLM judgments** the script left open. Read the actual code for each:
   - **`needs_judgment` claims → DISCHARGED vs DRIFTED.** Read the `discharged-by` symbol **and every
     `neighbors` pointer**, then judge: does the code fulfil the claim's `contract` / `intent`? Specifically
     hunt the **silent-collapse** failure mode — code that is locally correct (its own tests green) yet has
     erased a distinction the *purpose* depends on. The window is widened to the callees precisely because
     this collapse often hides one hop away: the claimed symbol still *looks* right while a delegate it calls
     stopped enforcing the guarantee (e.g. `run()` reads fine but the `redact()` it calls no longer redacts).
     That is DRIFTED even when nothing local looks broken. When `neighbors_truncated` is true the neighborhood
     is only partial — prefer recommending a `verified-by:` witness over a confident DISCHARGED. Record a
     one-line rationale.
   - **Candidate orphans → orphan / plumbing / claim.** For each, judge: a genuine `orphan` (real surface
     serving no stated purpose → finding); legit unclaimed `plumbing` (drop silently); or `claim` —
     real purpose nobody wrote down (the most valuable output → route to `telos` as a proposed claim).
   Be conservative: when unsure an orphan is meaningful, prefer `plumbing` (the candidate list is
   pre-filtered but the call-graph is best-effort; over-flagging trains a bulk-clear reflex).

4. **Write the judgments JSON, then emit + project the ledger** (all via Bash — no record mutation):
   ```bash
   cat > "$J" <<'JSON'
   { "TELOS-007": {"verdict": "DRIFTED", "rationale": "export.run no longer redacts before write"},
     "scripts/legacy.py::sync_v1": {"verdict": "orphan", "rationale": "dead path, no caller, no claim"} }
   JSON
   mkdir -p "$(dirname "$LEDGER")"
   python3 "$SKILL_DIR/telos_check.py" emit-ledger --result "$RESULT" --judgments "$J" --date "$DATE" > "$LEDGER"
   python3 "$SKILL_DIR/../audit-repo/audit_accuracy.py" --project "$LEDGER"   # off-repo accuracy store
   ```
   Verdict keys are claim-IDs (for `needs_judgment`) and candidate `target`s. Anything you leave unjudged
   emits as `(disp: pending)` — never a silent clean pass. Present the ledger path and the `## Top`
   findings to the user; hand the worklist to `/audit-remediate`.

5. **Bootstrap a claimless repo.** If step 1 aborted with "no telos record", enumerate the significant
   surface with the record-free bootstrap path (`audit` would just re-abort):
   ```bash
   python3 "$SKILL_DIR/telos_check.py" bootstrap "$R"   # significant surface → proposed-claim candidates
   ```
   Then point the user at `/telos` to author `docs/telos/app.md` (motive + telos + a first handful of
   claims grilled out of that surface). The audit bootstraps the record; it does not write it.

## Notes

- **Incremental cache (tier-gated, judged-keyed).** Pass `--prior <last-ledger>` to `audit` to carry
  forward a claim that was DISCHARGED last run with a carry-eligible tier (`witness`/`judged`/`cache`),
  whose `discharged-by` fingerprint (symbol source + contract + intent) is byte-identical, **and** whose
  tool-written `judged` receipt is still fresh — it skips the LLM judgment (tier `cache`). Staleness re-keys
  on the tool-written `judged` date in the ledger verdict table, **not** the author-written `last-grilled`
  (which a human can bump without re-grilling), so a stale judgment can't be revived by editing the record.
  Reuse this and the accuracy-store projection; do **not** reuse `audit-repo`'s background fan-out (a
  claim set is bounded — synchronous is correct).
- **Evidence tier & honesty.** The record can claim `state: DISCHARGED` honestly only when *backed*: the
  strict parser demotes an unbacked `DISCHARGED` (no `verified-by`) to SUSPECT at parse time (a read-time
  rule — it never mutates the `telos`-owned record), and a witness is the only path to a *recorded* clean
  DISCHARGED (an LLM verdict lives in the ledger as a tool-written `judged` receipt, never written back into
  the record). Rationale and the deferred record-write-back call: `docs/design/telos-evidence-tier.md`.
- **Coverage is advisory in v1.** A low figure (`refuse a clean verdict` flag set) means the record likely
  *under-claims* (a Goodhart trap: few claims read as "100% discharged"). Report it; do not treat it as a
  hard gate yet (uncalibrated — too aggressive a floor makes the record a chore that gets abandoned).
- **Untrusted repos:** the resolver is static AST and never imports/executes the target, but a
  `verified-by:` witness *does* run code. Use `--no-witnesses` when auditing a repo you don't trust.
- **Non-Python repos** run a degraded grep-existence mode: drift/unmet still work; orphan + coverage are
  announced as skipped (no call-graph).
- **Disputed "spirit of requirement"?** Don't auto-escalate. A human runs `/deliberate --run-id=<claim-ID>`
  on that one claim; the ruling is durably addressable by the claim-ID.
- The deterministic contract lives in `telos_check.py`'s module docstring; the ledger/facet schema is
  shared verbatim with `audit-repo` (`[telos-drift] [telos-unmet] [telos-orphan]`).
- **Coverage is not a halting oracle for an autonomous loop.** A self-paced `/loop` must not treat
  "all claims discharged" (or this coverage figure) as license to halt-and-merge — discharge is
  surface-not-correctness and a loop that authors its own `verified-by` witnesses satisfies the parser
  without satisfying the claim. Coverage may *trigger* a stop-and-surface; an out-of-loop reviewer confirms.
  The recipe that wires this audit in as a loop's progress signal is the `telos-loop` skill
  (`/loop /telos-loop <repo>`); see `docs/design/loop-telos-anchor-deliberation.md`.
