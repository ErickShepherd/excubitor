# Related work

Where excubitor sits in the fast-growing literature on making LLM agents safe to run. This is
**positioning, not a survey** — the citations are representative of a cluster, not exhaustive, and the
field moves monthly. The honest summary up front: excubitor is an **engineering artifact with a narrow,
specific thesis**, not a benchmarked research result. Several systems below have formal guarantees or
empirical evaluations excubitor does not claim. What excubitor offers instead is a *different target*
and a *different posture* — deterministic, witness-backed, self-auditing, and radically explicit about
its limits — on a slice of the problem the frameworks below mostly do not center.

## The landscape, in clusters

**Injection defense — protecting the agent from a hostile environment.** The largest body of recent
work defends the agent against *inputs it doesn't control*: indirect prompt injection, poisoned tool
outputs, manipulated runtime feedback. VIGIL ([arXiv:2601.05755](https://arxiv.org/abs/2601.05755))
is representative — a "verify-before-commit" protocol against **tool-stream injection**, where
"manipulated metadata and runtime feedback hijack execution flow." The threat model is
*environment → agent*.

**Probabilistic behavioral monitoring — detecting drift in an honest agent.** Agent Behavioral
Contracts ([arXiv:2602.22302](https://arxiv.org/html/2602.22302v1)) formalizes expected behavior as
preconditions/invariants/recovery and enforces it as **(p, δ, k)-satisfaction** — a contract holds with
probability *p*, within tolerance *δ*, recovering within *k* steps. It **detects and recovers** from
behavioral drift; its evaluated setting is *drift in honest agents under LLM non-determinism*, and it
does not take up whether the agent might tamper with its own monitor/contract — the integrity of the
enforcement layer is simply not its subject. (This is excubitor's reading of the paper's scope, not a
quotation from it.)

**Policy-DSL runtime enforcement — a language for what the agent may do.** A family of systems wraps
the agent in a domain-specific policy layer intercepting tool calls: NeMo Guardrails (input/output/
tool-call rails), and research enforcers such as AgentSpec and ProGent (DSLs for tool-access control at
call time). These are *expressive and general* — you write the policy — and typically presume the
policy engine is trusted and correctly specified.

**Verified code generation — prove the action before running it.** VeriGuard
([arXiv:2510.05156](https://arxiv.org/abs/2510.05156)) enhances agent safety by generating *verified*
code, shifting assurance to a formal-methods step ahead of execution.

**General deterministic rails.** The pragmatic baseline much of industry runs: fast, deterministic
pre-/post-LLM checks — regex PII/secret scanners, rule-based blocklists — in the hot path. Excubitor's
own `leak_check.py` is squarely in this tradition, and makes no larger claim for that piece.

## What excubitor shares — and where it diverges

Excubitor is a **runtime-enforcement** system in the same broad family as the DSL and rails work: it
intercepts tool calls (PreToolUse hooks) and decides deny/allow *outside the model*. It shares their
core conviction that prompts are advice and enforcement must be mechanical. It diverges on **target**,
**posture**, and one **assumption** the others mostly don't question:

- **Target — the agent's own forged "done," and the irreversibility boundary.** The clusters above
  largely defend against a hostile *environment* (injection), monitor *drift* in an honest agent, or
  express *general* policy. Excubitor centers a narrower, specific failure: an **unattended loop that
  blesses its own completion and then acts irreversibly on it**. Its two-axis decomposition —
  *is the done-signal forgeable?* × *is the act reversible?* — is a design lens aimed squarely at that
  case, not a general policy language. (The real-world instance it is built around, the July-2025
  Replit incident, is in [`docs/case-studies/replit-2025.md`](docs/case-studies/replit-2025.md).)

- **Posture — deterministic prevention + binary witness-backed evidence, over probabilistic
  monitoring or LLM judgment.** Where ABC bounds drift statistically and permits transient violations
  within a window, excubitor's guards are hard fail-closed fences on a specific irreversible set, and
  its evidence tier trusts a **witness's exit code over any model judgment** (an unbacked "done" is
  mechanically demoted, never argued with). This is less general and less adaptive on purpose — it buys
  a decidable, testable guarantee on a small surface instead of a probabilistic one on a large surface.

- **The assumption it refuses — that the judge is trustworthy.** This is the sharpest divergence.
  Most enforcement work leaves the enforcer's *own* integrity unaddressed — implicitly treating the
  monitor/policy layer as a separate privileged tier the agent cannot reach (ABC, ProGent, and
  AgentSpec each focus elsewhere and do not center self-tampering). Excubitor takes the opposite
  starting point: in a real agent
  harness the loop often *can* reach its own guards — the marker file, the hook scripts, the settings
  that register them — so it fences the guards' **own kill-switches** and treats
  *a judge the model can rewrite is not a judge* as a first-class requirement
  ([`hooks/guard-self-integrity.py`](hooks/guard-self-integrity.py), `TELOS-007/008/009`). Self-
  integrity of the enforcement layer is, as far as this positioning found, under-addressed in the
  cited work.

- **Honesty as a design constraint.** Excubitor enumerates its own bypasses
  ([`KNOWN-BYPASSES.md`](KNOWN-BYPASSES.md)) and states "seatbelt, not sandbox" plainly, where research
  systems understandably present their strongest evaluated case. Different genre, different obligation —
  but for a *practitioner* choosing what to install, the enumerated-limits posture is the contribution.

## What excubitor does NOT claim (the honest concessions)

- **No formal guarantee and no benchmark.** ABC has drift-bound theorems; VIGIL evaluates on a
  959-case injection benchmark (SIREN); VeriGuard leans on formal verification. Excubitor has a test
  suite and a self-audit, not a proof or a comparative eval. Its assurance is *"every claim is re-proven
  by an executed test on every CI run,"* which is engineering rigor, not a theorem.
- **No injection defense.** It does nothing about poisoned tool streams or prompt injection — VIGIL's
  and SafeMCP's territory, and a real gap if that is your threat.
- **Narrow blast radius.** It fences git/VC actions on one host runtime (Claude Code). Its decision
  core is *demonstrably* runtime-neutral — a second, non-Claude-Code adapter drives the same code with
  an equivalence test ([`SPEC.md`](SPEC.md)) — but that demonstration is a generic envelope, not an
  integration proven against a live third-party runtime (LangChain, an MCP gateway, etc.). The DSL
  systems are far more general.

## The one idea worth taking

If a single conceptual contribution survives the humility above, it is the pairing of **(1) the
two-axis lens** — decompose agent-act safety into *done-signal forgeability* × *blast-radius
reversibility*, and only permit autonomous action in the unforgeable-and-reversible quadrant — with
**(2) enforcement-layer self-integrity** — the judge must be one the judged agent cannot rewrite,
which most runtime-enforcement work assumes away. Those two, together, are the frame excubitor argues
for; the code is one small, honest, testable instance of it.

*Citations are representative and current as of mid-2026; this is a fast-moving area and omissions are
not judgments. Corrections and pointers to prior art we missed are welcome (see
[`SECURITY.md`](SECURITY.md) for how to reach out) — getting the positioning right matters more than
getting credit.*
