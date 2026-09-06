# Native Windows development loop

This is an opt-in development baseline for owner-selected code, named
`native-development-v1`. It does not claim credential isolation or containment of
hostile repositories. Existing strict runtime admission remains unchanged.

`ClaudeDevelopmentRuntime` runs tools-disabled Claude with structured output.
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
- CLI fixture operation is established. In-window launch, packaging, installed
  runtime promotion, other vendor adapters and automatic outward finish actions
  remain outside this slice.

The implementation is consolidated into the existing vendor-agnostic enforcement
worktree alongside its earlier process/job fixes. Those pre-existing edits were
preserved byte-for-byte. The task evidence directory retains source backups,
native receipts and the committed demo before the redundant worktree is removed.
