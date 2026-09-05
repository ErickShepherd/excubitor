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

## 2026-09-02 — Explicit Codex MCP mutation profiles

- Codex identifies MCP calls with canonical `mcp__server__tool` names and supplies the complete JSON
  arguments to `PreToolUse`. The hook matcher must therefore observe `mcp__.*`, while the adapter uses
  exact configured names so an unlisted tool stays silent and Codex keeps its normal permission flow.
- A profile is a completeness assertion by the policy owner: every path-bearing input is named with a
  JSON Pointer, with `*` available for every member of an array. Selected strings and arrays of strings
  are flattened and deduplicated before the shared dispatcher sees the mutation.
- Once a tool is configured as a mutation, a missing selector, empty array, non-string path, invalid
  pointer, or embedded NUL is an adapter-input denial. Silently dropping one malformed target would let
  a multi-target mutation bypass the branch and self-integrity policies.
- The discovered `.excubitor` policy directory is part of the armed adapter's protected roots. A
  configured MCP writer cannot remove its own profile and then rely on the unknown-tool pass path.
- Fixtures and installer tests establish adapter and registration behavior only. MCP remains outside the
  live Codex support claim until a harmless real MCP denial witness is captured and bound to a current
  reviewed registration.

## 2026-09-05 — Native integration contract correction

- Host launch indirection is the wrong product boundary. Excubitor must live in each host's native lifecycle
  and must never own shortcuts, aliases, shims, PATH launch targets, or host executables.
- An always-on baseline and elevated autonomy are different authorities. Trusted hook dispatch can activate
  restrictions, but an agent-writable file cannot safely authorize weaker behavior; elevated autonomy stays
  unsupported until a separately controlled grant mechanism exists.
- Exact-tuple registration removal is not enough for safe uninstall. A drifted registration can survive while
  its hash-matching dependency is deleted, so uninstall must validate surviving dependency references before
  changing either configuration or artifacts.
- Repository configuration is attacker-controlled from the enforcement boundary's perspective. It may add
  restrictions, but a tracked opt-out marker or `enabled = false` switch cannot be allowed to weaken the
  trusted baseline.
- The final support claim needs a matrix and real denial witnesses. A Windows TUI patch denial does not prove
  shell denial, headless dispatch, MCP coverage, another scope, another operating system, or another host.

## 2026-09-05 — Always-on conservative native-hook baseline

- Reaching the neutral resolver from a native adapter is itself the activation signal. An empty environment
  now selects the conservative posture, so loop version-control and self-integrity policies cannot disappear
  merely because a host was launched normally.
- Former `EXCUBITOR_LOOP_GUARD` and `CLAUDE_LOOP_GUARD` values are diagnostics only. Every present value is
  reported as deprecated and ignored, including `verifiable`, `yolo`, unknown text, and the empty string;
  none can select elevated autonomy.
- The live Codex hook immediately enforced the changed resolver against this worktree and rejected a later
  patch that named the protected package tests. That is useful dogfood evidence that the baseline loaded, but
  it is not a version-bound ordinary-host support witness and does not replace the final external review.

## 2026-09-05 — Stable-runtime bootstrap fork

- Codex currently registers the importable package in place: its command pins the active interpreter and
  development package parent, while the Codex profile stages and receipts no runtime artifact. Once the
  baseline became always-on, that correctly made the development package an uneditable protected surface.
- The deterministic zipapp builder is a strong candidate for the stable runtime because Python can import
  the adapter from one hashable file and the existing registration machinery already understands a package
  loaded from `.pyz`. Running the installer from an arbitrary zipapp is not enough, however: the current
  receipt would own only the registration and could leave that dependency behind or dangling.
- Choosing the deployed artifact and promotion authority affects user-level host configuration and the
  enforcement trust boundary. It is therefore not a reversible, repository-internal implementation detail;
  record it as an open checklist decision rather than letting the loop silently choose or bypass the active
  self-integrity fence.

## 2026-09-05 — Astra stable-runtime revision adopted

- Packaging, authorization, and native activation are separate mechanisms. A content hash in a user-writable
  directory identifies bytes but cannot authorize them when the same agent identity could replace the archive
  and receipt together.
