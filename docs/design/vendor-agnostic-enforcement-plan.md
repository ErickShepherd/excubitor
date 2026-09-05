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

## Stable runtime deployment and promotion contract

- A deterministic `.pyz` is the selected candidate package format, not an authorization mechanism. Native
  registrations invoke a direct hook entry point through a verified absolute interpreter in isolated startup
  mode (`python -I -S -B <absolute-archive> hook <host>`). They do not use `PYTHONPATH`, `python -m`, the working
  directory, user site packages, `sitecustomize`, or inherited Python activation variables to find policy code.
- Deployment requires an independently controlled user promotion action that the agent cannot execute or
  forge. Approval binds the exact archive digest, reviewed source inventory and build inputs, interpreter,
  canonical target registrations, and prior configuration. Ordinary agent-writable files, hashes, receipts,
  command flags, or chat-authored tokens are not approval. If no stronger same-user boundary is available,
  the documented claim is limited to covered agent tool calls rather than arbitrary same-user processes.
- The selected first-bootstrap authority is an owner-signed closed review packet consumed by a small,
  independently provisioned, owner-operated one-shot verifier/applier. Its signing key and signing operation
  remain unavailable to agents. The applier uses fixed enrolled locations and independently protects and
  verifies its own program and recovery bytes, verification key, interpreter dependency closure, artifact
  store, journals, revocation and replay state, exact machine and target, candidate and build evidence,
  configuration preimage and proposal, rollback material, expiry, and single-use transaction identity. It
  never imports promotion logic, trust roots, or state paths from the candidate.
- Approved archives are imported into new digest-addressed paths under the promotion authority's storage;
  existing objects are never overwritten. Each native registration, pending transaction, and rollback record
  references a canonical target identity derived from the actual host configuration location, so user scope
  and multiple project scopes do not collide. The registry records every target-to-artifact dependency.
- Promotion is atomic only per native target. Every target moves independently through staged, registered,
  needs-trust, verified, or rolled-back states, and a mixed-version fleet is reported honestly. Codex trust is
  definition-bound, so a registration change stays `needs-trust` until native review and a fresh witness.
- The prior known-good archive and registration remain recoverable throughout bootstrap, trust handoff, and
  rollback. An archive is retained while any registration, pending transaction, or rollback pin references
  it. Automatic garbage collection is initially disabled; cleanup is an explicit conservative operation.
- First deployment is a separate owner-controlled migration bound to an exact reviewed candidate and exact
  registration diff. It never edits or disables the active protected runtime to escape bootstrap, and recovery
  remains runnable through the verified prior artifact and interpreter when a candidate cannot start.
- Promotion runs only during an owner-operated maintenance window in which all known writers for the selected
  native target remain stopped. It revalidates approved preimages immediately before each configuration mutation,
  verifies written bytes before completion, rejects detected drift, symlinks, and platform redirections including
  Windows junctions/reparse points, and documents durability limits. Locks coordinate cooperating appliers; they
  do not exclude unrelated same-user processes. On drift or uncertain recovery state, it preserves the journal,
  prior and proposed bytes, runtimes, and conflict evidence for owner reconciliation instead of blindly restoring.
  Verification covers hostile import shadowing, inherited Python state, path replacement, concurrent installers,
  interrupted promotion, rollback, sharing violations, spaces, and shell metacharacters.
- Reproducibility establishes byte identity, not trust. Promotion evidence includes policy regressions, safe
  allow and denial checks, and a fresh native activation witness for every claimed target and tool surface.
  A harmless denial proves dispatch only. Host launch shortcuts, aliases, shims, PATH targets, and executables
  remain outside Excubitor ownership.

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
- [x] Make the neutral core resolve the conservative baseline as active under an empty environment; remove
  provider variables as baseline or elevated activation authority; keep only explicit deprecated-input
  reporting where compatibility requires it; and add empty-environment policy tests.
