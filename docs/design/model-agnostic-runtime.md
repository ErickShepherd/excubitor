# Model-agnostic Excubitor — feasibility and migration design

**Date:** 2026-07-15 (Phase 1 implemented 2026-07-17)
**Status:** Phase 1 (extract a neutral core with Claude parity) **IMPLEMENTED** as Campaign 1 —
`excubitor/core/` (the four policies + dispatcher, model-blind), the named Claude Code adapter
(`excubitor/adapters/claude_code.py` + the four thin hooks), and the generic `excubitor.pre_tool.v1`
protocol (`runtime/spec_adapter.py`). Phases 2–4 (real non-Claude host packages, installers, and
live-host probes) remain **proposed, not built** — no runtime other than Claude Code is *supported* yet.
**Depends on:** Phase 0 in
the review notes

## Decision

**Yes: Excubitor can be model-agnostic.** Its load-bearing controls are deterministic Python/Git
decisions made outside the model. No guard needs an Anthropic, OpenAI, Google, or local-model API.

It is not yet **runtime-agnostic** as a complete product. The current hook envelopes, tool names,
configuration paths, environment variables, installer, loop scheduling vocabulary, and subscription
usage reader are coupled to Claude Code. The existing `SPEC.md` proves portability only for the
`guard-loop-vc` decision core through a generic envelope; the other three guards and the workflow layer
remain unported.

The right target is therefore:

> **One model-blind policy core, thin agent-runtime adapters, and optional provider/runtime services.**

This distinction matters. A *model* chooses what tool call to propose. An *agent runtime* names the tool,
dispatches it, and decides whether a pre-execution hook may veto it. Excubitor belongs at that second
boundary. If a host cannot intercept and veto a call before execution, Excubitor can still provide its
read-only audits and scanners there, but it must not claim enforcement.

## Evidence checked on 2026-07-15

The design is based on current primary documentation, not on a presumed common hook API:

