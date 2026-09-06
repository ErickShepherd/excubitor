# Native lifecycle experiment

This is disposable test apparatus for the Ralph-only remediation. It is not an
installed adapter, an activation mechanism, or a working Ralph runner. Production
configuration and policy code do not import it. Do not register it in a real project.

`native_lifecycle.py` observes Codex, Claude Code, and Antigravity event envelopes.
Each registration supplies the runtime, event, exact disposable project root, and
local SQLite evidence path. Observations contain field shapes, hashed identities,
and recognized test messages. They do not contain prompt text, command bodies,
file contents, or transcript paths. The script never reads transcripts, executes
subprocesses, contacts a network service, approves tools, or edits native settings.

Observation is the default. The explicit `--exercise` option currently supports
only Codex. After the exact synthetic start prompt in the script, it exercises a
veto against `probe-denied.txt` and asks for at most two automatic continuations.
The second continuation requests an allowed edit. The next Stop ends the exercise;
later ordinary requests in that task pass. Cancellation, session end, clock rollback,
or ten elapsed minutes end the experiment. Other tasks, projects, parent directories,
nested Git repositories, and separate worktrees receive no test decisions.

The SQLite database must be unique to a host/interface experiment. A session cannot
restart its exercise using the same database; this bounds repeated or duplicated
hook events. The database is writable apparatus. Synthetic input can start an
exercise, copied or edited data can change its state, and a failed process cannot
enforce anything. These are explicit limitations: the experiment establishes native
event delivery and response behavior, **not trusted owner intent or protected state**.
It does not establish crash recovery, worker containment, or secure expiry for Ralph.

Run the offline apparatus checks with Python 3.11 or newer:

```text
python -B runtime/tests/test_native_lifecycle_probe.py
```

Before a native run, review and authorize the exact project-local registration and
complete the host's native trust review. Keep observation output and native tool
results separate. An emitted veto plus a missing marker is only a native witness when
the host actually proposed and blocked that operation. Two emitted continuation
responses do not prove the host continued. Record native CLI and GUI results separately.
Neither outcome certifies production Ralph-only activation or unattended completion.

Current protocol references:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks): project trust, event identities,
  prompt submission, tool veto, Stop continuation, and interruption. Stop can create
  a synthetic user prompt; prompt text and a session identifier do not establish an
  independent owner-authorization channel. This last point is a design inference.
