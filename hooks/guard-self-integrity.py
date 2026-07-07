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
(`()` and backticks), so a token glued inside `(rm PATH)` / `$(rm PATH)` / `` `rm PATH` `` is still
seen.

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

# Shell operators AND grouping/substitution boundaries that separate independent commands within one
# Bash invocation (same split as guard-loop-vc.py, so a compound command can't hide a mention behind a
# leading innocuous segment). The `()` and backtick are load-bearing: a subshell or command
# substitution glued to the path (`(rm PATH)`, `$(rm PATH)`, `` `rm PATH` ``) would otherwise leave the
# path stuck to a `)`/backtick inside one shlex token, so its basename never matches. Splitting on them
# is safe here because we only ever DENY on a positive kill-switch match — fragmenting an innocent
# command that merely contains these chars just yields no match (→ defer), never a false deny.
_SEGMENT_SPLIT = re.compile(r"&&|\|\||[|;&\n()`]")
# Leading redirection/fd noise on a token (`>file`, `2>>file`, `<file`) so the path inside is seen.
_REDIR_PREFIX = re.compile(r"^[\d<>&]+")

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
    resolved = os.path.abspath(os.path.join(cwd, os.path.expanduser(target)))
    hit = _kill_switch(resolved)
    if hit:
        return hit
    try:
        real = os.path.realpath(resolved)
    except OSError:
        return None
    return _kill_switch(real) if real != resolved else None


def _bash_kill_switch(command: str, cwd: str) -> str | None:
    """Best-effort scan of a Bash command for any token naming a kill-switch path."""
    for segment in _SEGMENT_SPLIT.split(command):
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment)
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

    # Inactive unless explicitly in a guarded loop — the same opt-in marker as guard-loop-vc.py,
    # either mode ("1" or "yolo"): YOLO's permit-to-act leans on these guards even harder.
    if not os.environ.get("CLAUDE_LOOP_GUARD"):
        _allow()

    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
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
