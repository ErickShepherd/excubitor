# Protected Ralph lifecycle candidate

`excubitor/runs.py`, `approval.py`, `acceptance.py`, and `session.py` are internal host-controller
components. `supervisor.py` now drives bounded workers, original checks, repair, and independent review.
`processes.py` supplies Windows process-tree supervision and `candidates.py` inspects real committed
bytes, index, selected branch, and the preserved base. A real Codex CLI demonstration completed two
units and a repair without owner restarts. There is no production launcher, registered endpoint, or
active hook integration. Complete native admission and crash reconciliation remain required. The old
always-active adapter remains unsuitable for reinstallation.

The normal-start candidate now accepts a job proposal through `RalphAction` when its host supplies
`JobPlanner`. The proposal contains work and input/output checks; native metadata still supplies the
task and project. Reusable host defaults supply omitted limits, and a required host admission callback
checks the complete proposal before any confirmation. The callback is trusted code supplied by the
adapter, never a tool argument. Existing fixed-plan adapters keep their original protocol.

The candidate skill at `runtime/skills/ralph` describes the explicit command workflow. It is not in an
auto-discovered skill location and has not been installed. The Codex invocation policy is explicit-only.
The shared proposal path is component-tested; a production backend, project-scoped connection, native
command discovery, and general-purpose verifier admission still need integration and native evidence.

## Preparing a normal job

The coding agent proposes the goal, units, and concrete input/output cases from the owner's request.
It selects verification runners by their advertised names. The host owns their actual commands,
execution policy, time ceilings, and reusable defaults. A proposal cannot supply an executable,
environment, storage location, native identity, approval, or extra completion powers. A registered
runner must exercise candidate behavior rather than accept a worker-written verdict or mutable tests
as the oracle. Freezing a command that merely runs editable tests would not freeze the tests themselves.

`ralph_start` receives the proposal as `job` and presents the existing native confirmation. Nothing
executes and no active record or oracle file is written before acceptance. Later edits to the submitted
data cannot alter the preview's immutable contract and checks. A pending preview cannot be replaced;
decline, transport cancellation, expiry, or connection closure starts nothing. Work is retained on an
isolated branch by default; automatic merge, publishing, and deployment remain unavailable.

With an active job, `ralph_start` takes no arguments and follows the existing reconnect path. A new
proposal in that task is rejected rather than resetting scope, attempts, or deadline. Changed host
defaults are considered only for a new proposal, never for recovery. The schema's structural ceilings
are implementation bounds, not claims about empirically optimal loop size or budgets.

In proposal mode, status includes unit and attempt progress. After completion it reads the last
accepted job's recorded result for that exact task. It distinguishes completed work from cancellation
and from a task that never started Ralph. This history does not reactivate protection or certify later
ordinary edits. Old fixed-plan adapter status text remains unchanged.