- The current `PYTHONPATH` plus `python -m` registration is unsuitable for the stable runtime because working
  directory imports and Python startup customization can redirect execution. The selected contract uses a
  direct zipapp hook entry through a verified interpreter with isolated startup instead.
- Host transitions are per target, not fleet-atomic. Canonical configuration-path identities, dependency and
  rollback references, Codex's definition-bound trust handoff, and honest mixed-version status all have to be
  modeled before shared artifacts can be promoted or removed safely.
- Deterministic output and one denial are narrow evidence: promotion approval must bind reviewed inputs and
  exact bytes, while regression checks plus fresh native allow/deny witnesses establish each support claim.
  The first migration remains an owner-controlled external step and must retain the prior working runtime.

## 2026-09-05 — Owner-controlled bootstrap runbook

- The bootstrap cannot safely precede its direct isolated entry, canonical target registry, per-target transaction,
  recovery, and independent promotion authority. The checklist now puts those prerequisites before activation.
- Candidate preparation and approval are distinct. An agent may build reproducible bytes and assemble a closed
  review packet, but only an authority unavailable to that agent may approve, import, or register those bytes.
- The first migration must be prepared away from the active protected runtime. It may not create a temporary
  exception, edit the live package in place, or use an agent-writable receipt as authorization.
- Trust and evidence close independently for every target. The prior runtime stays pinned through native review,
  harmless allow and deny checks, and rollback; partial migration remains an explicit mixed-version state.

## 2026-09-05 — Direct isolated zipapp hook entry

- Keeping the zipapp's top-level entry as a small reviewed source file is easier to audit than generating Python
  text inside the builder, while preserving the deterministic archive and the ordinary CLI.
- The hook route refuses to run unless both `-I` and `-S` are active and the visible interpreter and archive paths
  are absolute. Isolation is therefore a runtime precondition, not merely a registration convention.
- A hostile-state test uses a virtual-environment interpreter and an archive path containing spaces and shell
  metacharacters, while planting shadow packages in the working directory, `PYTHONPATH`, and site-packages and
  setting inherited Python variables. The embedded Codex adapter still produces its self-integrity denial.
- Python's Windows venv builder rejects any environment path containing `;`, the platform path-list separator.
  Keep that character on the archive path while using other shell metacharacters in the venv path.
- Only `hook codex` is available now. Unsupported hosts fail explicitly; Claude Code and Antigravity routes must
  be added by their later native-adapter units rather than guessed from the Codex contract.

## 2026-09-05 — Authoritative promotion authority gate

- The canonical registry and per-target promotion implementation exist only in the isolated candidate. Applying
  them to this checkout would mutate the package imported by the active protected hook, so integration cannot
  precede the documented stable-runtime bootstrap without defeating self-integrity.
- The existing machine-local publication promotion broker is not the stable-runtime authority. It is an
  agent-facing Git fast-forward tool, accepts an agent-written request, changes only Git refs, and explicitly does
  not claim an operating-system boundary against an unrestricted same-user process.
- The installed Ralph recipe still names a Claude-specific activation variable, but the newer repository contract
  makes both provider-era variables ignored diagnostics. For this campaign, the native conservative baseline and
  the one-checklist-unit-per-continuation cadence are authoritative; a later skill-update unit must remove the
  stale vendor-specific launch instruction rather than asking users to change their environment.

## 2026-09-05 — Astra-reviewed bootstrap authority selected

- First bootstrap will use an owner-signed closed review packet consumed by a small, independently provisioned,
  owner-operated one-shot verifier/applier. The signature proves which exact transition the owner approved; the
  protected applier separately verifies and performs that transition without trusting candidate code or paths.
- The owner's chat approval resolves the architecture only. It does not approve candidate bytes, provision the
  applier or signing key, select a live target, change a registration, or authorize the migration.
- Astra found that the isolated candidate is not ready for provisioning: its manifest is not a complete signed
  packet, its prior runtime can refer back to mutable imports, interpreter hashing omits dependency closure,
  configuration replacement has concurrent-writer gaps, and activation evidence trusts caller assertions.
- The denial boundary must cover signing, state-changing invocation, direct calls beneath the public entry,
  verifier and recovery bytes, keys, artifact storage, journals, and replay state. An unrestricted same-user
  process remains outside the stronger claim unless a genuinely separate security principal protects those
  surfaces; native-agent tool coverage must be stated more narrowly otherwise.

