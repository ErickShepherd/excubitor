# Decision record — telos evidence tier (make overclaiming mechanically impossible)

- **Date:** 2026-06-16
- **Status:** decided (Option **B**) — build authorized; implementation in worktree branch `feat/telos-evidence-tier`
- **Method:** `/brainstorm` (4 lenses → opus shortlister) → code-grounded verification (findings A–D) → direct
  A-vs-B decision (deliberation judged **not required**; the verification collapsed the contested core)
- **Supersedes nothing; orthogonal to** the prior `telos-schema-2026-06-15` rigor-tier/anchor decision (see *Reconciliation*).

## Problem

A telos claim carries an author-written `state` (one of `{DISCHARGED, UNMET, DRIFTED, SUSPECT}`). Today 2 of
8 claims in this repo carry an executable `verified-by` witness; the other 6 read `state: DISCHARGED` on a
contract pointer alone. The record can **claim more than has been demonstrated**. Two concrete overclaim
surfaces, both verified in code:

1. **The human-facing record overclaims.** `docs/telos/app.md` displays `state: DISCHARGED` for all 8 claims.
   That field is **author-written and only validated for legal vocabulary** (`telos_check.py` parse-time state
   check) — a human reading the record is told "discharged" with nothing behind it for 6 of them. (The
   deterministic `audit()` is actually more honest: a witness-free, non-suspect claim returns
   `needs_judgment`/`PENDING` on a fresh run — `telos_check.py:604-614` — so the *audit* does not mint a free
   DISCHARGED, but the *record a human reads* does.)
2. **The cache carries a stale judgment forever.** The incremental cache carries a prior DISCHARGED forward on
   a byte-identical fingerprint (`telos_check.py:605`). Its only expiry is staleness of **`last-grilled`**
   (`telos_check.py:583-584`) — an **author-written** date that can be bumped without re-grilling. So a one-time
   (possibly rubber-stamped) LLM judgment persists indefinitely. `claim_fingerprint` already folds in
   contract+intent (the DEF-4 fix), so an *amended* contract re-judges — but an unchanged one never does.

## The decision

**Option B — make overclaiming mechanically impossible now**, not merely visible. Chosen by the user over
Option A (surface the audit-computed tier in the ledger, defer enforcement). The hinge was the *consumer*
question (finding A): A is sufficient only while the **sole consumer of the record is a human applying
judgment**; B earns its cost once the record will feed an **automated gate** (a CI step, a git hook, or
`pre-merge-review` consuming the audit) that *acts on* the verdict with no human in the loop. The user intends
that trust posture, so the record must be tamper-proof up front.

### Why deliberation was not required
The brainstorm + the A–D code verification already collapsed the contested core: REPRESENT is settled by facts
(the tier is already computed; an author-declared tier just relocates the overclaim → **audit-computed**), and
the only genuine fork left was the trust-posture value call (visible-now vs tamper-proof-now), a single axis
the user decided directly. A 4-lens deliberation would have re-derived this at multiplied cost — the oracle
gate refuses it.

## Scope of B (the tamper-proof evidence model)

> **⚠ Superseded by the 2026-06-16 Deliberation addendum (below).** The in-record tool-written *seal* this
> section describes was **not implemented** — the deliberation moved the receipt to the **ledger** and dropped
> record write-back (D4). Read this section as the original proposal; the addendum governs what shipped.

Four **coupled** components (finding B proved demotion and receipts cannot ship apart):

- **B1 — audit-computed evidence tier, surfaced.** Add an explicit `tier` to each claim's audit result and
  render it in the ledger Clean section and per-claim verdict table (replacing the bare `discharged.` at
  `telos_check.py:724`). Vocabulary (derived by the tool, never author-written → unforgeable):
  `witness` (verified-by passed) · `judged` (LLM DISCHARGED with a fresh receipt) · `cache` (carried from a
  prior witness/judged) · `unproven` (needs judgment) · `asserted` (record says DISCHARGED with nothing
  behind it — an error condition, see B2).
