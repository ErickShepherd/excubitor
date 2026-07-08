# SPEC — the runtime-neutral guard contract

Excubitor's guards ship as Claude Code PreToolUse hooks, but the *decision* they make is
host-independent. This document specifies that decision as a contract, so the claim "portable to any
runtime that can intercept tool calls" is precise rather than aspirational — and honest about what a
port can and cannot deliver. The claim is backed by running code: `runtime/spec_adapter.py` drives the
**same** decision core from a non-Claude-Code envelope, and
`runtime/tests/test_spec_adapter.py::TestRuntimeEquivalence` proves the two adapters agree
decision-for-decision (`TELOS-011`).

## The shape: one core, many adapters

```
  host runtime  ──(its tool-call event)──►  ADAPTER  ──►  decision core  ──►  deny reason | None
                                             │                 │
              hooks/guard-loop-vc.py::main   │                 │  split_segments → _classify
              runtime/spec_adapter.py::decide ┘                 └  _dangerous / _yolo_merge_reason
```

- The **decision core** is pure: `_dangerous(command, yolo, cwd)` (with `split_segments`, `_classify`,
  `_yolo_merge_reason`) takes a command string and a little context and returns a deny-reason string or
  `None`. No stdin, no runtime types, no I/O. It currently lives inside `hooks/guard-loop-vc.py` (the
  Claude Code adapter and the core co-habit one file); a heavier refactor could split it into its own
  module, but the import boundary is already clean — `spec_adapter.py` imports and calls it without
  reaching into Claude Code anything.
- An **adapter** is the small, per-runtime part: translate the host's tool-call event into the core's
  inputs, supply the arming signal, and translate the core's answer back into the host's deny
  mechanism. Two adapters ship; they share the core verbatim.

## The contract

### Inputs the adapter must obtain from the host

| Field | Meaning | Required |
|---|---|---|
| `command` | the shell command string the agent is about to run | yes — absent ⇒ allow (nothing to classify) |
| `cwd` | the working directory (used only for branch detection in `yolo` mode) | optional |
| `loop_mode` | the arming signal: `"1"` (conservative), `"yolo"` (verifiable-autonomy), or `None` | `None`/absent ⇒ guard inactive |

The generic envelope is exactly this, as JSON:

```json
{ "command": "git push origin main", "cwd": "/repo", "loop_mode": "1" }
```

### Output

```json
{ "decision": "deny", "reason": "push to a remote (git push)" }   // or
{ "decision": "allow", "reason": null }
```

### Invariants an adapter MUST preserve

1. **Inactive unless armed.** `loop_mode` absent/`None` ⇒ always `allow`. The guard does nothing to
   ordinary interactive work; it engages only when the host says "a loop is running."
2. **Fail open in the process sense.** A malformed event must yield `allow`, never a crash that wedges
   the host's tool. (The *merge decision* in `yolo` still fails **deny** on ambiguity — that is a
   decision, not a process failure.)
3. **Classify shell commands only.** The core reasons about `git`/`gh` command strings. An adapter must
   route only shell-command tool calls into it; a non-shell tool call is out of scope (allow).
4. **Do not fork the security logic.** The whole point is one core. An adapter translates envelopes; it
   must not re-implement `_classify`/`_dangerous`. (If your runtime needs a decision the core doesn't
   make, extend the core and re-run every adapter's equivalence test — don't special-case an adapter.)

## Porting to a third-party runtime — the checklist

1. **Find the interception point.** The runtime must let you observe a tool/command call *before it
   executes* and *veto* it. (LangChain-style callbacks, an MCP server gateway, an OpenAI-tool
   pre-dispatch hook, a shell wrapper — anything with a pre-execution veto.)
2. **Map the event → the envelope.** Pull the command string (and cwd if available) out of the
   runtime's event shape; supply `loop_mode` from however your loop driver signals "armed" (an env var,
   a lease file, a flag).
3. **Wire the decision → the runtime's veto.** On `{"decision":"deny"}`, block the call and surface
   `reason`; on `allow`, defer to normal flow. Preserve the four invariants above.
4. **Prove it.** Add an equivalence test in the shape of `TestRuntimeEquivalence`: same commands
   through your adapter and through the core, identical decisions. A port without that test is a claim,
   not a port.

## What a port CANNOT fix (honest limits)

- **Host dispatch gaps are inherited, not repaired.** If a runtime's interception doesn't fire on some
  invocation path — e.g. Claude Code PreToolUse hooks historically not firing on subagent/Task calls
  (`anthropics/claude-code#21460`) — the guard never sees those calls on that runtime, and no adapter
  can change that. Coverage is a property of the host's dispatch, not of this contract. See
  [`THREAT-MODEL.md`](THREAT-MODEL.md).
- **The core's own residuals travel with it.** Every adapter inherits the command-string parser's
  documented limits (shell-expansion evasions, verbs outside the fenced set) — see
  [`KNOWN-BYPASSES.md`](KNOWN-BYPASSES.md). Porting changes the envelope, not the seatbelt-not-sandbox
  nature of the parse.
- **Only `guard-loop-vc` is specified here.** `guard-default-branch`, `guard-one-unit`, and
  `guard-self-integrity` follow the same core/adapter shape in principle, but this SPEC and its
  equivalence proof currently cover the VC-mutation guard — the one whose decision core is richest and
  most worth porting. Extending the equivalence proof to the others is straightforward, unclaimed work.

The bar this document holds itself to: a claim of portability that isn't backed by a second adapter and
an equivalence test is exactly the kind of unproven assertion the rest of this repo refuses to make.
Here the second adapter and the test are in the tree.
