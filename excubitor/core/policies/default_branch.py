"""The default-branch policy: deny editing a target that lives in a repo checked out on its default.

Extracted VERBATIM from the shipped `hooks/guard-default-branch.py` (now a thin host adapter). The
policy owns the security-load-bearing part — resolving **all** logical/resolved mutation targets so a
symlink can't launder an edit across a repo boundary into a protected repo (R-03) — and the
protected-default-branch decision via the read-only git boundary (`excubitor.core.git_state`).

Host-specific concerns stay in the adapter and are passed in: the per-repo opt-out marker's relative
path (`opt_out_relpath`) is adapter-supplied, so this neutral module hardcodes no host directory. The
adapter also owns envelope parsing, the blanket env off-switch, and native field-type validation.

`hooks/tests/test_guard_default_branch.py` is the differential oracle — a decision change here is a
regression, never a fixture update.
"""
from __future__ import annotations

import os

from excubitor.core import git_state


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
    except (TypeError, ValueError, OSError):
        # TypeError is belt-and-suspenders for a non-string that slips past the adapter's field-type
        # checks (P0.16) — os.path.join raising must fail OPEN, never exit 1 against the contract.
        return None
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _protected_repo_deny(target_dir: str, opt_out_relpath: str) -> "str | None":
    """If `target_dir` is inside a git repo checked out on its (un-opted-out) default branch,
    return the deny reason; else None (not a repo / opted out / on a feature branch).

    `opt_out_relpath` is the adapter-supplied per-repo opt-out marker (e.g. the host's
    `<control-dir>/allow-default-branch`); this module never names a host directory itself.
    """
    repo = git_state.repo_toplevel(["-C", target_dir])
    if repo is None:
        return None  # not a git repo → not our concern

    # Per-repo opt-out: bless main-only repos (or a one-off) with a marker file. isfile (not exists) so a
    # stray directory / dangling symlink of that name can't silently disable the guard.
    if os.path.isfile(os.path.join(repo, opt_out_relpath)):
        return None

    # Detached HEAD reads as 'HEAD'; a git fault reads as "" — both fall out of the protected set below
    # (defer), preserving the prior `.stdout.strip()` behavior.
    branch = git_state.current_branch(["-C", repo]) or ""

    # Always protect main/master; a resolved origin/HEAD ADDS to the set, never replaces it (replacing
    # it would silently un-protect main/master). The slash-safe resolution lives in the shared core.
    protected = git_state.protected_default_names(["-C", repo])

    if branch not in protected:
        return None
    return (
        f"On the default branch '{branch}' in {repo} — branch before editing. "
        f"`git switch -c <type>/<slug>` carries your current changes onto a new "
        f"branch (branching-strategy: feature/, fix/, docs/, chore/, refactor/, …). "
        f"To intentionally allow the default branch in this repo, create the marker: "
        f"touch {os.path.join(repo, opt_out_relpath)}"
    )


def deny_reason(cwd: str, logical_target: str, opt_out_relpath: str) -> "str | None":
    """The default-branch deny reason for editing `logical_target` (relative to `cwd`), or None to
    defer (allow).

    Denies if ANY candidate container — the logical target's OR its symlink-resolved container — is a
    protected repo: a safe logical container must NOT override an unsafe physical target, so the scan
    never short-circuits to allow on the first non-protected candidate. Malformed input yields None
    (fail-open). `opt_out_relpath` is the adapter-supplied per-repo opt-out marker path.

    NOTE (residual): a hard link is indistinguishable from an ordinary file at the path layer, so a
    hard link into a protected repo is NOT caught here (documented in KNOWN-BYPASSES.md).
    """
    candidates = _candidate_dirs(cwd, logical_target)
    if candidates is None:
        return None  # malformed target → fail open
    for target_dir in candidates:
        reason = _protected_repo_deny(target_dir, opt_out_relpath)
        if reason is not None:
            return reason
    return None
