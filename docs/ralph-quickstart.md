# Start a bounded Ralph coding job

Ralph works through an agreed goal on a separate checkout. The host runs your
original checks, asks a fresh model call to review the candidate, and retains
checked work on its own branch. One start advances all planned units. A model
saying “done” never completes the job by itself.

[Install the CLI](install.md) first. You need Git, a clean project with committed
acceptance tests, and a working model client or HTTP endpoint. Choose a model your
account or server actually provides. Setup and doctor make no model calls. Their
read-only Git queries respect your normal Git configuration, including line-ending
settings. Configured Git filters and helpers are trusted code and may run during
these queries; optional index writes and filesystem-monitor helpers are disabled.

## Create project settings

Suppose your project has `main.py` and a committed `tests/acceptance.py`. This small
acceptance script checks the candidate explicitly, keeping imports away from the
original checkout:

```python
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("candidate_main", Path(sys.argv[1]) / "main.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.add(2, 3) == 5
assert module.add(-2, 2) == 0
```

For your actual job, use tests that establish its agreed behavior. Tests should
fail for the missing behavior and pass for correct behavior. Setup cannot decide
what counts as success for you. Keep tests and the files they depend on outside
the editable selection.

Create a jobs directory outside the project. The examples below use `/work/project`
and `/work/jobs`; on Windows replace them with paths such as `C:/work/project` and
`C:/work/jobs`. Use absolute paths for project, profile and job storage in these
commands. Single-quoted JSON arguments work in PowerShell and POSIX shells.

```text
excubitor ralph init --project /work/project --output /work/jobs/profile.json --llm claude-cli --model YOUR_MODEL --editable 'main.py' --check-file 'tests/acceptance.py' --check-argv '["python","-I","-B","{checks}/tests/acceptance.py","{candidate}"]'
```

`init` finds Git, Python and the selected client on PATH and saves their absolute
paths. Use `python3` in the check JSON when that is your installed Python command,
or name the project environment's interpreter. Use `--executable` to select a
client outside PATH. Windows batch wrappers (`.cmd` and `.bat`) are refused because
they interpret shell syntax; select the native `.exe`, or use a command bridge
with an explicit interpreter and script arguments. It does not overwrite a
profile or modify the original.

Use repeated `--editable` and `--check-file` globs to select groups of tracked
files, and repeated `--check-argv` arguments for multiple checks. Quote globs so
Excubitor, rather than the shell, expands them. It previews concrete file lists in
the profile. This bounded adapter accepts at most 32 existing editable UTF-8 files,
64 KiB each. Frozen check files may be up to one MiB each. Redirected paths,
hard-linked editable files and hidden editable paths are rejected. Candidate
repositories currently exclude symlinks, submodules and generated/untracked files;
run trusted checks with bytecode/cache output disabled or routed outside the
candidate. These are current limits, not promises of arbitrary-repository support.

Checks created by `init` use the real process exit code: zero passes, with bounded
execution and output. Timing and ordinary test-runner output may vary. Legacy
`profile-template` profiles can instead compare exact stdout/stderr bytes. Either
mode is frozen into the agreement; an implementation cannot change the mode to
make a failing run pass. Each check command must reference `{checks}`, the external
frozen test copy, and must actually exercise `{candidate}`, the separate checkout.
Argument arrays are literal; there is no shell expansion.

Defaults allow 12 attempts and one hour; use `--max-attempts`,
`--time-limit-seconds` and `--check-timeout` to set your budget. Retries consume
those same limits. Review the generated JSON before planning.

Normal Git retention uses your configured author, signing and hook policy and
commits only admitted candidate changes. It never merges or pushes. Existing hooks are trusted code; their side effects remain part of your Git policy. If your
organization requires a separate committer, pass `--retain-command` as a literal
JSON argument array. That command receives `candidate`, `paths` and `run_id` on
stdin; the host subsequently verifies retained candidate state. A refusal stops
retention; it never switches to ordinary Git as a fallback. No host-specific
broker is required for ordinary third-party installation.

## Use bounded sub-agents

New profiles allow up to two helpers per work attempt. Set `--max-subagents 0`
during `init` to disable helpers, or choose a limit from zero through four. The
profile and proposed plan show this limit before starting. Existing saved jobs
and profiles without this setting keep helpers disabled; resuming cannot increase
an agreed limit.

The main worker decides whether an independent subtask would benefit from a fresh
helper. Simple work can proceed in one model call. For delegation, it assigns
bounded, non-overlapping editable-file scopes. Ralph runs the helpers concurrently
through the selected model adapter, then gives their proposals to one fresh main
worker to combine. Helpers return analysis and suggested file contents; they do
not receive command, recursive delegation or commit authority. Only the host
applies the main worker's final proposal.

