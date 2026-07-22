"""The self-integrity policy: while a loop guard is armed, deny touching a kill-switch path.

A judge the model can rewrite is not a judge. This policy denies any file-tool target or Bash token
that resolves to / names a KILL-SWITCH path — a path an unattended loop could use to disarm its own
guards: a guard hook script, the per-repo disarm marker, a settings file under the host's control
directory (where hooks are registered), OR a file inside a load-bearing policy-core directory
(`protected_roots`). The first three are matched by BASENAME (so the fence holds wherever the file
lives — repo source, an installed symlink, or a copy); the roots by REALPATH-PREFIX containment.

Why the roots matter: the guards' decision logic was extracted into an importable package (`excubitor/`)
that the thin hooks import at runtime, so editing anything there — neuter a classifier, make the
adapter's `emit_deny` a no-op (disarms every guard at once), or just break the import (fail-open) —
disarms the guards just as surely as editing a hook script. The extraction moved the disarm surface;
`protected_roots` follows it. The adapter supplies the resolved package root.

Extracted VERBATIM from the shipped `hooks/guard-self-integrity.py` (now a thin host adapter). The
protected surface is HOST-SPECIFIC and adapter-supplied via `ProtectedSurface` — the guard script
names, the disarm marker, the settings basenames, the control-directory component, and the protected
roots are all passed in, so this neutral module hardcodes no host directory or arming variable. The
arming check (the loop-guard env marker) and the full deny message (which names that marker) stay in
the adapter.

SCOPE / LIMITS (honest — a seatbelt for the default path, not a sandbox): matches a LITERAL path token,
never expands the shell. Word expansions (glob / brace / `$VAR` / tilde-via-shell), a live command
substitution inside double quotes, or a runtime-built path slip past — accepted residuals pinned in the
shipped guard's tests and KNOWN-BYPASSES.md. Realpath containment also cannot identify an external hard
link that shares a protected file's inode; that path-layer residual is pinned in the core tests. Fail
direction on ambiguity is DENY; a poisoned token
(embedded NUL) is a no-match that continues the scan, never a crash. `hooks/tests/
test_guard_self_integrity.py` is the differential oracle — a decision change here is a regression.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

from excubitor.core.shell import split_segments

# Leading redirection/fd noise on a token (`>file`, `2>>file`, `<file`) so the path inside is seen.
# The digits are an OPTIONAL fd number that must be FOLLOWED by a real redirect op (`<`/`>`/`&`) — else
# a bare digit-prefixed filename (`1allow-default-branch`, `2024-notes.txt`) would be wrongly stripped.
_REDIR_PREFIX = re.compile(r"^\d*[<>&]+")


@dataclass(frozen=True)
class ProtectedSurface:
    """The host-supplied kill-switch surface. Adapter-supplied because these are host-specific: the
    guard script names installed for the host, the per-repo disarm marker, the settings basenames, the
    control directory a settings file must sit under to register hooks, and — crucially —
    `protected_roots`, the DIRECTORY ROOTS whose contents are load-bearing (the policy core the guards
    import at runtime: editing / moving / deleting anything there disarms them). The first four are
    matched by basename; `protected_roots` by normalized path-component containment. Keeping them out
    of this module is what lets one policy fence any host's control surface."""

    guard_scripts: "frozenset[str]"
    marker: str
    settings_names: "frozenset[str]"
    control_dir: str
    protected_roots: "tuple[str, ...]" = ()


def _kill_switch(path: str, surface: ProtectedSurface) -> "str | None":
    """Return what kill-switch `path` names, or None. Basename match for the scripts/marker/settings,
    realpath-prefix containment for the protected roots."""
    norm = os.path.normpath(path)
    base = os.path.basename(norm)
    if base == surface.marker:
        return f"the guard disarm marker ({surface.marker})"
    if base in surface.guard_scripts:
        return f"a guard hook script ({base})"
    if base in surface.settings_names and surface.control_dir in norm.split(os.sep):
        return f"the hook registration in {surface.control_dir}/{base}"
    # Containment: a target inside a protected root — the policy core the guards import at runtime — is
    # a kill-switch. The extraction moved the decision logic OUT of the basename-fenced hook scripts and
    # INTO that core, so editing it (make a classifier return None, make the adapter's emit_deny a no-op,
    # or just break the import → fail-open) disarms the guards. `target_kill_switch` calls this on the
    # realpath too, so a symlink laundering a write into the core is caught; `commonpath` applies a
    # path-component boundary (not a raw string prefix), tolerates a configured trailing separator,
    # and handles a filesystem-root surface correctly.
    for root in surface.protected_roots:
        try:
            norm_root = os.path.normpath(root)
            if not os.path.isabs(norm_root) or os.path.commonpath((norm, norm_root)) != norm_root:
                continue
        except (OSError, TypeError, ValueError):
            # A malformed or cross-drive host configuration is not a target match. Adapters are
            # responsible for supplying absolute resolved roots; never let one bad root abort the
            # scan of later valid roots.
            continue
        rel = base if norm == norm_root else os.path.join(
            os.path.basename(norm_root) or norm_root, os.path.relpath(norm, norm_root)
        )
        return f"the protected policy core ({rel})"
    return None


def target_kill_switch(target: str, cwd: str, surface: ProtectedSurface) -> "str | None":
    """Kill-switch check for a file-tool target: the path as given AND its symlink-resolved form
    (a symlink named something innocent must not launder a write into a guard script).

    `expanduser` resolves a leading `~` so a target like `~/<control-dir>/guard-*.py` — and, more
    importantly, a symlink reached through it — is checked against the real installed file. This is
    path resolution for the fence, not a policy env read; it is the documented carve-out for this
    module (the neutrality invariant otherwise bars global-path reads)."""
    try:
        resolved = os.path.abspath(os.path.join(cwd, os.path.expanduser(target)))
    except (ValueError, TypeError):
        # ValueError: an embedded NUL byte. TypeError: a non-string cwd/target reaching os.path.join
        # (defense-in-depth for a direct caller — the hook already fails open on a non-string field).
        # Either way, treat as no-match so the caller's scan of the remaining tokens continues.
        return None
    hit = _kill_switch(resolved, surface)
    if hit:
        return hit
    try:
        real = os.path.realpath(resolved)
    except (OSError, ValueError):
        # realpath lstats each component; an embedded NUL raises ValueError ("embedded null byte"),
        # NOT OSError — catch both so one poisoned token can't crash the guard (fail-open would then
        # let a sibling kill-switch write through) or suppress the scan of the remaining tokens.
        return None
    return _kill_switch(real, surface) if real != resolved else None


def bash_kill_switch(command: str, cwd: str, surface: ProtectedSurface) -> "str | None":
    """Best-effort scan of a Bash command for any token naming a kill-switch path."""
    for segment in split_segments(command):
        try:
            # comments=True matches bash: an unquoted `#` starts a comment, so a kill-switch name that
            # appears only AFTER it (`rm foo # see guard-loop-vc.py`) is never acted on and must not be a
            # false deny. A `#` inside quotes is preserved by split_segments and stays a real token.
            tokens = shlex.split(segment, comments=True)
        except ValueError:
            tokens = segment.split()  # unbalanced quotes etc. → best-effort
        for tok in tokens:
            tok = _REDIR_PREFIX.sub("", tok)
            if not tok:
                continue
            hit = target_kill_switch(tok, cwd, surface)
            if hit:
                return hit
    return None