- [x] Adopt the independently reviewed stable-runtime deployment and per-target promotion contract above,
  keeping `.pyz` packaging separate from user authorization and native-host activation.
- [x] Document the steps in the [owner-controlled stable-runtime bootstrap runbook](../operations/owner-controlled-stable-runtime-bootstrap.md),
  including its hard prerequisites, closed review packet, independent approval, per-target trust and witnesses,
  rollback, and conservative cleanup boundaries.
- [x] Add a direct `.pyz` native-hook entry point and isolated absolute-interpreter invocation. Prove repository
  package shadowing, `sitecustomize`, inherited Python variables, virtual environments, ordinary working
  directories, spaces, and shell metacharacters cannot redirect execution.
- [x] DECIDE: Use an owner-signed closed review packet plus an independently provisioned, owner-operated one-shot
  verifier/applier for first bootstrap. The signature authenticates the owner's exact approval; the applier
  independently verifies and applies it without importing candidate-controlled code or state. GPT-6 Astra
  reviewed this design and the owner selected it. That selection does not authorize any candidate, target,
  registration change, provisioning action, or migration.
- [x] Introduce canonical target identities and a digest-addressed artifact dependency registry covering user
  and multiple project scopes, pending transactions, and rollback pins. Disable automatic garbage collection
  and preserve receipts whenever drift prevents complete uninstall. This is an isolated-candidate implementation
  claim only; independent review, promotion, integration, trust, and live activation remain separate gates.
- [x] DECIDE: Treat the signature suite and verifier implementation language as reviewable engineering choices
  during isolated candidate development, not as owner-gated prerequisites. Keep the approval payload and detached
  signature framing algorithm-neutral; a protected applier must later pin one independently reviewed algorithm
  and enrolled verification-key identity outside packet control. Re-open owner choice only if the implementation
  requires owner hardware, credentials, purchasing, or organizational signing policy. This resolution does not
  enroll a key, accept a signature, provision authority, or authorize migration.
- [x] Define strict, canonical, algorithm-neutral approval-payload and detached-signature codecs for one
  transaction. The isolated candidate binds the complete review packet, promotion manifest, artifact and
  source/build inventories, interpreter dependency closure, exact machine and target path semantics, current and
  proposed configuration, rollback material, expiry, revocation snapshot, and canonical non-zero transaction
  identity. It rejects duplicate, unknown, ill-typed, oversized, and noncanonical encodings and preserves the same
  bytes across Python 3.11 and 3.14. Parsing is explicitly not authorization: the protected verifier/applier below
  must still authenticate the exact bytes with its pinned key and algorithm, revalidate every attachment and live
  binding, and consume replay state before any mutation.
- [x] Preserve and verify complete dependency closures for both the selected runtime and the prior known-good
  runtime. Rollback must never return to an editable import tree, and interpreter verification must cover the
  standard library, extension modules, path configuration, and other startup dependencies rather than hashing
  only the interpreter executable. The isolated candidate now records and re-verifies a canonical closed inventory
  for both runtimes, requires the prior runtime to be a retained digest-addressed archive with its exact direct
  native registration, and uses `-B` so verification cannot mutate its own closure with bytecode. The operating
  system loader and system libraries are stated as the host trusted-computing-base boundary. This is candidate-only
  mechanism evidence; independent review, protected storage, authority provisioning, and live migration remain
  separate gates.
- [x] DECIDE: Use owner-operated, quiesced maintenance for native-configuration promotion, rollback, and
  interrupted recovery in this campaign. Every known writer for the selected target, including the native host,
  must remain stopped for the complete transaction. Locks coordinate cooperating appliers, while immediate
  rechecks, post-write verification, protected journals, and conflict-preserving recovery provide correctness
  checks. They do not exclude unrelated same-user processes, and protection against such processes remains
  unsupported. Enforced exclusion is deferred until a separately reviewed platform design proves control of both
  content and pathname replacement, handles existing writers, and preserves native host operation. GPT-6 Astra
  reviewed the fork and the owner selected its recommendation. This decision performs no provisioning or migration.
