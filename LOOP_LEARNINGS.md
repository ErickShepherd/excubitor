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

## 2026-09-05 — Broad Codex hook removed; ordinary development verified

- The owner-operated transaction removed the exact Codex user-scope hook and its receipt after the
  app and its Codex processes exited. The captured configuration contained only the owned entry and
  had not pre-existed the installation, so settings-file deletion preserved unrelated content.
- All three rollback backups still match their captured byte counts and digests. The 175 recorded
  settings, installed-skill, and Claude-hook filesystem entries matched before and after removal.
  Fresh CLI status after reopening the app reports an empty installation list.
- Previously blocked adapter/configuration-source reads now succeed. Native shell and apply_patch
  writes succeeded in a disposable repository on main without Ralph opt-in. The main-branch probe
  needs initialized branch history: the initial unborn branch did not reproduce the old adapter's
  default-branch denial. After initialization, an offline adapter call denied the same class of edit,
  while the actual ordinary native edit succeeded. Keep offline and native evidence distinct.
- Windows app packaging redirected the apparent AppData state path into package-local storage. The
  owner shell and the app used the same account and 64-bit PowerShell but saw different contents at
  the apparent path. GetFinalPathNameByHandleW on open receipt/probe files identified the physical
  locations. Explicit physical-path capture and the documented child-process-only state-home override
  addressed discovery without moving state or changing persistent environment settings.
- The app runs as ChatGPT.exe in this Windows build. Closing a window did not establish process
  quiescence; the owner used the native tray Quit action. A bounded wait in the one-time maintenance
  helper removed the timing problem while preserving process and preimage checks. It killed no process.
- The neutral configuration resolver still selects the conservative baseline whenever reached, and
  the adapter still configures ordinary branch restrictions without verified Ralph-run activation.
  The implementation therefore needs correction before reinstalling any hook. Removal is complete;
  native Ralph-only activation, unattended continuation, and replacement support remain unverified.
- No replacement hook, native trust grant, other-host registration, merge, push, or publication was
  performed. The installed Codex skills and pre-existing Claude placeholders were preserved.

## 2026-09-05 — Disposable native lifecycle apparatus prepared

- Before choosing protected activation state, measure native event delivery and continuation in a
  disposable project. The new standalone observer records field shapes and hashed identities without
  retaining raw prompt, command, or transcript content. It is not imported by installed adapters.
- A bounded Codex exercise distinguishes task/project identities, requests at most two continuations,
  and vetoes only a disposable test marker. Its synthetic trigger and writable SQLite data are test
  apparatus, not owner authority. Offline tests explicitly retain that limitation. A host response is
  not evidence of a native veto or continuation until the corresponding native operation is observed.
- Python's SQLite connection context manager commits or rolls back but does not close the connection.
  The first Windows apparatus test exposed locked files during cleanup. Explicit connection closing
  fixed it; all 19 apparatus tests then passed on Python 3.14.7 and Python 3.12.14.
- Codex documentation describes Stop continuation as a synthesized user prompt, while prompt hook
  input does not document an independent owner-origin field. Treat prompt text and session identity as
  observations; do not promote them to protected activation evidence without an independent source.
- Claude Code and Antigravity have observation normalization only in this experiment. No native host
  run, registration, trust change, activation implementation, or unattended Ralph completion is claimed.

## 2026-09-05 — Native Codex CLI continuation and ordinary-work isolation observed

- With separately authorized temporary project hooks, Codex CLI 0.153.4 on Windows performed two
  native Stop continuations, enforced a harmless apply_patch veto, and then allowed the requested
  second edit. The blocked marker was absent before any later ordinary edit was attempted.
- Ordinary edits succeeded before the exercise, in another task while it was active, afterward in
  the original task, and after registration removal in a fresh CLI. The parallel task deliberately
  used the vetoed filename in a separate directory, so a mistakenly shared active state would have
  rejected it. Its native event fell between exercise start and end and received no veto.
- Stop continuation retained the same native turn identity and did not refire UserPromptSubmit.
  The three Stop events carried stop_hook_active values false, true, true. Native CLI exits produced
  SessionEnd observations. Do not infer GUI, headless, worker, crash, or cancellation semantics.
- The exact hook file was removed after both test CLIs exited. Fresh native hook inspection showed
  zero installed/active hooks. Codex retained nine fixture hook trust records and project trust;
  the inspected native menu provided toggles but no forget-trust action. Preserve this distinction
  instead of claiming every trace of the temporary setup was erased.
- A combined cleanup command was rejected by command policy. Read-only reinspection confirmed the
  exact file and unchanged bytes; a single literal-file removal succeeded. No alternate tool or
  settings rewrite was used to bypass the rejection.
- These observations validate the bounded native apparatus. Its writable state and synthetic start
  remain unsuitable as production authority. Protected activation and completion verification still
  need implementation and native evidence; the always-active production adapter was not changed.

## 2026-09-05 — Protected lifecycle candidate and native storage denial

- The shared host-owned lifecycle preserves task/project scope, units, acceptance identities, attempt
  budget, deadline, and default retain-branch completion. Multi-unit progress, repairs, same-task
  resumption, cancellation drainage, and completion prerequisites are library operations, without
  owner reauthorization between units.
- Review found that putting directory identity in the lookup key could make a replaced active project
  appear inactive. Lookup now retains textual scope and separately validates live identity. Ended-run
  history skips live-directory validation so it cannot capture a recreated project. Terminal status
  requires recorded worker drainage. Observed expiry persists before a failed completion returns, so
  later clock correction cannot reopen it.
