"""Shared shell-command lexing for the policies that read a Bash command string.

`split_segments` splits a command into independent segments at the shell command separators
(`;` `|` `&` newline) AND the subshell / command-substitution boundaries (`(` `)` backtick), honoring
them ONLY outside quotes — so a separator (or a dangerous token) quoted in an argument stays literal
text and is not promoted to its own command. Both the loop-VC classifier and the self-integrity
kill-switch scanner split identically; this module is the one copy they share (extracted from the two
byte-identical copies). Stdlib only, no host coupling.

Honest limit inherited by every caller: this is literal-token lexing, NOT shell execution. A live
command substitution inside DOUBLE quotes (`"… $(cmd)"`, which bash would run) is not segmented — an
accepted under-block residual, the cost of not false-denying a literally-quoted token. See
KNOWN-BYPASSES.md.
"""
from __future__ import annotations

__all__ = ["split_segments"]

# Characters that, OUTSIDE quotes, separate independent commands within one Bash invocation: the
# command separators `;` `|` `&` newline, and the subshell / command-substitution boundaries `(` `)`
# backtick. `&&`/`||` fall out of the single-char `&`/`|` split (an empty middle segment is harmless).
_SEPARATORS = frozenset(";|&\n()`")


def split_segments(command: str) -> list[str]:
    """Split a Bash command into segments at _SEPARATORS, honoring them ONLY outside quotes.

    A separator inside single or double quotes is literal text, not a command boundary — so a token
    quoted in an argument stays inside its segment and is NOT promoted to its own command (which would
    be a false deny). The tradeoff is that a LIVE command substitution inside double quotes is likewise
    not segmented — an accepted under-block residual. Backslash escapes the next char (outside single
    quotes). Quote characters are preserved for the downstream shlex.split."""
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
