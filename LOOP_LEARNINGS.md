# Loop learnings

Append-only observations from vendor-agnostic enforcement iterations.

## 2026-09-02 — Native Codex adapter

- Current Codex `PreToolUse` sends both Bash and `apply_patch` text in `tool_input.command`; a pass is
  exit zero with empty stdout, while a deny uses `hookSpecificOutput.permissionDecision = "deny"`.
- `apply_patch` needs adapter-level target enumeration because one native call can add, update, delete,
  and move several files. Unknown action headers and incomplete boundaries are safer to deny than to
  normalize into an empty target set.
- The existing neutral config resolver already gives the desired precedence: `EXCUBITOR_LOOP_GUARD`
  first, with `CLAUDE_LOOP_GUARD` retained as a documented legacy alias.
- Windows fixture substitution must replace placeholders inside parsed values. Replacing placeholders
  in serialized JSON inserts unescaped backslashes and breaks otherwise-valid tests.
- Native adapter tests prove translation and shared-core decisions, not live host coverage. Codex
  registration, trust, telemetry, MCP mutation profiles, and a harmless real-host denial probe remain
  separate gates.

## 2026-09-02 — Broker enrollment

- The machine commit broker originally accepted only repositories with a `.git` directory. Linked
  worktrees need explicit pins for the `.git` pointer, administrative directory, common config, and
  branch; accepting a `.git` file without those bindings would weaken repository identity.
- A new enrollment can inherit full-tree publication findings that are unrelated to the requested
  paths. Grandfathering is safe only when it binds the exact rule, path, and staged blob digest and
  refuses any requested or changed path.
- The broker resets a pre-existing staged index after a post-staging refusal. Once that happened, the
  one-time recovery pin was no longer needed; the next admitted attempt could use normal broker-owned
  staging.

## 2026-09-02 — Codex registration and trust

- Codex user and project registrations both live in `hooks.json`; project hooks additionally depend
  on the project configuration layer being trusted. Unmanaged hook trust is bound to the exact current
  definition, so installation must hand off to `/hooks` and remain `needs-trust` rather than claiming
  that a written file is active.
- Registering `python -m excubitor.adapters.codex` through the validated interpreter and pinned package
  import path avoids a second adapter copy. The active command therefore depends on the same package
  root the adapter already supplies to self-integrity, while `.codex/hooks.json` and `config.toml`
  remain the native registration kill switches.
- A Codex install is a configuration-only transaction: it owns one exact hook tuple and no duplicate
  artifact files. The shared journal/receipt rollback still restores prior bytes exactly, and the plan
  must not create an unused `.codex/hooks` directory.

## 2026-09-02 — Live Codex enforcement witness

- Codex on Windows executes `commandWindows` through PowerShell. The portable `command` value used
  the existing Windows `cmd.exe` dialect and failed before the adapter ran, so registrations now own
  and validate the PowerShell override as part of their exact receipt tuple. Legacy receipts migrate
  without gaining ownership of a Windows override they did not record.
- In the Codex TUI, the trusted user hook allowed `git status --short` through `Bash` and executed it,
  then blocked an `apply_patch` marker attempt on the default branch without creating the marker. The
  checked-in observed fixture preserves the native fields with session paths and identifiers removed.
- The live support claim is deliberately narrow: Windows Codex TUI, user scope, `Bash` and
  `apply_patch`. `codex exec` did not dispatch the configured hook in this environment; MCP mutations,
  other specialized tools, project scope, and non-Windows hosts remain unverified.
- A local `protected` verdict must expire when behavior can change. The versioned witness therefore
  binds the exact receipt registration, the importable Excubitor implementation bytes, and the
  resolved Codex executable bytes; registration, policy, adapter, or host upgrades return the install
  to a review/probe state.