- Codex CLI 0.153.4's native Windows :workspace subprocess could edit an ordinary file but could not
  forge activation, advance or cancel the run, claim verification/review/completion, erase SQLite rows,
  or rewrite the external acceptance file. The parent confirmed unchanged authority and acceptance
  bytes, then closed the dummy run after subprocess exit. No hook or trust setting was added.
- The first expanded probe failed an assertion because changed limits correctly produced a contract
  conflict before a write instead of the expected storage error. That report is preserved. The fixed
  probe distinguishes this invariant rejection from native filesystem denial.
- This is a protected storage candidate, not an authentication service or independent verifier.
  Host APIs take trusted approval and candidate/check/review/liveness facts; there is deliberately no
  worker-callable mutation endpoint. Native owner authentication, writable-surface admission, crash
  routing, independent evidence collection, and the actual launcher remain unfinished. The always-active
  adapter is unchanged and still unsuitable for reinstallation.

## 2026-09-05 — Native confirmation bridge and independent output comparison

- Codex CLI 0.153.4 supplied task/workspace context in native MCP metadata separately from tool
  arguments and displayed a form with a false default. The test selected cancel and accept in that
  native UI. Cancellation created no run; acceptance created the exact task/project record with its
  original protected check definitions. Another task in that project stayed inactive. Copied metadata
  or a client-name string remains insufficient to authenticate arbitrary peers or admit every tool.
- The shared start handshake consumes a connection-bound pending confirmation once, freezes its
  exact contract and check definitions, and rejects conflicting scope, replay, changed checks,
  malformed replies, expired approval, and late responses after transport cancellation. It is an
  internal component; the disposable MCP bridge is not a registered production activation service.
- Five native read-only subprocess cases used one frozen output oracle. Wrong output, a forged green
  summary, and an early zero exit failed. Correct output passed. An oracle overwrite was denied and
  the original bytes survived. A passing output check did not bypass independent review. The fixture
  used dummy Git facts; general execution containment and committed-candidate collection remain open.
- The native CLI killed its MCP process without running Python cleanup. The accepted record stayed
  active, and the trusted parent closed that worker-free fixture after both processes exited. Do not
  depend on EOF/finally to revoke a real run. The new native SessionEnd binding records interruption
  without inventing worker shutdown; its live one-hook experiment is prepared but not registered.
- Process-only CLI MCP overrides needed no hook registration or new native trust. The top-level CLI
  rejected the sandbox helper's -P flag; interactive CLI used its verified -s workspace-write option.
  Both test CLIs exited. No production hook, trust rewrite, merge, push, or publication occurred.

## 2026-09-05 — Native SessionEnd delivery and ordinary-task isolation

- The owner approved the exact frozen one-hook test, native trust, and removal. Codex CLI 0.153.4
  clamped the requested ten-second SessionEnd timeout to three seconds. The native event still recorded
  interruption for the exact confirmed dummy run, retaining its protection state without claiming
  completion or worker drainage. MCP cleanup again did not run.
- An ordinary task in the same project edited its file successfully and produced an inactive
  SessionEnd observation. The test never launched workers. Normal exit is now evidenced; forced
  termination, crash reconciliation, resume behavior, and worker supervision are separate open claims.
- All test processes exited. The exact unchanged temporary hook was removed and a fresh CLI showed
  zero installed or active hooks. Native UI updated the existing fixture SessionEnd trust entry; it
  remains, while the rest of the parsed configuration is unchanged. No manual trust rewrite occurred.
  The trusted parent closed only the dummy record after preserving the native interruption evidence.
- The final local report initially failed while reading UTF-8 terminal evidence with Windows' default
  legacy encoding. Explicit UTF-8 fixed the report; the existing configuration capture was preserved
  and checked byte-for-byte. This did not affect the native test or mutate its run before the retry.

## 2026-09-05 — Shared supervision and a real multi-unit CLI job

- The shared supervisor now drives an already authorized run through workers, committed checkpoints,
  frozen output checks, repair, independent review, and completion. It reloads original checks each
  attempt, holds an OS lock against duplicate supervisors, and leaves interrupted protection when an
  in-flight journal or failing backend cannot prove drainage. Worker exit zero or a green summary is
  insufficient to complete the run. Repair feedback includes bounded actual verifier output.
- A Windows job owns the suspended root before execution and retains descendants after parent exit.
  Tests cover timeout, cancellation, output flooding, controller death, and breakaway requests. On one
  Python version the breakaway flag was accepted while the child remained in the supervisor's job;
  the corrected assertion checks actual membership and termination instead of demanding an error.
- The first model-worker attempt omitted the existing Windows sandbox implementation from isolated
  config. Native policy refused file operations and the run exhausted its budget without completion.
  Carrying forward the already provisioned native sandbox fixed startup; no policy bypass flag was used.
- A later job completed, but its configuration comparison caught native CLI project-trust persistence
  despite --ignore-user-config. The disposable project entry remains and is reported. The final driver
  refuses fresh enrollment and requires an already trusted completed fixture with a preserved branch.
- The final real Codex CLI job built two arithmetic features, observed an injected tripling bug fail
  unchanged doubling checks, repaired it without owner intervention, and passed all four original checks.
  A separate reviewer read the code and ran ten additional cases. Three worker attempts and thirteen
  supervised process calls produced a clean committed isolated branch, preserved base, and inactive run.
  Its native sandbox child was observed in the supervisor job; all calls drained. Native configuration
  stayed byte-identical in this final run. No hooks were installed, and no merge or publication occurred.
- This closes the small real CLI demonstration, not the full product. A production owner-start connection,
  complete writable-tool admission, durable crash reconciliation, native GUI entry points, and other
  vendor adapters still need implementation and verification. Ordinary development has no new policy.

### Native confirmation and controller recovery, 2026-09-05