## 2026-09-05 — Registry candidate reconciled

- A strict schema must reject duplicate JSON member names. Python's default decoder silently keeps the last
  duplicate, so the registry now uses duplicate-detecting object construction at every nesting depth rather than
  allowing an ambiguous durable record to reach semantic validation.
- The registry's identity and retention model already matched the current contract: identity binds runtime,
  user-or-project scope, and normalized absolute native settings path; dependencies cover registrations, pending
  transactions, and rollback pins; unknown objects fail closed; and no removal or automatic-collection API exists.
- The focused registry checks passed under Python 3.11 and 3.14, and the promotion consumer checks stayed green.
  The combined registry/uninstall run retained one known Windows-only baseline failure caused by a test expecting
  LF bytes after a text-mode write produced CRLF; it is not evidence against the registry behavior.
- The broader installer selection passed 135 checks and reproduced only the six already documented Windows test
  defects: four CRLF-versus-LF assertions and two hard-coded POSIX receipt-path lookups. No new registry or
  promotion-consumer regression appeared.
- The Windows Store Python 3.11 launcher reports an inaccessible app-alias path as `sys.executable`, which breaks
  installer tests that correctly require a resolvable interpreter. A local Python 3.14 environment populated from
  the hash-locked test requirements avoids that runner defect without weakening production validation.
- The implementation remains only in the isolated candidate. Checking the unit records a reviewable candidate
  claim; it does not integrate those bytes, approve a review packet, provision authority, or change any live hook.

## 2026-09-05 — Signed-envelope cryptographic fork

- The packet fields do not determine the cryptographic verification mechanism. The candidate is intentionally
  standard-library-only and contains no signature primitive, while several materially different mechanisms can
  authenticate the same canonical packet.
- A compiled Ed25519 verifier/applier keeps the signature format small and portable; operating-system certificate
  verification can reuse a platform trust store but changes portability and provisioning; a pinned cryptographic
  runtime adds a dependency closure that must itself be protected and reviewed.
- This choice fixes the owner's key-provisioning workflow, the verifier supply chain, cross-platform packet
  semantics, and long-lived trust-root compatibility. Those effects reach beyond reversible candidate internals,
  so implementation must wait for an explicit owner decision rather than letting the loop lock in one option.

## 2026-09-05 — Astra correction: cryptographic implementation is not an owner gate

- Astra found that the previous stop conflated isolated candidate implementation with later trust-root
  provisioning. The signature algorithm and verifier language can remain reviewable engineering choices until a
  design actually requires owner hardware, credentials, purchasing, or organizational signing policy.
- The packet codec can stay algorithm-neutral. Parsing never grants authority, and the independently provisioned
  applier must pin its accepted algorithm and enrolled verification-key identity rather than letting packet fields
  select either one.
- Replay denial belongs to protected transaction-consumption state, not to serialization alone. Codec tests may
  prove deterministic bytes and strict rejection, but must not claim to prove one-shot authorization.
- The next fresh unit is therefore the strict approval-payload codec with adversarial and cross-platform fixtures;
  key enrollment, protected installation, signing, bootstrap, and migration remain owner-controlled operations.

## 2026-09-05 — Canonical approval codec candidate

- Reusing the promotion manifest as a signature envelope would blur mechanism and authority. The candidate instead
  keeps a separate canonical payload that binds the manifest and every external review, artifact, source, build,
  interpreter-closure, configuration, rollback, and revocation attachment by exact digest and bounded size.
- Target path meaning cannot depend on the verifier's operating system. The payload carries an explicit Windows or
  POSIX flavor and validates with the corresponding standard-library path module, while preserving and hashing the
  exact canonical path text used by the existing target identity.
- Canonical UTF-8 JSON uses sorted keys, compact separators, one LF terminator, unescaped Unicode, strict duplicate
  and unknown-field rejection, bounded integers and text, and canonical unpadded base64url framing. A fixed payload
  digest passed unchanged under Python 3.11 and 3.14.
- The envelope exposes only exact payload bytes plus opaque detached-signature bytes. It intentionally carries no
  caller-selected algorithm or key and accepts a structurally valid altered payload with an old signature because
  parsing is not signature verification; the protected applier must detect that mismatch later.
