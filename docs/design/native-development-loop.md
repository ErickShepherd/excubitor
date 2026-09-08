# Native Windows development loop

This is an opt-in development baseline for owner-selected code, named
`native-development-v1`. It does not claim credential isolation or containment of
hostile repositories. Existing strict runtime admission remains unchanged.

`DevelopmentRuntime` uses the selected structured model adapter (Claude or Codex).
The host supplies a bounded snapshot of the editable files and applies validated
replacement contents only to those files. A proposed literal command is routed
through `WindowsDevelopmentExecutor`, using the already provisioned Codex
elevated command API. There is no unrestricted fallback or new installation.

The existing supervisor retains the agreement and attempt/deadline limits,
checkpoints the candidate through its host-provided commit callback, runs frozen
acceptance with a read-only candidate, and requests fresh independent review.
The model cannot complete the run by returning a success claim. The development
adapter adds no ordinary-task enforcement or native registration.

## What passed on Windows

The disposable median example started with a failing acceptance test. One native
Fable 5.1 work call returned an actual fix and a native test command. That command
passed, the host's frozen test passed, and a fresh native Fable 5.1 review approved
the supplied code. The supervisor persisted completion after one attempt, with
zero intermediate user interventions and a clean retained branch. The initiating
source and frozen check were unchanged. Calling the completed supervisor again
launched no new work.

Separate native checks denied a write outside the candidate and a write during
read-only verification. Cancellation stopped the running Python process and its
detached child, confirmed through their process handles; the outer job drained.
An ordinary command remained usable while a run was active, and another task in
the same initiating project had no Ralph activation. These are fixture results,
not installed GUI or exhaustive concurrency evidence.

The reviewer only inspected host-supplied source; it did not run tools or inspect
the whole repository. The host independently checked the actual retained bytes,
frozen check output, and unchanged initiating source. Both native model responses
identified `claude-fable-5-1` and advertised only `StructuredOutput`.

## Reproduce the code slice

From the consolidated development checkout, invoke `python -B -m runtime.probes.claude_development`
with `--baseline native-development-v1` and explicit `--root`, `--codex`,
`--codex-home`, and `--claude` paths. The output root must be a fresh D: directory
for this owner's task. Use the existing native account state and direct temporary
storage to D: before invoking the command. The fixture creates its own local Git
repository and branch; it does not commit the development repository or install
runtime integrations. Its work and review model is explicitly Fable 5.1, with
three supervisor attempts and a twelve-minute run deadline.

## Start, status, and stop from the CLI

The existing CLI now exposes `ralph start`, `ralph status`, and `ralph stop`.
Start is foreground unless `--background` is selected. Another
terminal can inspect or cancel the same run. Ctrl+C also requests cancellation;
the supervisor records cancellation only after the active worker has drained.

```text
python -B -m excubitor.cli ralph start --job D:/jobs/statistics.json --root D:/runs/statistics --baseline native-development-v1
python -B -m excubitor.cli ralph status --root D:/runs/statistics
python -B -m excubitor.cli ralph stop --root D:/runs/statistics
```

The job is an owner-reviewed JSON object with exactly these fields:

| Fields | Meaning |
| --- | --- |
| `origin`, `candidate`, `metadata`, `branch`, `git` | Existing absolute original/candidate/metadata/Git paths and the full isolated branch ref. The candidate must be clean, with external Git metadata and a separate `main` base branch. |
| `llm`, `executor` | Independently selected model and command adapters. Both are saved with the agreement. Legacy flat Claude settings remain readable. |
| `editable` | List of existing candidate-relative UTF-8 files the job may edit. |
| `goal`, `units` | Agreed work and its ordered, unique work units. |
| `checks` | Output oracles with `name`, literal `argv`, `stdin` (currently empty), and expected `stdout`; optional `stderr`, `exit_code`, and `timeout_seconds`. |
| `check_files` | Absolute external acceptance implementation files. Original bytes are fingerprinted and checked before each attempt. List all relevant files; dependencies are not discovered automatically. |
| `max_attempts`, `time_limit_seconds` | Original attempt budget and elapsed-time limit, including retries. |
| `retain_command` | Literal argv for the host's authorized committer. It receives JSON on stdin containing `candidate`, changed `paths`, and `run_id`. It must retain exactly that candidate through the appropriate broker and return zero only on success. |

The prepared-job form requires a host-prepared candidate and committer. `ralph plan`
can now prepare the candidate and job from a plain goal and reusable profile.
The CLI does not
enroll repositories or replace an existing broker. Its run directory must be
fresh and outside both workspaces. It saves the original job, acceptance
definitions, run state, and native execution receipts there. Status reports
progress and review state without starting another worker. A process crash leaves
interrupted work for reconciliation. The named-job watchdog now provides bounded
controller recovery and `ralph resume` reconnects after watchdog loss. The
[planning and recovery workflow](ralph-planning-and-recovery.md) describes those additions.

A native Fable 5.1 CLI rehearsal completed median and span implementations in two
units, then retried after a deliberately unavailable test dependency. The test
harness restored that dependency automatically after the first failed check;
neither the frozen check nor the production loop contained fault-injection logic.
The third attempt passed unchanged acceptance and a fresh review. There was one
owner start and no intermediate owner intervention. A second native run was
cancelled through `ralph stop`; its Claude process tree drained and status became
cancelled in under one second. Regression checks passed: 101 tests, including
two-unit retry, cancellation from another client, and changed-check rejection.

## Deliberate limits

- Only existing, host-selected UTF-8 files are editable through the structured
  interface: at most 32 files, each at most 64 KiB. No deletion or new directories.
- Work uses one edit/command batch per supervisor attempt. Failed commands/checks
  return feedback through existing retries. This is not a full interactive IDE
  tool loop.
- Commands use absolute executables and literal argv. This is a transport check,
  not an allowlist that makes the executed project code trustworthy.
- The coordinator has the existing vendor login. Project commands receive a
  reduced environment, but saved credential files may remain readable. No new
  read-denial rules are applied to shared user credentials.
- Windows command/exec rejects custom output caps. This adapter accepts only
  small buffered results and conservatively rejects output at least 4 KiB or
  containing a truncation notice. It does not support stdin or claim arbitrary
  binary-output fidelity. Native startup consumes the same deadline as work.
- Ordinary descendant shutdown was measured. No promise is made for arbitrary
  external services or brokers starting processes outside the observed job.
- The prepared-job CLI is exercised with disposable repositories. In-window launch, packaging, installed
  runtime promotion, adapters beyond Claude/Codex, and automatic outward finish
  actions remain outside this slice.

The implementation is consolidated into the existing vendor-agnostic enforcement
worktree alongside its earlier process/job fixes. Those pre-existing edits were
preserved byte-for-byte. The task evidence directory retains source backups,
native receipts and the committed demo. The redundant worktree was removed after
that preservation and verification.

## Interchangeable components

The planner and CLI now construct the shared runtime through host-selected adapter
descriptors. The model adapter returns structured proposals; the shared runtime
validates and applies edits, routes proposed commands to the executor, and requests
a fresh review. Claude and Codex use that same implementation. The supervisor,
agreement, frozen checks, budgets and watchdog remain shared.

See the [reusable profile example](ralph-planning-and-recovery.md) for selection.
The `codex-windows` executor still uses Codex's command API even when another
vendor supplies the model. A separately selected `windows-process` executor now
removes that dependency for trusted local projects. It requires the distinct
`trusted-local-v1` baseline and makes no filesystem/network isolation claim.
The default is never silently weakened when a sandboxed request fails.