- The native Start action now dispatches the shared supervisor after the exact pending form is accepted.
  It takes no worker-supplied authority arguments. Closing the MCP connection only retires pending
  offers; it cannot certify drainage or disarm accepted work. The action remains candidate/test wiring.
- A trusted parent can recover a crashed controller after its Windows job is observed empty. Preserve
  original authority and torn journal bytes, then consume the next original attempt. A crashed parent's
  own unacknowledged launch remains an unresolved fence, never permission to restart by elapsed time.
- The first crash test caught that ordinary worker semantics wait for surviving children. Controller
  supervision needs an explicit stricter mode: terminate remaining descendants when its root exits.
  Live Windows tests now cover that distinction, original deadlines/budgets, cancellation, handled
  denial without retry, torn journals, and watchdog death killing its controller without blind takeover.
- In the connected native CLI run, four real workers covered a forced controller crash, two features,
  and repair of an injected bug. Eight executions of the four frozen checks and one independent native
  review led to completion. The watchdog recorded both controller trees drained and preserved the base.
- The final reporter exposed another process boundary: subprocess.run timed out a Windows Git launcher
  while a child retained its output pipe. The failed report and identified helper are preserved. Windows
  candidate inspection now supervises the full Git tree with bounded output/time and explicit input and
  environment. A separate native MCP inspection using the correction verified the completed candidate
  and final drainage. Native configuration remained byte-identical; no hook or permanent tool allowance
  was installed. The full GUI/product rollout and takeover after watchdog loss remain unverified.

### Recoverable Windows ownership, 2026-09-05

- Creating a suspended process and assigning it to a job in a later call leaves an orphan window if
  the owner dies between calls. The job-list process attribute performs both in one Windows operation.
  A real owner-death test now verifies that even a never-resumed root is terminated.
- Named host-owned kernel jobs let a replacement watchdog reconcile its exact old tree under the
  same lock. Reopen access denial is not absence evidence. Global object names avoid false absence
  across Windows login sessions, without registering any global hook or service.
- An empty job count can precede complete process termination and release of the controller lock.
  Recovery also waits for the snapshotted process handles to signal before resuming the original job.
- Three watchdog lifetimes cannot reset the controller launch budget. Original attempts, deadline,
  and checks remain fixed; legacy or malformed histories cannot authorize another launch.
- Windows test runs printed handled access-violation notices despite passing assertions. An observation
  handler, which neither handled nor suppressed exceptions, attributed them to a loaded GameGuard
  module in both the previous process backend and the new backend. Preserve the noisy logs and this
  environmental limitation; a zero test exit alone does not explain a native exception.
- Native sandbox isolation of named jobs and actual native same-task reconnect still require evidence.
  Component recovery does not establish app-exit survival, GUI support, or a completed product.

### Native isolation and reconnect limits, 2026-09-06

- With the game closed, all 29 process/recovery tests passed without the earlier exception notices.
  The later admission/recovery run passed 50 tests and 7 subtests without those notices. This supports
  the environmental correlation; no game-specific behavior belongs in Excubitor.
- The actual unelevated Windows sandbox denied writes to the external acceptance file and mutation
  access to the host-owned named job, but allowed a query handle. Read access can retain the object's
  lifetime after host death. The probe correctly failed; the approval parser already excludes this
  mode and now has regression coverage for that exclusion. Elevated-mode isolation is still unverified.
- A native app-server task with no history had no saved rollout to resume. Explicitly labelled fixture
  history through the native injection API made the task persistent. Its identity survived server loss;
  another task in the same project kept a distinct identity. Both server lifetimes drained completely.
- Direct app-server MCP calls supplied a task ID and progress token, without the interactive CLI's
  active-turn envelope. All such calls failed the approval parser. Protocol identity does not establish
  protected Ralph resumption or authentic authority on an arbitrary connection.
- The final config comparison caught Codex saving project trust automatically inside the fresh isolated
  test homes. This repeats the earlier fresh-project enrollment hazard. Preserve the failed packets
  and entries for owner review; do not count phase-level RPC success as a clean native run. The updated
  driver requires an already trusted, separately approved disposable profile, checks configuration after
  each lifetime, and has offline refusal coverage. It has not yet been rerun against an approved fixture.
- All new task state and temporary files use the relocated task storage. The normal native profile was
  not used by these probes. No model turn, saved MCP registration, hook, or sandbox provisioning ran.
- The commit broker classified the reconnect probe's synthetic protocol-message example as a model
  conversation record. Following its private-retention instruction, the whole exploratory probe and
  its tests remain in private task storage. The broker and its policy are unchanged. Repository docs
  retain the findings; the native named-job probe and admission-parser regression remain code candidates.

### Approved isolated native reconnect check, 2026-09-06

- The owner approved reuse of one exact disposable profile and project for the no-model protocol
  check. No authorization was inferred from the automatically created trust entry itself.
- The corrected probe passed on the native Windows CLI: the original task, session, and project
  survived app-server process loss and resumption; a second task in the same project remained distinct.
  Native configuration stayed byte-identical after each lifetime and at final inspection. Both process
  trees drained, with nine and ten observed processes respectively, and neither timed out.
- Direct MCP calls still lacked the required turn context and were rejected by the approval parser.
  There were no saved credentials, model turns, permanent tool registrations, hooks, or sandbox setup.
  The result proves protocol identity persistence with unchanged approved fixture settings. It does
  not establish protected Ralph resumption, elevated-worker isolation, GUI support, or another vendor.

### Native Windows identity and existing-sandbox prerequisites, 2026-09-06

- The native unelevated worker and its host share the same user SID and medium integrity level.
  Its actual process was observed in the host kernel job, and the whole tree drained. Query access
  remained possible while mutation and acceptance-file writes were denied. A label-only distinction
  at the existing integrity level cannot close this gap; no weaker mode was admitted.
