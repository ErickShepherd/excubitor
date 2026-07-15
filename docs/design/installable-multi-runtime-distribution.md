# Installable multi-runtime distribution plan

**Date:** 2026-07-15
**Status:** proposed, not implemented
**Depends on:**
[`model-agnostic-runtime.md`](model-agnostic-runtime.md) and Phase 0 of the
the review notes

## Decision

Excubitor should be installed into **coding-agent runtimes**, not model providers. A Claude, GPT,
Gemini, or open-weight model does not execute Git or mutate a worktree by itself; the surrounding runtime
names tools, grants permissions, and dispatches calls. One runtime integration therefore covers every
model that can operate through that runtime.

Ship one versioned, model-blind policy engine and several thin native integration packages. A runtime is
advertised as enforcement-capable only after a real host smoke test proves that a harmless pre-tool probe
is denied before execution. Skills, prompts, configuration files, or an MCP server alone are not evidence
of enforcement.

The product position should be:

> **Installable safety policy for major coding agents, backed by runtime-independent workspace and
> repository controls.**

## Goals

1. Give individual users a single, reversible installation flow.
2. Give repository owners a reviewable project-scoped policy across supported runtimes.
3. Keep every policy decision in the shared core; native packages only translate and register it.
4. Prove native veto behavior, configuration integrity, upgrade safety, and uninstall safety per runtime.
5. Preserve the host's normal permission flow when Excubitor returns `pass`.
6. Work without a network or model API during enforcement.
7. State exactly which tools and invocation paths each integration covers.
8. Layer early denials with controls the agent cannot rewrite: sandbox permissions, remote branch
   protection, required CI, and restricted credentials.

## Non-goals

- Installing code into an LLM model or changing model weights, prompts, or provider behavior.
- Claiming that instructions or an Agent Skill are a security boundary.
- Claiming that MCP automatically intercepts a runtime's built-in shell or edit tools.
- Maintaining one monolithic installer that rewrites unknown vendor configuration heuristically.
- Calling a runtime supported because a configuration file exists but no veto was exercised.
- Replacing remote repository protections or an operating-system sandbox with a command parser.
- Guaranteeing equivalent workflow UX on hosts that lack scheduling, fresh-session, or human-surface
  capabilities.

## Support and claim levels

Keep installation, policy equivalence, and enforcement as separate claims.

| Level | Meaning | Public wording |
|---|---|---|
| 0 — unavailable | no maintained adapter | not supported |
| 1 — advisory | skill/instructions can be installed, but no pre-execution veto is proven | workflow guidance only |
| 2 — mediated | policy runs in an MCP server or custom dispatcher and every in-scope mutation is required to use it | enforced within the mediated boundary |
| 3 — native veto | a native pre-tool adapter passes fixtures, install tests, and a real harmless-denial smoke test | supported enforcement |
| 4 — managed | native veto plus administrator-controlled registration, sandbox policy, or remote authority the agent cannot rewrite | managed enforcement |

Never collapse these levels into one “compatible” badge. The support matrix must identify shell, direct
file tools, multi-file patches, subagents, cloud jobs, and self-integrity coverage independently.

## Initial runtime targets

The initial target set follows currently documented native packaging and hook surfaces:

| Runtime | Native package | Registration target | Initial goal |
|---|---|---|---|
| Claude Code | marketplace plugin | plugin `hooks/hooks.json` plus skills | Level 3; parity with the current installation |
| Codex | Codex plugin | bundled hooks, skills, and optional MCP configuration | Level 3; second conformance implementation |
| Gemini CLI | Gemini CLI extension | extension hooks, skills, and optional MCP configuration | Level 3 after Codex |
| GitHub Copilot CLI | Copilot plugin or project hook | plugin hook or `.github/hooks/*.json` | Level 3 for CLI |
| GitHub Copilot cloud agent | repository project kit | checked-in `.github/hooks/*.json` | Level 3 only for documented cloud events/tools |
| custom agent applications | Python API or generic JSON subprocess | application tool dispatcher | Level 2 or 3 depending on exclusive dispatch |

Primary packaging references checked for this plan:

