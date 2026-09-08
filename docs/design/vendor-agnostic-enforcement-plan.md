# Ralph-only native enforcement remediation

Current development evidence: the owner-approved native-development-v1 baseline now completes a
real Claude code fix, bounded Windows execution, frozen checks and fresh review without intermediate
owner input. It is consolidated in this worktree. See [the development-loop implementation](native-development-loop.md)
for its measured scope. This does not promote installed runtime support or credential isolation; the
older strict-isolation findings below remain historical evidence.

Status: product behavior agreed on 2026-09-05; broad Codex registration removed and ordinary-work
checks passed on 2026-09-05. Ralph-only runtime correction remains pending.

Excubitor helps the owner set up and run safe, unattended Ralph workflows with little repeated effort.
The owner agrees on the job, what proves it is done, and how far it may proceed automatically. Excubitor
handles iteration, verification, recovery within the agreed limits, and a concise completion report.

This plan replaces the earlier always-active baseline and its implementation checklist. Earlier work
and decisions remain in repository history and the append-only learnings log. They are evidence and
candidate mechanisms to assess, not instructions to continue broad enforcement or require Ralph for
ordinary development. Recording this correction does not change the running implementation.

## Agreed user experience

- Native Windows and Linux are both required implementation targets. Windows must run entirely
  natively, without WSL, a Linux worker, or a virtual machine. The earlier Linux-worker choice was
  superseded by the owner's explicit request for both platforms. Preserve the tested Linux backend;
  WSL may host Linux development tests but is not a dependency of Windows operation. Share the run
  contract, budgets, verification and completion behavior while implementing OS-specific isolation.
  Existing native vendor authentication must remain usable without another login or credential copying.
- Start Ralph from the existing coding app window using a consistent Ralph command or action, or
  from the host CLI. Codex, Claude Code, and Antigravity are requested integrations; Cursor is a
  prospective extension. Use native entry points with shared behavior, not a separate control panel.
  Adapt command syntax to the host without claiming an unimplemented universal slash command.
- Ralph is explicitly started for a particular job. Installing Excubitor, opening a project, asking for
  a fix, or continuing ordinary development does not start a Ralph run.
- Normal development remains available, including in a repository that previously ran Ralph. A small
  ad hoc task never has to be represented as a one-stage Ralph loop.
- Setup establishes the scope, acceptance checks, resource limits, and permitted completion actions.
  Reusable defaults avoid asking the same questions every run. Defaults cannot silently grant new
  outward actions or change the selected project or destination.
- Once started, the run advances through all agreed work units without requiring approval or a manual
  restart between units. Small units, durable checkpoints, and fresh reads of the plan remain useful
  internal mechanics. One worker finishing is not the whole run finishing. Select unit size, context
  reset timing, and additional intermediate review from observed results; they are not fixed rituals.
- The default completion result is reviewed, verified work committed on an isolated branch, ready for
  owner review. The run reports what was completed and anything unresolved, then ends its enforcement.
- Automatic merging is an option authorized once before the run starts, bound to a selected destination
  and required checks and review. It is not the default. Publishing and deployment require separate
  permissions, which may also be granted in advance. A completed run never invents those permissions.
- The run preserves the agreed definition of success. It cannot weaken acceptance checks, drop scope,
  alter trusted verification evidence, or expand its authority to declare itself complete. New tests
  authored during implementation may supplement the agreed checks but cannot replace them as authority.
- Interrupt the owner only for a decision outside the run's authority, an unresolved blocker, or an
  agreed resource limit. Routine implementation choices and recoverable failures stay within the run.
  Preserve progress when blocked; report partial work honestly instead of marking the job complete.

## Scope and activation

- Use each host's native hook or lifecycle facilities. No user-wide or machine-wide Ralph enforcement
  registration by default; no global Git hooks, launch wrappers, shortcut edits, or launch-time
  environment-variable ritual. A dormant global dispatcher is not an approved substitute.
- Distinguish installation, native trust, and an actively armed Ralph run. A project hook being present
  or trusted is not authority to enforce Ralph rules in every task in that project.