- The access probe can now prepare reuse of an already provisioned elevated native home. Its
  prerequisite checks perform no setup and retain only hashes of config, setup marker, and native
  sandbox credentials. Offline tests cover missing setup, unsupported state, and protected-file drift.
  That execution mode is not live-verified. Existing native support files can still be written in the
  selected home, so a storage restriction covering that drive must be resolved before invocation.
- The exact existing-sandbox test is prepared in private task storage. No new Windows account,
  firewall configuration, credential copy, or native installation was performed. Native approval
  context and full protected reconnect remain open; synthetic identities are not a substitute.

### Approved existing elevated sandbox access check, 2026-09-06

- The owner authorized a narrow native-runtime storage exception for one prepared check against the
  existing Windows sandbox. Its worker used a different Windows account and was denied query,
  termination, assignment, DACL, and owner access to the host-owned named job. The absent-object
  control returned a distinct absence error. The unelevated mode remains excluded.
- Ordinary project writing succeeded and the external acceptance file retained its exact bytes.
  The actual worker appeared in the runner's containment job; all eight observed processes drained
  within the limit. Native configuration, setup-marker, and sandbox credential fingerprints matched
  before, after, and at independent reinspection. No explicit setup or credential copy was needed.
- The named access target and actual containment job are separate kernel objects. This result proves
  the tested access denials and containment observation, not native forced-owner-death recovery,
  protected Ralph reconnection, GUI entry points, other writable tools, or cross-vendor support.
  Reports and test artifacts remain in private task storage; production adapters remain unchanged.

### Reconnecting the native supervised candidate, 2026-09-06

- The native demonstration adapter had a reconnect-capable core but no reconnect callback, and its
  create-once log prevented another connection lifetime. The candidate now dispatches the original
  watchdog, checks agreement and oracle bytes first, and retains separate logs and outcomes.
- A remembered attachment is not evidence that a controller thread is still alive. The native action
  can now ask its host about current thread liveness, while the watchdog lock and kernel observations
  continue to establish process safety. Closed transports cannot issue another Start.
- Real Windows process tests complete the original fixture after losing its connection process,
  both with and without a retained job handle. They preserve original limits, exclude another task,
  and request no new approval. A test server's injected exit applies only to its original lifetime.
  These tests use fixture identities; they do not authenticate native task resumption.
- The prepared native fault runs after the first actual worker drains, with a disclosed fixture child
  still alive. It exits only its own test server, then requires exact native task resumption. The live
  rehearsal remains pending; project trust from an old location cannot authorize a relocated fixture.
  No native application, native trust change, or production installation ran while preparing it.

### Approved native connection-loss rehearsal, 2026-09-06

- The owner approved one new disposable project trust entry and the existing native profile's runtime
  storage. The native trust-delta check accepted exactly that entry. Config, sandbox setup, and
  credential fingerprints then matched the sealed baseline. No credential copying or provisioning ran.
- Installed interactive CLI help differs from exec help: the config-isolation flag used by exec is
  not accepted at the interactive root. Quoting a simple dotted-key segment also made the override
  target a different invalid server. Both launch errors preceded activation and were preserved.
  Supported process-only feature/server overrides fixed the private launchers without changing native
  permissions or saved settings. Windows PTY submission used LF in a separate write after typing.
- The native job was confirmed once. After the first worker drained, the disclosed test connection
  and its watchdog exited with a live fixture descendant. Resuming the original interactive CLI task
  supplied the same authentic task binding; Start reconnected with the consumed attempt intact and no
  new confirmation. The watchdog recorded the exact old kernel job absent before replacement launch.
- Four of the original six attempts completed both units. Two unchanged checks caught the injected
  arithmetic fault, then automatic repair, all four checks, and independent review passed. Independent
  inspection confirmed original contract and oracle bytes, a clean committed isolated branch and its
  unchanged base, all thirteen recorded executions drained, and both exact controller jobs absent.
- Another native task in the same project remained inactive while Ralph ran. The original task became
  inactive after completion. Ordinary native file creation worked without Ralph activation; its bytes
  were independently inspected and the exact test file removed. No saved tool allowance, registration,
  hook, merge, or publication occurred. Private raw evidence and initial launcher failures are retained.
- The test driver explicitly reopened the original task. This proves the bounded Windows CLI
  reconnection path, not automatic reopening, a crash during a model turn, app-closed continuation,
  production launch UX, full native-tool admission, GUI surfaces, or other vendors.
- The first independent check matched all native fingerprints. After the native sessions exited, the
  final whole-profile comparison caught one unrelated project trust addition. The owner confirmed it
  came from separate concurrent work. Preserve that raw comparison failure and both snapshots instead
  of silently changing the baseline. Sandbox setup and credential fingerprints stayed unchanged, and
  the retained candidate still matched after ordinary-file cleanup. No settings restoration or extra
  native run followed the difference. Two model-task rollouts were archived; the trust-only task had
  no matching saved rollout in the dated directory, so its captured native UI remains the evidence.

### Normal-start proposal and command candidate, 2026-09-06

- The verified Start protocol still depended on a fixed host-built test plan. A new optional planner
  accepts proposed work units and input/output cases, resolves only host-admitted named runners, and
  reuses host defaults for omitted limits. Its required admission callback preserves the host checks
  previously performed by fixed-plan callbacks. Neither proposal conversion nor tool discovery starts
  work. The existing native confirmation remains the only activation path in this component.
- Caller edits after preview cannot alter the pending agreement. Replacing a pending preview is
  refused. Active jobs reject replacement proposals and reconnect with empty arguments; changes to
  defaults cannot reset their original attempts, deadline, or checks. The caller cannot specify native
  scope, executables, environment, authority storage, approval, or additional completion powers.
