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
        "git branch -m old new",               # rename (no delete)
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
        "git update-ref -d refs/heads/main",       # ref delete via plumbing
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
