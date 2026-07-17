"""The self-integrity policy: while a loop guard is armed, deny touching a kill-switch path.

A judge the model can rewrite is not a judge. This policy denies any file-tool target or Bash token
that resolves to / names a KILL-SWITCH path — a path an unattended loop could use to disarm its own
guards: a guard hook script, the per-repo disarm marker, or a settings file under the host's control
directory (where hooks are registered). Matched by BASENAME, so the fence holds wherever the file lives
(repo source, an installed symlink, or a copy).

Extracted VERBATIM from the shipped `hooks/guard-self-integrity.py` (now a thin host adapter). The
protected surface is HOST-SPECIFIC and adapter-supplied via `ProtectedSurface` — the guard script
names, the disarm marker, the settings basenames, and the control-directory component are all passed
in, so this neutral module hardcodes no host directory or arming variable. The arming check (the
loop-guard env marker) and the full deny message (which names that marker) stay in the adapter.

SCOPE / LIMITS (honest — a seatbelt for the default path, not a sandbox): matches a LITERAL path token,
never expands the shell. Word expansions (glob / brace / `$VAR` / tilde-via-shell), a live command
substitution inside double quotes, or a runtime-built path slip past — accepted residuals pinned in the
shipped guard's tests and KNOWN-BYPASSES.md. Fail direction on ambiguity is DENY; a poisoned token
(embedded NUL) is a no-match that continues the scan, never a crash. `hooks/tests/
test_guard_self_integrity.py` is the differential oracle — a decision change here is a regression.
"""
from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass

# Characters that, OUTSIDE quotes, separate independent commands within one Bash invocation: the
# command separators `;` `|` `&` newline, and the subshell / command-substitution boundaries `(` `)`
# backtick. Honored only outside quotes by split_segments(), so a kill-switch name quoted in an
# argument is NOT a false deny.
_SEPARATORS = frozenset(";|&\n()`")
# Leading redirection/fd noise on a token (`>file`, `2>>file`, `<file`) so the path inside is seen.
# The digits are an OPTIONAL fd number that must be FOLLOWED by a real redirect op (`<`/`>`/`&`) — else
# a bare digit-prefixed filename (`1allow-default-branch`, `2024-notes.txt`) would be wrongly stripped.
_REDIR_PREFIX = re.compile(r"^\d*[<>&]+")


@dataclass(frozen=True)
class ProtectedSurface:
    """The host-supplied kill-switch surface, matched by basename. Adapter-supplied because these are
    host-specific: the guard script names installed for the host, the per-repo disarm marker, the
    settings basenames, and the control directory a settings file must sit under to register hooks.
    Keeping them out of this module is what lets one policy fence any host's control surface."""

    guard_scripts: "frozenset[str]"
    marker: str
    settings_names: "frozenset[str]"
    control_dir: str


def split_segments(command: str) -> list[str]:
    """Split a Bash command into segments at _SEPARATORS, honoring them ONLY outside quotes.

    A separator inside single or double quotes is literal text, not a command boundary — so a
    kill-switch name quoted in an argument (`git commit -m "refactor (see guard-loop-vc.py)"`) stays
    inside its segment and is NOT promoted to its own command (which would be a false deny). The
    tradeoff is that a LIVE command substitution inside double quotes is likewise not segmented — an
    accepted under-block residual (see SCOPE / LIMITS). Backslash escapes the next char (outside
    single quotes). Quote characters are preserved for the downstream shlex.split."""
    segments: list[str] = []
    buf: list[str] = []
    in_single = in_double = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
        elif in_double:
            if ch == "\\" and i + 1 < n:
                buf.append(ch); buf.append(command[i + 1]); i += 2; continue
            buf.append(ch)
            if ch == '"':
                in_double = False
        elif ch == "'":
            in_single = True; buf.append(ch)
        elif ch == '"':
            in_double = True; buf.append(ch)
        elif ch == "\\" and i + 1 < n:
            buf.append(ch); buf.append(command[i + 1]); i += 2; continue
        elif ch in _SEPARATORS:
            segments.append("".join(buf)); buf = []
        else:
            buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [s for s in (seg.strip() for seg in segments) if s]


def _kill_switch(path: str, surface: ProtectedSurface) -> "str | None":
    """Return what kill-switch `path` names, or None. Matches on the normalized basename."""
    norm = os.path.normpath(path)
    base = os.path.basename(norm)
    if base == surface.marker:
        return f"the guard disarm marker ({surface.marker})"
    if base in surface.guard_scripts:
        return f"a guard hook script ({base})"
    if base in surface.settings_names and surface.control_dir in norm.split(os.sep):
        return f"the hook registration in {surface.control_dir}/{base}"
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
    except ValueError:
        return None  # e.g. an embedded NUL byte — treat as no-match (the caller's scan continues)
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
