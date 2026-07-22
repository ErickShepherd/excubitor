# Campaign 2 gate record — package and transactional installer foundation

**Evidence refreshed:** 2026-07-22

**Candidate:** `review/v0.2.0-candidate` with the post-review remediation on
`fix/review-findings-v0.2.0` (tip `9b4499a`), based on `main@4e5fd8d`.

**Status:** implementation and follow-up hardening are locally verified; the independent-review
`DECIDE:` gate is **OPEN**. An independent read-only review of the Campaign 2 diff has since run and its
must-fix findings are remediated on `fix/review-findings-v0.2.0` (see *Post-review remediation* below);
the gate stays open until the owner accepts that review.

**Posture:** no merge, push, publication, tag, release, credential activation, or remote change was performed.

This record collects the implementation and verification evidence for Campaign 2. It does not
self-ratify the open gate.

## What Campaign 2 built

The model-blind core is now an installable distribution with a transactional installer tested end to end
in isolated homes. Campaign 2 adds packaging, CLI, installer, and probe surfaces without changing the
shipped guard decision logic or its differential oracles.

| Unit | Deliverable | Candidate commit |
|---|---|---|
| C2.1 | `pyproject.toml`, console entry point, reproducible wheel/sdist builder, offline smoke test | `f7a818e` |
| C2.2 | neutral policy loading, environment precedence, documented legacy compatibility | `7d02df1` |
| C2.3 | deterministic runtime discovery and write-free `install --dry-run` | `0a63f37` |
| C2.4 | nested config validation and exact hash-bound ownership receipts | `1edfd6e` |
| C2.5 | atomic staging, exact-tuple registration, rollback, and journal recovery | `cbb3bd8` |
| C2.6 | receipt-owned uninstall preserving unrelated configuration | `98d6717` |
| C2.7 | status, configuration, compatibility, and stable JSON output | `02a38bb` |
| C2.8 | harmless-denial probe framework and disposable markers | `c8c6b08` |
| C2.9 | honest `needs-probe` diagnostic state without a real-host witness | `3fde6d5` |
| C2.10 | reproducible stdlib-only zipapp from the distribution source | `63e0ac4` |
| C2.11 | cross-platform installer cases and the CI operating-system matrix | `dca02d7` |

## Follow-up hardening incorporated into the candidate

Independent review found that the first implementation did not fully discharge the mutation and
distribution boundary. The candidate therefore adds fail-closed transaction recovery; invalid-policy
rejection; protection-evidence validation; canonical packaged guard resources; pinned CI inputs;
distributed-command lifecycle tests; strict recovery-journal decoding; and exact post-state binding.

The hardened contract refuses occupied fresh-install paths and drifted upgrades; validates the complete
journal, receipt, and target binding before mutation; rejects symlinked control/state chains; uses
exclusive same-directory temporary files and durable replacement; treats invalid policy as an error;
cannot persist or accept a fabricated `protected` state; packages exact canonical guard resources; and
preserves first-install provenance across repeat installs and upgrades. Recovery validates strict Base64,
receipt types, SHA-256 shapes, and expected post-state digests before changing any affected surface.

## Final local verification

All counts and artifact hashes below are refreshed against the post-review remediation tip
`9b4499a` (`fix/review-findings-v0.2.0`); the *Post-review remediation* section records what changed
since the gate commit and why the suite grew from 596 to 610.

- Python 3.11.15: `610 passed, 3 skipped, 42 subtests`.
- Python 3.12.13: `610 passed, 3 skipped, 42 subtests`.
- Python 3.13.14: `610 passed, 3 skipped, 42 subtests`.
- Telos parsed successfully and discharged all 11 active claims at witness tier.
- Ruff passed on all changed Python files. A full-repository scan also identified legacy violations in
  unchanged Phase 0, Campaign 1, and brand-support files; those files remain unchanged.
- Packaging and installer tests passed.
- Two independent builds were byte-identical. SHA-256 values (at tip `9b4499a`) are:
  - wheel `excubitor-0.2.0-py3-none-any.whl`: `e945586db4e3a024ed201c5b523a26a0715440ad6b9308ffbeb89820f7ef7e9a`
  - sdist `excubitor-0.2.0.tar.gz`: `f92dd1d1f3a8ff08931bf076787ca7d03ed7f60741442e4f4495f774546735b7`
  - zipapp `excubitor-0.2.0.pyz`: `50fc4667178fa8ec2bf1c57d3dead4ec9927f77ecb260092d9fc604db5b17169`