- Bind activation to the canonical project and the exact task/session where the host supports it.
  Other tasks in the same project, sibling repositories, parent directories, and separate worktrees
  must remain unaffected unless explicitly included in the authorized run.
- An ordinary agent-writable marker may describe intent but cannot create, extend, disable, replay, or
  redirect the protected activation or grant additional completion actions. Establish the native
  source of owner intent and task identity before selecting a state format or building a lease system.
- The model-blind core owns policy; thin host adapters normalize native events and return decisions.
  Apply Ralph restrictions only to the verified active run. Outside it, ordinary host permission rules
  apply without additional Ralph restrictions. Failure within a known active run must not silently
  disarm it or convert an uncertain state into permission.
- Completion, cancellation, interruptions, crashes, and resumption need explicit lifecycle behavior.
  End or revoke the run's authority and account for its remaining workers before removing protections.
  A stale or copied activation must never capture ordinary future work. An interrupted run may resume
  only within its remaining authority, without silently extending limits or permissions.
- Treat Codex, Claude Code, Antigravity, and prospective Cursor support as separate integrations.
  Verify interactive CLI, headless CLI when claimed, and each GUI surface separately. If a host cannot
  provide the required scope, trustworthy activation, or unattended continuation through native facilities, name
  the unsupported mode and missing capability. Do not broaden registration to simulate support.

## Completed removal of the broad Codex registration

The owner authorized removal of the existing Excubitor-owned user-scope Codex registration. Replacement
registration, native trust changes, candidate promotion, merge, push, and publication remain separate.

- Use the existing transactional uninstall interface. Before mutation, capture exact registration,
  receipt, and affected configuration bytes and their digests in a recoverable rollback packet.
- Confirm the exact owned entry and prove unrelated entries will remain intact. An uninstall preview
  is useful but does not replace that comparison or the rollback packet.
- Stop relevant configuration writers for the mutation interval. Preserve and recheck the preimages;
  if they drift, retain the evidence and stop instead of overwriting another writer's changes.
- After removal, validate the resulting configuration, or verify that deletion of the settings file
  was justified because no unrelated content remained. Confirm the owned entry and receipt are gone,
  status no longer lists Codex user scope, and an ordinary disposable workspace is unaffected.
- Preserve installed skills, unrelated native configuration, pre-existing Claude hook placeholders,
  shortcuts, and other hosts. Install nothing into Antigravity as part of this removal.
- If the transaction cannot safely perform removal, preserve its conflict evidence and obtain a
  concrete owner decision. Never edit around an active guard or replace the runtime to escape it.

The owner-operated supported uninstall removed the one receipt-owned registration after Codex exited.
The hook file contained only that entry and had not pre-existed the installation, so deleting it
preserved unrelated configuration. Its receipt is gone and fresh status reports no installations.
All 175 inventoried settings, skill, and Claude hook filesystem entries matched across removal. Exact
registration, receipt, and prior-probe backups remain available with verified digests.

After reopening Codex, previously denied implementation-source reads succeeded. Ordinary shell and
apply_patch writes succeeded in a disposable repository on main, without Ralph opt-in. An offline call
to the old adapter against that repository still denied a default-branch edit with an empty environment:
the installed interference is removed, but the old implementation still violates the target scope.
These native ordinary-work checks establish removal for the tested surfaces, not replacement support.

The Windows packaged app redirected its apparent AppData state directory to package-local storage.
An external PowerShell process initially could not see the receipt at the apparent path. Open-file
handle resolution established the physical receipt and probe paths; capture and the uninstall's
child-process-only state-directory override used those paths. No state was moved and no persistent
environment setting changed. Include packaged-app versus standalone-CLI state discovery in future tests.

## Existing work and support evidence

