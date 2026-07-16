#!/usr/bin/env python3
"""Tests for run_frozen_oracle.py — the R-04 atomic permit-to-act gate.

Builds throwaway local git repos (no remote): a `main` base carrying witness scripts, then a loop
branch. Pins the four-beat contract: precheck refusal (10), GREEN (0) / RED (1) verdicts only under
a frozen surface, the recheck refusal when the witness mutates its own oracle mid-run (the check/run
race the runner exists to close), shell-less execution (metacharacters stay literal), and the
timeout → RED path.

Stdlib unittest only. Run:
  python3 skills/ralph-loop/tests/test_run_frozen_oracle.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_frozen_oracle.py"

GREEN = 0
RED = 1
REFUSED = 10


def _run(repo: str, base: str, verified_by: str, timeout: str | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), "--repo", repo, "--base", base, "--verified-by", verified_by]
    if timeout is not None:
        cmd += ["--timeout", timeout]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestRunFrozenOracle(unittest.TestCase):
    def setUp(self) -> None:
        self.d = tempfile.mkdtemp(prefix="frozenrun-")
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

        def g(*args: str) -> None:
            subprocess.run(["git", "-C", self.d, *args], check=True, capture_output=True, text=True)

        self.g = g
        g("init", "-b", "main")
        g("config", "user.email", "t@t.t")
        g("config", "user.name", "t")
        tests = Path(self.d) / "tests"
        tests.mkdir()
        (tests / "witness_ok.py").write_text("import sys\nsys.exit(0)\n")
        (tests / "witness_fail.py").write_text("import sys\nsys.exit(3)\n")
        (tests / "witness_slow.py").write_text("import time\ntime.sleep(30)\n")
        # a witness that MUTATES its own oracle file mid-run, then exits 0 — the check/run race
        (tests / "witness_selfmut.py").write_text(
            "import pathlib\n"
            "p = pathlib.Path(__file__)\n"
            "p.write_text(p.read_text() + '\\n# mutated during run\\n')\n"
        )
        (Path(self.d) / "feature.py").write_text("x = 1\n")
        g("add", "-A")
        g("commit", "-m", "base")
        g("checkout", "-b", "loop/telos")

    def test_green_when_witness_passes_and_surface_frozen(self):
        p = _run(self.d, "main", "python3 tests/witness_ok.py")
        self.assertEqual(p.returncode, GREEN, p.stderr)
        self.assertIn("GREEN", p.stdout)

    def test_red_when_witness_fails(self):
        p = _run(self.d, "main", "python3 tests/witness_fail.py")
        self.assertEqual(p.returncode, RED)
        self.assertIn("RED", p.stderr)

    def test_refused_on_precheck_when_oracle_edited(self):
        # the loop committed an edit to its own witness → precheck refuses before anything runs
        (Path(self.d) / "tests" / "witness_ok.py").write_text("import sys\nsys.exit(0)  # weakened\n")
        self.g("add", "-A")
        self.g("commit", "-m", "edit witness")
        p = _run(self.d, "main", "python3 tests/witness_ok.py")
        self.assertEqual(p.returncode, REFUSED)
        self.assertIn("precheck", p.stderr)

    def test_refused_on_precheck_uncommitted_content_weakening(self):
        # R-04 finding #1 at the permit-to-act gate: the loop weakens a regular witness IN THE
        # WORKTREE without committing (here a would-fail witness rewritten to exit 0). Pre-fix the
        # precheck reported FROZEN (three-dot diff blind to worktree edits) and the runner then ran
        # the now-passing witness and returned GREEN — a false permit. Precheck must REFUSE.
        (Path(self.d) / "tests" / "witness_fail.py").write_text("import sys\nsys.exit(0)  # weakened, UNCOMMITTED\n")
        p = _run(self.d, "main", "python3 tests/witness_fail.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("precheck", p.stderr)

    def test_refused_on_recheck_when_witness_mutates_its_oracle(self):
        # THE RACE: precheck passes (surface pristine), the witness itself rewrites the oracle during
        # execution and exits 0 — the runner must NOT return that green. The recheck refuses: since
        # R-04 #1, the post-execution evaluate() also compares each oracle's content to base, so a
        # non-restored mutation is caught there; the snapshot before/after diff remains as an
        # independent, git-free backstop (defense in depth). Either way the mutation cannot pass.
        p = _run(self.d, "main", "python3 tests/witness_selfmut.py")
        self.assertEqual(p.returncode, REFUSED, f"stdout={p.stdout} stderr={p.stderr}")
        self.assertIn("recheck", p.stderr)

    def test_refused_on_uncommitted_retarget(self):
        # symlinked oracle repointed in the worktree (uncommitted) → precheck's state comparison refuses
        tests = Path(self.d) / "tests"
        os.symlink("witness_ok.py", tests / "witness_link.py")
        self.g("add", "-A")
        self.g("commit", "-m", "add link")
        self.g("checkout", "main")
        self.g("merge", "--ff-only", "loop/telos")
        self.g("checkout", "loop/telos")
        os.remove(tests / "witness_link.py")
        os.symlink("witness_fail.py", tests / "witness_link.py")  # uncommitted retarget
        p = _run(self.d, "main", "python3 tests/witness_link.py")
        self.assertEqual(p.returncode, REFUSED)

    def test_no_shell_metacharacters_stay_literal(self):
        # `$(touch pwned)` must reach the witness as literal argv, not execute: no shell, no side file
        p = _run(self.d, "main", "python3 tests/witness_ok.py $(touch pwned)")
        self.assertEqual(p.returncode, GREEN, p.stderr)
        self.assertFalse((Path(self.d) / "pwned").exists(), "command substitution must not execute")

    def test_shell_chain_does_not_chain(self):
        # `a; b` under a shell would run b and report ITS exit code; without a shell the `;` glues
        # into a literal filename argument. Witness scripts ignore argv → still the FIRST script's
        # verdict, and the chained command never runs.
        p = _run(self.d, "main", "python3 tests/witness_ok.py ; python3 tests/witness_fail.py")
        self.assertEqual(p.returncode, GREEN,
                         f"`;` must not chain a second command (stderr={p.stderr})")

    def test_timeout_is_red_not_green(self):
        p = _run(self.d, "main", "python3 tests/witness_slow.py", timeout="1")
        self.assertEqual(p.returncode, RED)
        self.assertIn("timed out", p.stderr)

    def test_missing_witness_executable_is_red(self):
        # a witness that cannot execute yields NO verdict — fail-safe is RED, never green
        (Path(self.d) / "tests" / "orphan.py").write_text("import sys\nsys.exit(0)\n")
        self.g("add", "-A")
        self.g("commit", "-m", "add orphan oracle")
        self.g("checkout", "main")
        self.g("merge", "--ff-only", "loop/telos")
        self.g("checkout", "loop/telos")
        p = _run(self.d, "main", "no-such-interpreter tests/orphan.py")
        self.assertEqual(p.returncode, RED)

    def test_refused_when_no_oracle_file(self):
        p = _run(self.d, "main", "echo done")
        self.assertEqual(p.returncode, REFUSED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
