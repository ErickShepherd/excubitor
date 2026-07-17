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
    # Keep test denies out of the real telemetry log (every deny appends — see hooks/_denial_log.py).
    env.setdefault("EXCUBITOR_DENIAL_LOG", os.devnull)
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
        # P0.14 spellings: repo selectors must not hide the subcommand from the conservative scan
        "git --git-dir=/repo/.git --work-tree=/repo merge topic",
        "git --git-dir /repo/.git push",
        "git --work-tree=/repo merge --no-ff topic",
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
        "(git push)",                                          # subshell glue must not hide the push
        "(git merge topic)",
        "echo $(git push)",                                    # command substitution
        "`git push`",                                          # backtick substitution
        "(git remote set-head origin develop)",                # trust-anchor rewrite inside a subshell
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
        # R-02: clustered short options — `-d`/`-D` hidden in a cluster still delete
        "git branch -vd feature",                              # verbose + delete
        "git branch -rd origin/feature",                       # remote-tracking delete
        "git branch -qD feature",                              # quiet + force-delete
        "git branch -dr origin/feature",                       # delete letter first in the cluster
        "git symbolic-ref -qd refs/remotes/origin/HEAD",       # quiet + delete
        # direct ref MOVES — repoint/rename/overwrite an existing ref without a porcelain verb; the
        # forge the P0.13 base-pin depends on being fenced (git branch -f main <sha>, etc.)
        "git branch -f main other",                            # force-move a branch ref
        "git branch --force main other",                       # ... long form
        "git branch -m old new",                               # rename (old name vanishes)
        "git branch -M main",                                  # force-rename
        "git branch -C main copy",                             # force-copy over an existing ref
        "git branch -fm a b",                                  # clustered force+move
        "git branch --forc main x",                            # unambiguous abbreviation of --force
        "git update-ref refs/heads/main HEAD",                 # move a ref directly (plumbing)
        "git update-ref -d refs/heads/main",                   # delete a ref directly
        "git -C /repo update-ref refs/heads/master HEAD~1",    # ... via -C
        "git switch -C main",                                  # force-recreate a branch
        "git switch -Cmain",                                   # ... attached value
        "git switch -fC main",                                 # ... clustered after -f
        "git checkout -B main",                                # force-recreate via checkout
        "git checkout -B main origin/main",
        "git worktree add -B main ../wt",                      # force-reset a branch ref via worktree
        "git worktree add -fB main ../wt",                     # ... clustered
        "sudo git branch -f main other",                       # launcher + ref move
        "cd /repo && git update-ref refs/heads/main HEAD",     # ref move in a compound command
        # exec-prefix launchers run the real command one token deeper — the fenced verb must still
        # be seen (representative cases; the full battery is TestLauncherPrefix)
        "env git push origin main",                            # POSIX launcher, no privilege
        "env -a x git push",                                    # env -a <argv0> still execs (coreutils 9.x)
        "env --argv0 x git branch -D main",                    # ... separate long form
        # value options CLUSTERED behind other short flags still consume their value (not read as
        # the command) — a `-u`→`-vu` cluster must not reopen the bypass
        "env -vu FOO git push",                                # -vu = -v (flag) + -u <var>; env intact
        "sudo -knu deploy git branch -D main",                 # -knu = -k -n -u <user>
        "ionice -tc 2 git push",                               # -tc = -t (flag) + -c <class>
        "timeout -fs KILL 30 git push",                        # -fs = -f + -s <sig>, then DURATION
        "sudo git branch -D main",                             # launcher + branch delete
        "nice -n 5 git merge --no-ff topic",                   # launcher with a value-option
        "timeout 60 git push",                                 # launcher with a leading DURATION
        "env gh pr merge 5",                                   # launcher in front of gh
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
        "git worktree add ../wt remove",      # 'remove' here is a branch/path name, not the subcommand
        "git worktree list",
        "git status && git diff",
        "git --git-dir=/repo/.git status",     # repo selector on a non-fenced subcommand
        "git --work-tree /repo status",
        # read forms of the trust-anchor verbs stay allowed (the guards themselves use them)
        "git symbolic-ref HEAD",
        "git symbolic-ref --quiet refs/remotes/origin/HEAD",
        "git symbolic-ref --short HEAD",
        "git remote -v",
        "git remote show origin",
        "git remote get-url origin",
        # R-02 read-only near-misses: clusters WITHOUT a delete letter must not false-deny
        "git branch -v",                       # verbose list
        "git branch -vv",                      # doubly verbose list
        "git branch -a",                       # all branches
        "git branch -r",                       # remote-tracking list
        "git branch --list -v",                # explicit list
        "git branch -u origin/main feature",   # -u takes a value; no delete here
        "git branch -c old new",               # NON-force copy (create): allowed, unlike -C
        "git switch -c fix/new",               # create+switch (lowercase -c): allowed, unlike -C
        "git switch -cFooCase",                # -c with an attached CamelCase name — not -C
        "git checkout -b fix/new",             # create branch (lowercase -b): allowed, unlike -B
        "git checkout -bFix",                  # -b attached name with a capital — not -B
        "git worktree add -b new ../wt",       # create-only worktree branch (-b): allowed, unlike -B
        "git switch --force main",             # discard-changes switch — a prefix of --force-create, allowed
        # a dangerous verb QUOTED in an argument is literal text, not a command — must not false-deny
        # (this repo's own commit messages are full of these strings)
        'git commit -m "document the (git push) bypass"',
        'git commit -m "pin the (git merge) case"',
        'echo "to release run (git push origin main)"',
        "echo 'inside single quotes: git push is literal'",
        'git commit -m "see guard-loop-vc.py `git push` handling"',
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
            "(git remote set-head origin develop)",             # grouped inside a subshell
            "echo $(git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop)",
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

    # Documented bypasses this seatbelt deliberately does NOT catch (the guard matches LITERAL
    # subcommand tokens; it does not expand the shell). Pinned BIDIRECTIONALLY: each asserts the
    # bypass currently ALLOWS, so if a change starts catching one, this fails and forces an honest
    # SCOPE / LIMITS + KNOWN-BYPASSES.md update rather than a silent scope change. Closing these means
    # reimplementing shell expansion — the deny-set-completeness creep the honest-limits brand resists.
    ACCEPTED_RESIDUALS = [
        "git pus{h,} origin main",           # brace expansion → a real `git push`
        "git merge{,} --no-ff topic",        # brace expansion → a real `git merge`
        "git pus*h origin main",             # glob (matches nothing, but token != 'push' either way)
        "G=push; git $G origin main",         # subcommand hidden in a shell variable
        'git commit -m "$(git push)"',       # LIVE substitution inside double quotes (bash WOULD run it)
    ]

    def test_accepted_residuals_still_allow(self):
        for cmd in self.ACCEPTED_RESIDUALS:
            rc, out = _run(cmd)
            self.assertEqual(
                (rc, out.strip()), (0, ""),
                f"ACCEPTED-RESIDUAL CHANGED: this bypass used to slip past (documented in SCOPE / "
                f"LIMITS); it is now caught. Update SCOPE / LIMITS + KNOWN-BYPASSES.md and move it "
                f"out of ACCEPTED_RESIDUALS: {cmd}")

    # Dangerous-but-out-of-scope git verbs the fence deliberately does NOT cover (KNOWN-BYPASSES.md
    # "dangerous git verbs outside the fenced set"). Pinned ALLOW bidirectionally: if one starts
    # being denied, this fails and forces an honest update rather than a silent scope expansion —
    # the guard's deny-set is a deliberate choice, not an accident, and this documents its edges.
    UNHANDLED_GIT_VERBS = [
        "git reflog expire --expire=now --all",    # drop the reflog
        "git stash drop",
        "git stash clear",
        "git tag -d v1.0",
        "git filter-branch --force HEAD",          # history rewrite (current branch)
        "git rebase -i HEAD~3",
        "git gc --prune=now",
        "git checkout -- .",                        # discard uncommitted tracked changes
        "git restore .",
    ]

    def test_unhandled_git_verbs_still_allow(self):
        for cmd in self.UNHANDLED_GIT_VERBS:
            rc, out = _run(cmd)
            self.assertEqual(
                (rc, out.strip()), (0, ""),
                f"DENY-SET CHANGED: this verb is documented as an out-of-scope known bypass "
                f"(KNOWN-BYPASSES.md) and used to ALLOW; it is now denied. If that is intended, "
                f"update KNOWN-BYPASSES.md and move it out of UNHANDLED_GIT_VERBS: {cmd}")

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

    def test_non_object_json_fails_open(self):
        # valid JSON that is not an object (5, "x", [], null) must fail OPEN, not crash with an
        # AttributeError on payload.get(...) — the never-exit-non-zero contract is unconditional.
        for raw in ("5", '"x"', "[]", "null", "true"):
            rc, out = _run("", raw=raw)
            self.assertEqual((rc, out.strip()), (0, ""), f"non-object payload must defer: {raw!r}")

    def test_non_dict_tool_input_fails_open(self):
        rc, out = _run("", raw=json.dumps({"tool_name": "Bash", "tool_input": "not-a-dict"}))
        self.assertEqual((rc, out.strip()), (0, ""))

    # --- P0.16 sibling hardening: truthy NON-string field types must fail OPEN, never exit 1 ---
    def test_non_string_command_fails_open(self):
        # A truthy non-string command pre-fix reached split_segments (len() on an int/list) →
        # TypeError → exit 1, against the never-exit-non-zero contract. Must defer.
        for command in (123, ["git", "push"], {"c": "git push"}, True):
            rc, out = _run("", raw=json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": command}}))
            self.assertEqual((rc, out.strip()), (0, ""),
                             f"non-string command must fail open, not crash: {command!r}")

    def test_non_string_cwd_falls_back_and_still_denies(self):
        # A truthy non-string cwd pre-fix crashed in os.path.join composing a relative -C (exit 1).
        # Post-fix it falls back to the process cwd — and the conservative merge deny still fires:
        # the malformed cwd degrades gracefully instead of dropping the fence.
        rc, out = _run("", raw=json.dumps(
            {"tool_name": "Bash", "cwd": 123,
             "tool_input": {"command": "git -C rel merge topic"}}))
        self.assertEqual(rc, 0, "non-string cwd must never exit non-zero")
        self.assertTrue(_denied(out), "the merge deny must survive a malformed cwd")


def _mkrepo(
    branches: "tuple[str, ...]" = (),
    *,
    checkout: str,
    default_config: "str | None" = None,
    at: "str | None" = None,
) -> str:
    """Create a throwaway local git repo (no remote) with an initial commit on `main`.

    Creates each name in `branches`, then checks out `checkout` (use "DETACH" for a detached HEAD).
    Local-only by design: exercises the main/master heuristic in _default_branch. `default_config`
    sets `init.defaultBranch` locally (to disambiguate when both main and master exist). `at` pins
    the repo to a specific directory (created if missing) instead of a fresh tempdir — used by the
    P0.14 composed-`-C` tests, which need repos at exact relative positions.
    """
    d = at or tempfile.mkdtemp(prefix="guardtest-")
    os.makedirs(d, exist_ok=True)

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


def _mkrepo_with_origin_head(default_branch: str) -> str:
    """A throwaway repo whose AUTHORITATIVE default is a slash-containing `default_branch`.

    Fabricates the remote trust anchor without a real remote: creates a local branch of that
    name, mirrors it into `refs/remotes/origin/<name>`, points `refs/remotes/origin/HEAD` at it,
    and checks the branch out — so the checked-out branch IS the resolved default. This is the
    R-01 shape (`release/2.0`, `team/main`): before the fix, `_default_branch` kept only the last
    slash segment and mis-resolved the default, waving a YOLO merge into the real trunk through.
    """
    d = tempfile.mkdtemp(prefix="guardtest-")

    def g(*args: str) -> None:
        subprocess.run(["git", "-C", d, *args], check=True, capture_output=True, text=True)

    g("init", "-b", "main")
    g("config", "user.email", "t@t.t")
    g("config", "user.name", "t")
    g("commit", "--allow-empty", "-m", "init")
    g("branch", default_branch)
    sha = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    g("update-ref", f"refs/remotes/origin/{default_branch}", sha)
    g("symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{default_branch}")
    g("checkout", default_branch)
    return d


class TestGuardClusteredShortOptions(unittest.TestCase):
    """R-02: clustered short options (`-vd`, `-rd`, `-qD`, `-qd`) must be denied, AND the denied
    spellings must be REAL Git operations — proven by executing them against a temp repo — so the
    deny cases can never rot into strawmen that Git would itself reject."""

    def setUp(self) -> None:
        self._repos: list[str] = []

    def tearDown(self) -> None:
        for d in self._repos:
            shutil.rmtree(d, ignore_errors=True)

    def _repo(self) -> str:
        d = tempfile.mkdtemp(prefix="guardtest-")
        self._repos.append(d)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", d, *args], check=True, capture_output=True, text=True)

        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        g("commit", "--allow-empty", "-m", "init")
        return d

    @staticmethod
    def _branch_exists(d: str, name: str) -> bool:
        return subprocess.run(
            ["git", "-C", d, "show-ref", "--verify", "--quiet", f"refs/heads/{name}"]
        ).returncode == 0

    def test_clustered_branch_delete_denied_and_is_real(self):
        # For each spelling: the guard denies it, AND (in a real repo) Git accepts it and deletes.
        for spelling in ("-vd", "-qD", "-dq"):
            d = self._repo()
            subprocess.run(["git", "-C", d, "branch", "victim"], check=True, capture_output=True)
            rc, out = _run(f"git -C {d} branch {spelling} victim")
            self.assertEqual(rc, 0, "fail-open contract")
            self.assertTrue(_denied(out), f"clustered branch delete must be denied: branch {spelling}")
            # prove the spelling is a genuine delete, not a strawman the guard 'catches' for free
            self.assertTrue(self._branch_exists(d, "victim"))
            subprocess.run(["git", "-C", d, "branch", spelling, "victim"], check=True, capture_output=True)
            self.assertFalse(self._branch_exists(d, "victim"), f"git branch {spelling} should have deleted")

    def test_clustered_symbolic_ref_delete_denied_and_is_real(self):
        d = self._repo()
        subprocess.run(["git", "-C", d, "symbolic-ref", "refs/test-anchor", "refs/heads/main"],
                       check=True, capture_output=True)
        rc, out = _run(f"git -C {d} symbolic-ref -qd refs/test-anchor")
        self.assertEqual(rc, 0, "fail-open contract")
        self.assertTrue(_denied(out), "clustered symbolic-ref delete (-qd) must be denied")
        # prove -qd genuinely deletes the symbolic ref
        exists = subprocess.run(["git", "-C", d, "symbolic-ref", "refs/test-anchor"],
                                capture_output=True).returncode == 0
        self.assertTrue(exists)
        subprocess.run(["git", "-C", d, "symbolic-ref", "-qd", "refs/test-anchor"],
                       check=True, capture_output=True)
        gone = subprocess.run(["git", "-C", d, "symbolic-ref", "refs/test-anchor"],
                              capture_output=True).returncode != 0
        self.assertTrue(gone, "git symbolic-ref -qd should have deleted the ref")


class TestGuardYoloDefaultBranchParsing(unittest.TestCase):
    """R-01: a slash-containing authoritative default branch must be resolved WHOLE, so a YOLO
    merge while checked out on it is denied (it is the real trunk, not a non-default branch)."""

    def setUp(self) -> None:
        self._repos: list[str] = []

    def tearDown(self) -> None:
        for d in self._repos:
            shutil.rmtree(d, ignore_errors=True)

    def _repo(self, default_branch: str) -> str:
        d = _mkrepo_with_origin_head(default_branch)
        self._repos.append(d)
        return d

    def test_denies_yolo_merge_on_slash_default_release(self):
        # origin/HEAD -> origin/release/2.0; checked out on release/2.0 (the real default).
        # Pre-fix: default mis-resolved to "2.0" != "release/2.0" and not a literal main/master → ALLOWED.
        d = self._repo("release/2.0")
        rc, out = _run(f"git -C {d} merge --no-ff topic", guard="yolo")
        self.assertEqual(rc, 0, "fail-open contract")
        self.assertTrue(_denied(out), "merge into the real default 'release/2.0' must be denied")

    def test_denies_yolo_merge_on_slash_default_team_main(self):
        # 'team/main' proves the CLASS, not the main/master hardcode: pre-fix it mis-resolved to
        # "main", and the literal-name guard does NOT catch "team/main" (!= "main") → ALLOWED.
        d = self._repo("team/main")
        rc, out = _run(f"git -C {d} merge --no-ff topic", guard="yolo")
        self.assertEqual(rc, 0, "fail-open contract")
        self.assertTrue(_denied(out), "merge into the real default 'team/main' must be denied")


class TestGuardYoloRepoSelector(unittest.TestCase):
    """P0.14: a repository/directory selector must not divorce YOLO branch detection from the repo
    the merge actually TARGETS. Pre-fix, only the separate `-C` was captured, so
    `git --git-dir=/protected/.git --work-tree=/protected merge --no-ff topic` (git-accepted) was
    evaluated against the payload cwd — an innocent feature-branch cwd waved a merge into another
    repo's default branch through. Modeled spellings (repeated/composed relative `-C`,
    `--git-dir`/`--work-tree` in separate and `=`-attached form) now resolve detection against the
    TARGET repo, faithfully in both directions (deny when it targets a default, allow when it
    targets a non-default). Unmodeled spellings — attached `-C<path>` (git-rejected today;
    hardening), `GIT_DIR`-family env assignments, launcher chdir options (`env -C`, `sudo -D`,
    `--chdir`) — fail-deny the merge outright rather than guess."""

    def setUp(self) -> None:
        self._dirs: list[str] = []

    def tearDown(self) -> None:
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _repo(self, **kw: object) -> str:
        d = _mkrepo(**kw)  # type: ignore[arg-type]
        self._dirs.append(d)
        return d

    def _protected(self) -> str:
        """A repo checked out on its default branch `main` — the merge target to protect."""
        return self._repo(checkout="main")

    def _innocent(self) -> str:
        """A repo checked out on a non-default branch — the cwd a bypass would launder through."""
        return self._repo(branches=("feature",), checkout="feature")

    def _denied(self, cmd: str, cwd: str) -> bool:
        rc, out = _run(cmd, guard="yolo", cwd=cwd)
        self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {cmd}")
        return _denied(out)

    def _deferred(self, cmd: str, cwd: str) -> bool:
        rc, out = _run(cmd, guard="yolo", cwd=cwd)
        return (rc, out.strip()) == (0, "")

    # --- modeled spellings: detection follows the selector to the TARGET repo ---
    def test_denies_git_dir_work_tree_merge_targeting_default(self):
        target, cwd = self._protected(), self._innocent()
        for cmd in (
            f"git --git-dir={target}/.git --work-tree={target} merge --no-ff topic",  # =-attached
            f"git --git-dir {target}/.git --work-tree {target} merge --no-ff topic",  # separate
            f"git --work-tree={target} --git-dir={target}/.git merge --no-ff topic",  # order swapped
        ):
            self.assertTrue(self._denied(cmd, cwd),
                            f"selector-targeted default-branch merge must be denied: {cmd}")

    def test_allows_git_dir_merge_targeting_nondefault(self):
        # The inverse direction: faithful modeling, not a blanket deny of --git-dir. The payload cwd
        # sits on main (a plain merge HERE would be denied); the selectors target a feature-branch
        # repo, so the merge is a legitimate YOLO integration and must defer.
        cwd, target = self._protected(), self._innocent()
        cmd = f"git --git-dir={target}/.git --work-tree={target} merge --no-ff topic"
        self.assertTrue(self._deferred(cmd, cwd),
                        "selector-targeted NON-default merge must still be allowed (no blanket deny)")

    def test_denies_composed_relative_C_merge_targeting_default(self):
        # git composes repeated relative -C values (`-C sub1 -C sub2` = sub1/sub2). Pre-fix each
        # value resolved against cwd independently, so detection landed on X/sub2 — planted here as
        # a feature-branch repo to pin the pre-fix ALLOW direction — instead of the real target
        # X/sub1/sub2, which sits on main and must deny.
        x = tempfile.mkdtemp(prefix="guardtest-")
        self._dirs.append(x)
        _mkrepo(checkout="main", at=os.path.join(x, "sub1", "sub2"))          # the real target
        _mkrepo(branches=("feature",), checkout="feature", at=os.path.join(x, "sub2"))  # decoy
        self.assertTrue(self._denied("git -C sub1 -C sub2 merge --no-ff topic", x),
                        "composed relative -C must resolve against the preceding -C, not cwd")

    def test_git_dir_selector_merge_is_real(self):
        # Prove the modeled spelling is a GENUINE cross-directory merge, not a strawman: from an
        # unrelated cwd, git accepts it and creates a merge commit on the target's checked-out main.
        target = self._protected()

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", target, *args], check=True, capture_output=True, text=True)

        g("switch", "-c", "topic")
        g("commit", "--allow-empty", "-m", "topic work")
        g("switch", "main")
        elsewhere = tempfile.mkdtemp(prefix="guardtest-")
        self._dirs.append(elsewhere)
        cmd = f"git --git-dir={target}/.git --work-tree={target} merge --no-ff topic"
        self.assertTrue(self._denied(cmd, elsewhere))
        subprocess.run(
            ["git", f"--git-dir={target}/.git", f"--work-tree={target}", "merge", "--no-ff", "topic"],
            cwd=elsewhere, check=True, capture_output=True, text=True)
        has_second_parent = subprocess.run(
            ["git", "-C", target, "rev-parse", "--verify", "HEAD^2"], capture_output=True
        ).returncode == 0
        self.assertTrue(has_second_parent,
                        "the selector spelling should have produced a real merge commit on main")

    # --- unmodeled spellings: fail-deny rather than guess ---
    def test_denies_attached_C_merge_and_git_still_rejects_it(self):
        target, cwd = self._protected(), self._innocent()
        cmd = f"git -C{target} merge --no-ff topic"
        self.assertTrue(self._denied(cmd, cwd), "attached -C<path> must fail-deny (unmodeled selector)")
        # Pin the hardening claim: git 2.47.3 REJECTS this spelling, so the deny is future-proofing,
        # not a live-bypass closure. If a future git starts ACCEPTING attached -C, this fails and
        # forces re-verification (the spelling would then need real modeling, not just a fail-deny).
        p = subprocess.run(["git", f"-C{target}", "status"], cwd=cwd, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0, "git now ACCEPTS attached -C — re-verify P0.14 modeling")

    def test_denies_git_env_selector_merge(self):
        target, cwd = self._protected(), self._innocent()
        for cmd in (
            f"GIT_DIR={target}/.git git merge --no-ff topic",
            f"GIT_DIR={target}/.git GIT_WORK_TREE={target} git merge --no-ff topic",
            f"GIT_WORK_TREE={target} git merge --no-ff topic",
            f"GIT_COMMON_DIR={target}/.git git merge --no-ff topic",
            f"env GIT_DIR={target}/.git git merge --no-ff topic",  # same selector via `env`
        ):
            self.assertTrue(self._denied(cmd, cwd),
                            f"GIT_DIR-family env selector must fail-deny a YOLO merge: {cmd}")

    def test_non_selector_env_assignment_still_allows(self):
        # Bidirectional: an ordinary env-assignment prefix is NOT a repo selector and must not trip
        # the fail-deny — the merge below targets the cwd's non-default branch and stays allowed.
        cwd = self._innocent()
        self.assertTrue(self._deferred("GIT_PAGER=cat git merge --no-ff topic", cwd))

    def test_denies_launcher_chdir_merge(self):
        target, cwd = self._protected(), self._innocent()
        for cmd in (
            f"env -C {target} git merge --no-ff topic",
            f"env -C{target} git merge --no-ff topic",        # attached short value
            f"env --chdir {target} git merge --no-ff topic",
            f"env --chdir={target} git merge --no-ff topic",  # =-attached long value
            f"sudo -D {target} git merge --no-ff topic",
            f"sudo --chdir={target} git merge --no-ff topic",
            f"env -C {target} bash -c 'git merge --no-ff topic'",  # threaded through the -c re-scan
        ):
            self.assertTrue(self._denied(cmd, cwd),
                            f"launcher chdir option must fail-deny a YOLO merge: {cmd}")
        # Documented cost of the fail-deny posture: even a chdir into a repo whose merge WOULD be
        # legitimate is denied — the guard refuses to model launcher chdir rather than half-model it.
        legit = self._innocent()
        self.assertTrue(self._denied(f"env -C {legit} git merge --no-ff topic", cwd))

    def test_launcher_chdir_non_merge_still_allows(self):
        # The unmodeled-selector flag feeds ONLY the YOLO merge decision — a chdir launcher in front
        # of a non-fenced command must not manufacture a deny.
        target, cwd = self._protected(), self._innocent()
        self.assertTrue(self._deferred(f"env -C {target} git status", cwd))
        self.assertTrue(self._deferred(f"GIT_DIR={target}/.git git status", cwd))

    def test_denies_cross_segment_dir_change_merge(self):
        # Independent-review finding (re-review round 2): a PRECEDING segment can relocate the repo
        # context — `cd /protected && git merge --no-ff topic` merges in /protected while detection
        # read the payload cwd. Same class as `env -C`, so the same fail-deny.
        target, cwd = self._protected(), self._innocent()
        for cmd in (
            f"cd {target} && git merge --no-ff topic",
            f"cd {target}; git merge --no-ff topic",
            f"pushd {target} && git merge --no-ff topic",
            f"cd {target} && echo ok && git merge --no-ff topic",  # flag persists across segments
            f"builtin cd {target} && git merge --no-ff topic",     # bash builtin-prefix spelling
            f"command cd {target} && git merge --no-ff topic",
            "popd && git merge --no-ff topic",
        ):
            self.assertTrue(self._denied(cmd, cwd),
                            f"cross-segment dir change must fail-deny a YOLO merge: {cmd}")

    def test_denies_cross_segment_git_env_export_merge(self):
        target, cwd = self._protected(), self._innocent()
        for cmd in (
            f"export GIT_DIR={target}/.git; git merge --no-ff topic",
            f"export GIT_DIR={target}/.git && git merge --no-ff topic",
            f"declare -x GIT_DIR={target}/.git; git merge --no-ff topic",
            f"GIT_DIR={target}/.git; export GIT_DIR; git merge --no-ff topic",  # bare-name promotion
            f"GIT_DIR={target}/.git; git merge --no-ff topic",  # assignments-only segment (conservative)
        ):
            self.assertTrue(self._denied(cmd, cwd),
                            f"cross-segment GIT_DIR export must fail-deny a YOLO merge: {cmd}")

    def test_cross_segment_marking_is_one_directional(self):
        # A dir change AFTER the merge cannot retroactively move it — the merge still targets the
        # payload cwd (non-default here), so it must stay allowed. Pins the in-order semantics.
        target, cwd = self._protected(), self._innocent()
        self.assertTrue(self._deferred(f"git merge --no-ff topic && cd {target}", cwd))
        # And a preceding dir change before a NON-fenced command manufactures no deny.
        self.assertTrue(self._deferred(f"cd {target} && git status", cwd))
        self.assertTrue(self._deferred(f"export GIT_DIR={target}/.git; git status", cwd))
        # A non-selector export must not trip the flag either.
        self.assertTrue(self._deferred("export GIT_PAGER=cat; git merge --no-ff topic", cwd))


class TestLauncherPrefix(unittest.TestCase):
    """Exec-prefix launchers (`env`/`sudo`/`nice`/`timeout`/…) run their argument list as a new
    command, so a fenced git/gh verb hides one token past the launcher. Before the fix, the guard
    anchored on the launcher basename (`env`), saw no `git` executable, and DEFERRED — a trivial,
    no-privilege disarm of the ENTIRE deny set (`env git push`, `sudo git branch -D main`,
    `env gh pr merge 5`). These pin that every launcher in the family is now stepped over, that a
    chain (`sudo nice git push`) is followed, and — bidirectionally — that ordinary launcher uses of
    a NON-fenced command are not false-denied. Closes the TELOS-001 hole; the whole irreversible set
    stays fenced regardless of a launcher prefix.
    """

    # Every one runs a fenced git/gh verb one token deeper → must DENY.
    LAUNCHER_DENY = [
        "env git push origin main",
        "env GIT_AUTHOR_NAME=x git push",       # env's own VAR=val before the command
        "env -i git push",                       # env clearing the environment
        "env -u FOO git push",                   # env -u <name> (value-option) then the command
        "env -- git push",                       # option terminator, then the command
        "command git push origin main",          # the bash `command` builtin form
        "exec git push origin main",             # exec replaces the shell with git push
        "exec -a name git push",                 # exec -a <name> (value-option)
        "nohup git push origin main",
        "setsid git push origin main",
        "nice git merge --no-ff topic",
        "nice -n 5 git push origin main",        # nice -n <adj> (value-option)
        "nice -5 git push origin main",          # nice -<adj> attached
        "ionice -c2 git branch -D main",         # ionice attached class
        "ionice -c 2 git branch -D main",        # ionice -c <class> (value-option)
        "stdbuf -oL git push origin main",       # stdbuf attached mode
        "timeout 60 git push origin main",       # timeout <DURATION> command (leading positional)
        "timeout -s KILL 60 git push",           # timeout -s <sig> then DURATION then command
        "time git push origin main",
        "sudo git push origin main",
        "sudo -u deploy git branch -D main",     # sudo -u <user> (value-option)
        "doas git push origin main",
        "sudo nice git push origin main",        # a launcher CHAIN is followed to the git verb
        "env nohup git branch -D main",          # ditto, different chain
        "/usr/bin/env git push",                 # launcher via absolute path → basename
        # further direct-exec launchers with small/stable value grammars (same class as `env`)
        "unbuffer git push origin main",         # fixes the stdbuf<->unbuffer asymmetry
        "eatmydata git push origin main",
        "catchsegv git push origin main",
        "torsocks git push origin main",
        "torsocks -u alice git push",            # torsocks -u <user> (SOCKS5 username, value-option)
        "torsocks --pass pw git branch -D main", # ... and --pass (the username/password pair)
        "doas -a myrole git push",               # doas -a <style> (value-option)
        # a shell running a `-c` command STRING: re-scanned as the command line it is. Only the
        # simple `-c`/`+c` flag-cluster forms (no value-consuming `-o`/`-O`) are modeled; the
        # `-o`-interleaved forms are the documented residual (LAUNCHER_RESIDUALS).
        'bash -c "git push"',
        "bash -c 'git push origin main'",
        "sh -c 'git branch -D main'",
        'dash -c "git merge --no-ff topic"',
        "zsh -c 'git push'",
        'bash -lc "git push"',                   # flag cluster `-lc` (no value-consuming letter)
        'bash -cx "git push"',                   # `-c` need not be last in the cluster
        'bash -cvx "git push"',                  # ... multi-letter cluster
        'bash -xc "git push"',                   # ... `-c` last but not first
        'bash +c "git push"',                    # `+`-prefixed cluster also runs the string
        'bash +cx "git push"',
        'bash --norc -c "git push"',             # a non-value long option before `-c`
        'sh -cx "git branch -D main"',
        'bash -c "env git push"',                # a launcher INSIDE the -c string
        'bash -c "gh pr merge 5"',
        'env bash -c "git push"',                # launcher in front of the shell
        "/usr/bin/time -o /tmp/x git push",      # GNU time -o <file> (value-option)
        "/usr/bin/time -f %e git push",          # GNU time -f <fmt> (value-option)
        "torsocks -p 9050 git push",             # torsocks -p <port> (value-option)
        "torsocks -a 127.0.0.1 git branch -D main",
    ]

    def test_launcher_prefix_denied(self):
        for cmd in self.LAUNCHER_DENY:
            rc, out = _run(cmd)
            self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {cmd}")
            self.assertTrue(_denied(out), f"launcher-hidden VC verb must be DENIED: {cmd}")

    # Ordinary launcher uses whose delegated command is NOT fenced must still DEFER — the step-over
    # must not manufacture a false deny. `sudo -u git push` is the sharp one: it runs a command
    # literally named `push` as the user `git`, NOT `git push` — the value-option consumes `git`.
    LAUNCHER_ALLOW = [
        "env",                                   # prints the environment; no command
        "env FOO=bar git status",                # git, but a non-fenced subcommand
        "time ls -l",
        "nice -n 10 make",
        "command -v git",                        # a `command` lookup, not a git run
        "sudo -u deploy git status",             # non-fenced git subcommand under sudo
        "timeout 60 make test",
        "nice git commit -m 'ready to push'",    # 'push' only in the commit message
        "sudo -u git push",                      # run cmd `push` as user `git` — NOT `git push`
        "env -uv FOO git push",                  # -uv = -u with ATTACHED value 'v' → runs cmd FOO, not git
        "env -vu FOO git status",                # clustered value-opt, but a non-fenced subcommand
        "unbuffer git status",                   # recognized launcher + non-fenced subcommand
        'bash -c "echo git push is coming"',     # 'git push' only inside an echo string
        'bash -cx "echo hi"',                    # multi-letter cluster, non-fenced inner
        'bash +c "echo hi"',                     # `+`-prefixed cluster, non-fenced inner
        'sh -c "git status"',                    # shell -c with a non-fenced inner command
        "bash script.sh",                        # a script shell (no -c) → body not scanned, defer
        "/usr/bin/time -o out.txt make",         # GNU time value-option before a non-fenced command
        "torsocks -p 9050 curl https://x",       # torsocks value-option before a non-git command
    ]

    def test_launcher_non_fenced_still_allows(self):
        for cmd in self.LAUNCHER_ALLOW:
            rc, out = _run(cmd)
            self.assertEqual((rc, out.strip()), (0, ""), f"must DEFER (no decision): {cmd}")

    # Exec-prefix mechanisms OUTSIDE the recognized set — an accepted residual, the same class as an
    # indirect wrapper script (KNOWN-BYPASSES.md "an exec-prefix outside the recognized launcher
    # set"). The recognized set is enumerated, not exhaustive; these are the notable ones left out —
    # a launcher with a leading positional of its own (cpu mask / RT priority / lock file); a large
    # or version-growing separate-value option grammar not confidently modeled (`unshare`, `numactl`,
    # `cpulimit`, `strace`, `ltrace`, `proot`) — half-modeling one invites the "claimed catch that
    # slips" defect, so it is documented, not claimed; a privileged shell string with a different arg
    # order (`su`/`runuser`/`sg -c`); a shell `-c` whose option vector has a value-consuming
    # `-o`/`-O` (or a `--rcfile`/`--init-file`) that shifts the command position; a string-splitting
    # option (`env -S`); and a launcher chain past the recursion cap. Pinned ALLOW BIDIRECTIONALLY:
    # if a change starts catching one, this fails and forces an honest SCOPE/LIMITS + KNOWN-BYPASSES
    # update (a caught residual should MOVE to LAUNCHER_DENY, not silently change scope).
    LAUNCHER_RESIDUALS = [
        "taskset 0x3 git push origin main",      # bare cpu-mask positional before the command
        "chrt 10 git push origin main",          # bare scheduling-priority positional
        "flock /tmp/lock git push origin main",  # flock <file> command (leading file positional)
        "unshare git push origin main",          # large/version-growing separate-value option set
        "unshare --map-user 1000 git push",      # ... e.g. --map-user <uid> (separate value)
        "numactl -N 0 git push",                 # ditto — value grammar grows across versions
        "cpulimit -l 50 git push",
        "xargs git push origin main",            # optional-arg opts (-i/--replace) unmodelable here
        "xargs --process-slot-var V git push",   # ... plus version-growing separate-value opts
        "echo x | xargs -i git push",            # -i is attached-only; runs git push per input line
        "strace git push origin main",           # heavier option grammar, not modeled → not caught
        "ltrace git push origin main",
        "proot -r /rootfs git push",
        "firejail git push origin main",         # large option surface; can't rule out a sep-value opt
        "firejail --whitelist /x git push",
        "su -c 'git push'",                      # privileged shell string, different arg grammar
        "runuser -u ci -c 'git push'",
        "sg developers -c 'git push'",
        "bash -co monitor 'git push'",           # shell `-o` eats a separate token → command shifts
        "bash -o monitor -c 'git push'",         # ... `-o` before `-c`
        "bash --rcfile /tmp/rc -c 'git push'",   # a separate-value long shell option before `-c`
        "env -S 'git push origin main'",         # env re-splits one string arg (an expansion)
        "sudo " * 11 + "git push",               # a launcher chain deeper than _MAX_LAUNCHER_DEPTH
    ]

    def test_launcher_residuals_still_allow(self):
        for cmd in self.LAUNCHER_RESIDUALS:
            rc, out = _run(cmd)
            self.assertEqual(
                (rc, out.strip()), (0, ""),
                f"ACCEPTED-RESIDUAL CHANGED: this launcher bypass is documented in KNOWN-BYPASSES.md "
                f"and used to ALLOW; it is now caught. Update SCOPE/LIMITS + KNOWN-BYPASSES.md and "
                f"move it out of LAUNCHER_RESIDUALS: {cmd}")


class TestShellKeywordAndEvalPrefix(unittest.TestCase):
    """Shell RESERVED WORDS / grouping tokens (`!`, `{`, `if`, `while`, `until`) and the `eval`
    builtin run a following LITERAL git/gh verb in the same segment, so a fenced verb hides one token
    past them. Before the fix the guard anchored `exe` on `!`/`{`/`if`/`eval`, matched nothing, and
    DEFERRED — a trivial, no-privilege disarm of the ENTIRE deny set (`eval git push`, `{ git push;
    }`, `! git push`, `if git push; then :; fi`), the exact class already closed for `env`/`bash -c`.
    These pin that every prefix is now stepped over (and `eval`'s args re-scanned), plus —
    bidirectionally — that ordinary keyword uses of a NON-fenced command are not false-denied.
    """

    # A fenced git/gh verb sits one token past a keyword/eval prefix → must DENY.
    KEYWORD_DENY = [
        "eval git push origin main",             # eval, unquoted
        'eval "git push origin main"',           # eval, quoted single arg (rejoin is load-bearing)
        "eval git branch -D main",
        "eval git merge --no-ff topic",
        "eval git branch -f main other",         # ref-move behind eval
        "eval gh pr merge 5",
        "eval env git push",                     # eval → launcher → git (nested resolution)
        "{ git push origin main; }",             # brace group
        "{ git branch -D main; }",
        "! git push origin main",                # pipeline negation
        "! git merge --no-ff topic",
        "if git push origin main; then :; fi",   # condition command runs
        "while git push; do break; done",
        "until git push; do break; done",
        "if git branch -D main; then :; fi",
        "{ eval git push; }",                    # keyword + eval chained
        "coproc git push origin main",           # coproc reserved word, simple command
        "coproc git branch -D main",
        "coproc worker { git push; }",           # coproc NAME <compound> — the name is skipped
        "coproc { git push; }",                  # coproc + anonymous group
        "builtin eval git push",                 # `builtin` twin of `command` (was asymmetric)
        "command builtin eval git push",         # launcher + builtin + eval chain
    ]

    def test_keyword_and_eval_prefix_denied(self):
        for cmd in self.KEYWORD_DENY:
            rc, out = _run(cmd)
            self.assertEqual(rc, 0, f"must exit 0 (fail-open contract): {cmd}")
            self.assertTrue(_denied(out), f"keyword/eval-hidden VC verb must be DENIED: {cmd}")

    # Keyword/eval uses whose delegated command is NOT fenced must still DEFER — the step-over must
    # not manufacture a false deny, and a keyword appearing as a plain WORD (not the segment head)
    # must not trip it.
    KEYWORD_ALLOW = [
        "echo if git push is scary",             # 'if'/'git push' are echo arguments, not the head
        "if grep -q foo file; then echo ok; fi", # condition is grep, body is echo — nothing fenced
        "for x in a b; do echo $x; done",        # 'for' loop over literals; git never runs
        "for x in git push; do echo $x; done",   # 'git'/'push' are for-loop WORDS, not a command
        "eval echo hello",                       # eval of a non-fenced command
        "eval git status",                       # eval of a non-fenced git subcommand
        "{ git status; }",                       # grouped non-fenced command
        "while read l; do echo $l; done",        # 'read'/'echo' — nothing fenced
        "! git diff --quiet",                    # negated non-fenced git read
        "coproc git status",                     # coproc of a non-fenced git subcommand
        "coproc worker { echo hi; }",            # coproc NAME group, non-fenced body
        "coproc mydb { psql; }",                 # coproc NAME group, non-git body
        "builtin cd /tmp",                       # builtin of a non-fenced command
        "echo coproc git push",                  # 'coproc'/'git push' are echo args, not the head
    ]

    def test_keyword_and_eval_non_fenced_still_allows(self):
        for cmd in self.KEYWORD_ALLOW:
            rc, out = _run(cmd)
            self.assertEqual((rc, out.strip()), (0, ""), f"must DEFER (no decision): {cmd}")

    def test_bypass_denied_in_both_modes(self):
        # the disarm worked identically in =1 and =yolo; the fix must close both.
        for guard in ("1", "yolo"):
            for cmd in ("eval git push", "{ git push; }", "! git push",
                        "if git push; then :; fi"):
                rc, out = _run(cmd, guard=guard)
                self.assertTrue(_denied(out), f"[{guard}] must be denied: {cmd}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