- [Claude Code hooks](https://code.claude.com/docs/en/hooks): separate native event
  contract. The observer does not enable a Claude continuation exercise.
- [Antigravity hooks](https://antigravity.google/docs/hooks): camelCase conversation
  fields, directly listed invocation/Stop handlers, and its different Stop response.
  The observer does not enable an Antigravity continuation exercise.

Cursor remains a prospective integration with no apparatus implementation here.

## Native interactive CLI result, September 5, 2026

The owner separately authorized the exact temporary Codex project hooks and native trust review.
Codex CLI 0.153.4 on Windows 11, using workspace-write sandboxing and on-request approvals, loaded
the nine project hooks. The configured model was gpt-6-astra xhigh. The native experiment observed:

- An ordinary apply_patch edit succeeded with hooks loaded but before the exercise started.
- The exact synthetic start triggered two automatic continuations, with no manual restart.
- The first continuation's apply_patch call received a native veto and left its marker absent.
- The second continuation created its allowed marker. The exercise then ended.
- A concurrent task in the same project created a matching test filename in a separate directory
  while the first task's exercise was active. Its event was observed without a veto.
- A later ordinary edit in the original task created the formerly denied marker successfully.
- Both CLI processes exited normally and produced SessionEnd observations. The exact unchanged
  temporary registration was removed. A fresh CLI showed zero installed/active hooks and performed
  another ordinary edit successfully.

The exercise lasted approximately 49 seconds. Its initial prompt, both continuations, and three
Stop events shared one native turn. Only the initial prompt produced UserPromptSubmit; later Stop
events set stop_hook_active to true. Do not assume Stop creates a fresh task, fresh context, or a
second owner authorization event. The observed prompt envelope supplied no independent owner-origin
field; this experiment does not establish that native task identity alone is protected authority.

Codex retained project trust and nine fixture-specific hook trust records. The native hook menu
offered enable/disable controls, with no forget-trust action observed. No trust file was manually
rewritten. The leftover trust records had no loaded hook source in the fresh CLI. An empty fixture
configuration directory remains. The initially combined cleanup command was rejected by command
policy; a narrower removal of the reverified exact file succeeded.

These are native apparatus results for interactive CLI and apply_patch. They do not certify
production Ralph activation, protected completion checks, cancellation/crash recovery, lingering
workers, fail-closed faults, GUI/headless behavior, or another vendor. The original adapter's
always-active baseline is still unsuitable for reinstallation.

## Protected lifecycle storage experiment

`protected_runs.py` provisions a dummy run through the real shared library, then attempts unauthorized
lifecycle and acceptance mutations through Codex's native sandbox. It creates only the selected
evidence directory, installs no hooks, and grants no native trust.

Supply absolute paths to the installed executables and a new evidence folder:

```text
python -B runtime/probes/protected_runs.py --codex ABSOLUTE_CODEX --python ABSOLUTE_PYTHON --output NEW_FOLDER
```

The tested Windows CLI accepts `codex sandbox -P :workspace -C PROJECT -- COMMAND`. Do not insert a
`windows` subcommand: this CLI would try to execute a program by that name. The report binds source
bytes, records runtime and observations, and preserves failed results. A passing test closes its dummy
run after subprocess exit. Preserve incomplete fixtures for review; no hook is attached to the run.

The [implementation notes](../../docs/design/protected-ralph-lifecycle.md) explain the result and gaps.
Dummy candidate facts are not an independently verified branch, and the subprocess boundary does not
cover every tool in a coding app.

## Native confirmation, output checks, and session reconciliation

`native_start.py` observes the native MCP form and its metadata. `native_start_record.py` connects the
same form to the shared start handshake using a fixed disposable contract and protected store. Neither
launches a worker or installs a hook. Use process-only CLI MCP overrides and the already authorized
disposable project; registration and native trust must not be inferred from these scripts being present.
Both scripts require `--output` with an absolute create-only JSONL log path. The record experiment also
creates a sibling `.authority` directory. Native metadata stays in local evidence, not repository docs.

The CLI test observed a cancelled form producing no run and a confirmed form creating exactly the native
task/project record. No identity environment variable was present; context came in the host's MCP metadata
outside tool arguments. The native client advertised form and URL elicitation. The parser intentionally
handles only the observed Windows CLI shape and does not authenticate arbitrary copies of that JSON.

`native_output.py --codex ABSOLUTE_CODEX --python ABSOLUTE_PYTHON --output NEW_FOLDER` runs five known,
finite programs in the native read-only sandbox. Incorrect output, a forged test summary, and an early
zero exit fail one unchanged oracle. Correct output and a denied oracle-overwrite attempt preserve the
expected result. Review remains required. This fixture's Git identity is deliberately dummy; its simple
subprocess wrapper must not be reused as a general untrusted-code executor or worker-drain proof.

CLI exit terminated the record observer before its cleanup handler ran. Its record correctly remained
active; explicit host cleanup of that worker-free fixture followed process-exit checks. The new
`native_session_end.py` accepts only a SessionEnd envelope for its configured exact project and stores
interruption, retaining protection and making no worker-drain or completion claim. Repeated events are
idempotent and other tasks remain inactive in the offline tests.

After separate owner approval of an exact frozen one-hook candidate, Codex CLI 0.153.4 on Windows 11
delivered SessionEnd into this binding. Cancelling the native form created no record; confirming it
created the exact scoped dummy record. Normal CLI exit changed that record to interrupted and retained
its protection state, without claiming completion or worker drainage. A different ordinary task edited
a file and exited with an inactive observation. Codex clamped the requested ten-second timeout to three
seconds; both hook observations completed. Keep shutdown work short and never treat hook delivery as
proof that child workers have stopped.

All test CLIs exited. The exact unchanged registration was removed, a fresh CLI showed zero installed
or active hooks, and the trusted parent closed the worker-free dummy record after preserving its native
state. Native trust updated the existing fixture SessionEnd entry, which remains; the rest of the parsed
configuration was unchanged. No trust file was manually rewritten. This is a normal interactive CLI
exit witness only. Forced termination, crashes, resumption, worker supervision, GUI, and other hosts
remain unverified. New registration and trust changes still require their own exact authorization.

## Real supervised CLI job

`supervised_job.py` connects the shared supervisor to actual Codex CLI workers, protected output
oracles, Git inspection, and a separate reviewer. It implements a small stdin arithmetic program in
two units, deliberately commits a wrong doubling function, and lets the next worker repair it after
the unchanged checks fail. The final native run took three worker attempts and thirteen supervised
process calls. All four original checks and an independent review passed. The reviewer also executed
ten additional cases. The resulting isolated branch and its base were retained, and the run ended inactive.

This is test apparatus with a trusted owner-authorized parent, not the production Ralph command.
It requires absolute `--codex`, `--python`, `--git`, `--native-config`, `--output`, and
`--reuse-completed` paths. The last argument identifies a previously completed disposable experiment
whose project is already natively trusted. The driver checks its retained commit and clean state,
creates a new branch, and preserves the previous branch. Output must be a new directory. Do not point
this fixture-only driver at a development checkout. Its direct Git writes are confined to the disposable
fixture; production commits must use the authorized broker.

On the tested Windows CLI, omitting `windows.sandbox` from isolated configuration caused policy to
refuse worker file operations. The driver preserves the owner's already provisioned sandbox implementation
and model settings while leaving execpolicy rules enabled. It stops on a native policy denial. The native
CLI also saved project trust automatically for a fresh writable fixture despite `--ignore-user-config`.
That observed trust entry remains. The driver now refuses fresh projects; the final reused-project run
left native configuration byte-identical. No hook registration or manual trust-file rewrite occurred.

The Windows process backend is not itself a filesystem or network sandbox. It accounts for processes
in its job; native services outside the tree require separate admission. This benign CLI example does
not certify arbitrary native tools, production owner authentication, GUI launching, another vendor,
automatic crash recovery, or optional merging. The earlier failed reports remain evidence.

Implementation references: [native CLI execution](https://learn.chatgpt.com/docs/non-interactive-mode),
[Windows sandbox configuration](https://learn.chatgpt.com/docs/config-file/config-basic),
[Windows job lifetime](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects), and
[explicit inherited handles](https://learn.microsoft.com/en-us/windows/win32/procthread/creating-processes).

## Native confirmed supervised job

`native_supervised_start.py` connects the shared native Start action to the shared watchdog and the
real CLI-worker demonstration. `prepare` accepts the same absolute executable/config/output paths
as the earlier driver and a passing `--reuse-completed` packet. It resolves that packet's actual
project, verifies its committed candidate, and prepares a fresh isolated branch in the already trusted
disposable fixture. Preparation creates no active run. Existing branches and evidence remain intact.
The initial fixture uses its original demo branch as the protected base; newer packets record the
base explicitly, so successive demonstrations can reuse their real project location.

`serve --packet ABSOLUTE_PACKET` exposes `ralph_start` and `ralph_status` through a process-only MCP
configuration for the disposable native CLI. Native tool permission and the exact job confirmation
are separate host interactions. Use a one-call tool allowance for this test; do not save a permanent
allowance. The confirmed job runs in a background host thread so the Start tool returns promptly.
Keep the native CLI open while the test runs. This script is not a plugin installer or a universal
slash command, and no project/user hook is created.

The first actual worker drains, then the test abruptly terminates its controller while a descendant
is still alive. The watchdog must kill that descendant, preserve the interrupted journal, and resume
the same contract without extending its limits. The restarted workers also encounter the earlier
deliberate arithmetic fault, which must fail the original checks and be repaired before review.
The packet retains raw native confirmation messages, separate controller outputs, watchdog receipts,
the crash archive, and the final candidate report. A handled native denial stops the experiment.

This fixture exercises native CLI confirmation and bounded controller recovery. It does not certify
all native writable tools, production owner authentication, GUI behavior, app-exit survival, another
vendor, or recovery after losing the watchdog. Production adapters do not import this apparatus.

The first connected run completed its work, checks, and review in four attempts. Its final reporter
failed when a Git launcher timed out but left a child holding captured pipes. Preserve that failed
report rather than relabeling it successful. After Windows Git inspection was moved into the bounded
process-tree runner, a separate native MCP read verified the original run and candidate with clean
drainage and unchanged native configuration. A whole-job completion and a successful reporter are
separate observations; the retained evidence records both the failure and the successful recheck.

## Native process-job access and task persistence

`named_job_access.py --codex ABSOLUTE_CODEX --python ABSOLUTE_PYTHON --output NEW_FOLDER`
tests the unelevated Windows sandbox without model work. The host creates one exact private job and
an external acceptance file. The native child writes an ordinary project file, attempts to change
the acceptance file, and attempts query, terminate, assignment, DACL, and owner access to the job.
It only opens and closes handles; it never changes the kernel object's permissions or terminates it.
A nonexistent random object is a control for distinguishing absence from access denial.

Codex CLI 0.153.4 on Windows denied all requested mutation access and preserved the acceptance file,
but allowed a query handle. The report correctly fails and exits nonzero. Even a query handle can
retain a job's lifetime, so this mode cannot be admitted for recovery based on last-handle closure.
Do not weaken that condition to turn the report green. The current approval parser already rejects
unelevated mode. This probe does not provision or test the elevated Windows sandbox.

The private `native_reconnect.py` experiment uses the installed app-server protocol and a read-only
MCP observer with process-only registration. The commit broker classified its synthetic protocol
message as a conversation record and required private retention. The complete probe and its tests
remain in local task storage; they are not shipped in this repository. The observations below are
retained findings, not instructions to reconstruct or enroll a native fixture automatically.
Use only an owner-approved disposable profile containing its one exact existing project trust entry
and no credentials or other saved settings. The driver refuses missing trust, parent/sibling trust,
and general-purpose profiles before starting Codex. It preserves and compares native config after
each lifetime and stops on drift. Existing trust alone is not owner authorization for the experiment.
It creates a native task, injects explicitly labelled fixture text through the native history API,
observes tool metadata, terminates the disposable server, drains its process tree, then resumes the
same task in a new server lifetime. A second task in the same project checks identity separation.
The seed provides persistence; it is never an owner approval, model response, or acceptance result.
An earlier empty-task experiment had no saved rollout and could not resume; preserve failed packets.

On the tested CLI, task identity and project survived resumption, and the other task kept a distinct
identity. Direct tool calls supplied a task ID and progress token without the active-turn context
needed by the approval parser; all were rejected. The final state comparison caught native automatic
project-trust writes in each formerly fresh isolated profile. Those failed packets and trust entries
remain for review. Earlier phase-success flags describe only RPC completion. The new preflight refusal
is tested offline; the changed driver has not been rerun against a newly approved native fixture.
An identity report explicitly leaves
`ralph_reconnect_verified` false. It does not prove native confirmation, autonomous continuation,
protected-store recovery, GUI support, or authentic identity on an arbitrary client connection.

The access probe creates a fresh native home and temporary directory inside the output folder. The
reconnect probe now requires a pre-existing, separately approved fixture home and uses a fresh output
and temporary directory. Both set native state locations only in child environments, use no
credentials, and install no hooks. Their reports stay private because they contain local paths and native metadata.
All child processes are bounded by the Windows tree runner. Native app-server startup can make
unauthenticated background catalog requests; this is not a claim of a network-isolated host process.
New native setup, registration, and trust still need their own authority.

References: [native app-server protocol](https://learn.chatgpt.com/docs/app-server),
[native state locations](https://learn.chatgpt.com/docs/config-file/environment-variables),
[Windows sandbox implementations](https://learn.chatgpt.com/docs/windows/windows-sandbox), and
[Windows job lifetime](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
