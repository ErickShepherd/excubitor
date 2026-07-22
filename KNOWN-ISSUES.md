# Known issues

## Windows support is experimental (path-portability gaps)

**Status:** tracked / not yet fixed. Linux and macOS are supported and gate CI; the
`windows-latest` matrix rows run for signal but are `continue-on-error` (see `.github/workflows/ci.yml`).
The package classifiers advertise POSIX / Linux + macOS accordingly — not OS-Independent.

On the 3-OS CI matrix (`ubuntu`/`macos`/`windows` × py3.11–3.13), Linux and macOS pass; Windows has a
set of platform-specific failures rooted in path handling that assumes POSIX semantics. They cluster as:

- **Path separator / drive-letter assumptions** — comparisons and containment checks that assume `/`
  and a single-root filesystem (`os.sep`, `commonpath`, `relpath` across drive letters).
- **Executable resolution** — `.exe`/`PATHEXT` and the fixed `"/usr/bin:/bin"` trusted PATH have no
  Windows analogue in the guard/oracle scripts.
- **Non-ASCII / spaced home directories** — installer byte-for-byte round-trip tests over
  `üníçödé-家-мир` and spaced paths.
- **File locking on byte-for-byte round-trips** — Windows mandatory locking on open files affects the
  installer/uninstaller receipt read-modify-write and probe sandbox teardown.

Affected suites (from the failing Windows matrix rows): `test_core_default_branch`,
`test_core_git_state`, `test_core_self_integrity`, `test_installer_crossplatform`,
`test_installer_uninstall`, `test_installer_review_regressions`, `test_probe`, `test_denial_log`,
`test_guard_default_branch`, `test_guard_loop_vc`, `test_guard_self_integrity`, `test_install_settings`,
plus the ralph-loop frozen-oracle suites.

**Scope note:** the macOS failures in the same era were a distinct, now-fixed bug (repo-root symlink
prefix in the frozen-oracle scripts — `$TMPDIR` → `/private/var`). Full Windows support is a separate
effort touching security-sensitive core/guard/installer code and warrants its own review.