Keep existing code, tests, isolated runtime candidates, and rollback evidence. Assess reusable policy,
adapter, packaging, and transactional mechanisms against this corrected product scope before extending
them. Existing signing, promotion, and independent evidence-collection proposals concern runtime
installation and upgrades; they must not become manual prerequisites for starting each normal run.
This correction does not provision authority, promote a candidate, or import candidate code into a
live hook. Detailed prior deployment decisions remain in history and the bootstrap runbook pending
review against the new scope.

| Host | Evidence available for this review | Ralph-only unattended support |
|---|---|---|
| Codex | The broad installation is removed. A separately authorized disposable interactive CLI experiment passed native apply_patch veto, two automatic continuations, concurrent-task isolation, and ordinary edits before/after the exercise. Its temporary registration was removed; a fresh CLI showed zero hooks and allowed an ordinary edit. | Production replacement support is not established. Protected activation, completion verification, faults, worker containment, and other interfaces remain unverified. |
| Claude Code | Existing adapter and installer are recorded; this review has not refreshed live configuration or lifecycle evidence. | Not established for the corrected contract. |
| Antigravity | The handoff records no registration; no fresh native capability or installation verification has been completed. | Not established; do not install or infer capabilities from another host. |
| Cursor | Prospective integration requested by the owner; official hook and CLI documentation reviewed. | Not established; no native runtime verification or installation performed. |

Installation, native trust, active-run identity, policy behavior, and unattended continuation are separate
claims. A fixture, old supported-runtime label, or successful CLI invocation cannot prove the corrected
contract. Record evidence per host version, operating system, scope, interface, and tool surface.

The [native workflow research](ralph-native-workflow-evidence.md) records current official facilities,
the experimental basis and limits of proposed workflow defaults, and the required local comparisons.
The documented capabilities are leads for native probes, not proof of support. Preserve the final
acceptance and permission boundaries while comparing context and intermediate review policies.

The [disposable native lifecycle experiment](../../runtime/probes/README.md) passed its bounded Codex
interactive CLI checks on Windows after separate owner authorization of the exact temporary
registration and native trust review. Both continuations stayed in one native turn and did not fire
additional UserPromptSubmit hooks. Native CLI session exit produced SessionEnd observations. The
registration is removed; Codex retains nine fixture-specific hook trust records and project trust.
The test apparatus does not treat its synthetic prompt or writable state as protected owner authority.
It is not production activation or a completed Ralph runner. Other hosts have observation code only;
the GUI and headless CLI were not tested. The broader capability checklist below remains open.

The [protected lifecycle candidate](protected-ralph-lifecycle.md) now implements an internal host-owned
store with fixed scope and limits, progress across units, repairs, same-task resumption, cancellation
drainage, and candidate-bound completion prerequisites. A native Codex subprocess could edit an
ordinary file but could not change the separate authority store or acceptance file. This is component
and storage-boundary evidence. The start handshake has since connected actual CLI confirmation to an
exact scoped record, and protected output comparison has passed native positive and negative cases.
MCP shutdown skipped cleanup. A separately authorized native SessionEnd test has now recorded interruption
for the exact confirmed record on normal CLI exit, without declaring completion or worker drainage.
Ordinary work in another task in the same project stayed inactive. The temporary hook was removed and
a fresh CLI showed zero hooks; its updated fixture trust entry remains. Forced termination, crash recovery,
complete native admission and the full owner-facing runner remain unfinished. A shared supervisor has
since completed a real two-feature Codex CLI job with an injected bug, automatic repair, original
acceptance checks, independent review, actual committed-candidate inspection, and process-tree drainage.
The final run used an already trusted disposable project, retained an isolated branch and its base,
ended inactive, and left native configuration unchanged. An earlier attempt exposed native automatic
project-trust persistence; that fixture entry is retained and the driver now refuses fresh enrollment.
This is bounded CLI demonstration evidence, not complete GUI, crash-recovery, or cross-vendor support.
Production adapters do not import these components.

