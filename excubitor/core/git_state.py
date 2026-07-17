"""Read-only Git state and default-branch resolution for the Excubitor policy core.

This is the ONE place under `excubitor.core` that starts a child process — and only to run
**read-only** `git` queries (the git boundary the pure policies depend on). It never mutates a
repository, reads no environment, and names no host or model. The repository is chosen explicitly by
`selectors` — the git global options `-C <dir>` / `--git-dir <dir>` / `--work-tree <dir>` reconstructed
from a guarded command — so a policy interrogates the SAME repository a command would target rather
than an implicit cwd (the P0.14 property).

The helpers are extracted **behavior-preserving** from the shipped hooks (`guard-loop-vc.py`'s `_git`
/ `_current_branch` / `_default_branch`, and `guard-default-branch.py`'s inline resolution). Both
guards previously carried their own copy of the slash-safe `origin/HEAD` resolution and read the same
trust anchor; this module is the single source of truth. The `hooks/tests/` suites are the
differential oracle — a decision change here is a regression, not a new baseline.
"""
from __future__ import annotations

import subprocess

__all__ = [
    "run_git",
    "current_branch",
    "repo_toplevel",
    "origin_head_name",
    "default_branch",
    "protected_default_names",
]

# refs/remotes/origin/HEAD is the trust anchor both guards read to resolve the default branch.
_ORIGIN_HEAD_PREFIX = "refs/remotes/origin/"


def run_git(selectors: list[str], *args: str) -> tuple[bool, str]:
    """Run a read-only `git` query; return ``(ok, stripped_stdout)``. Never raises (fails toward not-ok).

    `selectors` are the repository-selecting global options placed before the subcommand, so the query
    hits the intended repository. A missing / timed-out / non-zero git yields ``(False, "")`` — the
    fail-toward-not-ok posture the guards rely on to never wedge on a git fault.
    """
    try:
        p = subprocess.run(["git", *selectors, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if p.returncode != 0:
        return False, ""
    return True, p.stdout.strip()


def current_branch(selectors: list[str]) -> str | None:
    """The checked-out branch name, or None if undeterminable. A detached HEAD reads as ``"HEAD"``."""
    ok, out = run_git(selectors, "rev-parse", "--abbrev-ref", "HEAD")
    return out if ok else None


def repo_toplevel(selectors: list[str]) -> str | None:
    """The repository's working-tree root, or None if the selectors don't resolve to a git repo."""
    ok, out = run_git(selectors, "rev-parse", "--show-toplevel")
    return out if ok else None


def origin_head_name(selectors: list[str]) -> str | None:
    """The branch name ``refs/remotes/origin/HEAD`` points to, or None when there is no such symref.

    Strips the fixed ``refs/remotes/origin/`` prefix with :meth:`str.removeprefix`, NOT ``rsplit("/")``:
    a branch name can itself contain slashes (``release/2.0``, ``team/main``), and rsplit would keep
    only the last segment and resolve a DIFFERENT default (the R-01 defect). Both shipped guards
    implemented this identically; it now lives here once.
    """
    ok, out = run_git(selectors, "symbolic-ref", "--quiet", _ORIGIN_HEAD_PREFIX + "HEAD")
    if ok and out.startswith(_ORIGIN_HEAD_PREFIX):
        return out.removeprefix(_ORIGIN_HEAD_PREFIX)
    return None


def default_branch(selectors: list[str]) -> str | None:
    """The repository's SINGLE default branch, or None if it can't be determined unambiguously.

    Prefer ``origin/HEAD``; else, for a local-only repo, the SOLE of ``main`` / ``master``; if both
    exist, disambiguate only via an explicit ``init.defaultBranch`` naming one of them; otherwise None
    (genuinely ambiguous → callers fail-deny). A local-only repo has no authoritative default, so the
    main/master fallback is a best-effort heuristic — callers that must be safe also protect the
    literal ``main``/``master`` names. Extracted verbatim from ``guard-loop-vc._default_branch``.
    """
    name = origin_head_name(selectors)
    if name is not None:
        return name
    has_main = run_git(selectors, "show-ref", "--verify", "--quiet", "refs/heads/main")[0]
    has_master = run_git(selectors, "show-ref", "--verify", "--quiet", "refs/heads/master")[0]
    if has_main and not has_master:
        return "main"
    if has_master and not has_main:
        return "master"
    if has_main and has_master:
        ok, cfg = run_git(selectors, "config", "init.defaultBranch")
        if ok and cfg in ("main", "master"):
            return cfg
    return None


def protected_default_names(selectors: list[str]) -> set[str]:
    """The SET of branch names to protect as "the default": ALWAYS ``{"main", "master"}``, PLUS the
    name ``origin/HEAD`` resolves to when set.

    A resolved ``origin/HEAD`` ADDS to the set, never replaces it — replacing would silently
    un-protect main/master whenever origin/HEAD points elsewhere. Extracted verbatim from
    ``guard-default-branch``'s inline resolution.
    """
    protected = {"main", "master"}
    name = origin_head_name(selectors)
    if name is not None:
        protected.add(name)
    return protected
