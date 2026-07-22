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

    def test_not_frozen_uncommitted_regular_file_edit(self):
        # R-04 finding #1 (the core hole): the loop weakens a tracked regular oracle file IN THE
        # WORKTREE and does NOT commit. A three-dot base...HEAD diff compares commits, so the edit is
        # invisible there; the type/link check never looked at regular-file bytes → the gate used to
        # report FROZEN and hand out a false permit. The current-vs-base content comparison must catch
        # it. (Also touch feature code so it isn't a no-op branch.)
        self._commit("feature.py", "x = 2\n")
        (Path(self.d) / "tests" / "test_oracle.py").write_text(
            "def test_ok():\n    assert True  # weakened, UNCOMMITTED\n")
        self.assertEqual(_run(self.d, "main", self.VB), 1,
                         "an uncommitted regular-file oracle weakening must be NOT-FROZEN")

    def test_frozen_uncommitted_feature_edit_only(self):
        # control for the above: an uncommitted edit to NON-oracle code must NOT false-deny — the
        # content check applies only to the oracle surface, not the whole worktree.
        (Path(self.d) / "feature.py").write_text("x = 99  # uncommitted, not the oracle\n")
        self.assertEqual(_run(self.d, "main", self.VB), 0,
                         "an uncommitted non-oracle edit must stay FROZEN")

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

    def test_not_frozen_when_oracle_renamed(self):
        # R-04 family: a rename is a delete at the old path — the verified-by still names the old
        # path, which was tracked at base and is now gone → tamper, fail-deny.
        self.g("mv", "tests/test_oracle.py", "tests/renamed_oracle.py")
        self.g("commit", "-m", "rename oracle")
        self.assertEqual(_run(self.d, "main", self.VB), 1)


class TestSymlinkSurface(unittest.TestCase):
    """R-04: the frozen surface is lexical path + every chain hop + resolved target — a retarget of
    ANY of them (committed or not) must fail-deny, while an untouched symlinked oracle stays FROZEN."""

    def setUp(self) -> None:
        self.d = tempfile.mkdtemp(prefix="oraclefrozen-sym-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", self.d, *args], check=True, capture_output=True, text=True)

        self.g = g
        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        tests = Path(self.d) / "tests"
        tests.mkdir()
        (tests / "strong_oracle.py").write_text("def test_ok():\n    assert False  # strong\n")
        (tests / "weak_oracle.py").write_text("def test_ok():\n    assert True  # weak\n")
        os.symlink("strong_oracle.py", tests / "test_oracle.py")  # link → strong
        g("add", "-A")
        g("commit", "-m", "base: link -> strong, weak available")
        g("checkout", "-b", "loop/telos")

    VB = "python3 tests/test_oracle.py"

    def _retarget(self, link: str, new_target: str) -> None:
        p = Path(self.d) / link
        os.remove(p)
        os.symlink(new_target, p)

    def test_frozen_symlinked_oracle_untouched(self):
        # control: surface now includes the link itself — must NOT false-deny when nothing changed
        (Path(self.d) / "feature.py").write_text("x = 1\n")
        self.g("add", "-A")
        self.g("commit", "-m", "feature only")
        self.assertEqual(_run(self.d, "main", self.VB), 0)

    def test_not_frozen_committed_retarget(self):
        # THE R-04 REPRO: repoint the tracked link at a weaker tracked test and COMMIT. The diff
        # names the link; pre-fix the candidate set held only the new target → false FROZEN.
        self._retarget("tests/test_oracle.py", "weak_oracle.py")
        self.g("add", "-A")
        self.g("commit", "-m", "retarget link")
        self.assertEqual(_run(self.d, "main", self.VB), 1)

    def test_not_frozen_uncommitted_retarget(self):
        # the same retarget left UNCOMMITTED in the worktree — invisible to base...HEAD, caught by
        # the current-vs-base type/link-target comparison
        self._retarget("tests/test_oracle.py", "weak_oracle.py")
        self.assertEqual(_run(self.d, "main", self.VB), 1)

    def test_not_frozen_uncommitted_file_to_symlink_swap(self):
        # a regular oracle file swapped for a link to weaker bytes, uncommitted → type change → deny
        p = Path(self.d) / "tests" / "strong_oracle.py"
        os.remove(p)
        os.symlink("weak_oracle.py", p)
        self.assertEqual(_run(self.d, "main", "python3 tests/strong_oracle.py"), 1)

    def test_not_frozen_intermediate_chain_hop_retargeted(self):
        # chain link_a -> link_b -> strong; retarget the MIDDLE hop to weak and commit. The diff
        # names link_b only — the surface must include every hop, not just lexical + resolved.
        tests = Path(self.d) / "tests"
        os.symlink("test_oracle.py", tests / "entry_oracle.py")  # entry -> link -> strong
        self.g("add", "-A")
        self.g("commit", "-m", "add entry link")
        # re-fork so the entry link is part of base
        self.g("checkout", "main")
        self.g("merge", "--ff-only", "loop/telos")
        self.g("checkout", "loop/telos")
        self._retarget("tests/test_oracle.py", "weak_oracle.py")  # middle hop
        self.g("add", "-A")
        self.g("commit", "-m", "retarget middle hop")
        self.assertEqual(_run(self.d, "main", "python3 tests/entry_oracle.py"), 1)

    def test_not_frozen_absolute_path_retarget(self):
        # absolute-path verified-by naming the link must not dodge the surface normalization
        self._retarget("tests/test_oracle.py", "weak_oracle.py")
        self.g("add", "-A")
        self.g("commit", "-m", "retarget link")
        self.assertEqual(_run(self.d, "main", f"python3 {self.d}/tests/test_oracle.py"), 1)

    def test_not_frozen_multi_file_one_link_retargeted(self):
        # multi-file witness: one plain file untouched, one link retargeted → the survivors must not
        # vouch for the retargeted member
        self._retarget("tests/test_oracle.py", "weak_oracle.py")
        self.g("add", "-A")
        self.g("commit", "-m", "retarget link")
        vb = "python3 tests/weak_oracle.py tests/test_oracle.py"
        self.assertEqual(_run(self.d, "main", vb), 1)


