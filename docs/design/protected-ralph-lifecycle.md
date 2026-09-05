# Protected Ralph lifecycle candidate

`excubitor/runs.py`, `approval.py`, `acceptance.py`, and `session.py` are internal host-controller
components. A disposable native CLI experiment now connects confirmation to the run store and tests
protected output comparison. There is no production launcher, registered endpoint, or active hook
integration. Complete native admission, worker supervision, candidate collection, and independent
review remain required. The old always-active adapter remains unsuitable for reinstallation.

## Implemented behavior

Provisioning an empty store does not start Ralph. An authenticated host start records the exact native
runtime, task, canonical project and directory identity, agreed work units, fixed acceptance-check
identities, deadline, attempt budget, and default retain-branch completion action. An authorization
identifier can be consumed only once, including after cancellation. The identifier prevents replay;
it does not authenticate the owner. The host must bind real approval to the exact contract first.

Only that project and task have an active record. Other tasks, runtimes, parent directories, sibling
projects, and worktrees return inactive from an intact store. Replacing an active project's directory
raises an error. Completed history stays readable after its directory disappears and cannot capture
a new project at the old path.

A run advances through the agreed units and retries repairs without another authorization. Atomic
updates require the current revision, rejecting delayed workers and duplicate completion. Candidate
changes invalidate previous check and review results. Completion requires all units, all original
checks passing against the current candidate, passing review, a clean committed isolated candidate,
and worker shutdown. The library validates the supplied facts; it does not yet collect them.

The new output-check component stores exact command, input, expected output, expected exit status, and
timeout definitions outside the worker project. It reloads and verifies those original bytes before
comparing host-captured subprocess results. A worker's claimed test summary is never parsed as a pass.
This does not provide a general sandbox executor, collect Git facts, or establish independent review.

Cancellation first enters a stopping state. Only confirmed worker shutdown ends protection. An
interrupted job resumes in the original task after old workers stop, retaining progress and limits.
Exhaustion or an observed expired deadline blocks the job and retains protection. Recorded expiry
cannot be undone by a later clock correction. The host owns reliable timekeeping, worker termination,
and prompt reporting of expiry; this library runs no timer and kills no process.

Completion releases the run's scope. Merge, publication, and deployment are rejected as unimplemented
actions. Missing stores, unsupported versions, invalid contract bytes, and inconsistent progress raise
errors rather than reporting inactive. Consistency checks do not replace filesystem protection or
provide cryptographic integrity against a privileged writer.

## Verification

Run `python -B excubitor/tests/test_runs.py` on Python 3.11 or newer. The regression cases cover progress,
repair, frozen checks, conflicting updates, isolation, replay, cancellation, interruption/resumption,
limits, candidate changes, broken storage, directory replacement, and ordinary scope after completion.

`runtime/probes/protected_runs.py` creates a separate native experiment without hooks or trust changes.
A trusted parent creates a dummy run outside a disposable project and invokes the installed Codex
CLI's native `:workspace` sandbox. Its worker can edit an ordinary file and read the record, but cannot
forge activation, advance or cancel the run, claim verification/review/completion, erase SQLite rows,
or rewrite the external acceptance file. An extended contract is rejected before a write. The parent
checks unchanged authority and acceptance bytes, observes subprocess exit, and closes the dummy run.

This passed on Windows 11 with Codex CLI 0.153.4 and Python 3.14.7. Dummy candidate facts exercise
lifecycle writes; they are not an actual verified branch or semantic review. An earlier assertion
expected a storage error for changed limits but received the controller's correct contract-conflict
error. Its failed report was preserved before correcting the assertion.

This is a native denial witness for the tested local subprocess filesystem boundary. It does not
establish GUI behavior, another vendor, MCP or browser tools, all permission configurations, owner
authentication, privileged Git operations, verifier isolation, or complete Ralph support.

## Native integration still required

