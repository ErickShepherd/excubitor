# Start a bounded Ralph coding job

Ralph takes an agreed goal, works on a separate checkout, runs your frozen checks,
asks a fresh model call to review the result, and retains checked work through
your authorized committer. One start advances through the agreed work without
per-step restarts. It stops at checked completion, a concrete blocker, cancellation,
or the original limits. A model saying “done” does not complete the job.

This launcher is a native Windows development candidate. You need Python with
Excubitor importable, Git, a clean project with existing acceptance tests, and the
model and executor you choose below. Run the commands from the Excubitor source
checkout, or an environment where its package is installed. `python` means that
environment's Python; use its full executable path if necessary.

The PowerShell examples use `D:/jobs` for private storage and
`D:/Projects/my-project` for your project. Replace those example paths with your
own. Create `D:/jobs` once if it does not exist. Each planning directory must be
new and outside your original repository. No hook installation, global settings
change, launch wrapper or loop environment variable is needed for these commands.

## Create and fill in a profile

Choose a model transport and a test executor separately:

| Choice | What it uses |
| --- | --- |
| `claude-cli` | Your existing Claude executable and native login |
| `codex-cli` | Your existing Codex executable, home directory and login |
| `chat-completions` | A compatible HTTP endpoint, including a local server |
| `command-json` | Your own trusted executable that exchanges JSON with Ralph |
| `codex-windows` executor | Codex's Windows execution backend; requires `native-development-v1` at start |
| `windows-process` executor | Trusted local Windows processes; requires `trusted-local-v1` at start |

The trusted local executor manages process lifetimes and cancellation. It has
**no filesystem or network sandbox**: commands run with your account's access.
Choose it only for trusted local work. It is never selected automatically after
a native executor refuses work. Model clients and custom bridges are trusted host
integrations, too. This launcher does not establish credential isolation.

For example, generate a Claude profile with the Codex Windows executor:

```powershell
python -B -m excubitor.cli ralph profile-template --llm claude-cli --executor codex-windows --output D:/jobs/project-profile.json
```

The command creates only that file and refuses to overwrite an existing file.
It does not inspect or copy logins or keys. Edit the JSON and replace every
`REPLACE` value. The template includes all required fields:

- Set `git`, model/executor `executable`, and check-command executables to existing
  absolute paths. Set `home` to your existing Codex home wherever present. Select
  a model available to your account or server; the template deliberately does
  not guess one. Optional `--model YOUR_MODEL_ID` fills the model field at creation.
- Set `editable` to the existing source files Ralph may change, using forward
  slashes relative to your project, such as `src/parser.py`. This development
  adapter accepts one to 32 existing UTF-8 files, each at most 64 KiB. Hidden
  paths, symlinks, reparse points and hard-linked editable files are rejected.
- Set `check_files` to existing project-relative acceptance scripts and any local
  helper/data files those scripts need. Each file must be UTF-8 and at most one
  MiB. Planning copies them to external storage before implementation starts.
- Set `checks` to literal argument arrays with exact expected stdout, stderr,
  exit code and a timeout of one to 300 seconds. `{checks}` expands to the frozen
  test directory; `{candidate}` expands to the separate checkout. Check commands
  must test the candidate rather than importing code from the original project.
  Empty `stdin` works with either executor; nonempty `stdin` requires trusted local
  execution. Output is compared byte for byte, including newlines.
- Set `max_attempts` and `time_limit_seconds`. The example allows eight attempts
  and 30 minutes. Retries consume the same budget; resume does not refill it.
- Set `retain_command` to your existing authorized committer's literal argument
  array. It receives one JSON object on stdin with `candidate`, `paths`, and
  `run_id`; it must commit only the admitted candidate paths and exit successfully
  after retaining them. Ensure your broker admits the planned candidate. The
  template does not enroll a checkout or provide a direct-Git bypass. A command
  that merely exits zero does not prove work was committed.

For a small Python project with `main.py` defining `add(a, b)`, an acceptance file
at `tests/acceptance.py` could contain:

```python
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("candidate_main", Path(sys.argv[1]) / "main.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.add(2, 3) == 5
assert module.add(-2, 2) == 0
sys.stdout.buffer.write(b"ok\n")
```

The generated check array already runs this layout using
`{checks}/tests/acceptance.py` and passes `{candidate}`. Replace its Python path.
Prepare and review acceptance tests before planning, retain them through your
normal authorized workflow, and keep the original clean. For your actual job,
write checks that prove its agreed behavior. Do not use this tiny example as
evidence for unrelated work or change the frozen checks just to make a run pass.

## Check setup without a model call

```powershell
python -B -m excubitor.cli ralph doctor --profile D:/jobs/project-profile.json --project D:/Projects/my-project --root D:/jobs/my-fix
```

Doctor reports missing executables/model settings/key variables, dirty originals,
invalid file paths, malformed checks and limits. It does not create the planning
directory, edit the original, invoke a model, run a test, or call the committer.
It uses read-only Git queries with index refresh writes disabled. Add `--json`
for structured output; exit zero means local setup checks passed, exit one means
fixes are needed. No key values are printed or copied.

A passing doctor result does not verify authentication, model availability,
endpoint compatibility, check behavior, bridge script arguments, executor access
or broker authorization. It does not grant permission to start. Resolve reported
problems without discarding dirty work. Then rerun it using a fresh planning path.

## Plan, review once, and start