The native CLI Start action has now dispatched that supervisor through the shared confirmation
handshake. One agreed job recovered automatically from a forced controller crash, repaired the
deliberate arithmetic bug, and passed all four original checks and a fresh review in four attempts.
The watchdog recorded the old tree empty before restarting and preserved the interrupted journal.
The first final report exposed an uncontained Windows Git inspection helper; that failure is retained.
Git candidate inspection now uses the bounded Windows process-tree runner, and a separate native MCP
recheck verified the completed candidate and unchanged configuration with all inspection processes
drained. This does not establish recovery after losing the watchdog, app-exit survival, GUI behavior,
full native-tool admission, or another vendor. No persistent hook or tool registration was added.

The Windows component can now reconcile loss of the watchdog using an exact host-owned kernel job,
created together with its controller process. Tests kill the owner immediately after creation, kill
and replace watchdogs with both absent and retained kernel objects, and confirm repeated replacement
cannot reset the restart budget. Malformed history and denied kernel access preserve protection.
The native action can reuse the original accepted job through an adapter's reconnect callback.
These are component results. A subsequent actual native sandbox test rejected the unelevated Windows
mode: workers could open query handles to host-owned jobs despite denied mutation access. That mode
was already excluded from the approval parser; regression coverage now preserves the exclusion.
The separately approved existing elevated sandbox check subsequently denied all five requested kinds
of access, including query handles, using a different native worker account. Ordinary project writes
succeeded, the external acceptance file stayed unchanged, and all eight observed processes drained.
The worker appeared in its actual containment job; the named access target was a separate object.
Native configuration, setup-marker, and credential fingerprints remained unchanged at independent
inspection. This verifies the tested Windows CLI shell boundary, not native forced-owner-death recovery
or all writable tools. A native app-server experiment preserved a seeded task's identity through server
loss and resumption, but direct MCP calls lacked the required approval context
and were correctly rejected. Its final config comparison failed: Codex automatically trusted the
disposable project in each isolated test home. Those entries remain for review; the corrected probe
refuses fresh enrollment. The owner subsequently approved reuse of one exact isolated profile. That
native run passed identity preservation and task separation, drained both process trees, and retained
identical native configuration without saved credentials. Incomplete tool contexts were still rejected.
Those experiments left protected same-task Ralph reconnect, full native-tool admission, GUI behavior,
and other vendors needing direct verification. The full replacement remains unfinished.

The native supervised CLI candidate now connects its Start action's reconnect path to that watchdog,
retaining the original agreement and oracle bytes across separate connection logs. Windows component
tests passed through real connection-process death, including a retained kernel handle, without new
approval or reset limits. Closed connections cannot restart, and ended threads no longer look attached.
After explicit project-trust and storage approval, the native rehearsal passed on Windows with Codex
CLI 0.153.4. One native confirmation started the job. The test server and watchdog exited after the
first model worker drained with a disclosed fixture child alive. The driver reopened the original
native task, whose authentic turn envelope matched the accepted binding. Start reconnected without
another job confirmation or a reset attempt budget. The replacement recorded the old exact job absent
before proceeding. Both units completed in four of six attempts within the unchanged deadline.

The original checks caught the deliberate arithmetic bug; automatic repair, all four checks, and a
separate reviewer then passed. The clean committed branch retained its original base. Independent
inspection confirmed unchanged contract/check bytes and complete process drainage. Another native
task in the same project remained inactive during the run. The finished task also became inactive,
and ordinary native editing worked without starting Ralph. Native config, setup, and credential
fingerprints matched the sealed baseline at the first independent check. The post-exit comparison
found one new unrelated project trust entry, which the owner confirmed was separate concurrent work.
That comparison failure and its snapshots remain intact; no baseline or settings were replaced.
Sandbox setup and credentials remained unchanged.

This is a bounded native recovery result. The driver reopened the task; automatic reopening, recovery
during a model turn, and app-closed continuation were not tested. The everyday native launcher, full
tool admission, GUI surfaces, other vendors, and representative workflow comparisons remain open.
No replacement registration, saved tool allowance, hook, merge, push, or promotion occurred.

