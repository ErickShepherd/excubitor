#!/usr/bin/env python3
"""Tests for check_oracle_frozen.py — the YOLO oracle-immutability check.

Builds throwaway local git repos (no remote, no environment dependence): a `main` base with an
oracle test file, then a loop branch that either leaves the oracle untouched (FROZEN, exit 0) or
edits/deletes it (NOT-FROZEN, exit 1). Also pins the fail-deny cases: a verified-by with no
extractable oracle file, and a pytest-nodeid form.

Stdlib unittest only. Run:
  python3 skills/telos-loop/tests/test_check_oracle_frozen.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_oracle_frozen.py"


def _run(repo: str, base: str, verified_by: str) -> int:
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", repo, "--base", base, "--verified-by", verified_by],
        capture_output=True,
        text=True,
    )
    return p.returncode


class TestCheckOracleFrozen(unittest.TestCase):
    def setUp(self) -> None:
        self.d = tempfile.mkdtemp(prefix="oraclefrozen-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", self.d, *args], check=True, capture_output=True, text=True)

        self.g = g
        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        # base state: an oracle test + the code it guards
        (Path(self.d) / "tests").mkdir()
        (Path(self.d) / "tests" / "test_oracle.py").write_text("def test_ok():\n    assert True\n")
        (Path(self.d) / "feature.py").write_text("x = 1\n")
        g("add", "-A")
        g("commit", "-m", "base")
        # fork the loop branch
        g("checkout", "-b", "loop/telos")

    def _commit(self, path: str, content: str) -> None:
        (Path(self.d) / path).write_text(content)
        self.g("add", "-A")
        self.g("commit", "-m", f"edit {path}")

    VB = "python3 tests/test_oracle.py"

    def test_frozen_when_oracle_untouched(self):
        # loop changes only the feature code, not the oracle → FROZEN
        self._commit("feature.py", "x = 2\n")
        self.assertEqual(_run(self.d, "main", self.VB), 0)

    def test_ignores_inherited_git_dir(self):
        # An inherited GIT_DIR must NOT redirect the trusted queries away from --repo (confused-deputy
        # spoof). With GIT_DIR pointing at a non-repo, an unsanitized check would error → fail-deny;
        # sanitized, `-C <repo>` remains the sole source of truth and the untouched oracle stays FROZEN.
        self._commit("feature.py", "x = 2\n")
        env = dict(os.environ)
        env["GIT_DIR"] = os.path.join(self.d, "nonexistent-gitdir")
        env["GIT_WORK_TREE"] = self.d
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", self.d, "--base", "main", "--verified-by", self.VB],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(p.returncode, 0, f"GIT_DIR must be ignored; got: {p.stderr}")

    def test_not_frozen_when_oracle_edited(self):
        self._commit("tests/test_oracle.py", "def test_ok():\n    assert True  # weakened\n")
        self.assertEqual(_run(self.d, "main", self.VB), 1)

    def test_not_frozen_when_oracle_deleted(self):
        os.remove(Path(self.d) / "tests" / "test_oracle.py")
        self.g("add", "-A")
        self.g("commit", "-m", "rm oracle")
        self.assertEqual(_run(self.d, "main", self.VB), 1)

    def test_not_frozen_when_one_of_several_oracle_files_deleted(self):
        # THE MULTI-FILE HOLE: a verified-by naming several oracle files, of which the loop deletes ONE
        # while leaving the others untouched, used to pass FROZEN (survivors alone looked clean). The
        # deleted file was tracked at base, so its disappearance is tamper → must fail-deny.
        (Path(self.d) / "tests" / "test_oracle_b.py").write_text("def test_b():\n    assert True\n")
        self.g("add", "-A")
        self.g("commit", "-m", "add second oracle")
        # re-fork loop branch from this two-oracle base
        self.g("checkout", "main")
        self.g("merge", "--ff-only", "loop/telos")
        self.g("checkout", "loop/telos")
        os.remove(Path(self.d) / "tests" / "test_oracle.py")  # delete just ONE of the two
        self.g("add", "-A")
        self.g("commit", "-m", "rm one oracle")
        vb = "python3 tests/test_oracle.py tests/test_oracle_b.py"
        self.assertEqual(_run(self.d, "main", vb), 1, "deleting one of several oracle files must fail-deny")

    def test_frozen_when_multiple_oracle_files_untouched(self):
        # control: the same two-file verified-by, both untouched → still FROZEN (no false positive).
        (Path(self.d) / "tests" / "test_oracle_b.py").write_text("def test_b():\n    assert True\n")
        self.g("add", "-A")
        self.g("commit", "-m", "add second oracle")
        self.g("checkout", "main")
        self.g("merge", "--ff-only", "loop/telos")
        self.g("checkout", "loop/telos")
        self._commit("feature.py", "x = 3\n")  # touch only feature code
        vb = "python3 tests/test_oracle.py tests/test_oracle_b.py"
        self.assertEqual(_run(self.d, "main", vb), 0, "both oracle files untouched → FROZEN")

    def test_frozen_with_pytest_nodeid(self):
        # verified-by carries a `path::Test::method` nodeid; the file part is what matters
        self._commit("feature.py", "x = 3\n")
        self.assertEqual(_run(self.d, "main", "python3 -m pytest tests/test_oracle.py::test_ok"), 0)

    def test_not_frozen_nodeid_when_file_edited(self):
        self._commit("tests/test_oracle.py", "def test_ok():\n    assert 1\n")
        self.assertEqual(_run(self.d, "main", "pytest tests/test_oracle.py::test_ok"), 1)

    def test_fail_deny_when_no_oracle_file(self):
        # no token resolves to an existing file → immutability unverifiable → fail-deny
        self._commit("feature.py", "x = 4\n")
        self.assertEqual(_run(self.d, "main", "echo done"), 1)

    def test_fail_deny_on_bad_base(self):
        self._commit("feature.py", "x = 5\n")
        self.assertEqual(_run(self.d, "no-such-branch", self.VB), 1)

    # --- bypass regressions: the candidate must normalize to git's repo-relative diff space ---
    def test_frozen_absolute_path_untouched(self):
        self._commit("feature.py", "x = 6\n")
        self.assertEqual(_run(self.d, "main", f"python3 {self.d}/tests/test_oracle.py"), 0)

    def test_not_frozen_absolute_path_edited(self):
        # absolute-path verified-by must NOT defeat the check when the oracle is tampered
        self._commit("tests/test_oracle.py", "def test_ok():\n    assert True  # weakened\n")
        self.assertEqual(_run(self.d, "main", f"python3 {self.d}/tests/test_oracle.py"), 1)

    def test_not_frozen_when_symlinked_oracle_target_edited(self):
        d = tempfile.mkdtemp(prefix="oraclefrozen-sym-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", d, *args], check=True, capture_output=True, text=True)

        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        (Path(d) / "tests").mkdir()
        (Path(d) / "tests" / "real_oracle.py").write_text("def test_ok():\n    assert True\n")
        os.symlink("real_oracle.py", Path(d) / "tests" / "test_oracle.py")  # link → target
        g("add", "-A")
        g("commit", "-m", "base")
        g("checkout", "-b", "loop/telos")
        (Path(d) / "tests" / "real_oracle.py").write_text("def test_ok():\n    assert 1  # weakened\n")
        g("add", "-A")
        g("commit", "-m", "weaken target")
        # verified-by points at the SYMLINK; the loop edited the TARGET → must be caught
        self.assertEqual(_run(d, "main", "python3 tests/test_oracle.py"), 1)

    def test_fail_deny_untracked_oracle(self):
        # an untracked oracle's edits never show in a committed diff → unverifiable → fail-deny
        (Path(self.d) / "untracked_oracle.py").write_text("def test_ok():\n    assert True\n")
        self._commit("feature.py", "x = 7\n")
        self.assertEqual(_run(self.d, "main", "python3 untracked_oracle.py"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
