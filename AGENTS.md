# Excubitor development guidance

## Current product scope

Excubitor helps explicitly started Ralph runs finish agreed work safely and unattended. Ordinary
development remains ordinary, including fixes and roadmap work in this repository. Do not require
Ralph activation, a loop-specific environment variable, or a one-stage loop for ad hoc development.

Before changing runtime or distribution behavior, read the current
[Ralph-only remediation plan](docs/design/vendor-agnostic-enforcement-plan.md). It records the owner's
current scope and completion decisions and supersedes earlier always-active enforcement instructions.
Consult the [shared-core design](docs/design/model-agnostic-runtime.md),
[distribution design](docs/design/installable-multi-runtime-distribution.md), and
[known bypasses](KNOWN-BYPASSES.md) for architecture and existing evidence. Their older rollout order
or activation examples cannot override the corrected product scope.

## Ordinary development

Use focused, reviewable changes in an appropriate isolated worktree. Follow the configured commit
broker and preserve unrelated changes. A checklist can organize this work without activating Ralph.
Resolve routine implementation choices within the agreed scope; ask only when a consequential missing
decision or additional authority is needed. Do not create a decision gate for every internal choice.

Treat authorization as current and scope bound. A user instruction or explicit owner approval authorizes
the actions it names, including an outward action such as merge, push, publication, or deployment when
the destination and relevant conditions are clear. Do not infer authorization for a different action,
destination, or host state from historical plans, old receipts, or a nearby approval. Preserve rollback
evidence for material mutations and follow the supported transaction or broker.

A protection denial is evidence to diagnose the actual risk, affected scope, and available authorized
maintenance path. When a rule blocks progress, assess its empirical or logical basis, whether it
applies here, and whether a narrower alternative preserves the protection; use existing authorization
before asking for more. It is not by itself an approval gate or a reason to stop ordinary work. Do not
bypass security controls while the risk or authority remains unresolved; use the supported path or
surface the concrete blocker when no such path is available.

## Explicit Ralph runs

Use the [Ralph recipe](skills/ralph-loop/SKILL.md) and the appropriate anchor when the owner starts a
Ralph workflow. Verify the host can satisfy the current activation and continuation contract before
claiming unattended protection. Legacy environment-variable instructions are not the target activation
mechanism; never change launch shortcuts or silently broaden registration to make a run work.

Agree once on the work, acceptance checks, resource limits, and permitted completion actions. The
default result is reviewed, verified work committed on an isolated branch, followed by a concise report
and termination of that run's enforcement. Automatic merging requires advance authorization of its
destination and checks; publishing and deployment need their own permissions. Existing permissions
remain valid within their scope and do not require repeated approval between work units.

Bounded workers and fresh reads of the durable plan are internal mechanics. The native workflow must
advance through all agreed units without manual restarts. A worker completing one unit does not mean
the whole run is done. The run cannot weaken acceptance checks, drop scope, or expand its authority to
declare success. Preserve partial work and surface an unresolved blocker or resource limit honestly.

Record useful findings in the append-only learnings log; do not treat that log or self-checked boxes as
independent completion evidence. Never claim native trust, isolation, host support, required review,
publication, or other external outcomes without the corresponding evidence.