The next candidate replaces fixed test-plan input with agent-proposed jobs through the shared native
Start action. A host-supplied planner resolves advertised verification runners, reuses configured
limits, and requires an independent host admission check before the single native confirmation.
Draft fields cannot grant permission or replace native scope; an existing job reconnects without
draft arguments and retains its original budget. Status now exposes exact-task progress and recorded
completion without keeping the task active. The explicit `ralph` skill candidate uses these tools;
it refuses a manual-loop fallback if they are unavailable. Its source is retained outside automatic
skill discovery. This advances preparation and presentation; the skill, general project executor,
and scoped native connection required a separate live test.

The project backend now consumes the confirmed goal, units and original checks instead of the fixed
demonstration specification. It uses a separate candidate checkout and a required host commit path,
and verifies actual retained bytes after each checkpoint. Offline integration covers two different
jobs, real Git commits and output execution, acceptance repair, independent review repair, and release
of the completed task. A private native project connection and staged explicit command are prepared
for a bounded live test. The authorized Windows CLI test subsequently discovered the explicit command,
read the project README, proposed three units and ten checks, and accepted one native confirmation.
A malformed check-name proposal was rejected before that confirmation and corrected by the initiating
agent. The worker launcher then failed before model execution: ignoring user configuration while adding
only a disabled MCP entry creates an entry with no valid transport. All six work attempts were consumed
by that same startup error. No unit completed, no check or review ran, and neither source copy changed.
All worker and controller processes drained. Another native task reported no active Ralph job and
completed ordinary file editing after the fast failure; this does not supply a during-work witness.
The three unchanged temporary project files were removed, and only the two approved trust entries
remain. Native sandbox setup, credentials and unrelated settings stayed unchanged.

The corrected worker command uses an empty MCP table. Native configuration failure before model start
now interrupts after its first launch instead of repeatedly consuming attempts; failed candidate output
checks remain repairable. A separate read-only native startup diagnostic completed without tools or
edits and drained its process tree. The original failed run and its six-attempt limit were preserved.
Full project-job completion still needs a fresh native run. Production provisioning, GUI surfaces and
other vendors still require their own evidence.

The subsequently authorized fresh run progressed automatically through both implementation units,
with a real native worker and retained commit for each. Its next four worker turns failed with native
model-service capacity errors, exhausting the original six-attempt limit before host acceptance or
independent review. Two failures occurred before model output, and two after read-only tool activity.
The clean isolated partial branch, original base and unchanged checks remain preserved; all six worker
trees drained and the exact controller job was absent. A separate native task completed ordinary file
editing while the first worker was running. The earlier exhausted run stayed byte-identical. The three
temporary project files were removed after the native sessions exited, with only the two approved
trust entries added and unrelated settings unchanged. This establishes native unit progression and
ordinary-task exclusion during productive work, while full project-job completion remains unverified.

The candidate now recognizes the observed native capacity terminal event separately from candidate
output. It waits 30, then 60, then at most 120 seconds between capacity retries, bounded by the original
deadline and cancellable after worker drainage. Every failed launch still consumes the accepted attempt
budget. Reviewer capacity retries retain the same verified candidate and consume another attempt without
rerunning the implementer. Native status reports capacity failures and preserves them when blocked.
No model switching, reset or replacement agreement is part of retry handling. Component tests cover
these behaviors; a fresh native project run is still needed. The launch skill also explains valid check
names and omits redundant work units for verification and review already performed by the host.

The next fresh Codex CLI job completed both implementation units, all ten original output checks and
a fresh independent review in two of six attempts. Native skill discovery and the first proposal worked
without rejected check names or a redundant verification unit. Independent inspection matched the
accepted native form, frozen checks, retained clean isolated candidate, original base and process
drainage. Ordinary editing succeeded in another task during work and in the initiating task after
completion. The exhausted earlier runs stayed byte-identical. The three unchanged temporary project
files were removed after session exit; unrelated settings, sandbox setup and credentials were preserved.
No service-capacity failure occurred in this successful run, so live recovery from that failure remains
unverified. The retry behavior has component coverage. This completes the bounded project-backend CLI
demonstration; production provisioning, full tool admission, GUI and other vendors remain open.

