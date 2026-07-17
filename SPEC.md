# SPEC — the model-blind guard contract

Excubitor's guards ship as Claude Code PreToolUse hooks, but the *decisions* they make are
host-independent. This document specifies those decisions as a contract, so the claim "portable to any
runtime that can intercept tool calls" is precise rather than aspirational — and honest about what a
port can and cannot deliver. The claim is backed by running code: the four policies live in a
model-blind core (`excubitor/core/`), the shipped Claude Code hooks are thin adapters over it, and
`runtime/spec_adapter.py` drives the **same** core from a non-Claude envelope. The differential test
suites (`hooks/tests/`, `runtime/tests/`) prove the adapters and the core agree decision-for-decision
(`TELOS-011`).

## The shape: one model-blind core, thin per-runtime adapters

```
  host runtime ──(native pre-tool event)──► ADAPTER ──normalize──► PreToolEvent
                                              │                        │
        hooks/guard-*.py  (Claude Code)       │                        ▼
        runtime/spec_adapter.py (generic)     │         excubitor.core.dispatch.dispatch
                                              │         ├─ self-integrity   ┐ deny
                                              │         ├─ loop-vc          │ precedence
                                              │         ├─ default-branch   │ (first deny
                                              │         └─ one-unit         ┘  wins)
                                              ◄──render─── Decision(pass | deny, reason, policy)
```

- **`excubitor/core/`** is the model-blind core: stdlib-only, no stdin/stdout, no process exit, no
  environment reads, no host tool-names, no model/provider identity.
  - `events.py` — the canonical `PreToolEvent` (in) and `Decision(pass|deny)` (out) value types.
  - `git_state.py` — the read-only git boundary (the one place the core shells out — to read-only git
    queries only): branch/toplevel/`origin/HEAD` (slash-safe), single default branch, protected-name
    set, scoped commit count.
  - `policies/` — one pure module per guard: `loop_vc`, `default_branch`, `one_unit`,
    `self_integrity`. Each takes a `PreToolEvent` (plus any adapter-supplied config) and returns a
    deny-reason or `None`.
  - `dispatch.py` — runs every configured policy for one event and returns the first `deny` in a fixed
    precedence order; no host I/O.
- An **adapter** is the small, host-specific part: normalize the host's native event into a
  `PreToolEvent`, supply the arming signal and any host-specific config, call the core, and render the
  `Decision` back into the host's veto. It never re-implements a deny set.
  - **Claude Code:** `excubitor/adapters/claude_code.py` (shared PreToolUse envelope glue) + the four
    `hooks/guard-*.py` entry points, each registered for its tool-surface and calling its one policy.
  - **Generic:** `runtime/spec_adapter.py` — a JSON CLI/`decide()` over the full `excubitor.pre_tool.v1`
    envelope that routes through the dispatcher, so all four policies are reachable from any host.

## The canonical event — `excubitor.pre_tool.v1`

The generic envelope; the host fills what it knows and missing fields degrade conservatively:

```json
{
  "schema": "excubitor.pre_tool.v1",
  "runtime": "codex",
  "native_tool": "apply_patch",
  "capability": "file.mutate",
  "cwd": "/repo",
  "command": "git push origin main",
  "targets": ["/repo/a.py", "/repo/b.py"],
  "session_id": "…",
  "loop_mode": "conservative",
  "control_paths": ["/repo/.codex/config.toml"]
}
```

| Field | Meaning |
|---|---|
| `capability` | `shell.execute` / `file.mutate` / `notebook.mutate` / `other` — policies branch on this, not `native_tool` |
| `command` | the shell command string for `shell.execute`; else null |
| `targets` | EVERY file the tool may mutate (a patch can touch several); never just the first path |
| `cwd` | absolute working directory when known |
| `loop_mode` | `null` / `conservative` / `verifiable` (legacy aliases `1` / `yolo` accepted) — the neutral arming signal |
| `runtime`, `native_tool`, `session_id`, `control_paths`, `schema` | diagnostics / telemetry / compatibility; policies never branch on `runtime` |

Per-policy arming knobs that are **not** part of the neutral event — the opt-out-marker relpath
(default-branch), the one-unit cap, and the protected surface (self-integrity) — are host-specific and
supplied out of band (an optional `config` object in the generic adapter; module constants in the
Claude hooks). A legacy shell-only envelope `{command, cwd, loop_mode}` still works: the capability is
inferred from a present command / targets.

### The decision

```json
{"decision": "pass", "reason": null}
{"decision": "deny", "reason": "…", "policy": "loop-vc"}
```

`pass` means **Excubitor has no objection; preserve the host's normal permission flow.** It is
deliberately **not** named `allow`: on several hosts, rendering an explicit native "allow" can skip a
user's permission prompt. An adapter renders `pass` as no-decision / empty success — never an
auto-approval — and `deny` as the host's structured veto.