- The exact wheel and zipapp each completed isolated dry-run, install, registered-command execution,
  `doctor` returning `needs-probe`, and receipt-owned uninstall.

> Provenance note: an earlier revision of this section recorded hashes captured before the v0.2.0
> metadata fix (and before the remediation below), so they no longer matched a build of the tree they
> were listed under. The values above are rebuilt from tip `9b4499a` and reproduced byte-for-byte across
> two independent builds. Any future source change re-bases these hashes; they bind to the tip named, not
> to the release tag until the tag is cut on that exact commit.

These results establish the local candidate's functional and packaging evidence. They do not turn a
local test into a real-host enforcement witness or an independent approval.

## Security invariants retained

- The shared model-blind policy core remains authoritative; adapters only translate.
- `pass` preserves native permission flow and nothing auto-approves a request.
- Ownership uses exact path plus SHA-256 for files and exact tuples for registrations.
- Unknown policy versions and malformed nested structures stop before mutation.
- Installation is not called protected: the diagnostic state remains `needs-probe` until a real isolated
  host supplies the versioned runtime-dispatch evidence.
- Rollback and uninstall remove only receipt- or journal-owned bytes and preserve drifted files.
- Claude Code has the adapter foundation; Codex, Gemini, and Copilot remain designed, not built.

## Evidence still requiring an external or owner action

- A real Claude Code harmless-denial probe has not run. It requires an isolated authenticated host and
  explicit authorization; local mocks correctly remain `needs-probe`.
- The Linux tests passed locally, but the candidate has not been pushed, so its macOS and Windows CI rows
  have not run.
- Native plugin or marketplace packaging is outside Campaign 2. The Python distributions are not a
  marketplace trust-flow proof or publication authorization.

## Post-review remediation

An independent, read-only multi-reviewer pass over the Campaign 2 diff (v0.1.0 → candidate) ran after the
gate commit. Its must-fix findings are addressed on `fix/review-findings-v0.2.0` as focused commits, each
with its own regression test; the suite grew from 596 to 610 accordingly. None of these change a shipped
guard's decision on any input its differential oracle already pins — they close abbreviation-shaped
bypasses that the oracles did not exercise, harden fail-open edges, and correct documentation.

- `56f3e90` — close git long-option **abbreviation** bypasses in the loop-VC fences. `git` accepts any
  unambiguous long-option prefix (`--har`→`--hard`, `--del`→`--delete`) and resolves `--ff`/`--no-ff`/
  `--ff-only` last-wins; fences that matched full spellings only were evadable. `reset --hard`,
  `branch`/`symbolic-ref --delete`, and the YOLO `--no-ff` requirement now match by unambiguous prefix and
  by effective last-wins ff-mode. `KNOWN-BYPASSES.md` corrected to stop over-claiming abbreviation coverage.
- `cfec5b9` — harden `apply_uninstall` against a corrupted or non-object `settings.json` (parity with
  `apply_install`): a malformed root now fails cleanly with a `TransactionError` instead of mis-parsing.
- `c10447b` — `_canonical_prefix` (ralph-loop oracle-freeze check) resolves the environmental symlink
  prefix shortest-first, so an in-repo `self -> .` hop cannot collapse and hide a retargeting.
- `1ea0a94` — apply the P0.16 never-exit-non-zero posture to `guard-self-integrity` (non-string
  `cwd`/`target`/`command` payloads fail open, never `TypeError`), matching the other guards.
- `9b4499a` — bound the denial-telemetry **module load** (not just its write) in an abandonable daemon
  thread, so a hooks directory on a hung mount cannot hold a guard past the hook timeout.

Deferred by owner decision (Windows is shipped experimental this release, `continue-on-error` in CI): a
few Windows-only packaging and strict-symlink hardening items remain open and are tracked in
`KNOWN-ISSUES.md`, not blocking the Linux/macOS-supported v0.2.0.

## The open DECIDE gate

> **DECIDE: review installer mutation and supply-chain boundaries before any native marketplace or
> plugin package is published.**

A fresh independent reviewer should examine the mutation transaction and recovery failure modes; exact
ownership under adversarial configuration; artifact correctness and deterministic build posture; the
honesty of `needs-probe`; and whether the candidate is safe to publish. This gate remains open until that
review is accepted by the owner.

The remaining review and real-host evidence must be completed before publication.
