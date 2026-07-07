#!/usr/bin/env python3
"""Tests for the guard-loop-vc.py PreToolUse hook.

Drives the hook as a subprocess with a crafted PreToolUse stdin payload, asserting the deny/defer
contract: deny = exit 0 + JSON permissionDecision=deny on stdout; defer = exit 0 with no decision.
Pins the security-load-bearing properties: it is INACTIVE unless CLAUDE_LOOP_GUARD is set; it blocks
the irreversible VC mutations (merge/push/branch-delete/hard-reset/gh-pr-merge) including across
compound commands and background (`&`) operators and env-assignment prefixes; it does NOT false-block
safe reads (`merge-base`, `log --merges`, `branch --merged`, `gh pr view/checkout`); and it fails OPEN
on unparseable input (never a non-zero crash that would wedge the Bash tool).

Stdlib unittest only. Run:
  python3 hooks/tests/test_guard_loop_vc.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guard-loop-vc.py"


def _run(
    command: str,
    *,
    guard: "bool | str" = True,
    tool: str = "Bash",
    raw: "str | None" = None,
    cwd: "str | None" = None,
) -> "tuple[int, str]":
    env = dict(os.environ)
    env.pop("CLAUDE_LOOP_GUARD", None)
    if guard:  # True → conservative "1"; a str ("1"/"yolo") sets that mode; False → unset (inactive)
        env["CLAUDE_LOOP_GUARD"] = guard if isinstance(guard, str) else "1"
    payload = raw if raw is not None else json.dumps({"tool_name": tool, "tool_input": {"command": command}})
    p = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env, cwd=cwd)
    return p.returncode, p.stdout


def _denied(stdout: str) -> bool:
    try:
        return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    except (ValueError, KeyError):
        return False


class TestGuardLoopVC(unittest.TestCase):
    # --- deny set (guard active) ---
    DENY = [
        "git merge --no-ff feature",
        "git -C /repo merge topic",
        "git --attr-source HEAD merge topic",                 # global value-flag shifts subcommand
        "git --config-env sec.key=ENVVAR merge topic",        # ditto (--config-env takes a space value)
        "git push origin main",
        "git push",
        "git branch -d feature",
        "git branch -D feature",
        "git branch --delete feature",
        "git reset --hard HEAD~1",
        "git worktree remove ../wt",
        "gh pr merge 5 --squash",
        "gh -R owner/repo pr merge 5",                         # value-flag before subcommand path
        "gh pr --repo owner/repo merge 5",                     # value-flag between pr and merge
        "git add -A && git commit -m x && git merge topic",   # compound (&&)
        "sleep 1 & git push",                                  # background (&) must still segment
        "echo hi; git merge x",                                # semicolon
        "FOO=bar GIT_PAGER=cat git push",                      # env-assignment prefix
        "/usr/bin/git merge x",                                # absolute path → basename
        "git clean -fd",                                       # delete untracked files (no reflog)
        "git clean -fdx",
        "git clean -f",
        "git clean -xdf",                                      # combined short flags, any order
        "git clean",                                           # bare (harmless no-op, but deny anyway)
        "git -C /repo clean -fd",                              # via -C
        "git clean -fenode_modules",                           # -e<pattern> exclude: 'n' in pattern is NOT -n
        "git clean -fxe.next",                                 # ditto, trailing attached exclude
        "git clean -f -e node_modules",                        # separate -e value (not a flag)
        "git clean -fde -n",                                   # trailing -e in cluster eats '-n' as its value
        "git clean --exclude=foo -f",                          # long exclude, still a force delete
        "git clean -fd -- -n",                                 # '-n' after `--` is a pathspec, not dry-run
        "git clean -fdx secret -- --dry-run",                  # ditto: force-delete with post-`--` decoy
        "git clean -fd --end-of-options -n",                   # `--end-of-options` is the other terminator
        "git clean -fd --end-of-options --dry-run secret",     # ditto, --dry-run decoy after it
        # trust-anchor rewrites: both verbs can repoint refs/remotes/origin/HEAD, which the guards
        # read for default-branch detection — a loop may not re-aim its own judge
        "git remote set-head origin develop",
        "git remote set-head origin -a",
        "git -C /repo remote set-head origin main",
        "git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop",
        "git symbolic-ref -m reason refs/remotes/origin/HEAD refs/remotes/origin/develop",
        "git symbolic-ref -d refs/remotes/origin/HEAD",
        "git symbolic-ref --delete refs/remotes/origin/HEAD",
    ]

    # --- allow set (guard active): safe reads / non-irreversible writes ---
    ALLOW = [
        'git commit -m "done"',
        "git log --merges --oneline",
        "git merge-base main topic",
        "git branch --merged",
        "git switch -c fix/foo",
        "git checkout -b fix/foo",
        "git reset --soft HEAD~1",
        "git -c push.default=simple status",  # `push` here is a -c value, not the subcommand
        "git clean -n",                       # dry-run never deletes
        "git clean --dry-run",
        "git clean -nd",                      # combined short with 'n' → dry-run
        "git clean -fn",                      # force + dry-run → dry-run wins
        "git clean -e foo -n",                # exclude value 'foo' then a real -n → dry-run
        "git clean -n -- foo",                # real dry-run; 'foo' after `--` is a pathspec
        "git clean -fdn --end-of-options foo",  # real -n BEFORE the terminator → still dry-run
        "gh pr view 5",
        "gh -R owner/repo pr view 5",          # value-flag before a read subcommand → allow
        "gh pr list --label merge",           # `merge` is a flag value, not the subcommand
        "gh pr checkout some-merge-branch",   # branch name contains 'merge'
        "git status && git diff",
        # read forms of the trust-anchor verbs stay allowed (the guards themselves use them)
        "git symbolic-ref HEAD",
        "git symbolic-ref --quiet refs/remotes/origin/HEAD",
        "git symbolic-ref --short HEAD",
        "git remote -v",
        "git remote show origin",
        "git remote get-url origin",
    ]

    def test_deny_set(self):
        for cmd in self.DENY:
            rc, out = _run(cmd)
            self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {cmd}")
            self.assertTrue(_denied(out), f"should be DENIED but was allowed: {cmd}")

    def test_allow_set(self):
        for cmd in self.ALLOW:
            rc, out = _run(cmd)
            self.assertEqual((rc, out.strip()), (0, ""), f"should DEFER (no decision) but didn't: {cmd}")

    def test_trust_anchor_rewrite_denied_read_allowed(self):
        # TELOS-009 witness: the verbs that repoint refs/remotes/origin/HEAD (the default-branch
        # trust anchor BOTH guards read) are denied in write/delete form, while the read form —
        # which the guards themselves rely on — stays allowed.
        for cmd in (
            "git remote set-head origin develop",
            "git remote set-head origin -a",
            "git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop",
            "git symbolic-ref -m why refs/remotes/origin/HEAD refs/remotes/origin/develop",
            "git symbolic-ref -d refs/remotes/origin/HEAD",
            "git symbolic-ref --delete refs/remotes/origin/HEAD",
        ):
            rc, out = _run(cmd)
            self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {cmd}")
            self.assertTrue(_denied(out), f"trust-anchor rewrite must be DENIED: {cmd}")
        for cmd in (
            "git symbolic-ref HEAD",
            "git symbolic-ref --quiet refs/remotes/origin/HEAD",
            "git symbolic-ref --short HEAD",
            "git remote -v",
            "git remote show origin",
        ):
            rc, out = _run(cmd)
            self.assertEqual((rc, out.strip()), (0, ""), f"read form must stay allowed: {cmd}")

    def test_inactive_without_marker(self):
        # The same dangerous commands must be ALLOWED (deferred) when CLAUDE_LOOP_GUARD is unset.
        for cmd in ("git merge x", "git push", "git branch -D x"):
            rc, out = _run(cmd, guard=False)
            self.assertEqual((rc, out.strip()), (0, ""), f"must be inactive without marker: {cmd}")

    def test_non_bash_tool_defers(self):
        rc, out = _run("git merge x", tool="Edit")
        self.assertEqual((rc, out.strip()), (0, ""))

    def test_unparseable_stdin_fails_open(self):
        rc, out = _run("", raw="this is not json {{{")
        self.assertEqual((rc, out.strip()), (0, ""))  # fail open, never crash

    def test_empty_command_defers(self):
        rc, out = _run("")
        self.assertEqual((rc, out.strip()), (0, ""))


def _mkrepo(branches: "tuple[str, ...]" = (), *, checkout: str, default_config: "str | None" = None) -> str:
    """Create a throwaway local git repo (no remote) with an initial commit on `main`.

    Creates each name in `branches`, then checks out `checkout` (use "DETACH" for a detached HEAD).
    Local-only by design: exercises the main/master heuristic in _default_branch. `default_config`
    sets `init.defaultBranch` locally (to disambiguate when both main and master exist).
    """
    d = tempfile.mkdtemp(prefix="guardtest-")

    def g(*args: str) -> None:
        subprocess.run(["git", "-C", d, *args], check=True, capture_output=True, text=True)

    g("init", "-b", "main")
    g("config", "user.email", "t@t.t")
    g("config", "user.name", "t")
    if default_config is not None:
        g("config", "init.defaultBranch", default_config)
    g("commit", "--allow-empty", "-m", "init")
    for b in branches:
        g("branch", b)
    if checkout == "DETACH":
        sha = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        g("checkout", "--detach", sha)
    else:
        g("checkout", checkout)
    return d


class TestGuardYoloMode(unittest.TestCase):
    """YOLO mode (CLAUDE_LOOP_GUARD=yolo): allow --no-ff merges into a non-default branch only."""

    def setUp(self) -> None:
        self._repos: list[str] = []

    def tearDown(self) -> None:
        for d in self._repos:
            shutil.rmtree(d, ignore_errors=True)

    def _repo(self, **kw: object) -> str:
        d = _mkrepo(**kw)  # type: ignore[arg-type]
        self._repos.append(d)
        return d

    def _denied(self, cmd: str) -> bool:
        rc, out = _run(cmd, guard="yolo")
        self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {cmd}")
        return _denied(out)

    def _deferred(self, cmd: str) -> bool:
        rc, out = _run(cmd, guard="yolo")
        return (rc, out.strip()) == (0, "")

    # --- the one thing YOLO loosens: --no-ff merge into a non-default branch ---
    def test_allows_no_ff_merge_into_nondefault(self):
        d = self._repo(branches=("feature",), checkout="feature")
        self.assertTrue(self._deferred(f"git -C {d} merge --no-ff topic"))

    # --- everything else stays denied ---
    def test_denies_fast_forward_merge(self):
        d = self._repo(branches=("feature",), checkout="feature")
        self.assertTrue(self._denied(f"git -C {d} merge topic"))         # no --no-ff
        self.assertTrue(self._denied(f"git -C {d} merge --ff-only topic"))

    def test_denies_merge_into_default(self):
        d = self._repo(checkout="main")
        self.assertTrue(self._denied(f"git -C {d} merge --no-ff topic"))

    def test_denies_merge_on_detached_head(self):
        d = self._repo(checkout="DETACH")
        self.assertTrue(self._denied(f"git -C {d} merge --no-ff topic"))

    def test_denies_merge_when_default_ambiguous(self):
        # both main and master exist, init.defaultBranch names neither → undeterminable → fail-deny
        d = self._repo(branches=("master", "feature"), checkout="feature", default_config="trunk")
        self.assertTrue(self._denied(f"git -C {d} merge --no-ff topic"))

    def test_disambiguates_default_via_config_then_allows(self):
        # both exist, init.defaultBranch=main; on a feature branch → main is default, feature != main → allow
        d = self._repo(branches=("master", "feature"), checkout="feature", default_config="main")
        self.assertTrue(self._deferred(f"git -C {d} merge --no-ff topic"))

    def test_denies_merge_while_on_protected_name(self):
        # default resolves to main, but master is a protected name → merging on master is still denied
        d = self._repo(branches=("master", "feature"), checkout="master", default_config="main")
        self.assertTrue(self._denied(f"git -C {d} merge --no-ff topic"))

    def test_still_denies_destructive_acts(self):
        d = self._repo(branches=("feature",), checkout="feature")
        for cmd in (
            f"git -C {d} push",
            f"git -C {d} push origin main",
            f"git -C {d} reset --hard HEAD~1",
            f"git -C {d} clean -fd",
            f"git -C {d} clean -fenode_modules",   # the exclude-pattern bypass must stay denied in YOLO too
            f"git -C {d} branch -D feature",
            f"git -C {d} worktree remove ../wt",
            "gh pr merge 5",
            f"git -C {d} remote set-head origin develop",       # trust-anchor rewrite
            f"git -C {d} symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop",
        ):
            self.assertTrue(self._denied(cmd), f"YOLO must still deny: {cmd}")

    def test_conservative_mode_still_denies_all_merges(self):
        # the same --no-ff-into-non-default merge that YOLO allows must STILL be denied under "1"
        d = self._repo(branches=("feature",), checkout="feature")
        rc, out = _run(f"git -C {d} merge --no-ff topic", guard="1")
        self.assertTrue(_denied(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