```powershell
python -B -m excubitor.cli ralph plan --project D:/Projects/my-project --profile D:/jobs/project-profile.json --root D:/jobs/my-fix --goal 'Make add return the sum for positive and negative integers.'
Get-Content D:/jobs/my-fix/preview.txt
Get-Content D:/jobs/my-fix/job.json
```

Planning calls the selected model and prepares a separate candidate, frozen tests,
and a proposed set of steps. It does not start implementation or alter the original
checkout. Review the goal, work units, editable files, exact checks, selected model,
executor, resource limits and committer. Keep a failed planning directory for
diagnosis; use a new directory when preparing again. Do not hand-edit a prepared
agreement: update the source profile or goal and create a new plan instead.

After the owner has agreed to that plan, start with the baseline shown in its preview:

```powershell
python -B -m excubitor.cli ralph start --plan D:/jobs/my-fix --baseline native-development-v1 --background
python -B -m excubitor.cli ralph status --root D:/jobs/my-fix/run
```

For a profile explicitly choosing `windows-process`, the complete start command is:

```powershell
python -B -m excubitor.cli ralph start --plan D:/jobs/my-fix --baseline trusted-local-v1 --background
```

Use the one command matching the reviewed executor. Omit `--background` to stay
attached. Background launch prints a launch acknowledgement; inspect status for
the actual outcome. Work remains in `D:/jobs/my-fix/candidate` on its isolated
branch. Review it there when the run ends. Completion does not merge, push,
publish, deploy, or delete the original or candidate.

## Stop or reconnect

```powershell
python -B -m excubitor.cli ralph stop --root D:/jobs/my-fix/run
python -B -m excubitor.cli ralph status --root D:/jobs/my-fix/run
```

Stop requests cancellation; wait for terminal status before treating processes
as drained. A lost controller can be restarted automatically within the saved
limits. If the watchdog or machine was lost, reconnect to the same agreement:

```powershell
python -B -m excubitor.cli ralph resume --root D:/jobs/my-fix/run --background
```

Resume preserves saved settings, frozen checks, attempts and deadline. It does
not undo an explicit cancellation or extend an expired agreement. Look in the
run directory for `controller-error.json`, `retain-result.json`, watchdog logs,
and the `evidence` directory when a run is blocked. Preserve partial work and
report the actual blocker; model prose and self-checked boxes cannot replace
successful checks, review and retained candidate evidence.

## Use a local or hosted HTTP model

```powershell
python -B -m excubitor.cli ralph profile-template --llm chat-completions --executor windows-process --output D:/jobs/http-profile.json
```

Fill the same source, checks, limits and committer fields. For a local compatible
server, set `endpoint` to its full route, for example
`http://127.0.0.1:8000/v1/chat/completions`, `model` to its loaded model ID,
and `api_key_env` to `""` if that server needs no authentication. Remote endpoints
require HTTPS. URLs cannot contain credentials, query parameters or fragments.

For a hosted endpoint, `api_key_env` names an already provisioned environment
variable, such as `RALPH_MODEL_API_KEY`; put the **variable name**, never its secret
value, in the profile. The launching process must inherit that variable. Choose
`response_format: "json_schema"` if supported, otherwise `"json_object"` for a
compatible JSON-object server. The server must return one complete text response
containing a JSON object, without tool calls or refusal. Availability and
compatibility are established by an actual plan/run, not by doctor.

Use doctor and plan with `--profile D:/jobs/http-profile.json` and a fresh root,
then review and start with `--baseline trusted-local-v1` as above. Each call starts
with the current prompt and schema; no provider SDK is needed by the built-in bridge.

## Use your own model bridge

```powershell
python -B -m excubitor.cli ralph profile-template --llm command-json --executor windows-process --output D:/jobs/bridge-profile.json
```

Replace `llm.command` with an existing absolute executable and literal arguments,
for example `["D:/Tools/Python/python.exe", "-I", "-B", "D:/Tools/my_model_bridge.py"]`.
Use absolute script/config paths: each call runs in a fresh evidence directory.
Ralph does not expand shell strings. Provision client credentials separately;
do not place secrets in command arguments or the profile.

Your trusted client reads one JSON request from stdin:

```json
{"protocol":"excubitor.model.v1","id":"REQUEST_ID","model":"YOUR_MODEL_ID","prompt":"CURRENT_PROMPT","schema":{"type":"object"}}
```

It starts a fresh model conversation using the supplied prompt and schema, then
writes exactly one response object to stdout and exits zero:

```json
{"protocol":"excubitor.model.v1","id":"REQUEST_ID","model":"YOUR_MODEL_ID","output":{"goal":"Example plan","units":["Example work unit"]}}
```

Echo the request's protocol, ID and model exactly. `output` must be the JSON object
for the **supplied** schema; the plan example above is not a valid work or review
response. Send diagnostics to stderr and do not print credentials. The host bounds
call duration, output and process lifetime, rejects mismatched/incomplete responses,
and independently checks candidate results. A custom client controls a model
transport, not the loop's completion decision. Fill the remaining profile fields,
run doctor, prepare a fresh plan, review it, and start with the chosen executor's
baseline. Legacy Claude profiles and prepared `start --job` workflows still work.

Malformed work or review replies receive bounded feedback and another fresh call
within the original attempt and time limits. Identity mismatches and host refusals
remain errors. A saved stop request is observed before recovery starts. Stopping
the local HTTP client drains its process; it cannot prove that a remote provider
has stopped inference.