- Exact-task status can now report recorded completion or cancellation without reactivation. Database
  insertion order selects the last accepted job; revision counts, UUID order, and wall-clock guesses
  do not establish that ordering. A completed record describes its retained snapshot, not later edits.
- The new explicit command skill is a candidate outside normal discovery, with Codex implicit
  invocation disabled. It uses the native tools, requires the actual native form, and has no manual
  loop or installation fallback. Ordinary development and discussion of Ralph remain outside its scope.
- Component tests use fixture transport and host facts. They do not supply native discovery or
  production admission evidence. Input/output verifiers are the first supported proposal format;
  running worker-editable tests and freezing only their command would not freeze acceptance criteria.
  The existing fixed-plan probe protocol and installed skills remain unchanged.
- Final focused verification passed 124 tests and nine subtests, including the prior native-action,
  approval, lifecycle, supervisor, and connection-process regressions. No native app was launched for
  this change; the fixture transport tests do not broaden the previously observed native support.

### Project execution candidate, 2026-09-06

- The fixed demonstration backend embedded its own specification, filenames and fault injection.
  The new project backend instead reads the actual agreed goal, units and original checks for each
  worker and review. The launching project and worker checkout must not overlap. A host admission
  callback and an authorized commit path are required; neither comes from the proposed job.
- Checkpoints compare actual bytes with the committed tree before requesting retention. They send
  only changed paths, including additions and deletions, because an exact-path broker can reject a
  request containing unchanged files. Unchanged candidates need no empty commit. Callback success
  cannot certify a dirty or uncommitted candidate; independent Git inspection still decides that.
- Runtime configuration, nested Git metadata, redirected Git markers, and unsupported tree sizes
  are refused before retention. Commit refusal preserves partial work without claiming completion.
  Native subprocesses use the selected model, bounded process supervision and explicit child-only
  permission settings. Those settings narrow execution but do not prove all-tool native admission.
- Offline integration exercised two different proposed tasks with real disposable Git commits and
  actual program output. Each repaired a failed original check and a separate review rejection before
  completion. The initial test helper reversed cancellation and drainage fields; correcting its
  fixture values resolved those failures. The native transport was never launched by those tests.
- The private live-test adapter now composes native proposal confirmation, the watchdog, the project
  backend and independent inspection. Its scoped MCP connection and explicit skill are staged for a
  new disposable launch project with a separate candidate. Live registration, two exact native trust
  entries and existing-profile runtime storage still require the prepared test's owner authorization.
  The old fixed-plan and fault-injection experiments remain unchanged.
- Final verification passed 148 tests and nine subtests, including the previous proposal, approval,
  lifecycle, candidate, supervisor and connection-process cases. Formatting, lint, whitespace and
  the private-path/leak check passed. The native launch itself remains pending, not implicitly green.
- The commit broker refused an unapproved dummy email address in the new Git test fixture. The
  candidate and read-only diagnostic remain private. The fixture now uses the repository's existing
  approved test identity; no broker rule or enrollment was changed.

### Native project launch and startup correction, 2026-09-06

- Actual command discovery and a native confirmation worked. The initiating agent read the README,
  proposed three units and ten checks, and corrected rejected check names before one accepted form.
  The validation error now explains the allowed characters instead of merely asking for a short name.
- A disabled MCP entry still needs a valid transport. Combining a clean native profile with a lone
  disabled node entry failed before every worker's model call. The launcher now supplies an empty MCP
  table, and a real read-only native startup returned the expected response without tools or edits.
- Startup configuration errors are host failures, not work to repair. The old driver spent all six
  attempts on the same error; the regression now verifies interruption after one attempt, unchanged
  agreement and candidate, and retained process evidence. Candidate output with the same wording
  remains an ordinary failed check. The exhausted native job was not restarted or given more attempts.
- No native unit, acceptance check or review completed in the failed project run. Both source copies
  stayed unchanged and every recorded process tree drained. Ordinary native editing succeeded after
  the fast failure; it cannot establish isolation during running work. The owned temporary project
  registration and skill were removed after the disposable sessions exited. Only the two authorized
  project trust additions remain; sandbox credentials and unrelated settings were preserved.

### Fresh native project test, 2026-09-06

- A new authorized packet and confirmation preserved the previous exhausted run. The corrected
  launcher completed two real native implementation turns and retained both commits automatically.
  A separate native task reported no active Ralph job and completed ordinary file editing while
  the first worker was running. This closes that specific during-work observation.
- Four subsequent native turns failed with the model service's capacity error. Two failed before
  output, and two after reading context. Immediate retries consumed the remaining attempts before
  host acceptance or separate review. The worker's local test summary cannot replace those missing
  gates. The run remained blocked at six attempts, with its clean partial branch and checks retained.
- Native service availability and candidate-code failure need different recovery handling. Bounded
  waiting must preserve the original deadline, attempt cap, cancellation and configured model. A
  failure reason should also be available in native status. Neither improvement was implemented by
  this test; no model fallback, reset or automatic replacement job was used to evade the exhausted cap.
- Independent inspection verified two retained unit commits, the unchanged base and agreement, all
  six worker trees drained, the exact controller job absent, and the prior failed run byte-identical.
  The temporary project files were removed after clean session exit. Only the two authorized native
  trust additions remain. Full project-backend completion, GUI and other vendors remain unverified.

### Capacity-aware native retries, 2026-09-06

- The native service can fail before model output or after tools have already run. Only its observed
  terminal event is classified as capacity failure; nested program output and ordinary code errors
  cannot request this treatment. Partial bytes are preserved and every failed launch still counts.
