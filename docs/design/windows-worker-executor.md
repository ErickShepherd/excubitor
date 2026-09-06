# Native Windows worker implementation

Windows and Linux are required first-class targets. Windows runs Windows binaries
directly and has no WSL or virtual-machine dependency. Both use the same Ralph
contract, frozen checks, resource budgets and completion rules. Ordinary tasks
do not enter either executor.

`WindowsSandboxExecutor` is an offline implementation candidate. It combines a
Less Privileged AppContainer with a Windows Job Object: explicit file grants,
no network capabilities, a required noninteractive Windows session, aggregate committed-memory and
process-count limits, bounded output and time, cancellation, and kill-on-close
process ownership established atomically before any worker instruction executes.
It does not create a profile or perform vendor authentication. Registration and
native admission remain separate requirements; the class is not currently wired
into a production launcher.

A native test found that a worker in the interactive session could open and attach
to its Default desktop and obtain a screen device-context handle. No pixels were
captured or input injected. A private desktop and Job Object UI restrictions did
not block that route. The candidate now refuses execution outside session 0 at
both the executor and low-level process-creation boundaries. The revised mode
still requires native validation; its existence is not an admission result.

A one-shot Task Scheduler diagnostic is prepared to test that boundary under the
current user's S4U logon with limited privileges, no stored password, no recurring
trigger and a two-minute limit. It would remove its exact registration afterward.
The owner asked why it was proposed; its separate C: metadata exception remains
pending, and no scheduled task has been created. This is a diagnostic launch
choice. The permanent launcher is undecided. Users will still launch Ralph inside
their existing coding app or CLI, without per-iteration setup.

The fixed registryRead capability is necessary for runtime initialization; no
network or COM capability is supplied. The private desktop's host handle remains
open until the process job drains because early closure broke delayed DLL loading.
Disabling all Win32k system calls also broke the installed Python's ctypes support,
so that setting does not satisfy the intended general Windows tool compatibility.

The host must provide a separately provisioned dedicated identity and an exclusively
leased private root containing `candidate/` and `tools/`. Tools are private copies;
shared installed tool permissions are never changed. Paths are checked for reparse
points, hard links and unexpected entries before permission changes. Workers get
candidate write access; checks and reviewers get read access. Permission inheritance
and owner rights are reset before each execution. Temporary directories are fresh
for each call, and access is revoked after the process job drains. Unexpected path
changes or failed permission operations stop reuse. This requires the host lease;
path scanning alone does not prevent concurrent changes by another trusted controller.

AppContainer registration is Windows-managed user state. The documented creation API
creates a profile beneath the user's local application-data directory. On the current
development machine this is on C:. The owner approved that narrow storage exception,
and the setup helper created one unique identity. It refused pre-existing state and
made the new disk profile read-only to workers. Executable copies, candidates, caches,
temporary files and test evidence stay on D:. No registration has been made by the
executor itself, and no Claude credentials are read, copied, rotated or replaced.

The initial diagnostic confirmed that SID derivation alone creates no profile,
but process creation without registration failed before worker execution. That is
not a sandbox denial witness. The newer Windows composable-sandbox API is present
on this machine but is experimental and also creates an AppContainer profile; it
does not remove the storage decision. The implementation uses the existing Windows
process-attribute API rather than adding an experimental API dependency.

Before the session-0 requirement, the native suite passed 11 tests and failed three.
The failures exposed the desktop gap, Python's temporary-directory permissions bug
and an unsupported token-information query. The successful checks exercised files,
network denial with an outside baseline, host job-handle denial, output and memory
limits, cancellation, detached children and controller death. Failed packets remain
preserved. These passes do not admit the revised execution mode, whose native suite
has not run. Subsequent focused process, Windows job, sandbox-preflight, Claude and
Linux regression checks passed 90 tests with 12 platform-dependent skips.

Python 3.14.7 reproduced the upstream AppContainer mode-0700 directory bug. A
prepared compatibility patch in the private runtime includes the actual token's
AppContainer SID when creating those directories. It does not change installed
Python or existing permissions, and the parent directory's access check still
applies. Native success and denial witnesses for that patch remain pending.

Before native admission, verify file read/write and read-only enforcement, permission
and reparse-point escape attempts, host control-file and credential-canary denial,
network denial with a working outside baseline, inherited child restrictions,
job-handle isolation, cancellation, controller death, memory and process limits,
and ordinary work before/after. Then integrate the native vendor protocol and prove
an authenticated multi-unit job without disrupting the existing login. Linux keeps
its tested offline namespace/cgroup executor; authenticated Linux integration also
remains open. Neither OS component alone establishes complete product support.

Primary references:

- [Microsoft's AppContainer launch procedure](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
- [Windows process creation attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
- [Microsoft's noninteractive service guidance](https://learn.microsoft.com/en-us/windows/win32/services/interactive-services)
- [Task Scheduler security contexts](https://learn.microsoft.com/en-us/windows/win32/taskschd/security-contexts-for-running-tasks)
- [CPython's open AppContainer temporary-directory issue](https://github.com/python/cpython/issues/134587)
- [Windows composable sandbox API status](https://learn.microsoft.com/en-us/windows/win32/secauthz/createprocessinsandbox)
- [AppContainer implementation in Chromium](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/sandbox/win/src/app_container_base.cc)
