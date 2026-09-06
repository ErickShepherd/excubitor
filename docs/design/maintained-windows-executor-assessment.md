# Maintained Windows executor assessment

The installed Codex runtime can execute native Windows commands without making a
model call. It is not admitted as a shared Excubitor executor yet. Native tests on
September 6, 2026 found a read-denial bug in the standalone CLI and a separate
credential-access gap in the command API. These results do not establish a full
Claude Ralph job, GUI support, or production Windows support.

The intended architecture remains a native, authenticated model coordinator with
all project-code execution routed through an admitted executor. Ordinary tasks
must not acquire Ralph completion gates. The Linux executor and durable
supervisor remain in place. The custom AppContainer/session-0 prototype remains
experimental; no Task Scheduler experiment was performed for this assessment.

## What was observed

The installed runtime was Codex CLI 0.153.4 with its already provisioned elevated
Windows sandbox. The selected model was irrelevant: no model request was made.
All synthetic project files, probes and reports were on the task's D: storage.
The command API reused the owner's authorized existing Codex application data.

| Native test | Result |
|---|---|
| Standalone `codex sandbox` with an explicit private-directory read denial | Failed: the process read the synthetic private file |
| App-server `command/exec` with a named permission profile | Enforced the explicit private-directory read denial |
| Candidate edit and task-local temporary-file write | Allowed through the command API |
| Writes to authority and the candidate's protected Git marker | Denied |
| Direct network connection | Denied with Windows access-denied error |
| Open host-owned Job Object for query, termination, assignment or permission changes | Denied |
| Worker identity and process lifetime | Different Windows user; observed inside the host job; process tree drained |
| Concurrent ordinary command through the command API | Completed while the first worker's explicit private-file denial remained effective |
| Read a synthetic file carrying the real Claude login file's effective access rules | Allowed: credential separation failed |

The credential test copied access rules onto synthetic content. It did not read,
copy, alter, or send the real credential contents. This is evidence of a relevant
access-control gap, not a claim that the test exfiltrated a credential. Removing
API keys from the process environment does not close access through saved files.

The concurrency test covered one ordinary command through the same command API.
It is not exhaustive evidence for every native client or concurrent policy
change. The apparent passing result before the credential canary was added is
only a pass for that earlier, smaller set of checks.

## Bounded attempt to combine existing isolation mechanisms

After independent Fable review, one fixed-code probe tried launching an LPAC child
from the maintained runner's existing offline account. It reused the already
registered AppContainer SID, with task files and the child's profile/temp environment
on D:. Only a disposable copy of the launcher permitted that exact offline account
in the interactive session; the repository's session-0 guard remained unchanged.

The offline launcher started and passed its identity check. Private-desktop creation
completed, but `CreateProcessW` returned Windows error 2 before the LPAC child was
created. Python did not initialize. This is a process-creation failure, distinct from
the runtime-path problem the reviewer required the test to distinguish. It does not
identify the missing resource, prove a registration defect, or establish any of the
child's proposed security properties. The combination is not admitted.

The probe stopped at that first failure; the conditional cancellation test was not
run. The outer job drained all nine observed processes, and a subsequent owner-side
check confirmed that each observed process had exited. Synthetic canaries, native configuration and the setup
marker were unchanged. The temporary fixture's worker grants were revoked after
drainage, with its evidence preserved on D:. No new registration, account, scheduled
task, credential access or model-authored execution was introduced by this probe.

This bounded approach is now stopped. Additional sandbox mechanisms or machine setup
are not an automatic follow-on. The native Windows execution gap remains explicit;
the existing supervisor and Linux work remain usable development foundations.

## Why the standalone CLI failed

The exact released source passes an empty read-denial list to the Windows
sandbox session. Upstream has merged a correction that forwards the selected
profile's denial paths. At the time of assessment, both the latest stable release
and the latest inspected prerelease lacked it. No replacement binary was
downloaded or installed.

- [Upstream explanation and correction](https://github.com/openai/codex/pull/42835)
- [Installed release source](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/cli/src/debug_sandbox.rs)
- [Latest stable release checked](https://github.com/openai/codex/releases/tag/rust-v0.153.4)
- [Maintained Windows sandbox documentation](https://learn.chatgpt.com/docs/windows/windows-sandbox)

The correction is necessary for the standalone CLI route, but it is not proof
that the separate credential gap or all read isolation requirements are fixed.

## Remaining admission work

Before attaching Claude's authenticated coordinator to this executor, establish
a read boundary that excludes saved vendor credentials and protected run state.
It must remain effective across native token refreshes, concurrent ordinary work
and later commands. A policy label or an allowlist of command names is insufficient.
Do not silently change shared user credential permissions or machine enrollment
to manufacture a passing test.

Then validate read-only verification, controller cancellation and detached-child
cleanup through the selected transport, and run a fresh small Ralph job through
actual checks and independent review. No existing exhausted job may be reset to
perform that demonstration. The standalone CLI's source fix alone does not
authorize any of these production claims.

No product runtime implementation was changed by this assessment. The native
reproducer and detailed results are retained in the private task evidence packet,
including unsuccessful attempts and native startup errors. New app-server state
directories triggered native index backfill and failed within their bounds;
reusing the initialized, authorized Codex state allowed the API test to start.