- The final candidate checks passed 39 approval, registry, and promotion tests under Python 3.14 and all 17 codec
  tests under Python 3.11. Seventeen wheel, source-archive, and zipapp builder checks also passed. Compilation and
  the configured 110-character line limit were clean; Ruff was unavailable in the isolated test environment.
- These source and test bytes remain only in the isolated candidate. No signature was created or accepted, no
  replay state was provisioned or consumed, and no trusted program, hook registration, or live target changed.

## 2026-09-05 — Closed candidate and rollback runtime inventories

- Hashing only `python.exe` does not identify the code Python can execute. The isolated candidate now inventories
  the exact interpreter and base executable, shared Python library and path configuration, every regular file under
  the isolated import paths, standard-library files, extension modules, and relevant absent startup-config paths.
- Verification checks path presence and the entire file set before launching the interpreter, then repeats an
  isolated identity/path probe. This order prevents a newly added shadow module or path-config file from controlling
  the probe that is supposed to detect it. Symlinks, Windows reparse points, special files, unstable reads, oversized
  inventories, omitted files, added files, and changed bytes fail closed.
- Native archive registrations now add `-B` to `-I -S`; otherwise an ordinary hook invocation could write `.pyc`
  files and make the retained dependency inventory mutate itself.
- Promotion now requires complete inventories for both the selected and prior runtimes. The prior runtime must also
  be a retained digest-addressed archive whose exact direct native registration is present in the approved preimage;
  an empty target or editable `python -m excubitor` rollback is refused before importing candidate bytes.
- Promotion state, rollback records, activation witnesses, and health checks retain or bind the selected closure.
  Rollback re-verifies the prior closure and stable registration both before journaling and immediately before
  restoring settings, without reading or executing the failed candidate.
- The boundary is deliberately Python-owned dependencies. The operating-system loader and system libraries remain
  host trusted-computing-base inputs and must not be described as captured by this manifest.
- Fifty combined closure, approval, registry, and promotion checks passed under Python 3.14; nineteen focused
  promotion checks and ten deterministic zipapp checks also passed. The approval codec's seventeen tests and both
  changed modules compiled under Python 3.11. Ruff was unavailable, while a direct 110-character line-length scan
  reported no violations.
- All implementation and test bytes remain in the isolated candidate. No trusted program, signing key, protected
  store, native registration, host trust decision, or live target changed.

## 2026-09-05 — Native configuration exclusivity is an unresolved platform boundary

- The candidate's registry and per-target kernel locks serialize callers that use the promotion API. They do not
  stop an unrelated process from replacing the native settings pathname, so they cannot close the final-read to
  replacement race or justify an exclusive-writer claim.
- Atomic replacement is not compare-and-swap. A writer can change the target after the approved preimage is read
  and before replacement, causing an otherwise atomic `os.replace` to discard bytes that were never approved as
  the preimage.
- Windows sharing modes can deny later read, write, and delete opens while a no-share file handle is held. That
  same denial also prevents replacing the pathname while the handle remains open; writing through the handle would
  trade atomic replacement for crash recovery. On POSIX, rename leaves existing file descriptors attached to the
  old inode and ordinary file locks are advisory, so neither primitive alone protects a writable pathname.
- A strong cross-platform claim therefore needs an independently protected writer principal controlling the
  configuration location and recovery path. Otherwise the honest contract is cooperative or quiesced writers plus
  conflict detection, with no claim of exclusion against arbitrary same-user processes.
- Selecting that boundary changes owner provisioning, privileges, recovery, and the supported-platform claim.
  The plan did not choose those consequences, so this iteration records the fork instead of presenting the current
  advisory lock and hash rechecks as a completed security mechanism.

## 2026-09-05 — Astra-reviewed quiesced maintenance selected

- Astra confirmed the final-read-to-replacement race but falsified the claim that a new operating-system account
  is logically required. The actual requirement for the stronger claim is an enforceable exclusive mutation
  interval or a genuine host/filesystem conditional update; a dedicated principal is only one possible mechanism.
- Protecting a settings file alone would also be incomplete. A strong design must control replaceable parent and
  ancestor paths, account for existing handles or mappings, preserve protections on replacement files, and remain
  compatible with hosts that write trust or unrelated preferences into the same configuration.