- The supervisor waits within the accepted deadline, supports cancellation after drainage, and retries
  an unavailable reviewer against the same verified candidate without another implementation turn.
  Attempt exhaustion remains blocked. A crash during waiting requires shutdown reconciliation.
- Native status now explains capacity failures, including blocked jobs. The launch skill describes
  accepted check names and avoids redundant work units for checks and review that the host already owns.
  Component results do not establish native recovery from a real service outage or full project completion.

### Completed project-backend CLI run and legacy installation correction, 2026-09-06

- The next fresh run completed two implementation units, ten original checks and an independent review
  in two attempts. Both units were committed automatically. Actual native editing worked concurrently
  in another task and after completion in the initiating task. Independent inspection confirmed the
  agreement, checks, clean isolated candidate, preserved base, drained workers and inactive run.
- No capacity failure occurred. This proves normal project completion, not native recovery from a
  real capacity outage. Earlier exhausted packets remain unchanged. The three owned project files
  were removed after native session exit, preserving the two authorized trust additions and other settings.
- The first independent inspector treated reviewer commentary as JSON. Its failure is preserved;
  inspection now separately requires a completed native turn and validates the final structured report.
- The old installation CLI still offered always-active hooks, including user scope by default. New
  legacy registrations now fail without writing in either scope; previews, diagnostics and removal
  remain. The isolated transaction library is retained while the scoped Ralph installer is unfinished.
- A pre-existing Windows test fixture used text-mode CRLF while testing the documented canonical-JSON
  byte round trip. The fixture now writes canonical LF bytes explicitly; the equality assertion and
  transaction behavior are unchanged. Arbitrarily formatted settings retain their parsed values during
  legacy uninstall; only rollback promises verbatim restoration regardless of original formatting.

### Additional native boundary evidence, 2026-09-06

- A separate native diagnostic allowed patch and shell writes inside the candidate and rejected an
  external shell write. The native router also logged an outside-project patch rejection, although
  its JSON event stream omitted the rejected path. Preserve that narrower evidence claim instead of
  treating the model's final explanation as a complete tool receipt.
- All 57 observed processes drained, native settings and protected bytes stayed unchanged, and the
  host removed its exact owned canary and rechecked the clean completed candidate. No new run or
  registration was created. The earlier exhausted packets stayed unchanged.
- Current first-party documentation excludes native Windows from Claude's built-in Bash sandbox.
  Antigravity documentation differs between its Windows AppContainer feature claim and its dedicated
  sandbox platform table. These are integration gaps to verify, not permission to weaken the boundary
  or present the successful Codex CLI demonstration as cross-vendor or GUI support.

### Isolated Linux worker preparation, 2026-09-06

- The owner chose a Linux worker separate from recovery environments. A new QEMU VM keeps its
  disks and task data on D: without changing WSL or Docker. A D: WSL distribution alone would not
  address the existing shared swap default. Root-owned Linux authority and host-only Windows
  permissions protect the new VM's control keys and disks; no host directories are shared.
- Nine live cgroup tests passed, including detached children that close their pipes, actual memory
  and process caps, output limits, cancellation and permission denials. The fixed bootstrap joins
  the cgroup before executing untrusted code and drops to a separate UID with no_new_privs.
  Killing the controller alone is insufficient: admission still needs the enclosing VM lifetime
  and crash reconciliation. Do not reuse this component as an unisolated Linux model launcher.
- The first Bubblewrap canary failed before workload execution under Ubuntu's namespace policy.
  A profile limited to the packaged launcher was added inside the disposable VM; the general
  namespace restriction remained enabled. Writable and read-only canaries then passed with no
  control-file, host-path or network access. Tested guest source hashes matched the host source.
- Hardware-accelerated VM startup worked. Initial seed/media and command issues, a stalled full
  download, guest DNS failure and the ten-minute VM stop remain recorded in private evidence.
  Verified byte-range download and a temporary SSH setup tunnel resolved transfer/setup problems.
  The restricted execution session has no general egress; authentication and provider-only traffic
  still require their own checked path. Claude version/help success is not a completed Claude job.

### Claude project transport candidate, 2026-09-06

- Native help and first-party documentation support noninteractive permission denial, explicit tools,
  fresh sessions, disabled customizations and structured results. Flags alone are not an isolation
  witness. The adapter requires an admitted executor and never falls back to direct local execution.
- The independent reviewer has only file-reading tools. The host executes the frozen acceptance
  programs separately under read-only candidate access. Model prose and nested tool output cannot
  substitute for a uniquely completed native review with the required structured fields.
- Component fixtures reject changed model/tool/session metadata, duplicate JSON keys, conflicting
  terminal messages, prose verdicts and unsuccessful or undrained executions. These tests do not prove
  the installed native CLI actually emits the expected events with this complete flag combination.
- Host memory remained below the 4 GiB guest plus 1 GiB headroom threshold. The private VM helper now
  enforces that admission internally before creating a session packet. No Claude login or model job
  was attempted during this continuation; the earlier diagnostic packets remain unchanged.

### Existing Ubuntu WSL path, 2026-09-06

- The owner directed reuse of the installed Ubuntu distribution. Native inventory distinguishes it
  from the recovery distribution. It boots with systemd and cgroup v2; no separate 4 GiB VM reservation
  is necessary. The earlier threshold was a conservative QEMU setup choice, not measured application
  demand. A full Claude startup diagnostic peaked near 240 MiB; real coding/build demand is unmeasured.
- Dependencies were checksum-verified and extracted on D:, without installing distro packages. The
  source, evidence and new native profile stay on D:. Ubuntu's existing system disk stays on C:.
  Shared WSL settings and recovery distributions were not changed or started.
