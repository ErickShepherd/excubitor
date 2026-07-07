#!/usr/bin/env python3
"""Tests for check_suite_frozen.py — the YOLO green-the-suite immutability check.

Builds throwaway local git repos (no remote, no environment dependence): a `main` base with a test
dir, a conftest, and a runner-config file, then a loop branch that either leaves the whole verdict
surface untouched (FROZEN, exit 0) or weakens it — editing/deleting/adding a test, or editing the
runner config (NOT-FROZEN, exit 1). Also pins the fail-deny cases (typo'd pathspec, bad base, no
pathspec, non-git dir).

Stdlib unittest only. Run:
  python3 skills/ralph-loop/tests/test_check_suite_frozen.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_suite_frozen.py"


def _run(repo: str, base: str, test_paths: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPT), "--repo", repo, "--base", base]
    for tp in test_paths:
        cmd += ["--test-path", tp]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode


class TestCheckSuiteFrozen(unittest.TestCase):
    def setUp(self) -> None:
        self.d = tempfile.mkdtemp(prefix="suitefrozen-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", self.d, *args], check=True, capture_output=True, text=True)

        self.g = g
        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        # base state: a test surface (tests dir + conftest + runner config) and the code it guards
        (Path(self.d) / "tests").mkdir()
        (Path(self.d) / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
        (Path(self.d) / "tests" / "test_b.py").write_text("def test_b():\n    assert True\n")
        (Path(self.d) / "conftest.py").write_text("# shared fixtures\n")
        (Path(self.d) / "pytest.ini").write_text("[pytest]\naddopts =\n")
        (Path(self.d) / "feature.py").write_text("x = 1\n")
        g("add", "-A")
        g("commit", "-m", "base")
        g("checkout", "-b", "loop/green")

    def _commit(self, path: str, content: str) -> None:
        full = Path(self.d) / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        self.g("add", "-A")
        self.g("commit", "-m", f"edit {path}")

    def _rm_commit(self, path: str) -> None:
        os.remove(Path(self.d) / path)
        self.g("add", "-A")
        self.g("commit", "-m", f"rm {path}")

    SURFACE = ["tests/", "conftest.py", "pytest.ini"]

    # --- frozen: only production code changed ---
    def test_frozen_when_only_production_changed(self):
        self._commit("feature.py", "x = 2\n")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 0)

    def test_frozen_with_new_production_file(self):
        self._commit("helper.py", "y = 1\n")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 0)

    # --- not frozen: the loop touched the verdict surface ---
    def test_not_frozen_when_test_edited(self):
        self._commit("tests/test_a.py", "def test_a():\n    assert True  # weakened\n")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 1)

    def test_not_frozen_when_test_deleted(self):
        self._rm_commit("tests/test_b.py")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 1)

    def test_not_frozen_when_test_added(self):
        # adding a file under the surface is touching it (could be a collection-disabling conftest)
        self._commit("tests/test_c.py", "def test_c():\n    assert True\n")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 1)

    def test_not_frozen_when_conftest_edited(self):
        self._commit("conftest.py", "collect_ignore = ['tests/test_b.py']\n")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 1)

    def test_not_frozen_when_runner_config_edited(self):
        # the key config-freeze case: tests/ untouched, but addopts weakened to skip tests
        self._commit("pytest.ini", "[pytest]\naddopts = --ignore=tests/test_b.py\n")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 1)

    def test_not_frozen_when_whole_test_dir_deleted(self):
        self._rm_commit("tests/test_a.py")
        self._rm_commit("tests/test_b.py")
        self.assertEqual(_run(self.d, "main", self.SURFACE), 1)

    # --- glob pathspec ---
    def test_frozen_glob_pathspec_when_production_changed(self):
        self._commit("feature.py", "x = 3\n")
        self.assertEqual(_run(self.d, "main", ["tests/test_*.py"]), 0)

    def test_not_frozen_glob_pathspec_when_test_edited(self):
        self._commit("tests/test_a.py", "def test_a():\n    assert 1\n")
        self.assertEqual(_run(self.d, "main", ["tests/test_*.py"]), 1)

    # --- fail-deny cases ---
    def test_fail_deny_typo_pathspec_matches_nothing(self):
        # a surface that does not exist at base would freeze vacuously → fail-deny
        self._commit("feature.py", "x = 4\n")
        self.assertEqual(_run(self.d, "main", ["tests/", "nonexistent_dir/"]), 1)

    def test_fail_deny_on_bad_base(self):
        self._commit("feature.py", "x = 5\n")
        self.assertEqual(_run(self.d, "no-such-branch", self.SURFACE), 1)

    def test_fail_deny_no_test_path(self):
        # argparse requires --test-path → usage error (exit 2)
        self._commit("feature.py", "x = 6\n")
        self.assertEqual(_run(self.d, "main", []), 2)

    def test_fail_deny_not_a_git_repo(self):
        plain = tempfile.mkdtemp(prefix="suitefrozen-nogit-")
        self.addCleanup(shutil.rmtree, plain, ignore_errors=True)
        self.assertEqual(_run(plain, "main", ["tests/"]), 1)

    # --- a clean run touching nothing at all is still frozen (no false NOT-FROZEN) ---
    def test_frozen_no_changes_on_branch(self):
        self.assertEqual(_run(self.d, "main", self.SURFACE), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
