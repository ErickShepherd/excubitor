#!/usr/bin/env python3
"""PreToolUse guard: while a loop guard is armed, the loop may not disarm the guard.

A judge the model can rewrite is not a judge. The other guards in this repo fence *version-control*
acts, but every one of them has kill-switches an unattended loop could reach with ordinary file
writes: the `.claude/allow-default-branch` marker file (disables guard-default-branch per-repo),
the guard hook scripts themselves (the installed copies are symlinks back into this repo, so
editing either end rewrites the live guard), and the `hooks` block of a `.claude/settings.json`
(deregisters the guards entirely). Without this fence, "stop-and-surface" is one `touch` away from
"stop-and-act".

So: while `CLAUDE_LOOP_GUARD` is set (either mode — the same opt-in marker guard-loop-vc.py keys
on), DENY

  * Edit/Write/NotebookEdit whose target resolves to a kill-switch path, and
  * Bash commands that *name* a kill-switch path in any segment.

Kill-switch paths (matched by basename, so the fence holds wherever the file lives — repo source,
`~/.claude` symlink, or a copy):
  * `allow-default-branch` — the per-repo disarm marker,
  * the guard scripts: `guard-default-branch.py`, `guard-loop-vc.py`, `guard-one-unit.py`,
    `guard-self-integrity.py`,
  * `settings.json` / `settings.local.json` under a `.claude` directory (where hooks are
    registered).

The Bash rule is deliberately blunt: a command segment that names a kill-switch path as a *literal
token* denies, reads included. Distinguishing a read from a write in arbitrary shell is a losing
race, and the cost is low — the Read tool (not matched here) still reads anything, so the seatbelt
stays wearable. Fail direction on ambiguity is DENY, matching the posture of the set it protects.
Segments are split on the shell command separators AND on subshell/command-substitution boundaries
(`()` and backticks) — but only OUTSIDE quotes, so a token glued inside an unquoted `(rm PATH)` /
`$(rm PATH)` / `` `rm PATH` `` is still seen, while a kill-switch name quoted in an argument (a commit
message, an `echo`) is literal text and NOT a false deny.

SCOPE / LIMITS (honest — this is a seatbelt for the default path, not a sandbox). It matches a
*literal* path token; it does NOT expand the shell. Anything that produces the kill-switch path
through an expansion the guard doesn't perform slips past — and these are ACCEPTED residuals,
documented not chased (closing them means reimplementing the shell or denying every metacharacter,
which would break ordinary globbing and lose more than it gains):
  * **word expansions that mutate the token before bash resolves it** — a glob
    (`rm hooks/guard-loop-vc.p*`, `...p?`), a brace (`rm .claude/settings.jso{n,}`,
    `...allow-default-branch{,}`), a `$VAR` / `${VAR}` / tilde reference, or a
    command-substitution *result* — the token the guard sees (`...p*`, `...jso{n,}`, `$F`) is not
    the kill-switch basename, so it does not match. Pinned as accepted-residual fixtures in
    hooks/tests/test_guard_self_integrity.py::TestAcceptedResiduals.
  * a **live command substitution inside double quotes** (`echo "$(rm PATH)"`) — segments are split
    only outside quotes (to avoid false-denying a literally-quoted path), so a substitution bash
    WOULD run inside double quotes is not seen. The unquoted forms stay caught; this narrow quoted
    case is the accepted cost of eliminating the false deny.
  * a rename of a parent directory, a `find ~/.claude -delete`, or an interpreter one-liner that
    builds the path at runtime (`python3 -c '...'`).
It protects the *default path* by which an agent would disarm the guards, not every path.

Registered in settings.json for the Bash|Edit|Write|NotebookEdit tools.

Contract (docs/en/hooks): deny = exit 0 + JSON on stdout with
hookSpecificOutput.permissionDecision="deny"; emitting no decision defers to the normal flow.
We never exit non-zero — a guard bug must fail OPEN (process sense), never wedge the tool.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

# Characters that, OUTSIDE quotes, separate independent commands within one Bash invocation: the
# command separators `;` `|` `&` newline, and the subshell / command-substitution boundaries `(` `)`
# backtick (so a mention glued inside `(rm PATH)` / `$(rm PATH)` / `` `rm PATH` `` becomes its own
# segment instead of staying stuck to a `)`/backtick in one shlex token). Honored only outside quotes
# by split_segments(), so a kill-switch name quoted in an argument is NOT a false deny.
_SEPARATORS = frozenset(";|&\n()`")
# Leading redirection/fd noise on a token (`>file`, `2>>file`, `<file`) so the path inside is seen.
# The digits are an OPTIONAL fd number that must be FOLLOWED by a real redirect op (`<`/`>`/`&`) — else
# a bare digit-prefixed filename (`1allow-default-branch`, `2024-notes.txt`) would be wrongly stripped.
_REDIR_PREFIX = re.compile(r"^\d*[<>&]+")


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

_GUARD_SCRIPTS = {
    "guard-default-branch.py",
    "guard-loop-vc.py",
    "guard-one-unit.py",
    "guard-self-integrity.py",
}
_MARKER = "allow-default-branch"
_SETTINGS = {"settings.json", "settings.local.json"}


def _allow() -> None:
    """Emit no decision → defer to the normal permission flow. Always exit 0."""
    sys.exit(0)


def _deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def _kill_switch(path: str) -> str | None:
    """Return what kill-switch `path` names, or None. Matches on the normalized basename."""
    norm = os.path.normpath(path)
    base = os.path.basename(norm)
    if base == _MARKER:
        return f"the guard disarm marker ({_MARKER})"
    if base in _GUARD_SCRIPTS:
        return f"a guard hook script ({base})"
    if base in _SETTINGS and ".claude" in norm.split(os.sep):
        return f"the hook registration in .claude/{base}"
    return None


def _target_kill_switch(target: str, cwd: str) -> str | None:
    """Kill-switch check for a file-tool target: the path as given AND its symlink-resolved form
    (a symlink named something innocent must not launder a write into a guard script)."""
    try:
        resolved = os.path.abspath(os.path.join(cwd, os.path.expanduser(target)))
    except ValueError:
        return None  # e.g. an embedded NUL byte — treat as no-match (the caller's scan continues)
    hit = _kill_switch(resolved)
    if hit:
        return hit
    try:
        real = os.path.realpath(resolved)
    except (OSError, ValueError):
        # realpath lstats each component; an embedded NUL raises ValueError ("embedded null byte"),
        # NOT OSError — catch both so one poisoned token can't crash the guard (fail-open would then
        # let a sibling kill-switch write through) or suppress the scan of the remaining tokens.
        return None
    return _kill_switch(real) if real != resolved else None


def _bash_kill_switch(command: str, cwd: str) -> str | None:
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
            hit = _target_kill_switch(tok, cwd)
            if hit:
                return hit
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow()  # unparseable input → fail open, never wedge the tool
    if not isinstance(payload, dict):
        _allow()  # valid-JSON-but-not-an-object → fail open; payload.get(...) must never raise AttributeError

    # Inactive unless explicitly in a guarded loop — the same opt-in marker as guard-loop-vc.py,
    # either mode ("1" or "yolo"): YOLO's permit-to-act leans on these guards even harder.
    if not os.environ.get("CLAUDE_LOOP_GUARD"):
        _allow()

    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    tool_input = ti if isinstance(ti, dict) else {}
    cwd = payload.get("cwd") or os.getcwd()

    hit = None
    if tool in ("Edit", "Write", "NotebookEdit"):
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        if target:
            hit = _target_kill_switch(target, cwd)
    elif tool == "Bash":
        hit = _bash_kill_switch(tool_input.get("command") or "", cwd)

    if hit:
        _deny(
            f"Blocked: an autonomous loop (CLAUDE_LOOP_GUARD set) may not touch {hit} — "
            f"that path can disarm the loop's own guards, and a judge the model can rewrite "
            f"is not a judge. Reads still work through the Read tool. If a kill-switch file "
            f"genuinely needs changing, that is stop-and-surface work for a human outside the "
            f"loop. This is a seatbelt for the default path, not a sandbox — see this hook's "
            f"SCOPE / LIMITS docstring for what it does not catch."
        )
    _allow()


if __name__ == "__main__":
    main()
