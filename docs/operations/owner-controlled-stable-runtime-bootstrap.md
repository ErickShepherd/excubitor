# Owner-controlled stable-runtime bootstrap

Status: written procedure only. Do not run the migration until every prerequisite below has been implemented,
tested, and independently reviewed.

## Plain-language outcome

The bootstrap moves each native host registration away from an editable development import and onto one exact,
reviewed Excubitor zipapp. Codex, Claude Code, and Antigravity still launch normally. Their native hook mechanisms
call the promoted artifact directly; Excubitor does not replace a shortcut, shell, executable, alias, shim, or
`PATH` entry.

The move is deliberately one host target at a time. The old runtime remains available until the new target has
passed native trust review and fresh allow and deny checks. A partially migrated machine is a valid, visible state,
not something to hide behind an all-host success claim.

## Who may do what

- A builder, including an agent, may prepare source, build a candidate, run tests, and assemble a review packet.
  That work identifies proposed bytes; it does not approve or install them.
- The owner reviews the candidate and the exact configuration change on a trusted surface outside the candidate's
  control.
- An independent promotion authority imports approved bytes and changes native registrations. The agent must not
  be able to invoke, modify, impersonate, or mint approval for that authority.
- The owner completes each host's native trust or enablement interaction and observes the live checks.

An ordinary file, digest, receipt, command-line flag, environment variable, or approval phrase in chat is not the
independent authority. The selected design uses an owner-signed closed review packet and a small one-shot
verifier/applier that the owner installs independently at fixed enrolled locations. The signing key and signing
operation remain unavailable to the agent. The signature authenticates the owner's approval; the separately
protected applier verifies the packet, controls storage and journals, and performs one target mutation without
loading candidate promotion logic, trust roots, or state paths. Selecting this design in chat does not approve a
candidate, provision the applier, or authorize a migration.

The applier's protection has an explicit boundary. Its program and recovery bytes, verification key, interpreter
dependency closure, artifact store, journals, and revocation and replay state must be unavailable for agent
mutation. On Windows, elevation alone does not establish that boundary against every process running as the same
user. If the host configuration remains writable by an unrestricted same-user process, the support claim is
limited to the covered agent tool surfaces instead of claiming protection from that entire user account.

## Hard stop before migration

Do not change a live registration until all of the following exist:

- A candidate is built in an isolated checkout that is not the code loaded by the active protected hook.
- The zipapp provides the direct native entry `hook <host>` and works through a verified absolute interpreter as
  `<absolute-interpreter> -I -S -B <absolute-archive> hook <host>`.
- Tests show that the working directory, repository packages, user site packages, `sitecustomize`, virtual
  environments, inherited Python activation variables, spaces, and shell metacharacters cannot redirect it.
- A canonical target identifier distinguishes every host, user or project scope, and real native configuration
  path. Resolved paths have been checked for symlinks, junctions, and other reparse or redirection behavior.
- A digest-addressed artifact registry records registrations, pending transactions, rollback pins, and every
  target-to-artifact dependency.
- The promotion operation locks one target, rechecks its exact preimage immediately before mutation, journals the
  change, replaces configuration safely, and can recover after interruption.
- The owner has opened a maintenance window and stopped every known writer for the selected native target,
  including the host. The writers remain stopped until the transaction completes or recovery reaches a durable
  outcome. Locks coordinate cooperating appliers; they do not exclude unrelated same-user processes, and this
  deployment makes no stronger claim.
- Rollback is runnable through the known-good prior interpreter and runtime even when the candidate cannot start.
- Both the candidate and prior interpreter have canonical closed inventories covering the exact executable, base
  executable, every file under isolated import paths, standard-library and extension-module bytes, shared Python
  libraries, and present or absent startup path-configuration files. A fresh complete recapture matches before
  promotion or rollback. Operating-system loader and system-library bytes are an explicit host trust boundary.
- The prior registration invokes a retained digest-addressed archive directly. It does not return to an editable
  source/import tree, and `-B` prevents the registered interpreter from writing bytecode into its verified closure.
- The selected one-shot verifier/applier and recovery program have been independently reviewed and provisioned by
  the owner at fixed enrolled locations, with their verification key and durable state protected from the agent.

If any item is missing, stop after producing the review packet. Do not disable the current hook, edit its protected
source in place, or make a temporary registration exception to get around bootstrap.

## Owner-operated steps

1. **Freeze and inventory the current target.** Record the host and version, scope, canonical configuration path,
   exact configuration bytes and digest, current registration tuple, interpreter identity, runtime or import root,
   trust state, and latest live-witness state. Confirm that the host's ordinary launch path is outside Excubitor's
   ownership.

2. **Prepare the candidate away from the active runtime.** Use an isolated checkout that the live hook does not
   import. Implement the direct zipapp hook entry and run its policy, adapter, packaging, hostile-import, path,
   concurrency, interruption, and rollback tests. Never patch or disable the active protected runtime as a build
   convenience.

