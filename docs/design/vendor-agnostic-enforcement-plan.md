# Vendor-agnostic native enforcement plan

Status: active; implementation is blocked on the unchecked corrective units below.

This checklist moves Excubitor from a Claude-oriented distribution to native, testable enforcement inside
Codex, Claude Code, and Antigravity. Users continue launching each host normally. Each checked item is one
bounded implementation unit and one focused commit. A runtime is not called supported until a harmless
real-host denial probe proves that the host loaded the reviewed hook and honored its veto.

## Owner-approved product boundary

- Excubitor integrates through each host's native plugin or lifecycle-hook mechanism. It is not a launcher,
  wrapper, replacement shell, or supervisor for the host.
- Installation and uninstallation never create, edit, redirect, or delete shortcuts, aliases, shims, PATH
  launch targets, host executables, or unrelated host configuration. Receipts enumerate every Excubitor-owned
  registration and artifact.
- Removing Excubitor leaves Codex, Claude Code, and Antigravity independently launchable through their
  original entry points. An uninstall conflict fails before mutation rather than leaving a dangling hook.
- No environment variable is required to activate baseline enforcement. `EXCUBITOR_LOOP_GUARD`,
  `CLAUDE_LOOP_GUARD`, and similar provider-era switches are deprecated inputs, not activation authority.
- A trusted and loaded Excubitor hook is the activation signal for baseline enforcement. An untrusted,
  unloaded, unsupported, or undispatched hook is reported as unprotected; installation alone is not proof.

## Enforcement and authority contract

- The model-blind core remains the only policy authority. Runtime adapters translate native events, call the
  shared dispatcher once, and translate the result back; they do not copy deny sets.
- The always-on baseline comprises self-integrity, the conservative version-control act fence, and
  default-branch mutation protection. These policies run with an empty activation environment whenever a
  trusted native hook dispatches a covered event.
- One-unit enforcement only adds restrictions. It may be requested by a native workflow and may lazily bind a
  session/repository baseline from trusted hook metadata; it must not depend on a provider-named environment
  variable. Failure to establish an unambiguous baseline denies the restricted operation or reports the
  control inactive without weakening the always-on baseline.
- Elevated autonomy weakens the conservative act fence and therefore remains unsupported and fail-closed in
  this campaign. An ordinary file writable by the agent is not authorization. Any future elevated grant must
  have an independently reviewed issuer, canonical project and session binding, expiry, revocation, replay
  resistance, and tests showing that an agent cannot create, alter, renew, or reuse the grant.
- Repository policy may add protected roots and declare exact mutation surfaces, but it may not disable a
  baseline policy, choose an ordinary tracked opt-out marker, authorize default-branch mutation, or arm
  elevated autonomy. Exceptions that weaken baseline enforcement require a separate trusted user action and
  are unsupported until that authority boundary exists.
- A passing decision is silence: Excubitor has no objection and does not auto-approve past the host's normal
  permission flow.
- Irrelevant events and envelopes too malformed to identify a covered mutation may defer to the host. Once an
  event is recognized as a covered mutation, incomplete targets, invalid native fields, configuration
  failure, adapter exceptions, and timeouts must fail closed where the host contract permits. Degraded or
  unsupported operation must be observable rather than indistinguishable from a policy pass.
- Code, installation, trust, dispatch, and support are separate gates. Fixtures prove translation; only a
  version-bound live denial witness proves a named host surface is protected.

## Uninstall contract

- Exact registration matching protects user configuration from accidental deletion, but artifact deletion
  is also dependency-aware. Before deleting a script, module, receipt, or other artifact, uninstall checks
  every surviving host registration that could still reference it.
- If an owned registration has drifted or a surviving registration references an artifact scheduled for
  deletion, uninstall performs no mutation and reports the precise conflict. It preserves the dependency and
  receipt so a later retry can clean up safely.
- Interrupted install and uninstall operations remain journaled and recoverable. Repeated uninstall is
  idempotent, shared dependencies are retained until unreferenced, and a normal host launch after uninstall is
  part of lifecycle verification.

## Evidence matrix

Support is recorded separately for each host interface, host version, operating system, registration scope,
and tool surface. Each supported mutation surface needs both a harmless allow witness and a harmless denial
witness from an ordinary host launch with all activation variables absent. Shell allow evidence is not shell
denial evidence. Project-scope, non-Windows, headless, MCP, and specialized-tool claims remain unverified until
their own witnesses exist.

## Checklist

- [x] Replace the earlier environment-gated plan with the owner-approved native-hook, no-shortcut,
  always-on-baseline, monotonic-policy, dependency-safe-uninstall, fail-closed-mutation, and evidence-matrix
  contract described above.
- [ ] Make the neutral core resolve the conservative baseline as active under an empty environment; remove
  provider variables as baseline or elevated activation authority; keep only explicit deprecated-input
  reporting where compatibility requires it; and add empty-environment policy tests.
- [ ] Make repository policy monotonic: repository content may add restrictions but cannot disable baseline
  controls, select a tracked opt-out escape, or arm elevated behavior. Add hostile and malformed repository
  policy tests.
- [ ] Replace environment-derived one-unit state with a restriction-only, host-neutral session binding from
  native hook metadata, including ambiguous-state, tamper-attempt, expiry, and cleanup tests. Keep elevated
  autonomy unsupported.
- [ ] Harden adapter failure contracts so recognized mutations deny on incomplete input, configuration
  failure, unexpected exceptions, and host-supported timeout paths while irrelevant events remain no-op.
  Require observable diagnostics without leaking sensitive payloads.
- [ ] Make uninstall dependency-aware and conflict-atomic. Cover edited registrations, shared dependencies,
  interrupted and repeated uninstall, receipt retention, and successful ordinary host launch afterward. Add
  a regression test proving no shortcut, alias, shim, PATH target, or host executable is an install target.
- [ ] Reconcile the existing Codex native registration with the corrected contract, package hooks and skills
  through supported Codex integration surfaces where appropriate, retain explicit trust review, and verify
  the baseline with an empty activation environment.
- [ ] Reconcile the Claude Code native plugin/hooks with the same core contract and neutral public language;
  preserve only compatibility that does not weaken the corrected baseline.
- [ ] Add an Antigravity `PreToolUse` adapter from observed native fixtures, covering command execution and
  every documented file-mutation surface through the shared dispatcher.
- [ ] Add transactional Antigravity native registration, receipts, rollback, self-integrity coverage, trust
  or enablement handoff, and harmless real-host allow/deny probes without changing how Antigravity launches.
- [ ] Update installation documentation, support matrices, skills, examples, diagnostics, and known bypasses
  so all three hosts use native integrations with no activation-variable or launcher instructions.
- [ ] Capture version-bound real-host witnesses for every support claim from ordinary launches with activation
  variables absent. Keep unsupported interfaces visibly unsupported rather than extrapolating from fixtures.
- [ ] Obtain a final read-only GPT-6 Astra review of the implementation and this checklist. Resolve every
  blocking finding before presenting the branch for integration; the implementation may not self-ratify.