Codex documents [explicit skill invocation](https://learn.chatgpt.com/docs/build-skills) and
[project-scoped MCP configuration](https://learn.chatgpt.com/docs/extend/mcp). These support the chosen
entry-point design; they do not certify this candidate on a native surface. No global dispatcher,
launch wrapper, or environment-variable activation ceremony is introduced.

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
and worker shutdown. The lifecycle library validates supplied facts. The new host-side Git reader and
Windows process backend collect specific candidate and worker facts for the supervised demonstration.

The new output-check component stores exact command, input, expected output, expected exit status, and
timeout definitions outside the worker project. It reloads and verifies those original bytes before
comparing host-captured subprocess results. A worker's claimed test summary is never parsed as a pass.
The supervisor connects this comparison to a host backend. The native demonstration runs original
checks inside Codex's read-only sandbox and obtains review from a separate native model invocation.

Cancellation first enters a stopping state. Only confirmed worker shutdown ends protection. An
interrupted job resumes in the original task after old workers stop, retaining progress and limits.
Exhaustion or an observed expired deadline blocks the job and retains protection. Recorded expiry
cannot be undone by a later clock correction. The host owns reliable timekeeping, worker termination,
and prompt reporting of expiry; the lifecycle store runs no timer and kills no process. The Windows
backend limits individual executions and waits for its entire process job to drain.

Completion releases the run's scope. Merge, publication, and deployment are rejected as unimplemented
actions. Missing stores, unsupported versions, invalid contract bytes, and inconsistent progress raise
errors rather than reporting inactive. Consistency checks do not replace filesystem protection or
provide cryptographic integrity against a privileged writer.

## Verification

The shared supervisor re-reads the durable contract and original oracles each attempt. An OS-held lock
prevents duplicate supervisors. A durable in-flight event prevents blindly starting another worker
after a controller crash. An unfinished or damaged journal leaves the run interrupted and protected;
automatic crash reconciliation and safe resumption remain future host work. Cancellation releases a
run only after a backend confirms drainage. Backend exceptions never supply that confirmation.

The Windows backend starts the root suspended, assigns it to a non-inherited job, and then resumes it.
Only standard-I/O handles are inherited. Time, output, and process-count limits apply; the controller
waits for the job to empty, including children that outlive their parent. Closing the controller kills
that job's descendants. This is process supervision, not filesystem/network containment. A native
broker launching outside that job still requires separate admission. Local tests cover parent exit,
controller death, lingering children, cancellation, output flooding, and breakaway requests. Across
Python versions, a breakaway request may be refused or accepted while the process remains in the
ancestor job; test actual membership and drainage rather than requiring one particular error.

The Git reader uses host-selected metadata outside the project and checks actual file bytes against
the commit, index, expected branch, and unchanged base. It rejects extra/ignored files, links, shared
files, submodules, and unsupported tree shapes. This is a deliberately small first backend. Production
commits still need the owner's authorized broker; the demonstration commits only its disposable repo.

On Windows with Codex CLI 0.153.4, real native workers built a two-feature Python CLI. A disclosed fault
changed doubling to tripling in the retained candidate. Unchanged external checks failed, the next
worker repaired the code from verifier feedback, and all four original checks passed. A separate
native reviewer read the final code and ran ten additional cases. The run finished after three worker
attempts with a clean committed isolated branch, preserved base, and no active run. Its native sandbox
child was independently observed in the supervisor's Windows job; all thirteen process calls drained.

The first attempt omitted the already provisioned Windows sandbox setting from process-only config.
Native policy refused worker operations and the job exhausted its budget without claiming success.
Preserving the configured sandbox implementation fixed startup without disabling policy. A subsequent
job completed but its configuration check caught Codex automatically saving trust for the disposable
project despite `--ignore-user-config`. That entry is retained and reported. The final driver requires
an already trusted completed fixture, preserves its branch, and refuses fresh project enrollment. Its
final run left the native configuration byte-identical. No hook was installed in these demonstrations.

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
or worker drainage. A separately approved one-hook experiment now demonstrated native delivery into
this implementation: normal Codex CLI exit changed the exact confirmed record from running to interrupted,
retained its protection state, and made no completion or worker-drain claim. An ordinary task in the same
project edited a file successfully and its SessionEnd remained inactive. Codex clamped the hook timeout
to three seconds; both observations completed within that native limit.

All test processes exited, the exact unchanged temporary registration was removed, and a fresh CLI
showed zero installed or active hooks. Codex retained the updated fixture-specific SessionEnd trust entry;
the rest of its parsed configuration was unchanged. The trusted parent closed only the dummy record
after preserving the native interruption and confirming the test never launched workers. This verifies
normal interactive CLI exit, not forced termination, crashes, resumption, or worker containment. Never
rely on MCP EOF/finally for production run termination.

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
evidence. The supervised demonstration now connects those specific backend facts to the lifecycle.
Its benign local task does not attest every native tool or permission configuration for arbitrary work.

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

The next native integration must complete mode admission and provide the production in-app launcher.
The bounded native watchdog-loss rehearsal is recorded below. The native CLI demonstration
uses a trusted test parent, not a registered owner-facing activation endpoint. GUI behavior and other
vendors still require their own adapters and evidence. Replacement registration and trust remain separate.

## Native start and bounded controller recovery

`RalphAction` now connects an admitted native connection to the existing confirmation handshake and
a host launcher. Its start and status tools take no arguments. The adapter supplies the exact native
binding and a trusted plan; a tool argument cannot select authority storage, executable code, another
task, or an approval answer. Only acceptance of the pending native form dispatches the frozen job.
Declined, cancelled, late, malformed, and replayed answers cannot start workers. A launch failure
retains interruption. Closing the connection retires pending offers but does not claim that accepted
workers stopped. Status reads only the calling task's scope and never activates a run.

`ControllerWatchdog` owns a controller from its first launch, inside a Windows job that includes the
controller's descendants. When that controller exits, the watchdog terminates remaining descendants
and waits for an empty job before recovery. This differs from an ordinary bounded worker call, which
may legitimately wait for children to finish after its parent exits. The watchdog holds a separate OS
lock, records each launch before spawning, and persists actual drainage before resuming the same run.
It preserves the original journal bytes, including a torn final line, in a separate crash archive.
The resumed supervisor consumes the next original attempt and reloads original acceptance definitions.
No successful check or review from the interrupted attempt can authorize the new candidate.

At most two controller restarts are allowed across all watchdog lifetimes. Original attempts and
deadline remain unchanged. A handled admission error is surfaced without retrying the denied operation.
Cancellation releases the run only after drainage. Each launch now records an exact named Windows job
whose access list permits only the creating host account. Windows assigns the suspended root to that
job during process creation, closing the orphan window between creation and a later assignment.

A replacement watchdog holds the same exclusive lock and reconciles the recorded kernel object.
An existing object must have the expected owner and access list, and its processes must terminate
before resumption. Kernel-confirmed absence is usable only for this recorded, atomically assigned job.
The global Windows object namespace prevents another login session from mistaking a live object for
an absent one; it does not install a global dispatcher or hook. Access denial, changed permissions,
malformed history, reused names, and legacy histories without ownership evidence refuse recovery.
Timestamp and process-name searches provide no authority. Historical journals remain unchanged.

`RalphAction` can ask an admitted adapter to reconnect an existing job in the same native task.
It reuses the accepted contract without replanning or another approval; blocked work cannot reset its
limits. An adapter without a reconnect implementation reports that capability missing. Reconnection
does not imply that the application can continue working while closed.

The native supervised CLI candidate now supplies that reconnect implementation. Each connection
rechecks the frozen agreement and original oracles, then dispatches the same watchdog using the stored
task binding. Logs and outcomes are retained per connection. Actual thread liveness replaces the
candidate's permanent attachment assumption, while the watchdog's OS lock remains the authority for
exclusive process ownership. A closed native connection cannot restart anything. Native configuration
drift stops preparation or dispatch and prevents a passing final report.

Windows component tests exercise this connection path through real owner-process loss with and
without a retained job handle. The next action completes the original fixture within its unchanged
attempt budget and without replanning, while another task remains inactive. Those identities and
approvals are fixtures. A separately approved native CLI rehearsal subsequently lost the test connection
after a real worker drained, with a disclosed fixture child still alive, and resumed the exact native
task. Actual interactive turn metadata matched the original contract on both connections. The second
Start reconnected with the consumed attempt preserved and no replacement plan or confirmation. The
watchdog established the old exact kernel job absent before launching its replacement.

The job completed in four of six attempts before the unchanged deadline, repaired an injected failure
against the original checks, passed all four checks and independent review, and retained a clean
committed isolated branch. Independent inspection confirmed unchanged agreement/check bytes, an
unchanged base, both controller jobs absent, and all thirteen recorded executions drained. A separate
native task in the same project remained inactive while Ralph ran; the completed task became inactive,
and ordinary native editing still worked. Native protected fingerprints matched the sealed baseline
at the first independent check after the approved project trust addition. A post-exit comparison then
found one unrelated project trust entry, confirmed by the owner as separate concurrent work. Its raw
comparison failure and original baseline are preserved; no settings were restored. Sandbox setup and
credentials remained unchanged. There was no saved tool allowance, permanent MCP registration, hook,
or sandbox provisioning.

This closes that bounded Windows CLI reconnection witness. The test driver explicitly reopened the
original task; it did not prove automatic reopening, recovery during a model turn, or work while the
app is closed. Production launch UX, complete native-tool admission, GUI, and cross-vendor support
remain open. Raw native metadata, transcripts, and reports stay in private task storage.

Live Windows component tests cover owner death immediately after process creation, watchdog death
with and without a retained host job handle, repeated watchdog deaths exhausting the shared restart
limit, and malformed or inaccessible recovery evidence. The native unelevated Windows sandbox has
since failed the named-job isolation probe: it denied termination, assignment, permission changes,
and external oracle changes, but allowed a query handle. Such a handle can keep the job alive after
its host closes its own handle. The probe opened and closed it; it did not demonstrate a malicious
native worker retaining it through host death. This mode remains excluded by the metadata parser.
The separately authorized existing elevated sandbox check now supplies a native access-denial witness
on Windows with Codex CLI 0.153.4. Its worker used a different Windows account and could not open the
named target for query, termination, assignment, DACL, or owner access. Ordinary project writing
succeeded, the external acceptance bytes stayed unchanged, and the exact worker was observed in its
containment job. All eight observed processes drained within the bound, with native config, setup,
and credential fingerprints unchanged at final independent inspection. The access target and the
containment job are separate objects; this is not a native forced-owner-death demonstration.
Every other native tool and permission configuration still needs admission.
Production adapters still do not import these components.

The native token diagnostic confirmed that the unelevated worker shares both the host's Windows
account and its medium integrity level, and that this exact worker appears in the host job. Windows
integrity checks distinguish lower-level callers, so changing the job's label at the existing level
would not separate these two tokens. The candidate therefore retains its elevated-only admission
requirement. Reuse of the existing elevated sandbox passed its prerequisite and fingerprint checks
under the owner's narrow authorization for native runtime storage in that home. It did not require
an explicit setup command, native configuration edit, or credential copy. This storage exception is
specific to the approved check; future native runtime writes still need authority for their location.

The native app-server preserved a seeded test task's identity across forced server termination and
`thread/resume`, while another task in the same project received a different identity. Direct MCP
calls supplied only task identity and a progress token, without the interactive CLI's turn envelope;
the approval parser rejected all three calls. An empty newly started task had no saved rollout, so
the probe used the native history-injection API with clearly labelled, non-authoritative fixture text.
This verifies protocol persistence, not owner confirmation, protected Ralph reconnection, or GUI support.
The final state comparison failed because Codex automatically saved project trust in each isolated
fixture home. Those entries and failed reports remain for review. The probe now refuses fresh trust
and compares config after each native lifetime. After the owner approved reuse of one exact isolated
profile, the corrected native run passed: task and project identity survived restart, the unrelated
task stayed distinct, both process trees drained, and native config remained byte-identical after
each lifetime and at final inspection. All three incomplete tool contexts were still rejected.
No credentials, model turn, saved tool registration, or sandbox provisioning was involved, and the
owner's normal native home was not used. That result closed the approved protocol check and left
protected Ralph reconnect unverified at that point. The subsequent interactive rehearsal has its own
evidence and scope. The elevated access result supplies only the tested shell boundary; neither later
result enlarges this identity experiment's scope.

The atomic creation mechanism follows Microsoft's
[job-list attribute guidance](https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812).
The recovery conditions use the documented
[job lifetime](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[job access controls](https://learn.microsoft.com/en-us/windows/win32/procthread/job-object-security-and-access-rights),
and [object namespaces](https://learn.microsoft.com/en-us/windows/win32/termserv/kernel-object-namespaces).

The connected Windows CLI experiment completed in four attempts: a real worker ran, the controller
was forcibly terminated with a live descendant, the watchdog drained that tree and restarted, and
the remaining workers repaired a deliberately wrong arithmetic implementation. Four unchanged checks
and a fresh native reviewer passed. The original native confirmation and task identity matched the
retained contract. The final report then exposed a separate Git helper left alive after its launcher's
timeout. That failure report remains; the exact read-only helper was stopped after identification.
Windows candidate inspection now contains Git and its children in the existing bounded process runner,
with explicit input and environment, instead of killing only a timed-out launcher. A separate native
MCP inspection using that correction verified the completed candidate, unchanged native configuration,
and complete process drainage. No additional model implementation run or production support claim is
inferred from that read-only inspection.
