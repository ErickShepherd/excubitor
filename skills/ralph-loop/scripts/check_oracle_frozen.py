#!/usr/bin/env python3
"""Phase 2 of the YOLO/verifiable-autonomy loop posture: the oracle-immutability check.

A YOLO loop (CLAUDE_LOOP_GUARD=yolo) is permitted to *act* on a test-expressible telos claim only
because its `verified-by:` oracle is an UNFORGEABLE external signal — an exit code trusted over the
LLM. That guarantee evaporates if the loop can edit the oracle that gates it (it could weaken or
delete the test to force green, then integrate). With the out-of-loop human reviewer removed, that
defence must be MECHANICAL, not a convention the loop is asked to honour.

This script is that mechanical check. Given a claim's `verified-by:` command and the loop branch's
base, it confirms the oracle's frozen surface was NOT modified by the loop on its own branch:

    oracle frozen  ⟺  no path in the oracle SURFACE appears in `git diff <base>...HEAD`
                       AND every surface path's current type, symlink target, and (for a regular
                       file) content matches the base tree

where the SURFACE is each referenced file's lexical path, every symlink hop along its whole in-repo
path — file AND directory symlinks (R-04: the resolved target alone had a retarget hole — repoint a
tracked oracle link at a weaker tracked test and the diff named only the link, the candidate set only
the new target, empty intersection, false FROZEN; #2: a directory symlink in the path was likewise
collapsed away) — and its resolved target. `<base>...HEAD` (three-dot) diffs HEAD against the
merge-base, i.e. exactly "what the loop changed since it forked" — so an oracle COMMITTED-edited at
any point on the loop branch is caught; the current-vs-base type/target/content comparison
additionally catches an UNCOMMITTED retarget, type swap, or content weakening in the worktree (R-04
#1: a three-dot diff compares commits, so an uncommitted regular-file edit is invisible to it — the
content-hash-vs-base check is what closes that). Stronger than a hash-pin (no manifest to maintain or
forge) and reuses git. It remains a point-in-time check: binding the checked bytes to the witness's
exit code atomically is the runner's job (run_frozen_oracle), not this diagnostic's.

FAIL-DENY. Any ambiguity is treated as NOT frozen (non-zero exit): a `verified-by:` from which no
existing oracle file can be extracted (so immutability is unverifiable), or any git error. The
caller must refuse the YOLO act on non-zero — never integrate on an unconfirmed oracle.

LIMIT (honest). The *check* is mechanical, but the loop's obedience to it is recipe-level — the
guard hook prevents the default-branch merge mechanically, but it cannot know which file is "the
oracle", so it cannot run this check itself. Same seatbelt-not-sandbox caveat as guard-loop-vc.py.
The content comparison trusts git's own OID computation: a loop that can write `.git/config` (beyond
the tracked-file-edit threat this models) could install a `clean` filter mapping weakened bytes back
to the base blob and spoof FROZEN — inherent to any git-OID check and out of scope, documented not
chased. The remaining in-model residual is a witness that mutates its oracle DURING execution and
restores it before exiting (the runner's recheck sees start==end); see run_frozen_oracle.py.

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


def _existed_at_base(repo: str, base: str, rel: str) -> bool:
    """True iff `rel` was a tracked blob at `base` — the precise signal that a now-missing oracle file
    was DELETED/renamed on the loop branch (tamper), as opposed to a token that was never a file at all
    (an interpreter name, a bare test-id). `git cat-file -e <base>:<rel>` exits 0 iff the blob exists."""
    return _git(repo, "cat-file", "-e", f"{base}:{rel}")[0]


def _surface_paths(toplevel: str, abs_candidate: str) -> list[str]:
    """Every path whose retargeting would change which bytes the witness executes: the lexical
    candidate, every symlink hop along the WHOLE in-repo path — a DIRECTORY symlink in the prefix is
    load-bearing too (R-04 finding #2), not only the final component — and the fully resolved target.

    The prior approach realpath-collapsed the directory part before walking the final component's
    chain, so an uncommitted `tests -> weak_tests` directory retarget silently swapped the executed
    file (the resolved path matched base, the link was never in the surface). Anchoring the walk at
    the already-canonical repo toplevel and following every symlink component (dir OR file) closes
    that. Bounded against symlink loops."""
    abs_candidate = os.path.normpath(abs_candidate)
    hops: list[str] = []

    def add(p: str) -> None:
        if p not in hops:
            hops.append(p)

    add(abs_candidate)
    # Walk the candidate's in-repo components from the canonical toplevel down, capturing every
    # symlink hop. Ancestors above toplevel are canonical by construction (toplevel is realpath'd),
    # so they need no resolution; a candidate resolving outside the tree just keeps lexical+resolved.
    rel = os.path.relpath(abs_candidate, toplevel)
    if not rel.startswith(".."):
        resolved = toplevel
        guard = 0
        for part in rel.split(os.sep):
            if part in ("", "."):
                continue
            resolved = os.path.join(resolved, part)
            while os.path.islink(resolved) and guard < 80:  # ELOOP guard; real chains are 1-2 hops
                # Freeze the SYMLINK itself (its target string is checked against base); do NOT add its
                # resolved target here — an intermediate directory target is a tree, not a freezable
                # blob (and would false-trip the tamper check), while a terminal FILE target is added
                # once by the realpath below. Only symlink hops + the terminal file belong in the surface.
                add(resolved)
                guard += 1
                tgt = os.readlink(resolved)
                resolved = os.path.normpath(
                    tgt if os.path.isabs(tgt) else os.path.join(os.path.dirname(resolved), tgt))
    add(os.path.realpath(abs_candidate))
    return hops


def _oracle_files(repo: str, base: str, verified_by: str) -> tuple[dict[str, str], list[str]]:
    """Extract the **tracked, repo-relative** frozen surface a `verified-by:` command refers to.

    The command is e.g. `python3 scripts/test_validate.py` or
    `python3 tests/test_x.py TestClass.test_method` (a pytest/unittest node id). We keep only tokens
    that resolve to a real file inside the repo: the interpreter (`python3`) is on PATH not in the
    repo, and a test-id arg (`TestClass.test_method`, or a `path::test` nodeid's suffix) is not a file
    — both are correctly skipped. A `path::test` token is split on `::` first.

    R-04: the frozen surface is the **lexical path, every symlink-chain hop, AND the resolved
    target** — not the resolved target alone. Keeping only `realpath()` had a retarget hole: point a
    tracked oracle link at a weaker tracked test and the diff names the LINK while the candidate set
    held only the NEW target — empty intersection, false FROZEN. Each surface path is normalized to
    the SAME space as `git diff --name-only` (tracked, repo-relative to the work-tree root) so the
    intersection actually matches, which also defeats the **absolute-path** bypass (an abs verified-by
    never matched git's relative diff). A candidate that is out-of-tree or not tracked is dropped —
    it can't be reasoned about via the committed diff, which (if it leaves no oracle) yields fail-deny
    upstream.

    Returns ({repo-relative path: absolute path}, [tampered paths]).
    """
    ok, top = _git(repo, "rev-parse", "--show-toplevel")
    if not ok or not top.strip():
        return {}, []
    toplevel = os.path.realpath(top.strip())
    try:
        tokens = shlex.split(verified_by)
    except ValueError:
        tokens = verified_by.split()
    files: dict[str, str] = {}
    tampered: list[str] = []  # surface paths that existed at base but are gone/untracked now → fail-deny
    for tok in tokens:
        candidate = tok.split("::", 1)[0]  # pytest nodeid: keep the file part
        if not candidate or candidate.startswith("-"):
            continue
        abs_candidate = candidate if os.path.isabs(candidate) else os.path.join(repo, candidate)
        for p in _surface_paths(toplevel, abs_candidate):
            rel = os.path.normpath(os.path.relpath(p, toplevel))
            if rel.startswith(".."):
                continue  # outside the work tree → cannot appear in the diff
            # A path that ISN'T a currently-tracked file/link is dropped — BUT if that same path was a
            # tracked blob at `base`, its disappearance is exactly the tamper this check exists to
            # catch (deletion/rename of an oracle file, or of one file of a multi-file witness, must
            # NOT pass on the survivors). Distinguish deletion (existed at base → tampered) from a
            # non-file token that was never an oracle (interpreter / bare test-id → never at base →
            # safely dropped).
            present = os.path.isfile(p) or os.path.islink(p)  # islink: a dangling link still exists
            if not present or not _git(repo, "ls-files", "--error-unmatch", "--", rel)[0]:
                if _existed_at_base(repo, base, rel):
                    tampered.append(rel)
                continue
            files[rel] = p
    return files, tampered


def _base_state_mismatch(repo: str, base: str, rel: str, abs_path: str) -> str | None:
    """Compare the CURRENT lexical path against the base tree — its TYPE, and its BYTES.

    A committed change is caught by the diff intersection; this catches the UNCOMMITTED one: the loop
    can weaken a tracked oracle in the worktree without committing — retarget a link, swap a regular
    file for a link, OR edit a regular file's assertions (`assert real()` → `assert True`) — and a
    committed-diff-only check (three-dot `base...HEAD` compares COMMITS, so worktree edits are
    invisible) would still say FROZEN. That regular-file content case was R-04 finding #1: the type
    and link-target checks below never looked at a regular file's bytes.

    Git's blob for a 120000 entry is the link-target string, and for a regular file the content OID,
    so the base side needs no filesystem state: compare the base OID (from ls-tree) against a
    `git hash-object` of the current worktree file (`--path` applies the same gitattributes filters
    git used to compute the base OID, so a filter can't provoke a false mismatch). Any read failure or
    difference is a mismatch → fail-deny. Returns a human-readable mismatch or None."""
    ok, out = _git(repo, "ls-tree", base, "--", rel)
    if not ok:
        return f"{rel}: cannot read {base} tree state (fail-deny)"
    if not out.strip():
        return None  # not in the base tree — an added path; the diff intersection owns that case
    header = out.split("\t", 1)[0].split()  # "<mode> <type> <oid>" before the tab-separated path
    mode, base_oid = header[0], header[2]
    if mode == "120000":
        if not os.path.islink(abs_path):
            return f"{rel}: a symlink at {base} is no longer a symlink (type change)"
        ok, blob = _git(repo, "cat-file", "blob", f"{base}:{rel}")
        if not ok:
            return f"{rel}: cannot read {base} link target (fail-deny)"
        if os.readlink(abs_path) != blob:
            return f"{rel}: symlink retargeted from {blob!r} to {os.readlink(abs_path)!r}"
    elif os.path.islink(abs_path):
        return f"{rel}: a regular file at {base} is now a symlink (type change)"
    else:
        # Regular file at base, still a regular file: its BYTES must match the base blob (R-04 #1 —
        # an uncommitted content weakening is invisible to both the type check and the committed diff).
        ok, cur_oid = _git(repo, "hash-object", "--path", rel, "--", abs_path)
        if not ok:
            return f"{rel}: cannot hash current oracle content (fail-deny)"
        if cur_oid.strip() != base_oid:
            return f"{rel}: regular-file oracle content changed vs {base} (weakened without commit)"
    return None


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

    reason, oracle_files = evaluate(args.repo, args.base, args.verified_by)
    if reason is not None:
        print(f"NOT-FROZEN: {reason}", file=sys.stderr)
        return 1
    print("FROZEN: oracle untouched on the loop branch — " + ", ".join(sorted(oracle_files)))
    return 0


def evaluate(repo: str, base: str, verified_by: str) -> tuple[str | None, dict[str, str]]:
    """The full point-in-time freeze evaluation, reusable by the atomic runner (run_frozen_oracle.py).

    Returns (refusal_reason, surface): refusal_reason is None iff the complete oracle surface is
    frozen relative to `base`, in which case surface maps each repo-relative frozen path to its
    absolute path. Every ambiguity is a refusal (fail-deny)."""
    if not os.path.isdir(os.path.join(repo, ".git")) and not _git(repo, "rev-parse", "--git-dir")[0]:
        return f"{repo} is not a git repo", {}

    oracle_files, tampered = _oracle_files(repo, base, verified_by)
    if tampered:
        # A verified-by oracle file that was tracked at base is now missing/untracked — deleted or
        # renamed away on the loop branch. The survivors alone can't vouch for the ones that vanished
        # (the loop could have removed exactly the assertion that gated it), so fail-deny.
        return (f"oracle file(s) tracked at {base} are now missing/untracked on the loop "
                f"branch — deleted or renamed (tamper): {', '.join(tampered)} (fail-deny)"), {}
    if not oracle_files:
        # No extractable oracle file → immutability is unverifiable → fail-deny.
        return (f"no existing oracle file found in verified-by {verified_by!r}; "
                f"cannot confirm immutability (fail-deny)"), {}

    # R-04: the current lexical state (path type; link target) must match the base tree — this is
    # what catches an UNCOMMITTED retarget/type-swap that a committed-diff intersection never sees.
    for rel, abs_path in sorted(oracle_files.items()):
        mismatch = _base_state_mismatch(repo, base, rel, abs_path)
        if mismatch:
            return mismatch, {}

    changed = _changed_files(repo, base)
    if changed is None:
        return f"could not diff {base}...HEAD (fail-deny)", {}

    modified = sorted(set(oracle_files) & changed)
    if modified:
        return ("the loop modified its own gating oracle on this branch: " + ", ".join(modified)), {}

    return None, oracle_files


if __name__ == "__main__":
    sys.exit(main())