3. **Prove byte reproducibility.** Build the zipapp twice from clean, identical inputs in separate output
   directories. Require byte-for-byte equality. Record the SHA-256 digest, complete reviewed source inventory,
   build-tool versions, build command, and interpreter identity. Reproducibility identifies the candidate; it does
   not approve it.

4. **Render the exact proposed registration.** It must name the verified absolute interpreter and the future
   digest-addressed archive path, followed by `hook <host>`. It must not depend on `PYTHONPATH`, `python -m`, the
   working directory, a virtual-environment activation, or inherited Python startup variables. Include every
   platform-specific native field, such as the Windows command field, in the proposed tuple.

5. **Assemble a closed review packet.** The packet contains:

   - candidate archive and SHA-256 digest;
   - reviewed source and build-input inventory;
   - build and regression evidence;
   - verified interpreter path, identity, and digest where available;
   - canonical identities for every target requested in this approval;
   - exact current configuration bytes and digest for each target;
   - exact proposed configuration bytes and a readable diff;
   - prior known-good runtime, interpreter, registration, and rollback pin;
   - expected trust handoff and harmless allow and deny probes;
   - an explicit statement that shortcuts, aliases, shims, `PATH`, and host executables do not change.

   A strict signed envelope also binds the machine and single target, expiry, revocation state, and a single-use
   transaction identity. Its interpreter inventory covers the executable, standard library, extension modules,
   path configuration, and other startup dependencies for both the proposed and rollback runtimes. Unknown fields
   or a changed input invalidate the envelope rather than being ignored.

   Changing any bound input invalidates the packet and requires a new review.

6. **Review and approve outside the candidate's control.** The owner verifies the source diff, candidate digest,
   interpreter dependency closure, target, exact registration diff, regression evidence, and rollback path. The
   owner signs the canonical envelope using a key and signing operation unavailable to the agent. Approval of one
   candidate or target does not authorize a later build, a different configuration preimage, or another target.

7. **Import without overwriting.** The authority re-hashes the supplied archive, rejects a mismatch, rejects path
   redirection, and creates a new object at a path derived from the digest. It must fail if an existing object at
   that identity has different bytes. After writing, it reopens and re-hashes the stored object before recording
   it as staged. Existing known-good objects are never replaced.

8. **Activate exactly one target.** Stop every known writer for that target and keep the maintenance window
   quiesced for the whole transaction. Acquire the target lock, resolve and revalidate its canonical path, and
   compare the current configuration with the approved preimage. On drift or sharing conflict, make no
   configuration change. Otherwise, journal the prior bytes and rollback dependencies, safely replace the
   registration, read it back, and mark only that target `needs-trust`. If drift appears or recovery becomes
   uncertain, preserve the journal, both configurations, retained runtimes, and conflict evidence for owner
   reconciliation rather than overwriting the uncertain surface. Do not report the fleet as atomically migrated.

9. **Complete the native trust handoff.** Launch the host through its ordinary entry point with activation variables
   absent. Use the host's own review or enablement surface to inspect and trust the new definition. For Codex, this
   includes reviewing the exact hook definition through its native hooks interface. If the host does not expose a
   reviewable trust path, leave the target unverified and do not broaden the support claim.

10. **Capture fresh live evidence.** On a disposable target, exercise one harmless operation that should pass and
    one harmless covered mutation that should be denied. Independently capture the native trust result, host
    result, and absence of the denied side effect rather than accepting caller-supplied booleans or tool names.
    Bind the evidence to the host version, operating system, scope, tool surface, exact registration, interpreter,
    and artifact digest. A denial proves dispatch for that surface; it does not prove other tools, scopes, hosts,
    or operating systems.

11. **Close or roll back the target.** Mark the target `verified` only after trust review and both live checks pass.
    On startup, trust, dispatch, policy, or evidence failure, use the independent recovery path to restore the exact
    prior configuration. Re-run a normal launch and the prior runtime's checks, then mark the failed candidate and
    reason without deleting evidence.

12. **Repeat per target.** Start another host or scope only after the previous target has a durable `verified` or
    `rolled-back` outcome. Status must show each target's artifact and state so mixed versions remain visible.

13. **Retain rollback dependencies.** Keep every artifact and interpreter referenced by a registration, pending
    transaction, or rollback pin. Automatic garbage collection remains disabled. Cleanup is a separate owner
    operation that recomputes dependencies and refuses deletion on drift, ambiguity, or an incomplete journal.

14. **Record completion honestly.** The bootstrap is complete only for targets marked `verified`. The completion
    record lists unsupported targets and surfaces, retained rollback objects, unresolved trust steps, and the exact
    evidence behind each support statement.

## Current repository state

This procedure does not authorize a migration today. The direct isolated zipapp entry is implemented. Registry,
promotion, and complete Python-owned runtime-closure verification exist only in an isolated candidate and are not
integrated or trusted. The operating-system loader and system libraries remain an explicit host trust boundary. The
protected signature verifier, concurrent-writer defenses, independently captured activation evidence, and
independently provisioned verifier/applier and recovery program remain prerequisites. Until they are implemented
and reviewed, the current native hook and registration remain unchanged and protected-source work must happen only
in an isolated candidate checkout.
