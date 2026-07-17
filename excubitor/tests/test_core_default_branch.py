#!/usr/bin/env python3
"""Direct tests for excubitor.core.policies.default_branch — the extracted default-branch policy.

The shipped hook (`hooks/tests/test_guard_default_branch.py`) exercises this end-to-end through the
Claude Code adapter; this tests `deny_reason` DIRECTLY over real repos, including the security-critical
symlink-laundering case (R-03) and the union-not-replace protected set, plus the neutrality invariant.

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_default_branch.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from excubitor.core.policies import default_branch as db  # noqa: E402

_MARKER = os.path.join(".claude", "allow-default-branch")


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _repo(td: str, branch: str = "main", origin_head: "str | None" = None, marker: bool = False) -> str:
    _git(td, "init", "-q", "-b", branch)
    _git(td, "config", "user.email", "t@t")
    _git(td, "config", "user.name", "t")
    Path(td, "seed.txt").write_text("x")
    _git(td, "add", "-A")
    _git(td, "commit", "-qm", "seed")
    if origin_head:
        _git(td, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{origin_head}")
    if marker:
        Path(td, ".claude").mkdir(exist_ok=True)
        Path(td, ".claude", "allow-default-branch").write_text("")
    return td


class TestDenyReason(unittest.TestCase):
    def test_on_default_branch_denies(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, "main")
            self.assertIsNotNone(db.deny_reason(td, os.path.join(td, "f.py"), _MARKER))

    def test_on_feature_branch_defers(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, "main")
            _git(td, "switch", "-qc", "feat/x")
            self.assertIsNone(db.deny_reason(td, os.path.join(td, "f.py"), _MARKER))

    def test_main_protected_even_with_custom_origin_head(self):
        # union-not-replace: origin/HEAD -> develop must not un-protect main.
        with tempfile.TemporaryDirectory() as td:
            _repo(td, "main", origin_head="develop")
            self.assertIsNotNone(db.deny_reason(td, os.path.join(td, "f.py"), _MARKER))

    def test_opt_out_marker_defers(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, "main", marker=True)
            self.assertIsNone(db.deny_reason(td, os.path.join(td, "f.py"), _MARKER))

    def test_not_a_repo_defers(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(db.deny_reason(td, os.path.join(td, "f.py"), _MARKER))

    def test_relative_and_new_nested_target(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, "main")
            self.assertIsNotNone(db.deny_reason(td, "rel.py", _MARKER))  # relative to cwd
            self.assertIsNotNone(db.deny_reason(td, os.path.join(td, "new", "deep", "f.py"), _MARKER))

    def test_symlink_laundering_into_protected_repo_denies(self):
        # R-03: a symlink in a feature-branch repo pointing at a file in a repo on its default branch
        # must be caught — the realpath-resolved container lands in the protected repo.
        with tempfile.TemporaryDirectory() as prot, tempfile.TemporaryDirectory() as feat:
            _repo(prot, "main")
            _repo(feat, "main")
            _git(feat, "switch", "-qc", "feat/y")
            link = os.path.join(feat, "launder.txt")
            os.symlink(os.path.join(prot, "seed.txt"), link)
            self.assertIsNotNone(db.deny_reason(feat, link, _MARKER))

    def test_message_names_the_adapter_supplied_marker(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, "main")
            reason = db.deny_reason(td, os.path.join(td, "f.py"), _MARKER)
            self.assertIn(os.path.join(td, _MARKER), reason)


class TestPurity(unittest.TestCase):
    def test_no_host_provider_or_hardcoded_control_dir(self):
        src = (_REPO_ROOT / "excubitor" / "core" / "policies" / "default_branch.py").read_text("utf-8")
        low = src.lower()
        for token in ("claude", "anthropic", "codex", "openai", "gemini", "copilot",
                      "os.environ", "getenv", "subprocess", "sys.", "import sys"):
            self.assertNotIn(token, low if token in ("claude", "anthropic", "codex", "openai",
                             "gemini", "copilot") else src,
                             f"default_branch must stay neutral / IO-free: {token!r}")
        # It must not hardcode a host control directory — the marker is adapter-supplied.
        self.assertNotIn(".claude", src, "the opt-out marker relpath must be adapter-supplied, not hardcoded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
