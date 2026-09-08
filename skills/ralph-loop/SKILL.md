---
name: ralph-loop
description: >-
  Prepare, launch and monitor an Excubitor Ralph coding job when the user asks to
  Ralph a task, run an autonomous loop, green a suite, or work through a checklist
  or telos. Uses the installed launcher for bounded helpers, frozen checks, fresh
  review and retained changes. Ordinary coding requests do not start a loop.
allowed-tools: [Read, Grep, Glob, Bash, Edit, Write, Skill]
metadata:
  version: 0.6.0
---

# Ralph through the Excubitor launcher

You are the job's coordinator. Use terminal tools to prepare and start Excubitor;
its controller advances all agreed units. Keep the user's project, goal, model,
checks and limits intact. Do not perform each iteration yourself or nest this
launcher inside a repeatedly scheduled `/loop`.

## Establish the job

- Locate the installed `excubitor` executable or the user's explicit environment.
  Check `excubitor ralph --help` and the relevant subcommand help. If unavailable
  or incompatible, report the missing installation; do not silently substitute
  the legacy hook recipe or an arbitrary package from an index.
- Reuse a suitable saved profile and the user's existing decisions. Otherwise
  inspect the project and propose concrete editable files, committed acceptance
  checks, model/provider, attempt/time limits and helper count. A request to run
  Ralph authorizes preparation and model planning within its stated scope.
  Ask only for consequential missing decisions. Planning consumes model usage;
  honor a stated usage cap and do not guess that an unavailable model is usable.
- Require a clean committed project and an external job directory. Preserve dirty
  work; do not stash, discard or commit it just to satisfy setup. A separately
  approved clean checkout may be used. Select the existing retention command when
  the project requires a broker; a broker refusal has no direct-Git fallback.
- Convert the requested anchor into an explicit goal and meaningful frozen checks:
  failing tests define a suite goal; unchecked checklist items define work scope;
  telos claims define intended behavior and their witnesses. Read the relevant
  source from disk. Self-checked boxes and model judgment are not acceptance tests.
  If useful acceptance tests are missing, prepare them as reviewable ordinary work
  before creating the job. Keep checks and their dependencies outside editable
  selection. Do not self-discharge a telos claim merely because the job finishes.

The current adapter allows up to 32 existing editable UTF-8 files, 64 KiB each.
It excludes symlinks, submodules and generated/untracked candidate artifacts.
If the task exceeds those limits, surface the mismatch and propose bounded jobs;
do not silently drop requested work. Trusted local execution is not a filesystem,
network or credential sandbox. Use it only for a trusted project with that posture
accepted. Windows and Linux have native implementations; native macOS remains
unverified in this development candidate.

## Prepare and launch once

Use actual absolute paths and literal argument arrays. The example paths and model
below are illustrative; substitute the user's project and available model. On
Windows select a native executable; implicit `.cmd`/`.bat` wrappers are refused.
Quote JSON for the current shell, or pass literal argv through its process API.
Do not interpolate untrusted goal text into a shell command.

```text
excubitor ralph init --project /work/project --output /work/jobs/profile.json --llm claude-cli --model YOUR_MODEL --editable 'main.py' --check-file 'tests/acceptance.py' --check-argv '["python","-I","-B","{checks}/tests/acceptance.py","{candidate}"]' --max-attempts 12 --time-limit-seconds 3600 --max-subagents 2
excubitor ralph doctor --profile /work/jobs/profile.json --project /work/project --root /work/jobs/my-fix
excubitor ralph plan --profile /work/jobs/profile.json --project /work/project --root /work/jobs/my-fix --goal 'Implement the agreed behavior'
```

Skip `init` when reusing an appropriate profile. Choose `claude-cli`, `codex-cli`,
`command-json` or `chat-completions` according to the user's setup; inspect `init
--help` for provider-specific arguments. Existing authentication stays with the
client. Profiles contain environment-variable names for HTTP keys, never secrets.
The check must exercise `{candidate}` using the external frozen `{checks}` files.
Route test caches/output outside the candidate when required by the adapter.

Read the generated `preview.txt` and `job.json`. Explain the concrete scope,
checks, budget, helper limit, trusted execution and retention before launch.
Existing user approval suffices when this exact plan fits it; do not ask again
between units. If any consequential detail lacks authorization, present the
prepared plan and ask once before starting. A model-generated plan is not itself
owner approval. Do not edit saved agreements to expand their authority.

For a reviewed trusted-local plan:

```text
excubitor ralph start --plan /work/jobs/my-fix --baseline trusted-local-v1 --background
excubitor ralph status --root /work/jobs/my-fix/run
```

Use the baseline actually required by the reviewed preview. Advanced profiles may
require another explicitly selected executor; do not switch executors to bypass
a refusal. Installing this skill does not start a job, register hooks, or require
loop environment variables. The launcher retains changes on its candidate branch;
merge, push, deployment and cleanup are outside its completion behavior.

## Helpers and monitoring

New profiles default to two bounded helpers; zero disables them and four is the
maximum. Legacy saved jobs without a helper setting keep them disabled. The main
worker may request independent helpers, and the controller runs them concurrently
through the chosen model adapter. They return analysis and proposed file contents.
One final worker combines the results, and only the host applies that proposal.
Helpers cannot execute commands, commit or recursively delegate. Their calls share
the job's deadline and attempt budget. Do not separately spawn unrestricted agents
to write into a running job.

Record the actual job/run path and check status after starting. A launch
acknowledgement or a model saying done is not completion. Monitor with reasonable
backoff and concise updates; do not relaunch when a tool call times out. If you
cannot remain attached, leave the user the exact run path and status command,
without promising future monitoring that is not available.

```text
excubitor ralph stop --root /work/jobs/my-fix/run
excubitor ralph status --root /work/jobs/my-fix/run
excubitor ralph resume --root /work/jobs/my-fix/run --background
```

Use `stop` for requested cancellation and wait for terminal status before treating
workers as stopped. Use `resume` only for a resumable interrupted job within its
original approval, attempts and deadline. Explicit cancellation, exhausted limits
and uncertain surviving workers are not permission to create a replacement run.
Preserve evidence and surface the blocker. Never mutate a live candidate, frozen
checks or saved settings to make a run pass.

Report the terminal result: completed behavior, checks and fresh review, retained
changes and any unresolved work. Completion requires the controller's successful
checks, review and retention verification. Report partial work honestly when a
limit or blocker ends the job. A review refusal belongs to the controller's bounded
repair cycle; helper agreement and a green test alone do not override it.