The legacy install CLI now refuses new hook registrations in both user and project scopes. Those hooks
can enforce restrictions on ordinary tasks and must not stand in for the unfinished Ralph-only installer.
Read-only legacy previews and existing-installation diagnostics and removal remain available. The
transaction library is retained for maintenance and isolated regression tests. Nothing is newly
registered on the owner's machine by this correction.

A separate bounded native diagnostic then demonstrated an allowed patch and shell write inside the
candidate, an OS-denied shell write to an external canary, and a native-router outside-project patch
rejection. The protected canary and candidate preimages stayed unchanged, all 57 observed processes
drained, and removal of the one owned canary restored the completed clean candidate. The native JSON
stream omitted the rejected patch target; the router error is preserved separately. This supplies
observed shell/patch boundary evidence, not admission of every tool, path or host surface.

## Isolated Linux worker preparation, 2026-09-06

The owner selected an isolated Linux worker for Claude, separate from recovery environments.
The private preparation uses a dedicated QEMU VM and verified Ubuntu image on D:, with no host
filesystem sharing. Existing WSL distributions, shared WSL configuration, Docker configuration and
native Claude settings were not changed. The VM's control keys and disk images have host-only access.

The Linux process runner places its fixed launcher into a root-owned cgroup before dropping to the
worker account or executing the requested program. Nine actual Linux tests passed, including detached
children with closed pipes, cancellation, output flooding, process and memory caps, and denied writes
to control files. The kernel reports the group empty before successful drainage. This runner supplies
process containment; a separately admitted sandbox and outer lifetime owner remain required. Killing
the Linux controller alone does not destroy its cgroup. It is not connected to live Ralph activation.

Separate real Bubblewrap canaries passed writable-candidate and read-only-review modes, with control
files, Windows paths and network access unavailable. Ubuntu first denied namespace setup; an explicit
application profile was provisioned only inside the new VM, retaining its general namespace restriction.
Host comparison verified the tested source bytes. The Windows VM owner also drained at its original
ten-minute diagnostic limit. These results do not prove complete Claude tool coverage or controller
crash recovery. Claude Code's Linux build matching the existing Windows version was checksum-verified
and its version/help commands ran; the new guest is not authenticated. Native Claude job completion,
the reusable launcher and GUI integration remain open.

The Claude project adapter now connects the shared backend to a required isolated executor. It
starts a fresh native session for each worker and reviewer, retains the selected model, carries the
remaining original deadline and cancellation signal, and runs frozen checks directly in read-only
mode. The reviewer has file-reading tools only; executable checks belong to the host. Native session,
model, tool and terminal-result metadata must match before a successful execution can be accepted,
and the review verdict must come from the exact structured-output object. Malformed or conflicting
native evidence stops the host path instead of becoming candidate repair feedback. Execution evidence
is reserved before dispatch and retained before interpretation.