- The selected campaign contract is therefore owner-operated quiesced maintenance. All known target writers remain
  stopped for the complete transaction. Locks coordinate cooperating appliers, and protection against arbitrary
  same-user processes stays explicitly unsupported.
- Quiescence does not excuse avoidable correctness gaps. Promotion and rollback must read settings back before
  deleting the journal. Recovery must recheck each surface immediately before restoring it and must retain the
  journal plus both byte versions and conflict evidence when state is uncertain instead of blindly overwriting.
- The race after the last preimage read cannot be represented as mechanically prevented under this contract.
  Adversarial tests must preserve it as an explicit excluded case while separately proving that detectable
  post-write and recovery interference stops with recoverable evidence.
- This decision changes only the reviewed contract. It does not provision a principal, stop a host, approve a
  packet, invoke an applier, migrate a target, or broaden any native support claim.

## 2026-09-05 — Conflict-preserving staged promotion and recovery

- Digest-only journal allowlists were insufficient recovery evidence. The isolated candidate now retains exact
  preimages and every generated postimage, validates each digest against those bytes, and records bounded observed
  bytes or an explicit incomplete observation when recovery cannot establish the current state.
- Recovery must not validate all surfaces once and then restore them later. It now rechecks each surface directly
  before restoration, reads the restored bytes back, verifies all recovered preimages once more before journal
  removal, and refuses automatic retries after any conflict has been recorded so owner-attention evidence cannot
  disappear merely because a surface later returns to an allowed digest.
- Promotion and rollback read native settings back immediately after replacement and again before deleting their
  journal. Interference after replacement becomes an attention-required conflict without overwriting the unknown
  bytes; unreadable recovery state records the surface, phase, expected digests, and exception type without leaking
  exception text.
- Atomic replacement still is not compare-and-swap. A regression deliberately demonstrates that an unrelated
  writer between the final preimage read and replacement can be overwritten; this is evidence for the maintenance
  prerequisite, not a passing exclusion witness. Every known target writer must remain stopped for the transaction.
- Fifty-five combined approval, registry, promotion, and runtime-closure checks passed under Python 3.14, including
  new post-replacement, between-surface recovery, unreadable-state, rollback-readback, and failed-candidate recovery
  cases. The implementation remains only in the isolated candidate; no protected applier, registration, trust
  decision, live host, or migration changed.
- The wider Windows installer run passed 168 checks and reproduced only the six already recorded baseline defects:
  four text-mode CRLF-versus-LF expectations and two POSIX-only receipt-path lookups. Both changed files compile
  under Python 3.11, and their configured 110-character line limit is clean. Ruff remains unavailable in the
  isolated environment.

## 2026-09-05 — Activation-evidence authority fork

- Both existing witness writers accept caller-supplied success booleans, host metadata, limitations, and tool
  names. The checked-in observed Codex fixture has useful sanitized payload shapes, but its observation fields are
  also asserted booleans; parsing it would only move the same trust problem behind a file boundary.
- The contract says native trust, tool results, and denied-side-effect state must be captured independently, but it
  does not select the capturing principal or program, the authoritative raw record for each host, or the freshness
  and replay mechanism. Those are prerequisites for deriving a verdict rather than restating one.
- A collector inside the protected verifier/applier minimizes independent provisioning surfaces; a separate
  protected collector keeps activation evidence decoupled from promotion; host-native audit records offer stronger
  native provenance where they exist but may force unsupported results for hosts or interfaces without adequate
  records. All three can satisfy the words of the current item while producing materially different trust and
  support boundaries.
- This fork reaches owner-controlled provisioning and external host support, so it is not a reversible internal
  implementation choice. No witness API, fixture, test, protected state, live host, registration, or trust record
  changed in this iteration.

## 2026-09-05 — Astra-reviewed bounded activation collector selected

- The owner selected Astra's hybrid recommendation: activation evidence comes from a separate, bounded collector
  that may share an owner-controlled provisioning package with the verifier/applier but remains a separate process
  with no registration, trust, rollback, promotion-signing, promotion-state mutation, or promotion-key authority.
- Process placement does not make an input trustworthy. The collector may accept only independently authenticated
  host-native observations and complete operating-system observations covering the disposable probe interval;
  ordinary transcripts, caller assertions, sanitized fixtures, and signatures over unauthenticated inputs remain
  unverified observations rather than activation proof.