- The initial canary allowed creation of a fake `/init` file in the sandbox's private root; it did not
  access the host interop binary. The corrected sandbox remounts that private root read-only. Native
  candidate/read-only, control-path, host-path and network boundary tests then passed. Failed packets
  remain preserved. Killing the bounded systemd controller also drained its detached worker child.
- The complete native review launch accepted the explicit flags and reached missing authentication.
  Safe mode still advertised built-in skills; disabling slash commands removed them. Native help alone
  was insufficient to infer their absence. No model call or authenticated tool execution occurred.
- Use the intended canonical model name `claude-opus-4-8`; the saved `opus-4.8` shorthand generated an
  unrecognized-model warning. Do not replace it with a moving `opus` alias or edit unrelated settings.
- A native authentication error used `subtype=success` together with `is_error=true`. Preserve the
  full event framing and error flag. The new classifier interrupts after retaining evidence rather
  than consuming repeated work attempts. A browser-code login requires interactive stdin; the user
  helper passes that input directly to Claude and does not save it or ask for it in chat.

- A stricter Windows-executable canary subsequently reached the inherited WSL binary loader even
  though `/init` was hidden. It failed inside the loader before completing its harmless command;
  treating path hiding as proven interop isolation would have overstated the earlier evidence.
- Linux binary-format handlers inherit from parent user namespaces until the child initializes its
  own table. A separate canary creates an empty private table, unmounts it and drops all capabilities
  before the worker starts. Native Windows execution then returns an executable-format error, and
  ordinary WSL Windows execution remains successful. An initial bootstrap lacked the required private
  namespace capabilities and failed before dispatch. The corrected bootstrap is root only inside its
  new user namespace, mapped to the unprivileged outer worker; no global registration changes occur.
  Incorporate this tested boundary into the real Claude executor before admitting model tools.

### Preserve the existing Windows Claude login, 2026-09-06

- The owner reports an existing Windows login and that another WSL login would disrupt it. The
  prepared login helper is now disabled before process launch, and its user instruction is withdrawn.
- File metadata confirms a Windows credential file exists and the separate D: WSL profile has none.
  The prior missing-authentication result came from the empty profile, not the Windows installation.
  No credential contents were inspected, copied, refreshed or changed during this correction.
- Anthropic documents a long-lived token for unattended scripts, but its creation still requires
  authorization and the documentation does not guarantee that another login remains intact. Do not
  mint one or share rotating credentials as an automatic workaround. Authentication coexistence
  remains open; sandbox development can continue without touching the working Windows login.

### Reusable offline Ubuntu worker, 2026-09-06

- The previously separate namespace and cgroup probes now form a reusable executor. It validates its
  actual bounded service, serializes candidate access and uses fresh namespaces for each command.
  The private binary-format table and capability drop now run before every requested program.
- Native tests exercised read-only remount resistance, hidden host paths, hard links, environment
  injection, cancellation, detached descendants, output flooding, memory/process limits and the
  actual Claude version command. The final suite passed 28 checks. The socket-entry case was skipped
  because the D: filesystem itself refuses socket creation; do not claim a native socket witness.
- Ordinary WSL Windows interop was intermittently absent before the new executor ran. Preserve those
  failed baselines. The final suite had working ordinary interop before and after and returned
  ENOEXEC for the real Windows binary inside the sandbox. No WSL configuration was changed to get it.
- Separate native tests killed the controller and let the service deadline expire. Both removed
  detached children without delayed writes. A service with KillMode=process was refused before
  dispatch. These are process-lifetime results, not automatic app or machine restart recovery.
- Python 3.10 ran the Ubuntu diagnostic module; the package still declares Python 3.11 or newer.
  All new artifacts and test dependencies stayed on D:. Authentication, provider-only access,
  production transport/admission and complete Claude model execution remain open. No existing
  credentials were copied, refreshed or changed.

## 2026-09-06: explicit native development baseline

The owner chose a smaller ordinary-development loop rather than further hostile-code sandbox work. In an isolated candidate, structured Claude edits plus the maintained Windows command API completed a real median fix, a model-requested test, the frozen host check, fresh review and a clean retained fixture branch after one start. Both native calls identified Fable 5.1; no intermediate owner input was needed. This is bounded CLI evidence, not production registration or credential isolation.

Two practical findings: Windows command/exec rejects custom output caps, and extending the workspace profile while adding a read rule does not make verification read-only. Extending the read-only profile corrected that mistake and a native write-denial witness passed. Separate checks confirmed outside-write denial and cancellation of Python plus its detached child while an ordinary command still worked. Preserve the failed preflights as well as the passing evidence. The new development baseline is explicit; strict runtime admission was not weakened.

## 2026-09-06: prepared-job Claude CLI

The ordinary CLI now has explicit Ralph start, status and stop commands over the
existing supervisor. A prepared native job completed two statistics functions,
received a deliberate temporary dependency failure, retried without another owner
prompt, and passed the original check and fresh Fable review. The test harness
restored the dependency; the production command contains no injected failures.
A separate native stop request drained the active Claude worker and persisted
cancellation. The focused regression set passed 101 tests. Candidate preparation,
the authorized committer, and native account provisioning remain host inputs;
this foreground entry point does not install an app integration or recover from
controller crashes. The consolidated source and CLI use the existing commit broker.

## 2026-09-07: plain-goal preparation and recovery

Native Claude can invoke the ordinary CLI to prepare a separate checkout and a
reviewable job from a plain goal and reusable profile, then start it after review.
The planner needs the existing test source as context; command names alone led to
ambiguous iterator and spread wording. The owner's goal now remains verbatim.
Executable paths are checked before planning because an app update moved the
installed Codex executable between days.

