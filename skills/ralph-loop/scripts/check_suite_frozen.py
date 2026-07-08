#!/usr/bin/env python3
"""YOLO suite-immutability check for ralph-loop's green-the-suite anchor.

A green-the-suite loop under CLAUDE_LOOP_GUARD=yolo is permitted to *act* (self-discharge "suite
green" and integrate via a --no-ff merge) only because the suite's exit code is an UNFORGEABLE
external signal — trusted over the LLM. That guarantee evaporates if the loop can weaken, skip, or
delete tests to force green. With the out-of-loop human reviewer removed, that defence must be
MECHANICAL, not a convention the loop is asked to honour.

This is the green-the-suite analog of check_oracle_frozen.py. Where that script freezes a *named*
oracle file, a suite is many files, so this freezes a whole **verdict surface** (the test dirs/globs
PLUS any runner-config that affects collection — pytest.ini, the pyproject table's file, conftest.py,
tox.ini, …) named as git pathspecs. The rule:

    suite frozen  ⟺  no file under any --test-path pathspec appears in `git diff <base>...HEAD`

If the loop touched ZERO test-surface files, green came purely from production changes — exactly
"fix the code, not the test." A suite that legitimately *must* change means the loop is authoring
tests, which is the self-bless hazard; that work must stop-and-surface, not run under YOLO. So
"no test-surface file changed" is both simpler than a count ratchet and the more correct YOLO fence.

`<base>...HEAD` (three-dot) diffs HEAD against the merge-base, i.e. exactly "what the loop changed
since it forked"; letting `git diff -- <pathspec>` do the matching keeps us in git's exact diff space
and catches deletions (they show in --name-only).

FAIL-DENY. Any ambiguity is NOT frozen (non-zero exit): no --test-path given, a --test-path that
matches no tracked file at `base` (the author froze a surface that does not exist — likely a typo, so
the freeze would be vacuous), or any git error. The caller must refuse the YOLO act on non-zero.

LIMIT (honest, named — the same bargain as oracle incompleteness in loop-yolo-verifiable-autonomy.md).
The check freezes EXACTLY the pathspecs it is given. A verdict-affecting path not listed (e.g. an
`addopts = "--ignore=…"` in a config file the author forgot to freeze) is a hole the loop could weaken
through without tripping this. Enumerating the COMPLETE verdict surface is the DoD author's
responsibility; this makes the *freeze* mechanical, it cannot know which files constitute "the suite".
Same seatbelt-not-sandbox caveat as guard-loop-vc.py.

Exit codes: 0 = suite frozen (safe to act); 1 = NOT frozen / unverifiable (refuse); 2 = usage error.

Usage:
    check_suite_frozen.py --repo <path> --base <branch> \
        --test-path tests/ --test-path 'conftest.py' --test-path pytest.ini
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys


# Location-redirecting git env vars: an inherited GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE OVERRIDES
# `-C <repo>`, so a freeze check could silently evaluate a DIFFERENT tree than --repo names — a
# confused-deputy spoof of "frozen". Strip them so `-C <repo>` is the sole source of truth.
_REDIRECT_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                      "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE")


def _git_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _REDIRECT_GIT_VARS}


def _git(repo: str, *args: str) -> tuple[bool, str]:
    """Run a read-only git query; return (ok, stdout). Never raises."""
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=10,
                           env=_git_env())
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if p.returncode != 0:
        return False, ""
    return True, p.stdout


def _empty_tree(repo: str) -> str | None:
    """The repo's empty-tree object id (algorithm-correct for SHA-1 or SHA-256). None on error."""
    try:
        p = subprocess.run(
            ["git", "-C", repo, "hash-object", "-t", "tree", "--stdin"],
            input="", capture_output=True, text=True, timeout=10, env=_git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0 or not p.stdout.strip():
        return None
    return p.stdout.strip()


def _surface_exists_at_base(repo: str, base: str, empty_tree: str, pathspec: str) -> bool | None:
    """Does `pathspec` match ≥1 tracked file at `base`? (None on git error → fail-deny.)

    Diffs the empty tree against `base` limited to `pathspec`, so the existence check uses git's
    SAME pathspec engine as the tamper check (`git diff`) — directories, exact files, and `*` globs
    all resolve identically. (`git ls-tree` does NOT honour wildcard pathspecs, so it can't be used
    here.) The reference is the *frozen base* tree, not the possibly-tampered work tree. A pathspec
    that matches nothing means the author named a surface that does not exist — fail-deny upstream.
    """
    ok, out = _git(repo, "-c", "core.quotePath=false", "diff", "--name-only", empty_tree, base, "--", pathspec)
    if not ok:
        return None
    return any(line.strip() for line in out.splitlines())


def _changed_under(repo: str, base: str, pathspecs: list[str]) -> list[str] | None:
    """Files HEAD changed since the merge-base with `base`, limited to `pathspecs`.

    Returns the sorted list of tampered test-surface files (empty = frozen), or None on git error
    (→ fail-deny). `core.quotePath=false` keeps non-ASCII paths unescaped.
    """
    ok, out = _git(
        repo, "-c", "core.quotePath=false", "diff", "--name-only", f"{base}...HEAD", "--", *pathspecs
    )
    if not ok:
        return None
    return sorted({os.path.normpath(line) for line in out.splitlines() if line.strip()})


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify a green-the-suite loop did not touch its test/verdict surface (YOLO gate)."
    )
    ap.add_argument("--repo", required=True, help="path to the repo (the loop's working copy)")
    ap.add_argument("--base", required=True, help="the loop branch's base (the repo's default branch)")
    ap.add_argument(
        "--test-path",
        dest="test_paths",
        action="append",
        required=True,
        metavar="PATHSPEC",
        help="a git pathspec naming part of the frozen verdict surface (test dir/glob or runner "
        "config); repeat for each. ALL verdict-affecting paths must be listed.",
    )
    args = ap.parse_args()

    repo = args.repo
    if not os.path.isdir(os.path.join(repo, ".git")) and not _git(repo, "rev-parse", "--git-dir")[0]:
        print(f"NOT-FROZEN: {repo} is not a git repo", file=sys.stderr)
        return 1

    empty_tree = _empty_tree(repo)
    if empty_tree is None:
        print("NOT-FROZEN: could not resolve the empty-tree object id (fail-deny)", file=sys.stderr)
        return 1

    # Every named surface must actually exist at base; a vacuous (typo'd) pathspec would otherwise
    # freeze nothing and pass silently. Fail-deny on the first that matches nothing or errors.
    for pathspec in args.test_paths:
        exists = _surface_exists_at_base(repo, args.base, empty_tree, pathspec)
        if exists is None:
            print(f"NOT-FROZEN: could not list {pathspec!r} at {args.base} (fail-deny)", file=sys.stderr)
            return 1
        if not exists:
            print(
                f"NOT-FROZEN: --test-path {pathspec!r} matches no tracked file at {args.base}; "
                f"refusing to freeze a non-existent surface (fail-deny)",
                file=sys.stderr,
            )
            return 1

    tampered = _changed_under(repo, args.base, args.test_paths)
    if tampered is None:
        print(f"NOT-FROZEN: could not diff {args.base}...HEAD (fail-deny)", file=sys.stderr)
        return 1
    if tampered:
        print(
            "NOT-FROZEN: the loop modified its own test/verdict surface on this branch: "
            + ", ".join(tampered),
            file=sys.stderr,
        )
        return 1

    print("FROZEN: test surface untouched on the loop branch — " + ", ".join(args.test_paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