The internal start handshake now freezes the displayed contract and output-check definitions, requests
one confirmation with a false default, and consumes the matching response once on its native connection.
Preparation, cancellation, malformed or late replies, responses from another handshake, replay, changed
checks, and conflicting native scope cannot start a run. A transport cancellation or explicit connection
closure discards pending confirmations. Definitions are written before activation; an interrupted write
can leave an unused blob but cannot activate a partially stored check set.

A disposable Codex CLI 0.153.4 experiment supplied native MCP metadata separately from tool arguments,
including matching task identities, one workspace, sandbox mode, and automatic-review mode. The test
selected cancellation and confirmation in the actual CLI form. Cancellation created no run. Confirmation
created the exact scoped record and preserved its original acceptance definitions; another task in that
project remained inactive. This demonstrates the native bridge under the tested connection. Client-name
strings or copied metadata do not authenticate arbitrary MCP clients, and the parser does not attest
all writable tools. The bridge remains test apparatus rather than a production activation endpoint.

Five finite programs ran through Codex's native read-only subprocess sandbox against one frozen output
check. Wrong output, a forged green summary, and an early zero exit failed. Correct output passed. A
program's attempt to rewrite the protected oracle was denied and the original bytes remained intact.
The output pass could not finish the run without review. These programs used a dummy Git identity;
this experiment is not a committed-branch witness or a general arbitrary-code execution service.

Native CLI shutdown killed the test MCP process without executing its Python cleanup handler. The
accepted record remained active. The trusted test parent closed that dummy record only after both
processes exited and after checking that no worker had started. `record_session_end` now records a native
session ending as an interruption, preserving progress and protection rather than inventing completion
or worker drainage. Its exact-scope and repeated-event tests pass; native delivery into this implementation
still needs the separately prepared, unregistered one-hook experiment. Never rely on MCP EOF/finally for
production run termination.

The host must obtain one owner approval of the exact job outside the worker's ability to forge it.
The earlier native hook experiment established task identity and continuation, but its prompt envelope
supplied no independent owner-origin assertion. Prompt text, an environment flag, a skill invocation,
or a worker-written marker cannot fill that gap. Native approval of a bounded privileged start helper
was an earlier candidate mechanism. Native elicitation now has direct CLI evidence and is the current
connection candidate. This library needs no global dispatcher or application launch wrapper.

The controller and acceptance authority must be outside every worker-writable surface, including
tools outside the shell sandbox. Do not expose RunStore mutation methods through a worker-callable
CLI, MCP server, or hook JSON operation. An unsandboxed agent running as the store owner can modify it.
Safe mode admission remains unfinished. An agent-supplied profile name or hook permission-mode string
does not establish the actual writable surfaces.

The host must independently collect the current candidate identity, committed/clean/isolated facts,
check results, review, and worker liveness. Candidate code and repository-configured commands must
never execute with authority-store privileges. Worker booleans and test summaries are not verification
evidence. Check fingerprints currently bind identities; storing and executing the actual protected
acceptance oracles still requires a trusted backend.

The host must retain known-active task information and reconcile crashes. Lost storage must preserve
a known active boundary without imposing Ralph on unrelated tasks. Catching RunError and returning
inactive, or blocking all ordinary tasks on a storage fault, both violate the product contract.
This routing and native fail-closed behavior are not wired.

Current official references describe capabilities, not support certification:

- [Codex permissions](https://learn.chatgpt.com/docs/permissions): profiles and filesystem scope.
- [Codex approval and security boundaries](https://learn.chatgpt.com/docs/agent-approvals-security):
  local command containment and separate external-tool surfaces.
- [Codex hooks](https://learn.chatgpt.com/docs/hooks): lifecycle events and hook limitations.
- [Codex app server](https://learn.chatgpt.com/docs/app-server): native MCP elicitation and response flow.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks): elicitation hooks can automatically answer
  a form and modify its result, so that host needs a separate approval-path assessment.

The next implementation must connect authenticated approval and independently collected evidence to
this lifecycle, then demonstrate a real multi-unit job through native continuation. Replacement
registration and trust remain separate. Component tests do not complete broader support claims.
