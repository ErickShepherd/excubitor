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