## The four policies and deny precedence

`dispatch()` consults the policies in a fixed order and returns the first `deny` (any single deny is a
correct deny; precedence only decides which reason surfaces when more than one would fire, which is
rare — the policies are largely disjoint by capability and arming):

1. **self-integrity** — while a loop guard is armed, deny a file target or shell token that resolves to
   / names a kill-switch path (a guard script, the disarm marker, or a settings file under the host's
   control dir). The meta-guard: a judge the model can rewrite is not a judge.
2. **loop-vc** — while armed, deny the irreversible version-control set (merge/push/branch-delete/reset/
   clean/worktree-remove/`gh pr merge`/direct ref-moves); `verifiable` mode relaxes only to a `--no-ff`
   merge into a confirmed non-default branch, fail-deny on ambiguity.
3. **default-branch** — deny the direct file-edit tools on a repo's default branch (branch-first),
   catching a symlink-laundered target; its own env/marker off-switches.
4. **one-unit** — cap a headless loop worker at one unit-advancing commit per session (scope-matched
   commit count vs baseline).

## Invariants an adapter MUST preserve

1. **Inactive unless armed.** `loop_mode` absent/`null` ⇒ loop-vc and self-integrity `pass`. one-unit is
   inactive without its cap; default-branch has its own off-switches. The guards do nothing to ordinary
   interactive work.
2. **Fail open in the *process* sense.** A malformed event ⇒ `pass`, never a crash that wedges the
   host's tool. (A *safety decision* that requires certainty — YOLO default-branch detection — still
   fails **deny**; that is a decision, not a process failure.)
3. **Extract all mutation targets.** A patch tool can touch several files; a missing/ambiguous target
   follows the policy's documented conservative behavior, never silently becomes `cwd`.
4. **Do not fork the security logic.** Translate envelopes; never re-implement a policy. A runtime that
   needs a decision the core doesn't make extends the core and re-runs every adapter's tests.
5. **Preserve the native permission flow.** Render `pass` as no opinion; Excubitor never grants
   permission. Telemetry is best-effort and only *after* the native veto is serialized/flushed.

## Porting to a third-party runtime — the checklist

1. **Find the interception point** — the runtime must let you observe a tool/command call *before it
   executes* and *veto* it. A demo that prints a decision but cannot veto is not an enforcement port.
2. **Normalize the event → `PreToolEvent`** — map the native tool name to a `capability`, pull the
   command / all targets / cwd, and supply `loop_mode` from however your loop driver signals "armed."
3. **Supply the host-specific config** — the control-dir surface (self-integrity), the opt-out marker
   (default-branch), the cap (one-unit).
4. **Wire the `Decision` → the runtime's veto** — render `deny` as the host's structured veto with
   `reason`; render `pass` as no opinion (never an auto-approve).
5. **Prove it** — ship golden fixtures in the shape of `runtime/tests/` and an equivalence check: the
   same event through your adapter and through the core yields the same decision. A port without that
   test is a claim, not a port.

## What a port CANNOT fix (honest limits)

- **No runtime other than Claude Code is *supported* yet.** The core is model-blind and the generic
  adapter proves all four policies are reachable from a neutral envelope (`runtime/tests/`), but the
  only runtime with real, shipped enforcement is the Claude Code hooks. Codex, Gemini CLI, and other
  hosts are *designed* adapters in `docs/design/model-agnostic-runtime.md`, **not** built or probed on a
  real host — those are Campaign 2/3 gates. "Model-blind, multi-runtime *capable*" is the honest phrase;
  "multi-runtime *supported*" is not yet earned.
- **Host dispatch gaps are inherited, not repaired.** If a runtime's interception doesn't fire on some
  invocation path (e.g. Claude Code PreToolUse historically not firing on subagent/Task calls,
  `anthropics/claude-code#21460`), the guard never sees those calls and no adapter can change that. See
  [`THREAT-MODEL.md`](THREAT-MODEL.md).
- **The core's own residuals travel with it.** Every adapter inherits the parsers' documented limits
  (shell-expansion evasions, verbs outside the fenced set) — see [`KNOWN-BYPASSES.md`](KNOWN-BYPASSES.md).
  Porting changes the envelope, not the seatbelt-not-sandbox nature of the parse.

The bar this document holds itself to: a claim of portability that isn't backed by a real second adapter
and a passing equivalence test is exactly the kind of unproven assertion the rest of this repo refuses
to make. Here the model-blind core, a second (generic) adapter, and the tests are in the tree — and the
gap between "reachable from a neutral envelope" and "supported on a real non-Claude host" is stated,
not papered over.