A delegating attempt uses at most the helper limit plus two model calls: the
initial request, the helpers and the final combination. Those calls share the
original deadline, and failed helper work consumes the same work-attempt budget.
Helpers can therefore increase model usage; they never replenish the job's limits.
Failure or cancellation stops sibling calls and requires their processes to finish
before another writer runs. Unexpected candidate changes stop the run.

Frozen checks, fresh final review and the chosen retainer remain required.
Helper agreement is not acceptance evidence. This mechanism is shared across the
model adapters; it does not enable unrestricted provider-native agent tools.

## Choose another model

The loop and executor stay the same when you choose another transport:

| Model selection | Additional setup |
| --- | --- |
| `--llm claude-cli` | Existing Claude CLI and login; `--executable` if needed |
| `--llm codex-cli` | Existing Codex CLI and login; optional `--codex-home` |
| `--llm command-json` | `--model-command` with a trusted executable's literal JSON argv |
| `--llm chat-completions` | Full `--endpoint` route and `--api-key-env` variable name |

For HTTP, use the full compatible route such as
`http://127.0.0.1:8000/v1/chat/completions`. Remote endpoints require HTTPS. URLs
cannot contain credentials, query parameters or fragments. Keep keys in the
launching environment; only their variable name belongs in a profile. For a local
server without authentication, pass an empty `--api-key-env ''`. Select
`--response-format json_object` if the server cannot accept JSON Schema requests.
Doctor checks local setup; authentication and provider compatibility require a
real call. No provider SDK is required by the HTTP bridge.

A command bridge reads a fresh JSON request from stdin:

```json
{"protocol":"excubitor.model.v1","id":"REQUEST_ID","model":"YOUR_MODEL","prompt":"CURRENT_PROMPT","schema":{"type":"object"}}
```

It returns one JSON object and exits zero:

```json
{"protocol":"excubitor.model.v1","id":"REQUEST_ID","model":"YOUR_MODEL","output":{"goal":"Example plan","units":["Example work unit"]}}
```

Echo protocol, ID and model exactly. `output` must satisfy the supplied schema;
the example is a plan response, not a work or review response. Send diagnostics
to stderr, keep credentials out of arguments/output, and use absolute script
paths because each call runs from a fresh evidence directory. The host validates
the response and owns completion. Malformed work/review replies can be retried
within the original limits; identity mismatch and host refusal remain errors.

## Check, plan and start

```text
excubitor ralph doctor --profile /work/jobs/profile.json --project /work/project --root /work/jobs/my-fix
excubitor ralph plan --profile /work/jobs/profile.json --project /work/project --root /work/jobs/my-fix --goal 'Make add return the sum for positive and negative integers.'
```

Read `preview.txt` and `job.json` in the planning directory. They record the
original goal, proposed units, selected files/checks/model/executor, limits and
committer. Planning calls a model and prepares a candidate and frozen tests, but
does not start implementation. Preserve a failed planning directory and use a
fresh directory for a revised plan. Do not hand-edit a saved agreement.

Once you agree to the plan:

```text
excubitor ralph start --plan /work/jobs/my-fix --baseline trusted-local-v1 --background
excubitor ralph status --root /work/jobs/my-fix/run
```

Omit `--background` to remain attached. Background output acknowledges launch;
status reports actual progress and completion. Work remains in
`/work/jobs/my-fix/candidate` for review. A completed job has passed frozen checks,
fresh review and retained-candidate verification. It does not publish anything.

`init` selects the host's trusted local processes. Advanced `profile-template`
profiles may select `windows-process`, `posix-process` or the Windows-only
`codex-windows` executor explicitly. The latter requires
`--baseline native-development-v1`; it is never a fallback for a refused local
or native command. Use the baseline in the reviewed preview.

## Stop and recover

```text
excubitor ralph stop --root /work/jobs/my-fix/run
excubitor ralph status --root /work/jobs/my-fix/run
excubitor ralph resume --root /work/jobs/my-fix/run --background
```

Stop requests cancellation; wait for terminal status before treating workers as
drained. Resume reconnects to the same settings, attempts and deadline. It cannot
undo explicit cancellation or extend a limit. A model ending its reply does not
stop pending units. The controller carries original goals, current code and
compact failed-check/review feedback into fresh calls.

Trusted local execution has no filesystem, network or credential sandbox. Windows
uses Job Objects for process-tree lifetime. Linux and macOS use cooperative
process groups with a guardian; a process deliberately escaping its group is
outside that trusted contract. A surviving POSIX watchdog can recover from an
inner controller crash after group cleanup. If the POSIX outer watchdog is lost
with a pending launch, resume refuses uncertain ownership; a PID disappearing
is not proof that all old work stopped. Preserve that job and its evidence for
manual inspection. Windows retains its separately tested named-job recovery.
Stopping a local HTTP client cannot prove a remote server stopped inference.

Look in the run directory for controller errors, retention results, watchdog logs
and evidence. A successful test fixture or model reply cannot stand in for native
platform evidence. The current evidence matrix and remaining validation limits
are recorded in [portability validation](portability-validation.md).