- **B2 — the author cannot mint a free DISCHARGED (the core tamper-proofing).** A pointed, witness-free claim
  may not read `state: DISCHARGED` unless a tool-written attestation backs it. Mechanism (lean: extend the
  existing fingerprint/anchor machinery rather than add a parallel field — see *Reconciliation*): the audit
  writes back a tool-computed seal on a genuine DISCHARGED; the **strict parser demotes any `state: DISCHARGED`
  whose seal is absent or mismatches the recomputed fingerprint to SUSPECT at parse time**, before audit logic
  runs. A hand-typed DISCHARGED with no seal is therefore SUSPECT, not a clean pass. This *strengthens* the
  "never pass a broken/absent record clean" invariant rather than weakening it.
- **B3 — judgment receipts (closes the cache-staleness hole, INV2).** When the LLM tier returns DISCHARGED for
  a witness-free claim, persist a **tool-written `judged: <date>`** receipt. The cache-carry and staleness gate
  key on `judged`, **not** the author-written `last-grilled`, so bumping `last-grilled` can no longer keep a
  stale judgment alive. Absent/stale `judged` → re-judge. (`last-grilled` remains a human-authoring signal; it
  stops being load-bearing for the cache.)
- **B4 — tier-gated cache.** The incremental cache carries forward DISCHARGED only when the originating tier is
  `witness` or `judged` (with a fresh receipt), never `asserted`. Encodes the invariant explicitly even though
  B2 already prevents `asserted` from reaching the verdict table.

