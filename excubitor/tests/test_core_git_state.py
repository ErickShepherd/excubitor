#!/usr/bin/env python3
"""Tests for excubitor.core.git_state — read-only Git state + default-branch resolution.

Exercises the extracted helpers against real temp git repos, covering the cases the shipped guards
depend on: slash-containing defaults (the R-01 removeprefix fix), detached HEAD, missing-remote
local-only repos, and the ambiguous main+master case. These are the same properties the
`hooks/tests/` differential-oracle suites pin end-to-end; here they are unit-tested at the source.

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_git_state.py
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

from excubitor.core import git_state  # noqa: E402


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _init_repo(
    td: str,
    branch: str = "main",
    extra_branches: "tuple[str, ...]" = (),
    origin_head: "str | None" = None,
    init_default: "str | None" = None,
) -> str:
    """Init a one-commit repo on `branch`; optionally add branches, point origin/HEAD, set config."""
    _git(td, "init", "-q", "-b", branch)
    _git(td, "config", "user.email", "t@t")
    _git(td, "config", "user.name", "t")
    if init_default is not None:
        _git(td, "config", "init.defaultBranch", init_default)
    Path(td, "seed.txt").write_text("x")
    _git(td, "add", "-A")
    _git(td, "commit", "-qm", "seed")
    for b in extra_branches:
        _git(td, "branch", b)
    if origin_head is not None:
        _git(td, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{origin_head}")
    return td


def _sel(td: str) -> "list[str]":
    return ["-C", td]


class TestRunGit(unittest.TestCase):
    def test_ok_and_stripped(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            ok, out = git_state.run_git(_sel(td), "rev-parse", "--abbrev-ref", "HEAD")
            self.assertTrue(ok)
            self.assertEqual(out, "main")  # stripped, no trailing newline

    def test_not_ok_outside_repo(self):
        with tempfile.TemporaryDirectory() as td:
            ok, out = git_state.run_git(_sel(td), "rev-parse", "--show-toplevel")
            self.assertFalse(ok)
            self.assertEqual(out, "")

    def test_missing_git_dir_selector_fails_not_ok(self):
        ok, out = git_state.run_git(["-C", "/nonexistent/path/xyz"], "status")
        self.assertFalse(ok)
        self.assertEqual(out, "")


class TestCurrentBranch(unittest.TestCase):
    def test_on_named_branch(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="develop")
            self.assertEqual(git_state.current_branch(_sel(td)), "develop")

    def test_detached_head_reads_as_HEAD(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            sha = subprocess.run(["git", "-C", td, "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
            _git(td, "checkout", "-q", sha)  # detach
            self.assertEqual(git_state.current_branch(_sel(td)), "HEAD")

    def test_outside_repo_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(git_state.current_branch(_sel(td)))


class TestRepoToplevel(unittest.TestCase):
    def test_inside_repo(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            top = git_state.repo_toplevel(_sel(td))
            self.assertIsNotNone(top)
            self.assertEqual(Path(top).resolve(), Path(td).resolve())

    def test_outside_repo_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(git_state.repo_toplevel(_sel(td)))


class TestOriginHeadName(unittest.TestCase):
    def test_simple(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, origin_head="develop")
            self.assertEqual(git_state.origin_head_name(_sel(td)), "develop")

    def test_slash_containing_default_is_not_truncated(self):
        # R-01: a slashed default (release/2.0) must survive whole, not rsplit to "2.0".
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, extra_branches=("release/2.0",), origin_head="release/2.0")
            self.assertEqual(git_state.origin_head_name(_sel(td)), "release/2.0")

    def test_no_remote_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)  # local-only, no origin/HEAD
            self.assertIsNone(git_state.origin_head_name(_sel(td)))


class TestDefaultBranch(unittest.TestCase):
    def test_origin_head_wins(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="main", origin_head="develop")
            self.assertEqual(git_state.default_branch(_sel(td)), "develop")

    def test_origin_head_slash_safe(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, extra_branches=("release/2.0",), origin_head="release/2.0")
            self.assertEqual(git_state.default_branch(_sel(td)), "release/2.0")

    def test_sole_main(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="main")
            self.assertEqual(git_state.default_branch(_sel(td)), "main")

    def test_sole_master(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="master")
            self.assertEqual(git_state.default_branch(_sel(td)), "master")

    def test_both_ambiguous_without_config_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="main", extra_branches=("master",))
            self.assertIsNone(git_state.default_branch(_sel(td)))

    def test_both_disambiguated_by_init_default(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="main", extra_branches=("master",), init_default="master")
            self.assertEqual(git_state.default_branch(_sel(td)), "master")

    def test_neither_main_nor_master_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="trunk")  # no origin, non-standard trunk
            self.assertIsNone(git_state.default_branch(_sel(td)))


class TestProtectedDefaultNames(unittest.TestCase):
    def test_local_only_is_main_and_master(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td)
            self.assertEqual(git_state.protected_default_names(_sel(td)), {"main", "master"})

    def test_custom_origin_head_is_added_not_replaced(self):
        # The union property: main/master stay protected even when origin/HEAD points at develop.
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, branch="main", origin_head="develop")
            self.assertEqual(
                git_state.protected_default_names(_sel(td)), {"main", "master", "develop"}
            )

    def test_slash_containing_default_added_whole(self):
        with tempfile.TemporaryDirectory() as td:
            _init_repo(td, extra_branches=("release/2.0",), origin_head="release/2.0")
            self.assertEqual(
                git_state.protected_default_names(_sel(td)), {"main", "master", "release/2.0"}
            )


class TestGitStatePurity(unittest.TestCase):
    """git_state may shell out to read-only git (the documented carve-out) but must still name no
    host/provider and read no environment or home paths — the core neutrality invariant."""

    _FORBIDDEN = [
        ("claude", "provider/host identity"),
        ("anthropic", "provider identity"),
        ("codex", "host identity"),
        ("openai", "provider identity"),
        ("gemini", "host/provider identity"),
        ("copilot", "host identity"),
        ("os.environ", "environment read"),
        ("getenv", "environment read"),
        ("expanduser", "home-directory read"),
        # NOTE: `subprocess` is intentionally NOT forbidden here — the read-only git boundary is the
        # documented carve-out for this module (and only this module) under core/.
    ]

    def test_no_host_or_env_coupling(self):
        src = (_REPO_ROOT / "excubitor" / "core" / "git_state.py").read_text(encoding="utf-8").lower()
        for token, why in self._FORBIDDEN:
            self.assertNotIn(token, src, f"git_state.py must stay host/env-neutral: {token!r} ({why})")

    def test_only_read_only_git_verbs(self):
        # Defense against a future edit sneaking a mutating verb into the "read-only" boundary.
        src = (_REPO_ROOT / "excubitor" / "core" / "git_state.py").read_text(encoding="utf-8")
        for mutating in ('"push"', '"merge"', '"commit"', '"reset"', '"update-ref"', '"branch"'):
            self.assertNotIn(mutating, src, f"git_state must run only read-only git, not {mutating}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