- Evidence is specific to an exact host version, operating system, scope, interface, and tool surface. Every claimed
  surface needs attributable harmless allow and denial outcomes plus proof that the denied effect did not occur; a
  single global allow/deny pair cannot bless an arbitrary list of tools.
- Source provenance, event attribution, native trust, freshness, and replay resistance are mandatory. If a host or
  interface lacks an authoritative source, or attribution is ambiguous, that surface stays unsupported. The target
  threat model trusts the host and operating system; arbitrary same-user host compromise remains outside the claim.
- Keeping capture parsing outside the mutation-capable applier reduces the consequence of a malformed host record,
  while closed evidence packets preserve a separate owner approval boundary. New privileges, credentials, privacy
  exposure, provisioning, or broader support claims still require a concrete owner decision.
- This iteration changes only the reviewed plan. No witness code, protected collector, signing key, packet, live
  host, native registration, trust state, migration, or support claim changed. The next unit removes the legacy
  paths that can turn caller-supplied booleans and fixtures into verified or protected activation claims.

## 2026-09-05 — Owner-agreed Ralph-only correction

- The owner corrected the product scope: Excubitor should make explicitly started Ralph runs easy to
  set up and complete unattended, while leaving ordinary development unaffected, including other tasks
  in the same project. Installing or trusting a project hook is not sufficient authority to arm a run.
- The owner agreed that default completion means reviewed, verified work committed on an isolated
  branch, followed by a report and termination of the run's enforcement. Automatic merging is optional
  and authorized once before the run; publishing and deployment have separate permissions. Work units
  should advance automatically, and routine choices must not become repeated owner approval gates.
- The earlier always-active baseline and mandatory-Ralph roadmap instruction conflict with that scope.
  The plan and repository guidance now record the correction. Earlier candidate mechanisms and evidence
  are preserved; runtime promotion machinery must not become a manual ritual for each ordinary run.
- Read-only attempts to inspect the registration, adapter, and uninstall source were denied by the
  active PreToolUse hook in an unrelated ordinary task. Do not hide paths, use an alternate source path,
  or edit guard code to evade those denials. Supported CLI diagnostics remain available.
- The CLI entry is the cli module, not the package itself: invoking the package failed because it has
  no main module. The documented uninstall preview succeeds and reports one Codex user-scope
  registration, zero installed files, and deletion of the settings file. A subsequent status call still
  lists the installation, native trust needing review, and stale prior enforcement evidence. The
  preview's wording does not establish that removing the settings file preserves unrelated content.
- Exact rollback capture and inspection remain incomplete, and the active host has not been quiesced.
  Do not perform live removal until the supported transaction's preconditions are satisfied. No native
  registration, trust state, installed skills, shortcuts, candidate runtime, or other host changed in
  this documentation correction. Runtime activation, isolation, and unattended completion remain open.

## 2026-09-05 — Native launching and evidence-based workflow defaults

- The owner wants a consistent Ralph command or action inside each app's existing window, plus CLI
  launching. Codex, Claude Code, and Antigravity are requested; Cursor is prospective. A separate
  control panel and an environment-variable launch ritual do not satisfy that requirement.
- Official host documentation provides candidate native entry points and continuation mechanisms.
  It does not establish protected opt-in, task isolation, cleanup, or unattended completion on the
  installed builds. CLI, headless execution, and each GUI surface require separate evidence.
- The research document distinguishes original practitioner experience, first-party demonstrations,
  documented host capabilities, owner requirements, and proposed Excubitor experiments. Later
  harness experiments changed reset and review policies as model capability changed; do not turn
  fresh context or intermediate review after every change into a universal requirement.
- Verify ordinary work immediately after completion in the same task, not only in another project.
  Skill lifetime and task lifetime need not equal Ralph-run lifetime. Test native handler failures as
  well as successful denials; fixtures alone cannot prove host behavior on timeout or malformed output.
- Gemini 3.1 Pro was consulted for research. Its unsupported claims and recommendations that conflict
  with the agreed scope were excluded after checking primary sources. A model response is not a
  verification witness. The evidence document contains the source links and proposed comparisons.
- This update changes only research and planning documentation. Live removal still requires rollback
  capture and writer quiescence. No hook, trust, runtime, launcher, skill installation, or support
  claim changed; no replacement registration or publication occurred.
