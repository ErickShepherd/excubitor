# Bounded offline Linux executor

`excubitor.linux_sandbox.LinuxSandboxExecutor` combines the previously separate
filesystem, namespace and cgroup prototypes. It implements the execution interface
consumed by `ClaudeProjectRuntime`, but currently permits **no network or credentials**.
It is a development component, not an installed Ralph command or admitted Claude mode.

The trusted launcher uses `service_command()` to start a fresh transient systemd
service. The controller constructs the executor inside that service, invokes one
command at a time, and closes it before exiting. No service is installed or enabled.
The constructor checks the actual service's controller PID, cgroup, delegation,
finite runtime, memory/process limits, disabled swap, termination behavior and
disabled restart before creating workload groups. Insufficient controller headroom
or a service that only terminates its main process causes refusal.

Each execution gets new user, mount, process, network, IPC, UTS and cgroup namespaces.
The visible filesystem contains read-only system tools, the admitted native binary
at `/opt/claude`, the candidate at `/workspace`, and disposable home/temp directories.
The caller selects `workspace-write` or `read-only`. Only the candidate bind changes;
review can still use temporary files without changing the candidate. There is no
host home, account profile, host mount tree, controller evidence or external network.

The fixed bootstrap runs before any requested program. It initializes an empty
private binary-format table, hides the table, drops all capabilities and verifies
`no_new_privs`. This blocks inherited WSL Windows-executable handlers. Namespace
root maps to an unprivileged outer UID; requested programs receive no capabilities.
Nested user namespaces cannot make the inherited read-only candidate writable.
The implementation follows the observed behavior of the
[Linux binary-format loader](https://raw.githubusercontent.com/torvalds/linux/v6.18/fs/binfmt_misc.c)
and [Bubblewrap's namespace construction](https://github.com/containers/bubblewrap/blob/v0.6.1/README.md).

The host keeps authority over setup:

- Supply a fresh `excubitor-worker-<UUID>.service` name, trusted controller code,
  and explicit service limits. `service_command()` takes literal argument tuples;
  it does not create shell command strings.
- Keep the candidate's parent private and enforce exclusive use across controllers.
  This executor serializes its own calls; it does not supply the supervisor's
  cross-run lease, original deadline, acceptance checks or permission grant.
- Admit immutable system tools, extracted dependencies and the native binary before
  launch. Reuse the verified paths; this component does not download or install them.
- Keep control files and credentials outside the candidate. On Windows-backed mounts,
  rely on the host's access controls rather than Linux chmod as an independent boundary.
- Pass the same canonical candidate path as `cwd`. The native binary's executable
  path maps to `/opt/claude`; candidate executable paths map to `/workspace`.
  Other arguments are preserved literally and must name paths visible inside the sandbox.
- The environment is fixed. A caller can repeat admitted fixed values, but custom
  loader settings, authentication variables and provider overrides are refused.
- Stop the exact owned service on cancellation or disconnection and independently
  observe its disappearance. The service deadline bounds an abandoned controller;
  this is not automatic application or machine restart recovery.

Candidate validation rejects replacement of its root, nested host mounts, existing
hard links and special files, and unreadable or excessively large directory inventories.
Workers cannot link to invisible host files. Symlinks resolve within the private mount
tree. Candidate parents and source inputs must not be replaced concurrently by the host.

`LinuxProcessTree` bounds stdin, combined output, time, memory and process count. It
places the fixed launcher in the cgroup before requested execution, starts the workload
under a separate outer UID/GID, and verifies that all descendants drain. Memory and process
limits are ceilings, not reservations. The outer service needs at least 64 MiB and eight
process slots beyond the workload limits for its controller.

The reusable executor was tested directly on the owner's Ubuntu WSL with Bubblewrap
0.6.1 and the WSL Linux 6.18 kernel. The controller diagnostic used Ubuntu's Python 3.10;
this does not change the package's declared Python 3.11 minimum or establish a complete
packaged installation on that Python version. No recovery distribution was started and
no WSL settings were changed. Source, dependencies, test files and reports stayed on D:.

Validation covered exact input/output, removal of capabilities, writable and read-only
access, a nested-namespace remount attempt, hidden host paths, symlink escape attempts,
blocked network, fresh home/temp storage, environment injection, candidate identity,
hard links, output flooding, cancellation, timeouts, memory exhaustion, process limits,
the real native Claude version command, and real Windows-executable denial.

The final native suite passed 28 checks and skipped one socket case: the D: filesystem
refused to create a Unix socket before the executor could inspect it. That specific
entry-type check remains without a native socket witness on this filesystem. Separate
tests passed controller death, service deadline expiry, and refusal of a service with
incomplete process cleanup. In both death tests, detached children disappeared and
their delayed writes did not occur.

Some earlier runs found ordinary Windows interop missing before the executor started.
Those runs did not count as Windows-denial evidence. A later run had working ordinary
interop before and after, while the same Windows executable failed with `ENOEXEC`
inside the sandbox. The cause of the intermittent outside-sandbox failure is unresolved;
future native admission must establish a working baseline rather than assume one.

Still required before an unattended Claude job: authentication that preserves the
existing Windows login, restricted provider access, host transport and admission,
actual model tool checks, and complete worker/check/reviewer completion evidence.
Independent review and normal in-app/CLI installation remain separate unfinished work.