### Deferred / rejected
- **INV3 (non-vacuous witness — a `verified-by` must reference its `discharged-by` symbol or declare `covers:`)**
  — orthogonal COST hardening against a fake `exit(0)` witness; **deferred** to a follow-up branch (separable,
  not needed for B's honesty core).
- **FP4 (git-ancestor self-invalidation)** — **rejected**: a `git merge-base` per claim breaks the
  fully-offline / no-VCS-introspection posture (itself a telos claim, TELOS-002 family).
- **FP1 (remove `state` entirely; author-written state = parse error)** — **deferred** as a possible future
  north-star; B2's seal achieves the honesty (a forged DISCHARGED is demoted) without the larger break.

## Constraints (carried verbatim)
stdlib-only + fully offline; `state` vocabulary `{DISCHARGED, UNMET, DRIFTED, SUSPECT}` — B adds parser keys
(`judged`, and the seal field or an extension of `anchor`/fingerprint), a **deliberate breaking change**; must
**not** weaken "the audit never passes an absent/broken record clean" (B2 strengthens it); portable across
repos; a false "this is proven" is worse than an honest "this is only asserted."

## Reconciliation with prior decisions (finding C)
- The `telos-schema-2026-06-15` deliberation decided a **rigor `tier`** (claim-ledger default + opt-in
  content-hash **`anchor`** promotion). That is **orthogonal** to this *evidence* tier (witness/judged/…), so
  this work is **not** redundant. To avoid the reinvention finding C warned of, **B2 should extend the existing
  `anchor`/`source_hash`/`claim_fingerprint` machinery** (already at `telos_check.py:576,581`) rather than add a
  parallel `sealed` subsystem; resolve `seal` vs `anchor` at build (they differ: `anchor` attests *code hasn't
  drifted*; the seal attests *a verdict was reached* — complementary, possibly one combined field).
- **DEF-4 is already fixed** (`claim_fingerprint` folds in contract+intent), so the remaining cache hole is
  narrowly the `last-grilled`-keyed staleness bypass, which **B3** closes.

## Build plan
1. **B1** — compute + surface the `tier` (ledger Clean section + verdict table). Smallest, observable first.
2. **B3** — tool-written `judged:` receipt + re-key the staleness/cache gate off it.
3. **B4** — tier-gate the cache carry.
4. **B2** — parse-time seal write-back + demotion of an unbacked `state: DISCHARGED` (the breaking change; land
   last, on top of the machinery the others establish).
5. Extend `scripts/`-style tests (stdlib `unittest`, mirroring `audit-telos/tests/`): planted records exercising
   each tier; a forged unbacked DISCHARGED demotes to SUSPECT; a bumped `last-grilled` no longer revives a stale
   judgment; cache carries `witness`/`judged` only.
6. Update `docs/telos/app.md` (this repo's own record) to the new schema; run the full audit; confirm the 6
   witness-free claims read their honest tier, not a free DISCHARGED.
7. `pre-merge-review` (opus) → on SIGN-OFF, local `--no-ff` merge into `main`, remove the worktree. No push.

## Open build-time sub-choices (decide while implementing, not blocking)
- **seal vs anchor:** one combined fingerprint field, or a distinct `judged`-seal alongside `anchor`?
- **demote vs reject:** an unbacked `state: DISCHARGED` → SUSPECT (degrade, recommended) vs hard parse abort?
- **state authorship:** keep `state` author-written-but-sealed (this plan) vs move to fully audit-written
  (FP1) — start with the former; revisit if forging proves a live problem.

## Prediction block (for `decision-review`)
- **crux:** does making overclaiming *mechanically impossible* (B), rather than merely *visible* (A), earn its
  added cost (breaking schema change + receipts + seal) before any automated consumer of the record exists?
- **tip-condition:** *fires* (A would have sufficed) if, by review, **no** automated gate consumes the telos
  record and the seal/receipt machinery has caught **zero** real forged/stale DISCHARGEDs — i.e. B was paid for
  and unused. *Does not fire* if an automated gate (CI/hook/pre-merge) starts trusting the record, or the seal
  catches ≥1 real overclaim.
- **testable-claim:** after B, no `state: DISCHARGED` can appear clean in the audit without a passing witness or
  a tool-written `judged` receipt; a bumped `last-grilled` cannot revive a stale judgment; all current repos'
  audits stay green except the 6 witness-free claims, which read their honest tier.

---

## Deliberation addendum — 2026-06-16 (revises the build, not the goal)

**Method:** `/deliberate` (4 lenses — Advocate, Ambition, Risk, Operator; toward:caution = 2:2 balanced; 2
rounds; opus Synthesizer, leanings-blind). **Trigger:** implementation discovered a conflict the plan did not
reconcile — B's mechanism specifies a **tool-written `judged:` seal written *into* the record**, but
`audit-telos` is **contractually read-only on `docs/telos/`** (SKILL.md: "cannot mutate the intent record. No
Write tool"; `allowed-tools` has no `Write`; writer(`telos`)/reader(`audit`) is a deliberate integrity
boundary). Note this read-only rule lives in SKILL.md + `allowed-tools`, **not** an explicit TELOS claim.

**The one framed question** ("where does the seal/receipt live: A=ledger / B=record-audit-writes /
C=record-telos-writes") **decomposed into four separable decisions.** The bundling was a vocabulary artifact;
the debate converged on an à-la-carte mix none of A/B/C cleanly named.

### Settled by fact during debate (not values)
- Pre-existing `audit()` was **already honest** — a witness-free resolving claim returns `needs_judgment`,
  never a free DISCHARGED. The **new** overclaim surface is the **record-as-read**.
- The seal is a **non-cryptographic** `sha256(source+contract+intent)` — hand-recomputable, no secret key. So
  an in-record seal **deters casual overclaiming but is forgeable**; a re-run `verified-by` witness is
  **strictly stronger** evidence (it forces the code to pass at audit time). [Risk; conceded by Advocate]
- The `judged:` receipt is **forgery-equivalent wherever it lives** — ledger or record. Location does not
  change its strength. [conceded by Advocate, Ambition, Risk]
- A gate can consume the **tool-written ledger tier**; *"the gate must read the record, not the ledger"* is an
  **assumption, not a constraint**. [conceded by Ambition, Risk]
- Parser-demotion is **in-memory**: it makes every consumer routed through `parse_record`/`audit()` see
  SUSPECT, but does **not** rewrite the file — so the **raw `state: DISCHARGED` markdown still misleads a
  human/naive grep**. Only **write-back** fixes the raw text.

### Verdict (per decision)
- **D1 — compute + surface the evidence `tier` (B1). SHIP (this worktree).** Read-derived, no write path.
- **D2 — tool-written `judged:` receipt in the LEDGER + re-key the cache/staleness gate off it (B3). SHIP.**
  This is the load-bearing honesty win for the 6 witness-free claims: it closes the `last-grilled`-bump
  staleness hole. Ledger-resident = forgery-equivalent to the record at **zero contract/blast-radius cost.**
- **D3 — parser demotes an unbacked `state: DISCHARGED` → SUSPECT in-memory (B2's read half). SHIP.** The
  single most leveraged honesty mechanism, requires **no write**, fail-safe (a bug yields a false SUSPECT,
  never a false-clean). Makes every parser-routed consumer honest — this is what collapsed Ambition's
  "rework / second breaking change" thesis.
- **B4 — tier-gate the cache carry (only `witness`/`judged` carry forward). SHIP.** Uncontested.
- **D4 — record WRITE-BACK (the B / C axis proper). NON-DECISION — premature; DO NOT SHIP NOW.** Its only
  marginal value over D1–D3 is making the **raw** `.md` honest to a **human reader / naive grep** — a UX gap,
  not a mechanical one. Against that: the read-only contract break, the **confused-deputy loop** (the same
  process reaches the verdict *and* writes the attestation of its own verdict into the record it audited —
  unrebutted by Risk), markdown-surgery/idempotency/fingerprint-round-trip fragility, and the untrusted-repo
  write surface (`--no-witnesses` disables witness execution but **not** the write-back). Operator's decisive
  point: write-back of the *demoted state* is **weaker** than a seal (an author re-edit just restores
  DISCHARGED); write-back of the *seal* is **forgeable** — the invasive option is also the weak one.
  **Resolvable prerequisite to revisit:** a concrete automated consumer reads raw `docs/telos/` state
  **outside** `audit()`, **or** a real human-review incident traces to a stale raw DISCHARGED.
  **If ever taken, the answer is C (the `telos` owner writes the seal), not B** — B is strictly dominated
  (receipt is ledger-resident regardless, so B keeps only the confused-deputy loop as its differentiator).

### Net: this **is Option A, fully realized** — ship D1 + D2(ledger) + D3 + B4 here; **drop record write-back**
as premature. It captures essentially all the demonstrable honesty gain at zero contract cost.

### Preserved dissent (the surviving values/empirical fork on D4)
- **FOR write-back (Ambition):** location of trust enforcement matters; the hybrid **bets all future consumers
  are well-behaved parser-users.** If a future gate reads raw record `state` without calling `audit()`, the
  raw record is a live overclaim vector and you pay a write-back change later.
- **AGAINST (Risk + Operator):** the seal is self-computed (not a MAC); write-back adds attack + maintenance
  surface without the strength a re-run witness already provides better. Not reconcilable by argument — turns
  on an **unobserved future fact**; hence a non-decision, not a coerced pick.

### Structured predictions (for `decision-review`)
- **D1 (tier):** crux = does tier discrimination have any consumer? · tip = *fires* if after a quarter no
  reader (human/tool) ever distinguishes tiers · claim = tier costs ~2–3 tests and is consumed by the
  cache-gate on day one.
- **D2 (ledger receipt + re-key):** crux = does re-keying staleness require record mutation? · tip = *fires*
  if a consumer is found that can obtain the `judged` date only from `docs/telos/` and cannot read the ledger
  · claim = a ledger-resident tool-written `judged` date closes the `last-grilled`-bump hole for all 6
  witness-free claims without touching the record.
- **D3 (parser-demotion):** crux = do consumers route through the parser? · tip = *fires* if a real consumer
  ships that reads record `state` without calling the parser (if fired, it strengthens D4, not D3) · claim =
  in-memory demote of unbacked DISCHARGED→SUSPECT makes every parser-routed consumer honest, no write,
  fail-safe.
- **D4 (write-back):** crux = existence of a parser-bypassing raw-`state` consumer, weighed against the
  confused-deputy / forgeable-seal cost · tip = *fires* when a concrete automated consumer reads raw
  `docs/telos/` state outside `audit()`, **or** human-review confusion from a stale raw DISCHARGED causes a
  real incident · claim = with no parser-bypassing consumer, write-back buys only raw-file readability at
  disproportionate integrity/operability cost; if later justified, the record owner (C) writes it, not the
  auditor (B).
