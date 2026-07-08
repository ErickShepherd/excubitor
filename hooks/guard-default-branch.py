#!/usr/bin/env python3
"""PreToolUse guard: block file mutations while on a repo's default branch.

Enforces a branch-first workflow (see this repo's README, "The workflow these
fences assume"): no editing on main/master — branch first. Registered
in settings.json for the Edit|Write|NotebookEdit tools.

Defers to the normal permission flow (no decision) when:
  - the target file isn't inside a git repo,
  - the current branch isn't the repo's default branch,
  - a `.claude/allow-default-branch` marker file exists at the repo root, or
  - CLAUDE_ALLOW_DEFAULT_BRANCH is set in the environment.
Otherwise it denies the call with a message telling Claude to branch first.

Contract (docs/en/hooks): deny = exit 0 + JSON on stdout with
hookSpecificOutput.permissionDecision="deny"; emitting no decision defers. We never
exit non-zero — a guard bug must not wedge the editor, only fail open.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError) as e:
        # git missing / not executable / timed out / killed → behave like a non-zero result so callers
        # fail OPEN (the documented contract: never exit non-zero, never wedge the editor on a guard fault).
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr=str(e))


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


def _nearest_existing_dir(path: str, fallback: str) -> str:
    """Walk up from `path` to the first directory that exists on disk.

    Handles Write creating a brand-new file (and even new parent dirs) inside a repo:
    the file itself doesn't exist yet, so resolve to its nearest existing ancestor.
    """
    candidate = path if os.path.isdir(path) else os.path.dirname(path)
    while candidate and not os.path.isdir(candidate):
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    return candidate if os.path.isdir(candidate) else fallback


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow()  # unparseable input → fail open, never wedge the tool
    if not isinstance(payload, dict):
        _allow()  # valid-JSON-but-not-an-object → fail open; payload.get(...) must never raise AttributeError

    # Blanket off-switch (set via settings.json "env" to disable globally).
    if os.environ.get("CLAUDE_ALLOW_DEFAULT_BRANCH"):
        _allow()

    ti = payload.get("tool_input")
    tool_input = ti if isinstance(ti, dict) else {}
    cwd = payload.get("cwd") or os.getcwd()
    # Edit/Write use file_path; NotebookEdit uses notebook_path.
    target = tool_input.get("file_path") or tool_input.get("notebook_path") or cwd
    # Resolve a relative target against the payload cwd, else it resolves against the process cwd and the
    # repo detection lands on the wrong directory (e.g. a sibling repo). abspath is a no-op if already absolute.
    target = os.path.abspath(os.path.join(cwd, target))
    target_dir = _nearest_existing_dir(target, cwd)

    top = _git(["rev-parse", "--show-toplevel"], target_dir)
    if top.returncode != 0:
        _allow()  # not a git repo → not our concern
    repo = top.stdout.strip()

    # Per-repo opt-out: bless main-only repos (or a one-off) with a marker file. isfile (not exists) so a
    # stray directory / dangling symlink of that name can't silently disable the guard.
    if os.path.isfile(os.path.join(repo, ".claude", "allow-default-branch")):
        _allow()

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip()

    # Resolve the protected default branch: the remote's HEAD if there is one,
    # else fall back to the conventional names (covers local-only repos).
    origin_head = _git(
        ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], repo
    ).stdout.strip()
    # Always protect the conventional names; a resolved origin/HEAD ADDS to the set, never replaces it
    # (replacing it would silently un-protect main/master whenever origin/HEAD points elsewhere).
    protected = {"main", "master"}
    if origin_head:
        protected.add(origin_head.rsplit("/", 1)[-1])

    if branch in protected:
        _deny(
            f"On the default branch '{branch}' in {repo} — branch before editing. "
            f"`git switch -c <type>/<slug>` carries your current changes onto a new "
            f"branch (branching-strategy: feature/, fix/, docs/, chore/, refactor/, …). "
            f"To intentionally allow the default branch in this repo, create the marker: "
            f"touch {os.path.join(repo, '.claude', 'allow-default-branch')}"
        )
    _allow()


if __name__ == "__main__":
    main()
