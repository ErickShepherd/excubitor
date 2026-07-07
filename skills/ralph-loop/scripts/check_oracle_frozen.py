#!/usr/bin/env python3
"""Phase 2 of the YOLO/verifiable-autonomy loop posture: the oracle-immutability check.

A YOLO loop (CLAUDE_LOOP_GUARD=yolo) is permitted to *act* on a test-expressible telos claim only
because its `verified-by:` oracle is an UNFORGEABLE external signal — an exit code trusted over the
LLM. That guarantee evaporates if the loop can edit the oracle that gates it (it could weaken or
delete the test to force green, then integrate). With the out-of-loop human reviewer removed, that
defence must be MECHANICAL, not a convention the loop is asked to honour.

This script is that mechanical check. Given a claim's `verified-by:` command and the loop branch's
base, it confirms the oracle's file(s) were NOT modified by the loop on its own branch:

    oracle frozen  ⟺  no file referenced by `verified-by:` appears in `git diff <base>...HEAD`

`<base>...HEAD` (three-dot) diffs HEAD against the merge-base, i.e. exactly "what the loop changed
since it forked" — so an oracle edited at any point on the loop branch is caught. This is stronger
than a hash-pin (no manifest to maintain or forge) and reuses git.

FAIL-DENY. Any ambiguity is treated as NOT frozen (non-zero exit): a `verified-by:` from which no
existing oracle file can be extracted (so immutability is unverifiable), or any git error. The
caller must refuse the YOLO act on non-zero — never integrate on an unconfirmed oracle.

LIMIT (honest). The *check* is mechanical, but the loop's obedience to it is recipe-level — the
guard hook prevents the default-branch merge mechanically, but it cannot know which file is "the
oracle", so it cannot run this check itself. Same seatbelt-not-sandbox caveat as guard-loop-vc.py.

Exit codes: 0 = oracle frozen (safe to act); 1 = NOT frozen / unverifiable (refuse); 2 = usage error.

Usage:
    check_oracle_frozen.py --repo <path> --base <branch> --verified-by "<command>"
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


def _git(repo: str, *args: str) -> tuple[bool, str]:
    """Run a read-only git query; return (ok, stdout). Never raises."""
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if p.returncode != 0:
        return False, ""
    return True, p.stdout


def _oracle_files(repo: str, verified_by: str) -> list[str]:
    """Extract the **tracked, repo-relative** file paths a `verified-by:` command refers to.

    The command is e.g. `python3 scripts/test_validate.py` or
    `python3 tests/test_x.py TestClass.test_method` (a pytest/unittest node id). We keep only tokens
    that resolve to a real file inside the repo: the interpreter (`python3`) is on PATH not in the
    repo, and a test-id arg (`TestClass.test_method`, or a `path::test` nodeid's suffix) is not a file
    — both are correctly skipped. A `path::test` token is split on `::` first.

    Each candidate is normalized to the SAME space as `git diff --name-only` (tracked, repo-relative
    to the work-tree root) so the later intersection actually matches — defeating two tamper-and-pass
    bypasses: an **absolute-path** verified-by (its abs path never matched git's relative diff) and a
    **symlinked** oracle (we must compare the realpath target the loop actually edits, not the link).
    A candidate that is out-of-tree or not tracked is dropped — it can't be reasoned about via the
    committed diff, which (if it leaves no oracle) yields fail-deny upstream.
    """
    ok, top = _git(repo, "rev-parse", "--show-toplevel")
    if not ok or not top.strip():
        return []
    toplevel = os.path.realpath(top.strip())
    try:
        tokens = shlex.split(verified_by)
    except ValueError:
        tokens = verified_by.split()
    files: list[str] = []
    for tok in tokens:
        candidate = tok.split("::", 1)[0]  # pytest nodeid: keep the file part
        if not candidate or candidate.startswith("-"):
            continue
        abs_candidate = candidate if os.path.isabs(candidate) else os.path.join(repo, candidate)
        real = os.path.realpath(abs_candidate)  # resolves symlinks → the file actually executed
        if not os.path.isfile(real):
            continue
        rel = os.path.normpath(os.path.relpath(real, toplevel))
        if rel.startswith(".."):
            continue  # outside the work tree → cannot appear in the diff
        # Require tracked: an untracked oracle's edits never show in a committed diff, so its
        # immutability is unverifiable here → drop (→ fail-deny if it was the only oracle).
        if not _git(repo, "ls-files", "--error-unmatch", "--", rel)[0]:
            continue
        files.append(rel)
    return files


def _changed_files(repo: str, base: str) -> set[str] | None:
    """Files HEAD changed since the merge-base with `base` (None on git error → fail-deny).

    `core.quotePath=false` keeps non-ASCII paths unescaped so they compare equal to the candidates.
    """
    ok, out = _git(repo, "-c", "core.quotePath=false", "diff", "--name-only", f"{base}...HEAD")
    if not ok:
        return None
    return {os.path.normpath(line) for line in out.splitlines() if line.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a telos claim's verified-by oracle is loop-immutable.")
    ap.add_argument("--repo", required=True, help="path to the repo (the loop's working copy)")
    ap.add_argument("--base", required=True, help="the loop branch's base (the repo's default branch)")
    ap.add_argument("--verified-by", required=True, help="the claim's verified-by command string")
    args = ap.parse_args()

    repo = args.repo
    if not os.path.isdir(os.path.join(repo, ".git")) and not _git(repo, "rev-parse", "--git-dir")[0]:
        print(f"NOT-FROZEN: {repo} is not a git repo", file=sys.stderr)
        return 1

    oracle_files = _oracle_files(repo, args.verified_by)
    if not oracle_files:
        # No extractable oracle file → immutability is unverifiable → fail-deny.
        print(
            f"NOT-FROZEN: no existing oracle file found in verified-by {args.verified_by!r}; "
            f"cannot confirm immutability (fail-deny)",
            file=sys.stderr,
        )
        return 1

    changed = _changed_files(repo, args.base)
    if changed is None:
        print(f"NOT-FROZEN: could not diff {args.base}...HEAD (fail-deny)", file=sys.stderr)
        return 1

    tampered = sorted(set(oracle_files) & changed)
    if tampered:
        print(
            "NOT-FROZEN: the loop modified its own gating oracle on this branch: "
            + ", ".join(tampered),
            file=sys.stderr,
        )
        return 1

    print("FROZEN: oracle untouched on the loop branch — " + ", ".join(oracle_files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