These are protocol component results, with fixtures based on the installed CLI help and current
[headless documentation](https://code.claude.com/docs/en/headless). They do not admit the CLI flag
combination, native Bash sandbox, network/credential boundary, native session metadata or complete
Claude workflow. In particular, post-execution metadata checking cannot protect the first tool call;
the supplied executor must already enforce every exposed tool boundary. There is no direct process
fallback or live registration in this adapter. Authenticated native testing remains outstanding.

## Remediation checklist

The current platform requirement is full native Windows plus Linux support. The Ubuntu work below
records Linux component evidence, not the required Windows architecture. Native Windows filesystem,
network, process and resource boundaries, authenticated vendor execution, and in-app/CLI integration
still require implementation and direct verification; Linux authentication and integration remain open.

The owner subsequently directed use of the existing Ubuntu WSL distribution. It is separate from the
recovery distribution and boots successfully. This replaces the separate QEMU launch for the current
Claude path; the earlier 5 GiB free-memory threshold was a provisional QEMU budget, not an established
Excubitor requirement. Task files, extracted dependencies and the new Claude profile remain on D:.
Ubuntu's existing system disk is on C:. No distro package installation, global WSL setting change or
recovery-distribution startup was performed.

Actual WSL canaries passed writable-candidate/read-only-review boundaries and denied host paths,
control files and network access. A separate test killed the diagnostic controller
while a detached child was running; the owning transient systemd service removed the entire cgroup,
and no delayed write appeared. This is a bounded process-lifetime result, not complete job recovery.
Claude startup with the actual reviewer flags reached the expected missing-authentication result and
reported only the selected reading/structured-output tools. Its service peaked near 240 MiB; this
does not measure a complete model job or its build tools.

Native inspection also found that `opus-4.8` is unrecognized, while `claude-opus-4-8` selects the
intended version without that warning. The native Windows setting was not edited. Safe mode still
advertised built-in skills, so the adapter now explicitly disables slash-command skills and verifies
their absence. A native authentication failure can carry a success subtype while its error flag is
true; the adapter recognizes the actual error envelope and interrupts for sign-in instead of spending
the remaining attempts. The proposed interactive sign-in helper was subsequently disabled: the owner
reports that a new WSL login would disrupt the existing Windows login. The missing-authentication
diagnostic used an empty, separate WSL profile; it did not test the Windows login. Preserve ordinary
Windows authentication and do not copy or share its rotating credentials. A supported authentication
arrangement that preserves those sessions remains unresolved. Authentication, provider access, native
model tool denial and complete Claude job execution remain open.

A later test with a real Windows executable found that hiding `/init` does not remove the inherited
WSL binary loader. The loader started but failed before the harmless Windows command completed;
that failure is not an adequate isolation boundary. A separate corrected canary initializes an empty
binary-format table inside a fresh private user namespace, hides the table and drops every capability
before executing the worker. The real Windows executable then fails with an executable-format error,
while ordinary WSL Windows execution still succeeds. The correction is now included in the reusable
offline executor and was retested with a working outside-sandbox baseline. The executor also joins
filesystem isolation to validated service lifetime and cgroup limits. Its final native suite passed
28 checks, with one Unix-socket case skipped because the candidate filesystem refused socket creation.
Separate native controller-death, deadline-expiry and unsafe-service-refusal checks passed. Earlier
outside-sandbox interop failures remain recorded; no global registration or settings were changed.
Authentication and provider networking are deliberately unavailable in this component, so this does
not establish native Claude job completion. See [the executor boundary](linux-worker-executor.md).

The maintained Windows command API was then tested as a possible shared executor.
It enforced explicit private-directory denial and bounded a different-user process
tree, but could read a synthetic credential file with the real login file's access
rules. After Fable review, one bounded attempt combined that existing account with
the existing LPAC identity. Windows refused child creation before Python ran. The
experiment stopped, its process tree drained, and its D: fixture grants were revoked.
Neither result admits a Windows executor; no new account, registration or scheduler
was introduced. The [maintained executor assessment](maintained-windows-executor-assessment.md)
records the distinction between launch failure and untested security behavior.

A tools-disabled native Claude controller rehearsal then completed two text-only
units, fixed host checks and a fresh structured review after one start. It reused
the existing supervisor, store, project backend and native framing checks. The host
saved returned text at two fixed paths and retained real isolated Git checkpoints;
Claude's writers exposed no tools and its reviewer exposed only StructuredOutput.
Reopened state preserved progress, the original deadline and attempt budget. All
native process trees drained, and calling the completed run started nothing. The
62 existing controller and Claude protocol tests passed. This establishes the tested
native coordination flow; it does not admit project-code execution or in-app launching.
The sample reviewer missed wording that incorrectly required human review and implied
a manual, single-unit workflow, so those cards remain diagnostic data, not product copy.

- [x] Record the owner-agreed Ralph-only product scope and default completion behavior; remove the
  repository instruction that routes ordinary roadmap work through Ralph. This is a documentation change.
- [x] Record native in-app and CLI launching requirements and a primary-source workflow/capability
  inventory. This is research and documentation; it does not complete the native verification below.
- [x] Capture a rollback packet and safely remove the exact Codex user-scope installation through the
  existing transaction during a quiesced maintenance window; verify unrelated state and ordinary work.
- [ ] Verify the native activation and continuation capabilities of each requested host. Establish the
  trusted source of owner intent, project/task identity, worker lifetime, and end/resume behavior before
  selecting implementation mechanisms. Record explicit unsupported modes and their missing capabilities.
- [ ] Implement the smallest independently reviewable Ralph-only activation unit in an isolated candidate
  for a host whose capabilities support the contract. Keep live registrations and trust unchanged until
  the exact replacement is reviewed and separately authorized.
- [ ] Verify unrelated projects, projects without opt-in, installed but inactive projects, ordinary tasks
  in the same project, siblings, parents, and worktrees remain unaffected. Verify an explicitly armed run
  receives the intended protections and cannot alter its authority or completion checks.
- [ ] Reject stale, copied, malformed, cross-project, cross-task, replayed, redirected, and extended
  activation. Verify cancellation, crashes, lingering workers, expiry, resumption, and ordinary work
  after completion. Report incomplete enforcement honestly where a native host cannot fail closed.
- [ ] Connect bounded workers through the host's native continuation facilities. Verify a multi-unit job
  completes without human restarts, tolerates recoverable failures, respects resource limits, preserves
  its acceptance criteria, and produces the default verified branch and report.
- [x] Demonstrate the shared supervisor with real bounded native CLI workers, a failed unchanged check,
  automatic repair, independent review, and a clean committed branch. This completes the disposable
  Windows CLI example; native activation, mode admission, GUI integration, and crash recovery remain open.
- [x] Demonstrate the approved Windows CLI connection-loss rehearsal with authentic same-task native
  resumption, one original confirmation, unchanged limits/checks, automatic repair, independent review,
  complete process drainage, and ordinary-task exclusion. The test driver reopens the task; automatic
  reopening, mid-worker crashes, production admission, and other native surfaces remain open.
- [x] Implement the normal-start proposal and confirmation path, reusable host defaults, exact-task
  result history, and explicit command skill candidate. Verify draft mutation, authority injection,
  admission refusal, replay, cancellation, and unchanged recovery limits in component tests. Native
  command discovery, general project execution, and scoped installation remain open.
- [x] Connect confirmed jobs to a project backend with a separate candidate checkout, required host
  admission and commit path, and native worker/check/reviewer transport. Exercise actual Git and
  program output on two different proposals with acceptance and review repair. Native calls in those
  tests are fixtures; the staged project command and live launch still need separate verification.
- [ ] Compare workflow variants on representative tasks with fixed acceptance checks, permissions,
  model versions, and budgets. Record all attempts, failures, interventions, setup effort, quality, and
  resource use. Keep safety protections fixed and select the simplest adequately performing defaults.
- [ ] Implement optional preauthorized merge and separate outward-action permissions only with an
  enforceable grant and required verification. Default runs retain their work without merging or
  publishing; out-of-scope destinations and actions remain unavailable to the active loop.
- [ ] Verify transactional project install/uninstall, shared dependencies, edited registrations, failed
  and interrupted removal, packaged versus standalone state discovery, and unchanged ordinary host
  launch. Preserve unrelated entries and skills.
- [ ] Reconcile skill recipes, installation examples, diagnostics, support matrices, and older design
  documents with the implemented lifecycle. Remove environment-activation rituals and broad-enforcement
  claims from current instructions; retain historical evidence with explicit historical status.
- [ ] Obtain an independent read-only review and fresh native allow/deny, isolation, and completion
  evidence for each claimed mode before presenting the replacement for integration or registration.

## Working on the correction

Ordinary development can advance this checklist without being a Ralph run. Use focused, reviewable
changes in the dedicated development worktree and the configured commit broker. An explicitly started
Ralph workflow must honor the agreed run contract; unavailable native protection is a capability gap,
not a reason to force unrelated work through a one-stage loop. Do not rewrite the append-only learnings
log or treat its observations as completion authority.