- [x] Implement per-target staged promotion, platform redirection defenses, and candidate-independent interrupted
  recovery under the quiesced-maintenance contract. Add native-settings readback before journal removal; recheck
  each surface immediately before restoring it; and preserve an explicit attention-required journal, prior and
  proposed bytes, retained runtimes, and conflict evidence on observed or uncertain recovery conflicts instead of
  blindly restoring. Test Windows junctions, reparse points, path aliases, sharing violations, interference after
  replacement, interference between recovery validation and restoration, rollback through the retained prior
  runtime, and honest mixed-version status. Preserve a regression that demonstrates final-read-to-replacement
  interference is outside the quiescence prerequisite rather than claiming the cooperating lock prevents it. Do
  not claim arbitrary-writer exclusion or an atomic all-host rollout. The isolated candidate now stores exact
  preimages and postimages in a strict journal, reads settings back after promotion and rollback writes and again
  before journal removal, validates and reads back each recovery surface around restoration, and makes detected or
  unreadable recovery state an owner-attention outcome whose journal cannot be automatically cleared. Existing
  canonical-identity, redirection, sharing-violation, retained-prior-runtime, and mixed-version tests remain green;
  new adversarial checks preserve both the detectable conflict behavior and the final-read-to-replacement gap as
  an explicit quiescence violation. This is isolated-candidate mechanism evidence only. The recovery logic does
  not read or execute a failed candidate artifact, but independently provisioned recovery packaging remains a
  later prerequisite; no arbitrary-writer exclusion, integration, authority provisioning, or migration is claimed.
- [ ] DECIDE: Select the authority and capture protocol that can produce non-self-asserted activation evidence.
  The viable designs are: extend the independently provisioned verifier/applier with a host-specific one-shot
  collector; provision a separate protected collector that emits an owner-signed closed evidence packet; or accept
  only independently verifiable host-native audit records and leave interfaces without adequate records
  unsupported. The selected design must pin who controls and may invoke the collector, the raw trust and tool-event
  sources accepted for each host, how tool identity and allow/deny outcomes are derived, an operating-system
  observation of the denied marker, sanitization without changing evidentiary meaning, and target, registration,
  artifact, host-version, time, freshness, and replay bindings. Caller-authored booleans, tool labels, prose,
  fixtures, and agent-writable capture state never qualify. This choice changes protected provisioning and the
  achievable support matrix, so implementation waits for owner selection after independent review.
- [ ] Derive activation evidence from independently captured native trust, harmless allow, harmless denial, and
  denied-side-effect results for each claimed host tool surface. Do not accept caller-supplied booleans or tool
  names as proof of native activation.
- [ ] Package the minimal one-shot verifier/applier and candidate-independent recovery program for independent
  owner provisioning at fixed enrolled locations. They must not load candidate promotion code or accept
  agent-selected keys or state directories. The applier must authenticate the codec's exact payload bytes with its
  pinned algorithm and enrolled key, rehash every bound attachment, reject expiry, revocation drift, stale
  configuration, machine or target mismatch, and prior consumption including after rollback, then atomically
  consume the transaction before mutation. Add denial witnesses proving the agent cannot sign, invoke a
  state-changing operation, alter the verifier, key, store, journal, or replay state, or bypass the public entry by
  calling an underlying function directly.
- [ ] After the required isolated entry, registry, promotion path, recovery path, and independent authority have
  been implemented and reviewed, have the owner independently provision the applier and verification key, sign
  the closed packet outside agent reach, and run the first one-target bootstrap from the protected development
  import to the exact approved artifact and registration diff. Keep the prior runtime available, complete native
  trust review, and capture fresh allow/deny dispatch evidence before protected-source work resumes here.
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
