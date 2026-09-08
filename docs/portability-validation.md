# Portability validation

This is an unreleased local development candidate. It shares the loop, provider
adapters, frozen acceptance, review and completion rules across operating systems.
Native support claims remain limited to the evidence below.

| Surface | Evidence from this development cycle |
| --- | --- |
| Windows | Native Job Object regression checks; installed real Claude job completed two units with checks, fresh review and ordinary Git retention |
| Linux | Actual Ubuntu WSL kernel; native process/guardian checks and an independently exercised installed command-bridge workflow on ext4 completed retries, two units, failed-review repair and retention |
| macOS | POSIX implementation and CI target; no Mac was available, so native execution is unverified |
| HTTP | Actual local HTTP protocol fixtures; no live hosted endpoint was configured |
| Distribution | Standard PEP 517 wheel and sdist build succeeded; installed Windows/Linux commands work outside the source checkout; isolated package install, replacement and uninstall checks passed |
| Independent review | Reproduced and cleared Windows batch argument injection and clean-original Git configuration rejection; verified installed workflows, unchanged original index bytes, frozen-setting tamper refusal, exact retained bytes and nested Linux controller-crash cleanup |
| Hosted CI | Dedicated Windows/Linux/macOS workflow defined; no hosted run is claimed for this unpublished candidate |

The independently reviewed standard wheel contains the same 71 Python source files
as the checkout. The reviewer forced malformed model output and a negative review
in separate installed Windows and Linux jobs. Both completed in four work attempts
and two review calls, preserving their original limits and original project files.
The real Windows Claude job is separate live-provider evidence; Linux's installed
model transport was a deterministic fixture, not a live provider login test.

Windows uses Job Objects for process-tree lifetime. POSIX manages trusted,
cooperative process groups with a guardian and deliberately refuses uncertain
recovery after losing its outer watchdog. Deliberate group escape is outside that
contract. Neither trusted-local mode is a filesystem, network or credential sandbox.
Windows implicit batch wrappers are refused; explicitly selected shell interpreters
and existing Git hooks remain trusted code with their own side effects. Original
project inspection respects ordinary Git configuration, including line-ending
normalization. Configured Git filters/helpers may run during read-only queries;
optional index writes and filesystem-monitor helpers are disabled. Candidate
verification remains separately isolated and requires exact admitted bytes.

Linux candidate and retention tests use an isolated ext4 image stored on D:.
Earlier NTFS-mounted fixtures failed strict executable-mode checks; those failed
receipts remain preserved, and the checks were not weakened. Native process tests
that do not depend on Unix file modes also ran on the Windows-mounted directory.
This is Linux on WSL, not evidence from a separate Linux machine. One Windows
breakaway test hit its short startup deadline during concurrent verification and
passed unchanged in isolation and in the final serial combined regression run.

Final Windows combined regression: 443 passed, four POSIX-only skips and nine
subtests passed. Linux receipts separately cover 77 core tests, 55 onboarding and
retention tests, 105 process/transport tests and nine original-Git-configuration
tests. Platform-specific skips and overlapping earlier runs are not added to
those counts. Both final installed review fixtures used unchanged CRLF originals
with Git line-ending normalization; original source and index bytes stayed intact.
All changed Python files passed Ruff. A subsequent test-only fixture identity
alignment passed 24 focused tests without changing the runtime or installed wheel;
the candidate then passed the unchanged publication policy.

Current bounded scope: up to 32 existing editable UTF-8 files, 64 KiB each;
no symlinks, submodules or generated/untracked candidate artifacts. Acceptance
scripts and helpers must be selected explicitly and operate on the candidate.
Exit-code checks are convenient, but only meaningful tests establish the agreed
behavior. These constraints and explicit trusted execution belong in any release
notes; this is not arbitrary-repository or hostile-code sandbox support.

Before a release, run the dedicated portable-ralph workflow on all native targets,
exercise the installed CLI on macOS, and validate each provider or native sandbox
combination claimed in release notes. This cycle grants no publication, merge,
push, new host registration or credential-isolation authority.
