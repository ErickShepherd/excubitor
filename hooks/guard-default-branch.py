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

Every deny is also appended, strictly best-effort AFTER the decision is on stdout, to a local
JSONL telemetry log (see hooks/_denial_log.py) — a telemetry fault never changes the decision.
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


def _record_denial(reason: str, payload: dict) -> None:
    """Best-effort denial telemetry via the sibling hooks/_denial_log.py (loaded by resolved
    path, the runtime/spec_adapter.py pattern, so the ~/.claude symlink layout finds it). ANY
    fault — module missing (a copied guard with no sibling), unwritable log, anything — is
    swallowed: the deny already flushed to stdout must never be affected."""
    try:
        import importlib.util

        mod_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "_denial_log.py")
        spec = importlib.util.spec_from_file_location("_denial_log", mod_path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.record("guard-default-branch", reason, payload)
    except Exception:
        pass


def _deny(reason: str, payload: dict) -> None:
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
    # Decision first, telemetry second: flush the deny to the harness BEFORE any telemetry I/O.
    # Flushing alone is necessary but not sufficient — a hung write would still hold this process
    # past the hook timeout (which fails OPEN and lets the fenced call run) — so record() also
    # time-bounds the filesystem I/O in an abandonable daemon thread (see hooks/_denial_log.py).
    sys.stdout.flush()
    _record_denial(reason, payload)
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


def _candidate_dirs(cwd: str, logical_target: str) -> "list[str] | None":
    """The existing directories to test for protected-repo membership.

    Both the LOGICAL target's container AND the realpath-resolved container, because a symlink can
    launder a write across a repo boundary: a symlink in a feature-branch repo can point at a
    tracked file in a *different* repo checked out on its default branch. Inspecting only the
    logical container (as the original code did) misses that — the resolved path lands in the
    protected repo. `realpath` resolves symlinks in every existing path component even when the
    leaf does not exist yet (a Write creating a new file through a symlinked directory).

    Returns a de-duplicated, order-preserving list, or None on malformed input (embedded NUL, etc.)
    so the caller fails OPEN — never wedge the editor on a crafted-but-broken path.
    """
    try:
        abs_target = os.path.abspath(os.path.join(cwd, logical_target))
        dirs = [_nearest_existing_dir(abs_target, cwd)]
        real_target = os.path.realpath(abs_target)
        if real_target != abs_target:  # a symlink (or /./ , .. , etc.) actually moved the path
            dirs.append(_nearest_existing_dir(real_target, cwd))
    except (ValueError, OSError):
        return None
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _protected_repo_deny(target_dir: str, payload: dict) -> "str | None":
    """If `target_dir` is inside a git repo checked out on its (un-opted-out) default branch,
    return the deny reason; else None (not a repo / opted out / on a feature branch)."""
    top = _git(["rev-parse", "--show-toplevel"], target_dir)
    if top.returncode != 0:
        return None  # not a git repo → not our concern
    repo = top.stdout.strip()

    # Per-repo opt-out: bless main-only repos (or a one-off) with a marker file. isfile (not exists) so a
    # stray directory / dangling symlink of that name can't silently disable the guard.
    if os.path.isfile(os.path.join(repo, ".claude", "allow-default-branch")):
        return None

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo).stdout.strip()

    # Resolve the protected default branch: the remote's HEAD if there is one,
    # else fall back to the conventional names (covers local-only repos).
    origin_head = _git(
        ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], repo
    ).stdout.strip()
    # Always protect the conventional names; a resolved origin/HEAD ADDS to the set, never replaces it
    # (replacing it would silently un-protect main/master whenever origin/HEAD points elsewhere).
    protected = {"main", "master"}
    if origin_head.startswith("refs/remotes/origin/"):
        # Strip the fixed ref prefix, NOT rsplit("/") — a branch name can itself contain slashes
        # (release/2.0, team/main), and rsplit would yield the wrong tail ("2.0") and silently
        # un-protect the real default branch. removeprefix keeps the full name.
        protected.add(origin_head.removeprefix("refs/remotes/origin/"))

    if branch not in protected:
        return None
    return (
        f"On the default branch '{branch}' in {repo} — branch before editing. "
        f"`git switch -c <type>/<slug>` carries your current changes onto a new "
        f"branch (branching-strategy: feature/, fix/, docs/, chore/, refactor/, …). "
        f"To intentionally allow the default branch in this repo, create the marker: "
        f"touch {os.path.join(repo, '.claude', 'allow-default-branch')}"
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:  # JSONDecodeError is a ValueError subclass — one catch suffices
        _allow()  # unparseable input → fail open, never wedge the tool
    if not isinstance(payload, dict):
        _allow()  # valid-JSON-but-not-an-object → fail open; payload.get(...) must never raise AttributeError

    # Blanket off-switch (set via settings.json "env" to disable globally).
    if os.environ.get("CLAUDE_ALLOW_DEFAULT_BRANCH"):
        _allow()

    ti = payload.get("tool_input")
    tool_input = ti if isinstance(ti, dict) else {}
    cwd = payload.get("cwd") or os.getcwd()
    # Edit/Write use file_path; NotebookEdit uses notebook_path. Resolve a relative target against the
    # payload cwd, else repo detection lands on the wrong directory (e.g. a sibling repo).
    logical_target = tool_input.get("file_path") or tool_input.get("notebook_path") or cwd

    candidates = _candidate_dirs(cwd, logical_target)
    if candidates is None:
        _allow()  # malformed target → fail open

    # Deny if ANY candidate (logical container OR symlink-resolved container) is a protected repo.
    # A safe logical container must NOT override an unsafe physical target — so we never short-circuit
    # to allow on the first non-protected candidate; only after every candidate has cleared.
    # NOTE (residual): a hard link is indistinguishable from an ordinary file at the path layer (no
    # link to resolve), so a hard link into a protected repo is NOT caught here — documented in
    # KNOWN-BYPASSES.md, not chased (detecting it means stat-ing inode/nlink across repos).
    for target_dir in candidates:
        reason = _protected_repo_deny(target_dir, payload)
        if reason is not None:
            _deny(reason, payload)
    _allow()


if __name__ == "__main__":
    main()
