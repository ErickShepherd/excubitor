#!/usr/bin/env python3
"""Direct tests for excubitor.core.policies.one_unit — the extracted one-unit cap policy.

The shipped hook (`hooks/tests/test_guard_one_unit.py`) exercises this end-to-end through the Claude
Code adapter; this tests `deny_reason` DIRECTLY: deny once the scope-matched count exceeds baseline,
scope-matching so a sibling stage doesn't cross-trip (parallel-worker safety), and fail-open on a
non-repo. Plus the neutrality invariant.

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_one_unit.py
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

from excubitor.core.policies import one_unit  # noqa: E402


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _repo_with(subjects: "list[str]") -> str:
    d = tempfile.mkdtemp(prefix="one-unit-core-")
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    _git(d, "commit", "--allow-empty", "-qm", "chore: root")
    for s in subjects:
        _git(d, "commit", "--allow-empty", "-qm", s)
    return d


class TestDenyReason(unittest.TestCase):
    def test_denies_once_unit_committed(self):
        repo = _repo_with(["feat(alpha): the one unit"])
        # baseline 0 at spawn, now 1 scope-matched commit → over cap → deny.
        reason = one_unit.deny_reason(repo, "alpha", 0)
        self.assertIsNotNone(reason)
        self.assertIn("scope 'alpha': 1 vs baseline 0", reason)

    def test_defers_before_unit_lands(self):
        repo = _repo_with([])  # only the root chore commit; no alpha commits
        self.assertIsNone(one_unit.deny_reason(repo, "alpha", 0))

    def test_defers_at_baseline(self):
        repo = _repo_with(["feat(alpha): pre-existing"])
        # baseline already counts this one (spawned after it) → count == baseline → defer.
        self.assertIsNone(one_unit.deny_reason(repo, "alpha", 1))

    def test_scope_matched_sibling_does_not_trip(self):
        # Two workers on the same branch, disjoint scopes: beta's commit must NOT trip alpha's cap.
        repo = _repo_with(["fix(beta): sibling stage commit"])
        self.assertIsNone(one_unit.deny_reason(repo, "alpha", 0))
        self.assertIsNotNone(one_unit.deny_reason(repo, "beta", 0))

    def test_fail_open_on_non_repo(self):
        with tempfile.TemporaryDirectory() as td:  # not a git repo
            self.assertIsNone(one_unit.deny_reason(td, "alpha", 0))


class TestPurity(unittest.TestCase):
    def test_neutral_and_io_free(self):
        src = (_REPO_ROOT / "excubitor" / "core" / "policies" / "one_unit.py").read_text("utf-8")
        for token in ("claude", "anthropic", "codex", "openai", "gemini", "copilot"):
            self.assertNotIn(token, src.lower(), f"one_unit must name no host: {token!r}")
        # Reads no env and shells out only via the git_state boundary (not directly).
        for token in ("os.environ", "getenv", "subprocess", "import sys", "sys."):
            self.assertNotIn(token, src, f"one_unit must not do host I/O directly: {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
