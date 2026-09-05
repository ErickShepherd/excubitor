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
