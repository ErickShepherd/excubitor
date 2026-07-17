#!/usr/bin/env python3
"""Golden excubitor.pre_tool.v1 fixtures runner + all-four-policy reachability (C1.9).

The fixtures (fixtures/pre_tool_v1.json) pin the generic adapter's decision across the canonical event
shapes (shell / file / notebook / multi-target / read-only / malformed) and the pass/deny
serialization — the drift oracle for the protocol. Because default-branch and one-unit need real git
state, their reachability THROUGH the same generic protocol is proven separately against temp repos.

Stdlib unittest only. Run:
  python3 runtime/tests/test_pre_tool_v1.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # runtime/ holds spec_adapter.py
import spec_adapter as sa  # noqa: E402

FIXTURES = _HERE.parent / "fixtures" / "pre_tool_v1.json"


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


class TestGoldenFixtures(unittest.TestCase):
    def test_fixtures(self):
        data = json.loads(FIXTURES.read_text(encoding="utf-8"))
        surface = data["surface"]
        self.assertGreaterEqual(len(data["cases"]), 12, "fixtures shrank unexpectedly")
        for case in data["cases"]:
            with self.subTest(case=case["name"]):
                config = {"protected_surface": surface} if case.get("use_surface") else case.get("config")
                d = sa.decide(case["event"], config)
                exp = case["expect"]
                if exp["deny"]:
                    self.assertEqual(d["decision"], "deny", f"{case['name']}: {d}")
                    if "policy" in exp:
                        self.assertEqual(d.get("policy"), exp["policy"], f"{case['name']}: {d}")
                    if "reason_contains" in exp:
                        self.assertIn(exp["reason_contains"], d["reason"], f"{case['name']}: {d}")
                else:
                    self.assertEqual(d["decision"], "pass", f"{case['name']}: {d}")
                    self.assertIsNone(d["reason"], f"{case['name']}: {d}")


class TestDecisionSerialization(unittest.TestCase):
    def test_pass_shape(self):
        self.assertEqual(sa.decide({}), {"decision": "pass", "reason": None})

    def test_deny_shape_carries_policy(self):
        d = sa.decide({"capability": "shell.execute", "command": "git push", "loop_mode": "conservative"})
        self.assertEqual(d["decision"], "deny")
        self.assertEqual(d["policy"], "loop-vc")
        self.assertIsInstance(d["reason"], str)


class TestAllFourPoliciesReachable(unittest.TestCase):
    """default-branch and one-unit need git state — prove their generic reachability with temp repos."""

    _MARKER = os.path.join(".claude", "allow-default-branch")

    def _repo(self, td, branch="main", commits=(), switch_to=None):
        _git(td, "init", "-q", "-b", branch)
        _git(td, "config", "user.email", "t@t")
        _git(td, "config", "user.name", "t")
        Path(td, "seed.txt").write_text("x")
        _git(td, "add", "-A")
        _git(td, "commit", "-qm", "chore: root")
        for s in commits:
            _git(td, "commit", "--allow-empty", "-qm", s)
        if switch_to:
            _git(td, "switch", "-qc", switch_to)
        return td

    def test_default_branch_deny_on_main(self):
        with tempfile.TemporaryDirectory() as td:
            self._repo(td)  # on main
            d = sa.decide(
                {"capability": "file.mutate", "targets": [os.path.join(td, "f.py")], "cwd": td},
                {"opt_out_relpath": self._MARKER},
            )
            self.assertEqual(d["decision"], "deny")
            self.assertEqual(d["policy"], "default-branch")

    def test_default_branch_pass_on_feature(self):
        with tempfile.TemporaryDirectory() as td:
            self._repo(td, switch_to="feat/x")
            d = sa.decide(
                {"capability": "file.mutate", "targets": [os.path.join(td, "f.py")], "cwd": td},
                {"opt_out_relpath": self._MARKER},
            )
            self.assertEqual(d["decision"], "pass")

    def test_one_unit_deny_over_cap(self):
        with tempfile.TemporaryDirectory() as td:
            self._repo(td, commits=["feat(alpha): the unit"])
            d = sa.decide(
                {"capability": "shell.execute", "command": "echo x", "cwd": td, "loop_mode": "conservative"},
                {"unit_cap": {"scope": "alpha", "baseline": 0, "repo_dir": td}},
            )
            self.assertEqual(d["decision"], "deny")
            self.assertEqual(d["policy"], "one-unit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