- [Claude Code hooks](https://code.claude.com/docs/en/hooks) provide `PreToolUse`, JSON on stdin, and a
  structured `hookSpecificOutput.permissionDecision = "deny"` response.
- [Codex hooks](https://learn.chatgpt.com/docs/hooks) provide `PreToolUse`, JSON on stdin, matchers for
  `Bash`, `apply_patch`/`Edit`/`Write`, and the same structured deny shape. Codex also supports user,
  project, managed, and plugin-bundled hook sources with explicit trust review.
- [Codex custom model providers](https://learn.chatgpt.com/docs/config-file/config-advanced#custom-model-providers)
  separate the Codex runtime from its model provider and include local-provider support. This reinforces
  why Excubitor must bind to runtime capabilities, not a model slug.
- [Gemini CLI hooks](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/writing-hooks.md)
  provide a `BeforeTool` veto with the same JSON-over-stdin pattern, but their idiomatic structured result
  is top-level `{"decision":"deny","reason":"..."}`.
- The [Agent Skills specification](https://agentskills.io/specification) defines the portable `SKILL.md`
  directory/frontmatter format. It also exposes current portability work in this repository: the spec's
  `allowed-tools` field is an experimental space-separated string, while Excubitor currently uses
  runtime-specific YAML lists and runtime tool names.

These sources establish feasibility for three runtimes. They do **not** establish identical coverage:
tool names, patch/file inputs, subagent dispatch, trust, configuration precedence, and failure behavior
still need adapter tests on every host.

## Three layers of coupling

### 1. Model provider — already almost neutral

The guard and audit decisions do not call an LLM API and do not inspect a model identity. This is the
strong part of the current architecture: the same deny must result whether the proposed call came from
Claude, GPT, Gemini, an open-weight model, or a human-authored automation.

The only provider-specific executable is
`skills/ralph-loop/scripts/claude_usage.py`, which reads Claude subscription utilization. It affects
when a loop reschedules, not whether a dangerous act is permitted. Move it behind an optional usage
provider; do not put quota/provider logic in the policy core.

### 2. Agent runtime — portable with adapters

Runtime coupling currently includes:

- Claude Code's `PreToolUse` event and `hookSpecificOutput` response;
- native tool names (`Bash`, `Edit`, `Write`, `NotebookEdit`);
- native tool-input fields (`command`, `file_path`, `notebook_path`);
- `~/.claude/settings.json`, `.claude/settings.local.json`, and `~/.claude/hooks`;
- kill-switch discovery that knows `.claude` but not `.codex` or `.gemini`;
- `CLAUDE_LOOP_GUARD` and `CLAUDE_ALLOW_DEFAULT_BRANCH`;
- the installer and default denial-log path.

This is adapter/configuration work. Claude Code and Codex are close enough that they may share parsing
helpers, but they must remain named adapters so a change in either host cannot silently change the other.
Gemini needs a different output renderer and tool-name map.

### 3. Workflow UX — requires capability-specific bindings

The skill prose assumes `/loop`, `claude -p`, `ScheduleWakeup`, `AskUserQuestion`, Claude subscription
windows, and paths under `~/.claude/skills`. Those are not model concepts and are not part of the Agent
Skills file format; they are host capabilities.

The telos parser, leak scanner, oracle runner, suite checker, and Git policies are portable executables.
The unattended-loop recipe needs a small runtime binding for:

- fresh-session re-invocation;
- durable arming/environment propagation;
- scheduling or polling;
- surfacing a question/decision to a human;
- identifying shell and file-mutation tool calls;
- observing quota exhaustion, if the runtime exposes it.

A runtime without one of these capabilities should degrade explicitly (for example, no automatic
reschedule) rather than simulate a capability in model prose.

## Current component assessment

| Component | Model-neutral now? | Runtime-neutral now? | Required work |
|---|---:|---:|---|
| `leak_check.py` | yes | yes (CLI) | packaging/docs only |
| `telos_check.py` | yes | yes (CLI), skill prose is coupled | standardize skill frontmatter and bindings |
| oracle/suite freeze logic | yes | yes (CLI), recipe is coupled | close R-04; expose atomic runner |
| `guard-loop-vc` decision core | yes | partially; generic adapter exists | extract from hook file; add real host adapters |
| default-branch/one-unit/self-integrity decisions | yes in principle | no | extract pure policy functions and equivalence tests |
| denial telemetry | yes | path/schema assume Claude naming | use neutral state location and runtime field |
| installer/config registration | yes in principle | no | replace with runtime-aware installer/packages |
| ralph/telos loop skills | no model API dependency | heavily runtime-bound | split common protocol from host bindings |
| `claude_usage.py` / suspend | no | provider-specific | optional provider plugin; generic fallback |

## Target architecture

```text
native tool event
      │
      ▼
runtime adapter ──normalize──► canonical pre-tool event
                                  │
                                  ▼
                    model-blind policy dispatcher
                    ├─ default-branch policy
                    ├─ loop VC policy
                    ├─ one-unit policy
                    └─ self-integrity policy
                                  │
                          pass │ deny(reason)
                                  ▼
runtime adapter ───render native veto/no-op──► host runtime
                                  │
                                  └──► best-effort neutral telemetry
```

Suggested layout:

```text
excubitor/
  core/
    events.py                 # canonical event and decision dataclasses
    dispatch.py               # deny precedence; no host I/O
    git_state.py              # read-only Git queries and branch helpers
    policies/
      default_branch.py
      loop_vc.py
      one_unit.py
      self_integrity.py
  adapters/
    claude_code.py
    codex.py
    gemini_cli.py
    generic.py
  runtime_profiles/
    claude-code.json          # tool/config/control-path capabilities
    codex.json
    gemini-cli.json
  telemetry/
    denial_log.py
  providers/
    usage/
      anthropic_subscription.py
  installers/
    cli.py
```

Keep the package stdlib-only. The code can remain executable directly from a checkout; packaging it as a
Python distribution is optional and should not be a prerequisite for the first adapters.

## Canonical event contract

The current generic envelope covers only a shell command. Expand it into a versioned semantic event:

```json
{
  "schema": "excubitor.pre_tool.v1",
  "runtime": "codex",
  "native_tool": "apply_patch",
  "capability": "file.mutate",
  "cwd": "/repo",
  "command": null,
  "targets": ["/repo/app.py", "/repo/tests/test_app.py"],
  "session_id": "...",
  "loop_mode": "conservative",
  "control_paths": ["/repo/.codex/config.toml"]
}
```

Fields:

| Field | Meaning |
|---|---|
| `schema` | explicit compatibility/version marker |
| `runtime` | telemetry/adapter identity only; policies must not branch on a model |
| `native_tool` | retained for diagnostics, not primary classification |
| `capability` | `shell.execute`, `file.mutate`, `notebook.mutate`, or `other` |
| `cwd` | absolute working directory when known |
| `command` | shell command for `shell.execute`, otherwise null |
| `targets` | every file the native tool may mutate; never only the first path |
| `session_id` | optional telemetry join key |
| `loop_mode` | `null`, `conservative`, or `verifiable` |
| `control_paths` | host registration/config paths whose mutation can disarm enforcement |

Use a two-outcome core result:

```json
{"decision": "pass", "reason": null}
{"decision": "deny", "reason": "...", "policy": "loop-vc"}
```

`pass` means **Excubitor has no objection; preserve the host's normal permission flow**. Do not name this
result `allow` in the core: on several hosts, rendering an explicit native “allow” can skip a user
permission prompt. Adapters render `pass` as no decision/empty success, never as auto-approval.

## Pure policy boundaries

Each policy should expose a typed function and contain no stdin/stdout, process exit, native tool-name,
home-directory, or runtime-config logic. Examples:

```python
def decide_loop_vc(event: PreToolEvent, git: GitReader) -> Decision: ...
def decide_default_branch(event: PreToolEvent, git: GitReader) -> Decision: ...
def decide_one_unit(event: PreToolEvent, git: GitReader, cap: UnitCap | None) -> Decision: ...
def decide_self_integrity(event: PreToolEvent, protected: ProtectedSurface) -> Decision: ...
```

The adapter owns malformed native input. The policy owns decision ambiguity after successful
normalization. Preserve the existing distinction:

- adapter/process failure: fail open without crashing the host;
- a safety policy that explicitly requires certainty (for example, YOLO default-branch detection): return
  an ordinary fail-deny decision.

All policies run for one event and deny wins. Telemetry occurs only after the native denial has been
serialized and flushed, preserving the existing ordering contract.

## Adapter contract

Every runtime adapter must:

1. Verify that the event is a pre-execution event with a real veto, not post-tool feedback.
2. Normalize native tool names to semantic capabilities.
3. Extract **all** mutation targets. Patch tools can affect several files; a missing/ambiguous target must
   follow the policy's documented conservative behavior rather than silently becoming `cwd` by accident.
4. Supply the neutral loop mode and the runtime's real control/config paths.
5. Invoke the same policy dispatcher; never reimplement a deny set in the adapter.
6. Render `pass` as no opinion and `deny` as the host's structured veto.
7. Preserve the native permission flow; Excubitor does not grant permission.
8. Bound diagnostics and telemetry, and never let them delay a veto past the host timeout.
9. Ship golden fixtures copied from the runtime's documented/native event shape.
10. Prove equivalence: the normalized event sent directly to the core and through the native adapter must
    yield the same policy result.

### Claude Code adapter

- Input: `PreToolUse` with `Bash`, `Edit`, `Write`, and `NotebookEdit` mappings.
- Output: current `hookSpecificOutput.permissionDecision = "deny"` JSON.
- State/config: current paths remain supported during migration.
- Goal: exact behavior parity before any installer or environment-variable rename.

### Codex adapter

- Input: `PreToolUse`; map `Bash`, `apply_patch`, MCP filesystem mutations, and any native file-edit tools
  actually surfaced by Codex.
- Output: structured Codex `PreToolUse` denial; keep `pass` silent.
- Configuration: user/project/managed/plugin hook sources require different self-integrity surfaces.
- `apply_patch` is the main normalization challenge: extract every path from structured input if Codex
  provides it; otherwise parse its patch format conservatively or deny the whole patch while the cwd is a
  protected branch. Do not assume Claude's `file_path` field.
- Package option: a Codex plugin can bundle skills and hook configuration, but trust review and managed-hook
  policy must remain visible to the user.

### Gemini CLI adapter

- Input: `BeforeTool`; map `run_shell_command`, `write_file`, `replace`, and other mutation tools from
  actual fixtures.
- Output: top-level `decision`/`reason` structured veto.
- Package option: a Gemini CLI extension can bundle the hook and skills.
- Treat this as a separate conformance target; similar JSON syntax is not proof of identical semantics.

### Generic adapter

Keep a generic JSON CLI for embedding in a tool dispatcher, MCP gateway, or shell wrapper. Its contract
must state that a caller is conforming only if it invokes the adapter before execution and honors `deny`.
A demo that prints a decision but cannot veto is not an enforcement port.

## Neutral names, paths, and compatibility

Introduce provider-neutral names without breaking current installations:

| Current | Neutral primary | Migration behavior |
|---|---|---|
| `CLAUDE_LOOP_GUARD=1` | `EXCUBITOR_LOOP_GUARD=conservative` | read neutral first; support legacy alias with warning |
| `CLAUDE_LOOP_GUARD=yolo` | `EXCUBITOR_LOOP_GUARD=verifiable` | same |
| `CLAUDE_ALLOW_DEFAULT_BRANCH` | `EXCUBITOR_ALLOW_DEFAULT_BRANCH` | same |
| `.claude/allow-default-branch` | `.excubitor/allow-default-branch` | recognize and protect both during transition |
| `~/.claude/excubitor/denials.jsonl` | platform state dir or `EXCUBITOR_STATE_HOME` | continue reading override; document state lookup |

The self-integrity policy must not hardcode one runtime directory. Each adapter supplies its effective
hook registrations and control paths (`.claude`, `.codex`, `.gemini`, installed scripts, plugin manifests,
and managed policy where observable). Protecting a filename without protecting the actual active
registration is not sufficient.

## Installer and distribution

Replace the Claude-only shell installer with a tested Python entry point:

```text
python3 scripts/install.py --runtime claude-code --scope user
python3 scripts/install.py --runtime codex --scope project
python3 scripts/install.py --runtime gemini-cli --scope user
```

Requirements:

- dry-run and diff output before modifying settings;
- exact idempotence over event + matcher + command, not script-name substring matching;
- schema validation at every nested level;
- atomic settings writes with backup/recovery behavior;
- runtime-specific trust/reload instructions;
- uninstall that removes only Excubitor-owned entries;
- isolated temporary-home tests for every runtime;
- plugin/extension packaging may be added later, but the checked-in installer remains the reference
  implementation and conformance oracle.

## Agent Skills migration

The skill directories are a useful portable base, but format portability and workflow portability are
different claims.

1. Make frontmatter conform to the Agent Skills spec: portable `name`/`description`, optional
   `compatibility`, and a spec-valid `allowed-tools` representation where that experimental field is used.
2. Move host commands and paths into `references/runtimes/claude-code.md`, `codex.md`, and
   `gemini-cli.md`.
3. State the common loop protocol once in runtime-neutral language: re-read durable anchor, advance one
   unit, commit, recompute stop predicate, then either re-invoke in a fresh session or surface.
4. Define required capabilities rather than native nouns: `fresh_session`, `pre_tool_veto`,
   `schedule_resume`, `surface_question`, `shell`, and `file_mutation`.
5. A runtime binding must say which capabilities it implements and which degrade. For example, lack of a
   scheduler disables automatic resume but does not weaken the act fence.
6. Keep provider quota readers optional. A runtime may return `PROCEED` with an explicit “usage unavailable”
   diagnostic, matching today's fail-open reschedule policy.

Do not mechanically replace “Claude” with “agent.” Historical case studies, provenance, source-runtime
facts, and provider-specific binding docs should keep their correct names.

## Testing strategy

### Core tests

- Move current parser/policy cases to direct canonical-event tests.
- Add Phase 0 regressions before extraction.
- Assert that no file under `core/` contains runtime/provider names or reads environment/global paths.

### Adapter conformance tests

For each runtime, keep checked-in golden events for:

- shell command;
- one-file mutation;
- multi-file patch;
- notebook mutation where supported;
- unrelated/read-only tool;
- malformed event;
- native denial serialization;
- pass/no-op serialization.

Run the same semantic decision table through every adapter. A runtime may be “supported” only when its
native adapter fixtures and installer smoke test pass.

### Host smoke tests

Where CI can install a runtime without credentials, verify hook discovery and a denied harmless probe. Keep
credentialed/model calls out of the deterministic test gate. Manual release checks should cover trust UI,
subagent dispatch, project/user precedence, and host timeout behavior.

### Documentation honesty gate

Publish a support matrix with separate columns for:

- policy-core equivalence;
- pre-tool veto confirmed;
- direct file tools covered;
- shell covered;
- subagent calls covered;
- self-integrity control paths covered;
- installer tested;
- workflow skill tested.

“Model-agnostic” must never be used as shorthand for “all runtime invocation paths are fenced.”

## Phased migration

### Phase 0 — remediate before porting

Complete R-01 through R-09 from the review plan. In particular, do not copy the slash-default,
short-option, symlink, oracle, or vacuous-audit bugs into a neutral core.

### Phase 1 — extract a neutral core with Claude parity

1. Add canonical dataclasses and `Decision(pass|deny)`.
2. Extract Git queries and the VC classifier from the hook file.
3. Extract the other three policy decisions.
4. Convert current hook entry points into a named Claude Code adapter.
5. Run all current end-to-end tests unchanged plus adapter/core equivalence tests.

No user-visible behavior or path changes in this phase.

### Phase 2 — ship Codex support

1. Capture real Codex hook fixtures for `Bash`, `apply_patch`, and MCP mutation tools.
2. Implement the Codex normalizer and output renderer.
3. Define `.codex` self-integrity surfaces and installer behavior.
4. Package the neutral skills plus runtime binding, optionally as a Codex plugin.
5. Publish a coverage matrix; call unsupported tool paths unsupported rather than inferred safe.

Codex is the recommended second runtime because its current hook contract is closest to the shipped
Claude Code contract.

### Phase 3 — neutralize public configuration and skills

1. Add `EXCUBITOR_*` variables and `.excubitor/` marker/state conventions with legacy fallback.
2. Replace hardcoded `~/.claude` commands in common skill prose with runtime binding references.
3. Make skill frontmatter spec-conformant.
4. Split Anthropic subscription usage into an optional provider module.
5. Update README/architecture claims only after both Claude Code and Codex host smoke tests pass.

### Phase 4 — Gemini CLI and generic embedding

1. Add Gemini golden fixtures, adapter, self-integrity profile, and extension/install path.
2. Stabilize the generic JSON protocol as `excubitor.pre_tool.v1`.
3. Provide a minimal embedding example that genuinely vetoes a tool dispatcher.
4. Invite third-party adapters behind the same conformance suite.

## Success criteria

The project may call itself model-agnostic when:

- no policy decision depends on model identity or provider API;
- all four guards use the shared core;
- Claude Code and at least one non-Claude runtime pass the same semantic decision suite and native host
  smoke tests;
- the support matrix states invocation-path gaps explicitly;
- neutral skills follow the Agent Skills specification, with runtime bindings for nonstandard capabilities;
- provider-specific usage/scheduling helpers are optional and cannot weaken a deny decision;
- `SPEC.md` describes the full four-policy contract, not only `guard-loop-vc`.

It should call itself **model-blind, multi-runtime** rather than universally runtime-agnostic until a stable
adapter conformance suite exists and more than two host implementations pass it.

## Non-goals

- Reimplementing a shell to close all command-string evasions.
- Claiming a hook is a sandbox.
- Making hosts without a pre-execution veto enforce policy.
- Normalizing model quality or prompting behavior; deterministic safety must not depend on either.
- Hiding runtime-specific trust, permission, or subagent gaps behind one generic “supported” badge.
- Replacing accurate Claude Code provenance/history with generic wording.