- [Claude Code plugins](https://code.claude.com/docs/en/plugins) can bundle hooks and skills and be
  distributed through plugin marketplaces.
- [Codex plugins](https://learn.chatgpt.com/docs/build-plugins) can bundle skills, hooks, MCP configuration,
  and assets; [Codex hooks](https://learn.chatgpt.com/docs/hooks) provide the veto surface.
- [Gemini CLI extensions](https://github.com/google-gemini/gemini-cli/blob/main/docs/extensions/index.md)
  can package hooks, MCP servers, subagents, and Agent Skills.
- [GitHub Copilot hooks](https://docs.github.com/en/copilot/reference/hooks-reference) provide
  `preToolUse` in Copilot CLI and the cloud agent, with surface-specific behavior.

Cursor, Cline, IDE-specific agents, and future runtimes are candidates, not initial support claims. Add
one only after current native documentation establishes a pre-execution veto and its real host passes the
same conformance suite. Chat-only web products are outside scope unless they operate tools through an
enforceable app or dispatcher.

## Distribution architecture

```text
                         release artifacts
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
       Python CLI/core    native packages    generic embedding
       PyPI + .pyz        plugins/extensions Python API + JSON CLI
              │                 │                 │
              └─────────────────┼─────────────────┘
                                ▼
                     one canonical policy core
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
         runtime hook      workspace sandbox  remote Git/CI authority
        early feedback        local boundary       final boundary
```

Suggested layout after the neutral-core extraction:

```text
pyproject.toml
src/excubitor/
  cli.py
  core/
  adapters/
  installers/
  runtime_profiles/
  telemetry/
integrations/
  claude-code/
  codex/
  gemini-cli/
  github-copilot/
  generic/
packaging/
  zipapp/
docs/support-matrix.md
```

Native packages contain only vendor manifests, hook registration, runtime bindings, and assets. They
invoke the same installed core; they do not carry forked policy functions.

## Release artifacts

Publish the following from one tagged source revision:

1. **Python package:** `excubitor`, installable with `pipx` or `uv tool`, with a documented minimum
   Python version.
2. **Standalone zipapp:** `excubitor.pyz` for machines with Python but no Python package manager.
3. **Claude Code plugin:** versioned plugin plus marketplace entry.
4. **Codex plugin:** versioned manifest, hooks, skills, and trust instructions.
5. **Gemini CLI extension:** versioned extension and gallery metadata when stable.
6. **Copilot project kit:** checked-in hook configuration and launcher suitable for CLI and cloud-agent
   repositories; add a plugin where the supported surface can install it.
7. **Checksums and provenance:** SHA-256 manifest for every artifact and release attestations from CI.

Standalone platform executables are optional later. They should not delay the first release because the
current code is stdlib-only and a zipapp remains small and auditable.

## User-facing CLI

Target flow:

```text
uv tool install excubitor
excubitor install --runtime auto --scope project --dry-run
excubitor install --runtime claude-code,codex --scope project
excubitor doctor --probe
excubitor status --json
excubitor uninstall --runtime codex --scope project --dry-run
```

| Command | Contract |
|---|---|
| `install` | detect or select runtimes, validate configuration, show a plan, apply an atomic merge, and write a receipt |
| `doctor` | validate versions, registrations, trust, control paths, permissions, and a harmless native veto probe |
| `status` | report core/adapter versions and the last successful probe; never infer safety from file presence alone |
| `upgrade` | verify compatibility, stage artifacts, replace atomically, rerun probes, and roll back on failure |
| `uninstall` | remove only receipt-owned entries and files; preserve unrelated user configuration |
| `print-config` | show the effective neutral policy and all runtime/legacy overrides with precedence |

`--runtime auto` may detect candidates, but installation remains explicit: it prints the detected runtimes
and exactly which files or native package managers it will touch. Unknown configuration versions stop the
write and produce migration instructions.

## Scopes and ownership

Support three scopes without pretending they are equally strong:

- **User:** convenient across local repositories; mutable by the user and normally by an agent with
  unrestricted home-directory access.
- **Project:** reviewable and reproducible for a team; checked-in policy can prompt collaborators to
  install or trust packages. This is the recommended default for open-source use.
- **Managed:** administrator-controlled hooks, immutable workspace policy, or remote repository settings.
  This is the recommended organizational security boundary.

Commit the neutral policy as `.excubitor/policy.toml`. Store receipts, probe timestamps, and mutable
telemetry in a platform state directory or `EXCUBITOR_STATE_HOME`, never in committed policy. Receipts
record exact files, native identifiers, versions, and hashes owned by one installation so upgrade and
uninstall never search by substring.

## Installer transaction

Every runtime installer follows the same state machine:

1. **Discover:** locate the runtime and applicable configuration sources without writing.
2. **Validate:** parse complete nested schemas, resolve precedence, and reject unsupported versions or
   malformed structures with a precise path.
3. **Plan:** render a deterministic diff of files, package commands, trust steps, and control paths.
4. **Stage:** write files beside their destinations, set restrictive permissions, and verify hashes.
5. **Register:** atomically merge the exact event, matcher, command, timeout, and package identity.
6. **Trust:** surface the runtime's native review/trust action; never bypass it silently.
7. **Probe:** ask the real host to attempt a harmless synthetic action that must be denied before execution.
8. **Commit receipt:** record ownership and the successful adapter/core/host versions.
9. **Rollback:** on failure, restore prior configuration and remove only staged artifacts.

Installation succeeds only after the probe succeeds. If the runtime cannot be invoked non-interactively,
installation finishes as `needs-probe`, not `protected`, and prints the manual verification command.

## Harmless denial probe

Each adapter defines a probe safe even when the hook fails. The probe targets a disposable directory and
attempts to create or change a unique marker only after the denial should have occurred. Doctor verifies:

1. the host reports Excubitor's structured denial; and
2. the marker was not created or changed.

Do not use `git push`, branch deletion, destructive Git flags, user files, or a real default branch as an
installation probe. CI host tests use isolated homes, repositories, credentials, and runtime caches.

## Native-package rules

Every native package must:

- declare its compatible Excubitor core protocol range;
- use a runtime adapter and never invoke a provider API;
- register every in-scope shell and file-mutation tool explicitly;
- include actual runtime control paths in self-integrity evaluation;
- render core `pass` as no opinion rather than native auto-approval;
- retain runtime trust and permission prompts;
- keep executable paths inside the package or resolve a verified core launcher;
- document configuration precedence and which party can disable the hook;
- expose its version in denial telemetry and `doctor` output;
- ship no secrets, credentials, subscription tokens, or writable policy defaults.

Because vendors copy, cache, trust, and update packages differently, the installer must not assume a path
outside a plugin or extension remains available. Each package gets fixtures for its final installed layout,
not only its source-tree layout.

## MCP and generic embedding

Offer an optional Excubitor MCP server for guarded Git/filesystem operations and a Python/JSON embedding
API for custom tool dispatchers. The [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
defines how servers expose callable tools, but it does not require a client to route native shell or file
tools through a particular server.

Therefore:

- MCP reaches Level 2 only when the administrator removes or denies competing native mutation tools.
- A custom agent reaches Level 3 only when every in-scope tool call passes through Excubitor before
  execution and an integration test proves a denied call never reaches its executor.
- MCP errors must not be described as host-level denials unless the host prevents the alternate path.
- The server is useful for portability and least-privilege tool design, but is not the universal installer
  or root security boundary.

## Layered controls beyond the runtime

Native hooks improve feedback and stop common dangerous calls early, but the strongest deployment also
uses controls outside the agent's writable surface.

### Workspace boundary

- Run unattended agents in an isolated worktree or container, never in the authoritative default-branch
  worktree.
- Mount oracle files and policy/registration material read-only where possible.
- Restrict writable paths and available credentials to the current repository/task.
- Keep denial policy and hook launchers outside the agent-writable workspace for managed installations.

### Remote authority

- Protect default branches and require pull requests and status checks.
- Give unattended jobs credentials that cannot bypass protection, administer hooks, or rewrite rules.
- Separate commit permission from merge, push, and administrative permission.
- Run the telos/oracle witness in required CI from the reviewed revision.
- Retain server-side audit logs for pushes, merges, rule changes, and credential use.

These controls remain effective across models and agent runtimes. Runtime hooks are the early seatbelt;
workspace and remote authority are the crash structure.

## Test and release matrix

### Core and adapter gate

- all Phase 0 regressions pass;
- every native fixture normalizes to the canonical event expected by the shared semantic table;
- `pass` and `deny` serialize correctly without changing normal host permission flow;
- multi-file patches and ambiguous targets take the documented conservative path;
- adapters contain no duplicated policy decisions.

### Installer gate

- clean install, repeat install, upgrade, downgrade refusal, uninstall, and interrupted rollback;
- malformed and future-version configuration causes no write;
- unrelated user hooks and plugins survive byte-for-byte;
- paths containing spaces and non-ASCII characters work on Linux, macOS, and Windows;
- user, project, and supported managed scopes use isolated test homes;
- the receipt identifies every owned mutation exactly.

### Host gate

- the released native package is installed into a fresh runtime profile;
- the harmless probe is denied and leaves no marker;
- an unrelated safe call follows normal permission behavior;
- direct file, shell, multi-file patch, subagent, and cloud coverage are measured separately;
- timeout, crash, malformed-output, and disabled/untrusted behavior are recorded;
- results publish to `docs/support-matrix.md` with runtime and package versions.

No runtime receives the Level 3 badge from mocked events alone.

## Delivery phases

These distribution phases sit on top of, and do not replace, the implementation phases in
`model-agnostic-runtime.md`.

### Distribution A — prerequisites and package skeleton

1. Complete the remediation plan's Phase 0 safety fixes.
2. Extract the canonical event, decision, and four shared policy cores.
3. Add `pyproject.toml`, the CLI, neutral policy loading, and isolated installer primitives.
4. Produce reproducible wheel/sdist and `.pyz` artifacts from one tag.
5. Preserve current Claude hook entry points as compatibility launchers.

**Exit:** Claude behavior remains unchanged, the package installs offline from a built artifact, and every
policy is callable without runtime-specific global state.

### Distribution B — Claude Code and Codex packages

1. Convert the current Claude installation to a marketplace-ready plugin without changing decisions.
2. Build the Codex plugin and adapter from captured native fixtures.
3. Implement `install`, `doctor`, `status`, and receipt-owned `uninstall` for both.
4. Run real host probes on Linux, macOS, and Windows where supported.
5. Publish the first honest support matrix.

**Exit:** two runtimes pass core equivalence, installer transactions, and harmless native-veto probes.

### Distribution C — Gemini CLI and GitHub Copilot

1. Build the Gemini CLI extension and runtime profile.
2. Build Copilot CLI package/project registration.
3. Add the repository kit and isolated cloud-agent smoke workflow for Copilot cloud.
4. Record surface differences rather than sharing a badge across CLI, IDE, and cloud.
5. Test upgrades across at least two released core protocol versions.

**Exit:** each advertised surface independently meets Level 3 or is labeled at its lower verified level.

### Distribution D — generic embedding and optional MCP

1. Stabilize `excubitor.pre_tool.v1` and a small Python API.
2. Ship a reference dispatcher proving denied calls never invoke their executors.
3. Ship the optional MCP server with an exclusive-mediation checklist.
4. Publish an adapter authoring kit, fixtures, and conformance runner.
5. Accept additional runtimes only through the same host gate.

**Exit:** third parties can implement adapters without importing vendor packages or copying policy code.

### Distribution E — managed enforcement blueprints

1. Publish container/worktree profiles with read-only control surfaces.
2. Publish GitHub/GitLab remote-protection and least-privilege credential checklists.
3. Add administrator-controlled examples for runtimes that expose managed hooks.
4. Define drift detection for installed versions, trust, probes, and remote rules.
5. Threat-model the combined runtime, workspace, and remote layers.

**Exit:** organizations can reach Level 4 without granting the agent authority to rewrite or disable the
controls that judge it.

## Milestones and issue breakdown

Create focused issues or pull requests in this order:

1. `core: neutral package skeleton and canonical protocol`
2. `cli: policy config, status, and dry-run transaction engine`
3. `installer: receipts, atomic merge, rollback, and probe framework`
4. `integration: Claude Code plugin parity`
5. `integration: Codex plugin and host conformance`
6. `release: wheel, sdist, zipapp, checksums, and provenance`
7. `integration: Gemini CLI extension`
8. `integration: Copilot CLI and cloud project hooks`
9. `embedding: Python API, JSON CLI, and optional MCP server`
10. `docs: generated support matrix and managed-control blueprints`

Keep policy fixes, core extraction, adapter work, installer mutation, and publication in separate reviews.
A runtime package must not become the place where a core bypass is fixed for only one host.

## Definition of installable

Excubitor may call a runtime integration installable only when all of these are true:

- a versioned native artifact or deterministic project kit exists;
- installation has dry-run, exact ownership, atomic write, rollback, and uninstall behavior;
- the runtime's trust/enable action is explicit;
- a clean real-host installation passes the harmless denial probe;
- normal permission flow is preserved on `pass`;
- upgrade compatibility and failure behavior are tested;
- the support matrix identifies every known uncovered invocation path;
- the package invokes the same remediated policy core as every other runtime.

Until those conditions hold, describe the work as an adapter prototype or workflow package, not an
installable safety control.
