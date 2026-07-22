#!/usr/bin/env python3
"""Direct tests for excubitor.core.policies.loop_vc — the extracted loop-VC classifier.

The shipped hook (`hooks/tests/test_guard_loop_vc.py`) exercises this policy end-to-end through the
Claude Code adapter, and `runtime/tests/test_spec_adapter.py` proves the generic adapter reaches the
same decisions. This module tests the core `_dangerous` DIRECTLY — representative conservative/YOLO
cases, the git_state-integrated YOLO branch check against real repos, and the neutrality invariant.

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_loop_vc.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from excubitor.core.policies import loop_vc  # noqa: E402


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _repo(td: str, on_branch: "str | None" = None) -> str:
    _git(td, "init", "-q", "-b", "main")
    _git(td, "config", "user.email", "t@t")
    _git(td, "config", "user.name", "t")
    Path(td, "seed.txt").write_text("x")
    _git(td, "add", "-A")
    _git(td, "commit", "-qm", "seed")
    if on_branch:
        _git(td, "switch", "-qc", on_branch)
    return td


class TestConservativeDenySet(unittest.TestCase):
    def _deny(self, cmd: str) -> None:
        self.assertIsNotNone(loop_vc._dangerous(cmd, False, "/tmp"), f"expected DENY: {cmd!r}")

    def _allow(self, cmd: str) -> None:
        self.assertIsNone(loop_vc._dangerous(cmd, False, "/tmp"), f"expected allow: {cmd!r}")

    def test_core_verbs_deny(self):
        for cmd in ("git push origin main", "git merge topic", "git branch -D feature",
                    "git reset --hard HEAD~1", "git clean -fd", "git worktree remove ../wt",
                    "gh pr merge 5"):
            self._deny(cmd)

    def test_ref_moves_deny(self):
        for cmd in ("git branch -f main abc", "git switch -C main", "git checkout -B main",
                    "git update-ref refs/heads/main abc", "git worktree add -B main /tmp/wt",
                    "git remote set-head origin develop",
                    "git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/x"):
            self._deny(cmd)

    def test_launchers_and_shells_deny(self):
        for cmd in ("env git push", "sudo nice git branch -D main", 'eval "git push"',
                    'bash -c "git push"', "(git push)", "! git push"):
            self._deny(cmd)

    def test_reads_and_safe_forms_allow(self):
        for cmd in ("git clean -n", "git status && git diff", "git symbolic-ref HEAD",
                    "echo hi", "git pull", "git commit -m done",
                    'git commit -m "mentions (git push) in prose"'):
            self._allow(cmd)

    def test_documented_residual_allows(self):
        # brace-expansion mutates the verb token before the guard sees it (accepted residual).
        self._allow("git pus{h,} origin main")


class TestYoloBranchCheck(unittest.TestCase):
    """YOLO allows only a --no-ff merge into a confirmed non-default branch — via git_state."""

    def test_no_ff_merge_on_feature_branch_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, on_branch="feat/x")
            self.assertIsNone(loop_vc._dangerous("git merge --no-ff topic", True, td))

    def test_no_ff_merge_on_default_branch_denied(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td)  # on main
            self.assertIsNotNone(loop_vc._dangerous("git merge --no-ff topic", True, td))

    def test_fast_forward_merge_denied_in_yolo(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, on_branch="feat/x")
            self.assertIsNotNone(loop_vc._dangerous("git merge topic", True, td))

    def test_push_still_denied_in_yolo(self):
        self.assertIsNotNone(loop_vc._dangerous("git push", True, "/tmp"))

    def test_selector_targets_the_named_repo(self):
        # P0.14: --git-dir/--work-tree select the repo, so branch detection reads THAT repo's default.
        with tempfile.TemporaryDirectory() as td:
            _repo(td)  # main is default and checked out
            cmd = f"git --git-dir={td}/.git --work-tree={td} merge --no-ff topic"
            self.assertIsNotNone(loop_vc._dangerous(cmd, True, "/some/other/cwd"))


class TestOptionAbbreviationBypasses(unittest.TestCase):
    """git accepts any unambiguous long-option prefix; the reset/delete/merge-ff fences must too.

    Regression guard for the review finding: the ref-move fences used prefix-aware `_long_opt_matches`
    while `reset --hard`, `branch/symbolic-ref --delete`, and the YOLO merge `--no-ff` test still
    matched full spellings only, so `git reset --har` / `git branch --del` slipped through.
    """

    def _deny(self, cmd: str, yolo: bool = False) -> None:
        self.assertIsNotNone(loop_vc._dangerous(cmd, yolo, "/tmp"), f"expected DENY: {cmd!r}")

    def _allow(self, cmd: str) -> None:
        self.assertIsNone(loop_vc._dangerous(cmd, False, "/tmp"), f"expected allow: {cmd!r}")

    def test_reset_hard_abbreviations_deny(self):
        for cmd in ("git reset --har HEAD~1", "git reset --ha HEAD~1", "git reset --h HEAD~1"):
            self._deny(cmd)
            self._deny(cmd, yolo=True)

    def test_reset_safe_modes_allow(self):
        for cmd in ("git reset --soft HEAD~1", "git reset --mixed HEAD~1", "git reset --keep HEAD~1"):
            self._allow(cmd)

    def test_branch_delete_abbreviations_deny(self):
        for cmd in ("git branch --del feature", "git branch --dele feature",
                    "git branch --delet feature", "git branch --d feature"):
            self._deny(cmd)

    def test_symbolic_ref_delete_abbreviation_denies(self):
        self._deny("git symbolic-ref --del refs/remotes/origin/HEAD")

    def test_branch_nondelete_long_opts_allow(self):
        for cmd in ("git branch --list", "git branch --merged", "git branch --show-current"):
            self._allow(cmd)

    def test_yolo_merge_trailing_ff_overrides_no_ff_denied(self):
        # --no-ff then --ff resolves last-wins to a fast-forward — the permit must not allow it.
        with tempfile.TemporaryDirectory() as td:
            _repo(td, on_branch="feat/x")
            self.assertIsNotNone(loop_vc._dangerous("git merge --no-ff --ff topic", True, td))
            self.assertIsNotNone(loop_vc._dangerous("git merge --no-ff --ff-only topic", True, td))

    def test_yolo_merge_trailing_no_ff_wins_allowed(self):
        # --ff then --no-ff resolves last-wins to a real merge commit (revertable) — allowed.
        with tempfile.TemporaryDirectory() as td:
            _repo(td, on_branch="feat/x")
            self.assertIsNone(loop_vc._dangerous("git merge --ff --no-ff topic", True, td))
            self.assertIsNone(loop_vc._dangerous("git merge --no-f topic", True, td))


class TestPurity(unittest.TestCase):
    """The policy is model-blind and shells out to git ONLY via the git_state boundary."""

    def test_no_host_provider_or_direct_io(self):
        src = (_REPO_ROOT / "excubitor" / "core" / "policies" / "loop_vc.py").read_text("utf-8")
        low = src.lower()
        for token in ("claude", "anthropic", "codex", "openai", "gemini", "copilot",
                      "os.environ", "getenv"):
            self.assertNotIn(token, low, f"loop_vc must stay host/env-neutral: {token!r}")
        # git access is delegated to git_state — the policy itself never spawns a process or touches sys.
        for token in ("subprocess", "sys.stdin", "sys.stdout", "sys.exit", "import sys"):
            self.assertNotIn(token, src, f"loop_vc must not do host I/O directly: {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