The Sonnet 5 rehearsal completed both units and independent review after its
launching Claude command returned. Fable had reached its limit before planning;
the alternative model was selected before any job started. A separate fault test
killed a controller and then its watchdog. Automatic controller recovery and a
later resume completed the same agreement without extending its limits. Existing
named-job recovery supplied the process evidence; no new host service was needed.

### Vendor-neutral model adapters, native Windows comparison

The planner and launcher had embedded Claude construction even though the
supervisor was already shared. Extracting structured model calls from edit
application lets Claude and Codex reuse planning, work, checks and fresh review.
Keep model and execution descriptors separate: the present Windows executor is
still Codex-backed. CLI compatibility is not installed app integration or support
for every LLM.

A native comparison exposed over-fragmented planning: six units under an
eight-attempt budget repeatedly ran whole-suite checks before later changes were
ready. Preserve that blocked run. Group related changes, reserve retry capacity,
and distinguish optional focused commands from the host's final frozen checks.
The fresh Claude plan and Codex plan both completed; Codex stop and two-stage
recovery also passed with original limits. These small-fixture receipts are
evidence of this workflow, not a universal model-reliability claim.

### Durable continuation and vendor-independent transport completion cycle

The owner clarified that persistence across fresh contexts is the product's
purpose, with guards supporting the workflow. Research on multi-turn reliability
does not supply a universal coding-turn reset threshold. Keep fresh bounded model
calls and durable host feedback; record prompt sizes, durations and outcomes for
future calibration instead of labeling a few failures statistical degradation.

Retry feedback was held only in controller memory. A transactional continuation
sidecar now survives controller/watchdog journal rotation, while RunStore retains
completion and budget authority. Real process-loss tests cover worker, check and
review feedback. A generic JSON model bridge and explicit trusted local Windows
executor completed a native model job and bounded two-stage recovery. HTTP
support has local protocol evidence, not live service evidence on this host.

Git preflight can preserve original bytes, including its index, by disabling
optional locks and fsmonitor and removing inherited Git redirections. Profile
templates and doctor perform no model, check or committer calls.

The owner separately authorized the exact broker Python-pin repair after its
signed installed runtime was verified. Only that pin changed; rollback bytes
were preserved. The early combined backup/plan write was rejected by tool policy,
then retried only after explicit owner authorization.

Independent review found two persistence failures: malformed model replies were
treated as host refusals, and a fast recovery could finish before the stop monitor
noticed a saved request. Retry only narrowly classified response-shape failures
with durable host feedback; preserve fatal identity and scope checks. Check a
saved cancellation synchronously before entering the watchdog.


## 2026-09-08 portable completion cycle

Keep loop state, frozen checks, review and retry limits shared; isolate only process
lifetime and provider protocols. An OS convenience selector must resolve before
saving the agreement, so reconnect cannot silently choose a new backend.

Windows batch launchers can interpret metacharacters despite literal argument arrays.
Independent native review reproduced this; reject implicit batch execution at setup,
preflight, model and process boundaries, including path aliases. Explicitly chosen
shell interpreters remain trusted commands. POSIX shebang scripts remain supported.

POSIX group cleanup can anchor its identity with a living unreaped guardian and
inheritance channels, but that does not create hostile-process containment or safe
recovery after outer-owner loss. Refuse uncertain reconnect rather than kill a saved
PID. Independently exercise nested groups during controller death.

Git clone does not preserve local author, signing or hook policy. The ordinary
retainer needs an intentional commit-policy copy into isolated metadata, exact file
admission, actual-byte comparison and post-commit verification. Preserve hook refusal;
never switch to another committer. Existing hook code is trusted and can have its own
side effects. Current exact-byte candidates intentionally reject filter transformations.

Linux tests on a Windows-mounted filesystem can fail executable-mode checks for the
filesystem rather than product behavior. Keep the checks strict and use a native
filesystem fixture. A WSL mount may not persist across independent exec invocations;
mount, verify the filesystem, run and unmount inside one shell. Keep failed receipts.

Separate standard package installation from legacy agent-hook registration. The
legacy broad-registration refusal predates this cycle; packaging tests must preserve
that refusal, while the portable launcher is exercised from a fresh installed wheel.

A clean original must be inspected under its ordinary Git configuration. Suppressing
system/global line-ending settings can falsely report unchanged CRLF files as dirty;
Git stat caching can hide the bug unless a regression forces content reinspection.
Preserve original-read configuration while removing repository redirection and
disabling optional index writes/fsmonitor. Keep candidate exact-byte checks isolated.
Read-only Git queries may still invoke trusted configured filters and helpers.

Publication admission also checks fixture identities. Synthetic email addresses are not automatically approved public identities. Use the existing approved public fixture identity, keep author-copy assertions meaningful, preserve refusal evidence and recheck the source against unchanged policy before resubmitting the broker request.

Ralph helper delegation belongs in the shared host, with fresh bounded proposal
calls and one final writer. Enabling arbitrary native agent tools would expand the
existing proposal-only contract. Freeze the helper cap in the saved agreement,
validate disjoint scopes and all child output, join drained children before parent
consolidation, and treat unknown drainage as interruption. Preserve original
deadlines and attempt limits; compare candidate bytes rather than normalized text.

Publication checks must retain deliberate secret-detection fixtures while using portable paths and synthetic local identities. Branding regeneration accepts a separately supplied font; keeping that build input outside the public tree does not change the rendered pixels. Code-test results, binary inspection, exact content classification and publication permission remain separate evidence.

A launcher skill coordinates one durable job; it must not wrap the controller in another repeated loop. Reuse agreed scope and budgets, inspect the generated plan before launch, and monitor the actual run path. Legacy skill recipes and aliases must be updated together so they cannot reintroduce session environment flags, self-certified completion or a second writer.
