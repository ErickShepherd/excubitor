# Ralph in the coding app you already use

Research checked on 2026-09-05. This is a proposed workflow and a native capability inventory,
not a claim that the corrected Excubitor runtime is implemented or verified.

The owner wants to select a consistent Ralph command or action inside the existing Codex,
Claude Code, or Antigravity window, and also start runs from those tools' CLIs. Cursor is a
prospective integration. There is no separate Excubitor control panel. Ordinary development
remains ordinary development, including in a project or conversation that previously ran Ralph.

## What the owner should experience

Choose **Ralph**, describe the job or select an existing plan, and start it with reusable defaults.
Excubitor prepares a short description of the intended result, checks, limits, and allowed final
actions. Ask only about missing consequential choices. Once the owner authorizes that job,
implementation, testing, repair, review, and continuation happen without repeated approval.

The default result is verified, reviewed work committed on an isolated branch, plus a concise
report. Merge may be authorized upfront for a specified destination. Publish and deploy have
separate permissions. A run cannot rewrite its agreement to make unfinished work count as done.
Those are the owner's product requirements, not claims established by the research below.

Use the same Ralph name and behavior across hosts, adapting to their native invocation syntax.
Do not advertise a literal universal `/ralph` command before it exists and works in every claimed
surface. For example, Codex documents explicit `$skill` invocation and an option to disable
implicit invocation; Claude documents slash-command skills and an option that prevents model
invocation. These are candidate entry points, not proof of protected owner authorization.
([Codex skills](https://learn.chatgpt.com/docs/build-skills),
[Claude skills](https://code.claude.com/docs/en/skills))

## What the research actually supports

The original Ralph account supports a repeated task loop, a durable specification, focused
feedback, and tuning based on observed failures. It describes practitioner experience rather
than a controlled comparison proving one best recipe for all models and projects.
([Original Ralph account](https://ghuntley.com/ralph/))

Anthropic's earlier application-building experiments observed premature completion, oversized
changes, and lost progress between sessions. Their successful recipe used initial setup, an
explicit feature list, incremental changes, progress notes, Git checkpoints, and tests of the
running application. The authors explicitly limited the demonstration to full-stack applications
and left broader generalization open. This supports sensible starting defaults; it does not prove
that every task needs an elaborate initializer or that a passing checklist is tamper-resistant.
([Long-running agent experiments](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents))

The later experiments changed the recipe as models improved: context resets were dropped for
Opus 4.5, and the later Opus 4.6 setup removed mandatory sprints and moved evaluation to the end
of the build. Review still found substantial defects, but it required tuning and missed some
issues. Comparisons also used substantially different budgets. They do not establish a universal
review cadence or a matched-budget advantage. Excubitor should evaluate context and review
policies instead of permanently requiring a fresh agent and reviewer after every small change.
([Later harness experiments](https://www.anthropic.com/engineering/harness-design-long-running-apps))

The proposed working sequence is:

| Step | Recommended behavior | Basis and remaining uncertainty |
|---|---|---|
| Prepare | Reuse the project's setup and existing checks. Turn the requested outcome into observable acceptance criteria and record limits once. | Explicit requirements and reproducible setup have demonstration evidence; the permission boundary is an owner requirement. |
| Start | Bind an explicit owner action to this project and task. Create an isolated working branch and record the agreed completion actions. | Required for this product. Native activation and protection still need to be demonstrated. |
| Orient | Read the agreed job, remaining work, and recent checkpoint; run a small relevant baseline check before building on uncertain state. | Durable handoffs and basic environment checks address observed lost-progress failures. |
| Build | Advance a coherent piece of the job, preserving recoverable progress. Replan implementation details within the existing scope when useful. | Incremental work is a good initial default. Exact unit size and context-reset timing need local comparison. |
| Verify | Exercise the promised behavior, including the real UI, API, or other boundary when relevant. Record failures and repair them within limits. | Running-application tests caught defects that narrower tests missed in the demonstrations. |
| Review | Check the resulting work against the agreed outcome. Keep the final review; add intermediate review when risk or observed failures justify it. | The owner requires reviewed completion. The research supports evaluating the cost and benefit of additional review. |
| Continue or finish | Continue until all agreed work is verified, or a genuine blocker or limit is reached. Report the actual result and end the run's authority. | An implementer's claim of success is insufficient. Lifecycle isolation and completion enforcement require Excubitor-specific tests. |

The references above provide the experimental basis for the sequence. They do not prove the
entire proposed sequence as one system. Protected acceptance checks, isolated authority, bounded
retries, and the agreed completion permissions are safety requirements to implement and verify.
New implementation tests may add evidence; they cannot silently replace the agreed acceptance
criteria. Missing or inconclusive evidence means incomplete, not success.

## Native facilities and their limits

All rows below still need live evidence for Ralph-only unattended operation. A documented hook,
an installed CLI, or one successful research invocation is not that evidence.

| Host and requested surface | Documented starting point | What still needs proof |
|---|---|---|
| Codex interactive CLI and desktop app | Native skills, long-running goals, and hooks provide candidate launch and continuation paths. | Explicit owner activation, correct task/worker binding, tool coverage, safe failure behavior, and cleanup in each interface. |
| Claude Code interactive CLI and local desktop Code session | Skills and hooks are available; desktop documentation describes shared local configuration. Native goals can continue work. | Skill lifetime must not capture later ordinary messages; test start, continuation, cancellation, and hook failures separately in CLI and GUI. |
| Antigravity interactive CLI and existing GUI | Native hooks include tool decisions, invocation events, and a Stop continuation response. | Verify skill/action discovery and hook configuration in each interface, owner-origin evidence, failure semantics, and exact worker lifetime. |
| Cursor CLI and editor, prospective | Native hooks document continuation and configurable failure handling; a separate CLI is documented. | Establish the relevant CLI hook coverage and native launch action, then prove the same isolation and completion contract. |

Codex documents project and user hook scopes, with hook sources combined rather than a project
configuration automatically replacing global hooks. Its Stop hook can request continuation;
its session-end event is not a per-job completion signal. A project installation therefore still
needs an explicit active-run boundary and a cleanup path. Native long-running goals continue
work within existing permissions; they are not an independent acceptance verifier.
([Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Codex long-running work](https://learn.chatgpt.com/docs/long-running-work))

Claude's local desktop and CLI share relevant skills and settings. Skill-loaded hooks can persist
for the rest of the session. Command hooks can allow normal permission processing to continue
after a timeout, so an adapter returning the right denial in a fixture does not prove enforcement
during a handler failure. A native goal and an interval-based `/loop` scheduler have different
continuation semantics. Neither establishes that every accepted feature really works.
([Claude desktop](https://code.claude.com/docs/en/desktop),
[Claude hooks](https://code.claude.com/docs/en/hooks),
[Claude goals](https://code.claude.com/docs/en/goal))

Antigravity documents workspace hooks, native conversation identity fields, tool allow/deny
decisions, and `Stop` with `decision: "continue"`. It also documents invocation-level continuation.
These are promising integration points. A conversation identifier in a payload does not by
itself prove that an owner authorized a protected run. Configuration discovery and failure
behavior must be checked against the actual CLI and GUI builds.
([Antigravity hooks](https://antigravity.google/docs/hooks))

Cursor's Stop response uses `followup_message` with a loop limit. Its hooks expose configurable
`failClosed` behavior, which defaults to false. This differs from other hosts' protocols. Neither
the editor hook contract nor a general CLI feature page establishes every required CLI hook's
behavior; retain prospective status until native probes establish it.
([Cursor hooks](https://cursor.com/docs/hooks),
[Cursor CLI](https://cursor.com/docs/cli/overview))

Interactive CLI, headless CLI, local desktop, IDE extension, and cloud execution are separate
support claims. Do not imply that passing one covers the others. For example, Antigravity's
headless documentation says an unavailable interactive approval can be soft-denied while the
process still exits successfully. Exit status therefore cannot be the completion oracle.
([Antigravity headless mode](https://antigravity.google/docs/cli/headless/))

## The smallest useful verification program

First remove the existing broad Codex registration using its supported transaction and verified
rollback capture. Then inspect reusable implementation mechanisms against the corrected scope.
Do not let preparation for every future run inherit the complexity of repairing this installation.

Before promising a host/interface, use a disposable project to demonstrate:

- Ordinary work before installation, after installation but before opt-in, in another task of the
  same project, and immediately after a Ralph run remains free of Ralph restrictions.
- Explicit launch starts a bounded job; an ordinary prompt, edited marker, copied state, or
  synthetic continuation cannot grant or expand its authority.
- A harmless allowed operation succeeds and a prohibited operation produces a native denial with
  no prohibited effect. Cover the actual edit, shell, and other claimed mutation tools.
- A job with several meaningful steps continues without human restarts, repairs an injected
  recoverable failure, and cannot claim completion with a missing feature or weakened check.
- Cancellation, interruption, crash, handler timeout, invalid hook output, and a lingering worker
  preserve the correct boundary. Resumption retains the original limits. Later ordinary work is
  unaffected. If a native mode cannot enforce this, report that limitation explicitly.

For workflow quality, compare a minimal baseline against one change at a time: context resets
versus supported compaction, smaller versus larger work units, and extra intermediate review
versus final review. Keep the final acceptance checks, permissions, model/version, task inputs,
and budgets fixed. Keep mandatory safety protections in every variant.

Use representative small fixes, multiple-feature work, and integration-heavy tasks. Repeat runs,
record every attempt including failures, and independently assess the actual outputs. Measure
completion, escaped defects, false completion, human interventions, setup effort, elapsed time,
and token/cost overhead when available. Also measure false denials during ordinary development.
Choose the simplest configuration that meets the quality and isolation requirements; revisit it
when host or model versions change. No such comparative Excubitor results are claimed here.

## Research provenance

Sources are original practitioner writing, first-party engineering experiments, and official host
documentation checked on the date above. Documentation describes a capability; demonstrations
suggest a workflow; neither substitutes for local native verification or a comparative evaluation.

Antigravity Gemini 3.1 Pro was consulted through its CLI in research-only plan mode. Its response
was treated as leads, not evidence. Unsupported universal context-reset claims, a Cursor response
shape contradicted by its native documentation, and suggestions to use global hooks and a launch
environment variable were excluded. The latter also conflict with the owner's agreed scope.

The research and documentation update changed no live hook, native trust, launcher, skill
installation, or runtime support claim. Removal and runtime correction remain pending.
