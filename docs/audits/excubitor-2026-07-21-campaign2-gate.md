# Campaign 2 gate record — package and transactional installer foundation

**Evidence refreshed:** 2026-07-22

**Candidate:** `candidate/excubitor-v0.2.0`, based on `main@4e5fd8d`

**Status:** implementation and follow-up hardening are locally verified; the independent-review
`DECIDE:` gate is **OPEN**.

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

- Python 3.11.15: `596 passed, 3 skipped, 42 subtests` in 35.29 seconds.
- Python 3.12.13: `596 passed, 3 skipped, 42 subtests` in 34.10 seconds.
- Python 3.13.14: `596 passed, 3 skipped, 42 subtests` in 34.20 seconds.
- Telos parsed successfully and discharged all 11 active claims at witness tier.
- Ruff 0.15.22 passed on all 34 changed Python files. A full-repository scan also identified 69 legacy
  violations in unchanged Phase 0, Campaign 1, and brand-support files; those files remain unchanged.
- Packaging and installer tests passed: `89 passed`.
- Two independent builds were byte-identical. SHA-256 values are:
  - wheel `excubitor-0.2.0-py3-none-any.whl`: `a6080faaaf62e1db3f33acbda2a8db63cad41106a57cbb61b23f3ece2099f280`
  - sdist `excubitor-0.2.0.tar.gz`: `d14f330f33a31306e1d16904bbfc47e837989e23de50f310f9e16a98ae9b8b2d`
  - zipapp `excubitor-0.2.0.pyz`: `74bb2dbe00c6b53de930ed677af7790e1890270c9ff01a4b3a8882de9f63c881`
- The exact wheel and zipapp each completed isolated dry-run, install, registered-command execution,
  `doctor` returning `needs-probe`, and receipt-owned uninstall.

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

## The open DECIDE gate

> **DECIDE: review installer mutation and supply-chain boundaries before any native marketplace or
> plugin package is published.**

A fresh independent reviewer should examine the mutation transaction and recovery failure modes; exact
ownership under adversarial configuration; artifact correctness and deterministic build posture; the
honesty of `needs-probe`; and whether the candidate is safe to publish. This gate remains open until that
review is accepted by the owner.

The remaining review and real-host evidence must be completed before publication.