class TestDirectorySymlinkSurface(unittest.TestCase):
    """R-04 finding #2: a DIRECTORY symlink in the oracle path is load-bearing too. Retargeting the
    directory (e.g. `tests -> weak_tests`) swaps which file the witness executes; the prior code
    realpath-collapsed the directory part before building the surface, so the dir-link was never
    frozen and an uncommitted retarget read as FROZEN."""

    def setUp(self) -> None:
        self.d = tempfile.mkdtemp(prefix="oraclefrozen-dir-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", self.d, *args], check=True, capture_output=True, text=True)

        self.g = g
        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        (Path(self.d) / "strong_tests").mkdir()
        (Path(self.d) / "strong_tests" / "oracle.py").write_text("def test_ok():\n    assert False  # strong\n")
        (Path(self.d) / "weak_tests").mkdir()
        (Path(self.d) / "weak_tests" / "oracle.py").write_text("def test_ok():\n    assert True  # weak\n")
        os.symlink("strong_tests", Path(self.d) / "tests")  # DIRECTORY symlink → strong_tests
        g("add", "-A")
        g("commit", "-m", "base: tests -> strong_tests")
        g("checkout", "-b", "loop/telos")

    VB = "python3 tests/oracle.py"

    def test_frozen_when_dir_symlink_untouched(self):
        # control: the directory symlink is now part of the frozen surface — must not false-deny
        (Path(self.d) / "feature.py").write_text("x = 1\n")
        self.g("add", "-A")
        self.g("commit", "-m", "feature only")
        self.assertEqual(_run(self.d, "main", self.VB), 0)

    def test_not_frozen_uncommitted_dir_symlink_retarget(self):
        # THE #2 REPRO: retarget the directory symlink to the weaker tree, uncommitted. The resolved
        # file path changes (strong_tests/oracle.py → weak_tests/oracle.py) but each of those matches
        # its own base bytes; only the `tests` dir-link's target changed — which must be in the surface.
        os.remove(Path(self.d) / "tests")
        os.symlink("weak_tests", Path(self.d) / "tests")
        self.assertEqual(_run(self.d, "main", self.VB), 1,
                         "an uncommitted directory-symlink retarget must be NOT-FROZEN")

    def test_not_frozen_committed_dir_symlink_retarget(self):
        os.remove(Path(self.d) / "tests")
        os.symlink("weak_tests", Path(self.d) / "tests")
        self.g("add", "-A")
        self.g("commit", "-m", "retarget dir link")
        self.assertEqual(_run(self.d, "main", self.VB), 1)


class TestCanonicalPrefix(unittest.TestCase):
    """_canonical_prefix resolves only the environmental prefix, never an in-repo self-link hop."""

    def setUp(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("check_oracle_frozen", SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.d = tempfile.mkdtemp(prefix="canonprefix-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)
        self.top = os.path.realpath(self.d)  # toplevel is always realpath'd upstream

    def test_environmental_prefix_is_resolved(self) -> None:
        # A symlink standing in for macOS $TMPDIR -> /private/var above the repo root is resolved.
        link = os.path.join(os.path.dirname(self.top), "canonlink-" + os.path.basename(self.top))
        os.symlink(self.top, link)
        self.addCleanup(os.unlink, link)
        got = self.mod._canonical_prefix(os.path.join(link, "tests", "oracle.py"), self.top)
        self.assertEqual(got, os.path.join(self.top, "tests", "oracle.py"))

    def test_in_repo_self_link_hop_is_preserved(self) -> None:
        # `self -> .` resolves to the repo root but is IN-repo; its hop must NOT be collapsed, or the
        # R-04 surface would lose a retargetable component. Shortest-first stops at the true root.
        os.symlink(".", os.path.join(self.top, "self"))
        got = self.mod._canonical_prefix(os.path.join(self.top, "self", "tests", "oracle.py"), self.top)
        self.assertEqual(got, os.path.join(self.top, "self", "tests", "oracle.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
