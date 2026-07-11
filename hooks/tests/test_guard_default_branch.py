#!/usr/bin/env python3
"""Tests for the guard-default-branch.py PreToolUse hook.

Drives the hook as a subprocess with a crafted PreToolUse stdin payload against a real temp git repo,
asserting the deny/defer contract: deny = exit 0 + JSON permissionDecision=deny on stdout; defer = exit 0
with no decision. Pins the security-load-bearing properties: main/master stay protected even when
origin/HEAD points elsewhere (the union, not replace), git-failure fails OPEN (never a non-zero crash),
the marker must be a real file, and a relative file_path resolves against the payload cwd.

Stdlib unittest only; every test uses a temp repo. Run:
  python3 hooks/tests/test_guard_default_branch.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guard-default-branch.py"


def _git(args: list[str], cwd: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _repo(td: str, branch: str = "main", origin_head: "str | None" = None) -> str:
    """Init a repo with one commit on `branch`; optionally point refs/remotes/origin/HEAD somewhere."""
    _git(["init", "-q", "-b", branch], td)
    _git(["config", "user.email", "t@t"], td)
    _git(["config", "user.name", "t"], td)
    Path(td, "seed.txt").write_text("x")
    _git(["add", "-A"], td)
    _git(["commit", "-qm", "seed"], td)
    if origin_head:
        _git(["symbolic-ref", f"refs/remotes/origin/HEAD", f"refs/remotes/origin/{origin_head}"], td)
    return td


def _run(payload: dict, env: "dict | None" = None) -> "tuple[int, str]":
    env = dict(os.environ) if env is None else dict(env)
    # Keep test denies out of the real telemetry log (every deny appends — see hooks/_denial_log.py).
    env.setdefault("EXCUBITOR_DENIAL_LOG", os.devnull)
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


def _denied(stdout: str) -> bool:
    try:
        return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    except (ValueError, KeyError):
        return False


class TestGuardDefaultBranch(unittest.TestCase):
    def test_main_still_protected_when_origin_head_is_custom(self):
        # The regression: origin/HEAD -> develop must NOT un-protect main (union, not replace).
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main", origin_head="develop")
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertEqual(rc, 0)
            self.assertTrue(_denied(out), "main must stay protected even when origin/HEAD points at develop")

    def test_custom_default_also_protected(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="develop", origin_head="develop")
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertTrue(_denied(out), "the resolved custom default (develop) is protected too")

    def test_slash_containing_default_protected(self):
        # A slash-containing default branch (release/2.0, team/main) must stay protected — rsplit("/")
        # used to yield "2.0" and silently un-fence the real default. removeprefix keeps the full name.
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="release/2.0", origin_head="release/2.0")
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertEqual(rc, 0)
            self.assertTrue(_denied(out), "editing on the slash-named default branch must be denied")

    def test_feature_branch_defers(self):
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main")
            _git(["switch", "-qc", "feature/x"], td)
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertEqual((rc, out.strip()), (0, ""))  # not on default → defer (no decision)

    def test_marker_must_be_a_regular_file(self):
        # A DIRECTORY named like the marker must NOT disable the guard (old os.path.exists said yes).
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main")
            (Path(td, ".claude", "allow-default-branch")).mkdir(parents=True)  # a dir, not a file
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td})
            self.assertTrue(_denied(out), "a directory marker must not bless the default branch")

    def test_relative_target_resolves_against_payload_cwd(self):
        # A relative file_path must resolve against the payload cwd (not the process cwd / a fallback),
        # so repo detection lands on the intended sibling — here a feature-branch repo → defer.
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td, "a"), Path(td, "b")
            a.mkdir(); b.mkdir()
            _repo(str(a), branch="main")
            _repo(str(b), branch="main")
            _git(["switch", "-qc", "feature/y"], str(b))
            rc, out = _run({"tool_input": {"file_path": "../b/f.py"}, "cwd": str(a)})
            self.assertEqual((rc, out.strip()), (0, ""))  # resolves to repo b (feature) → defer, not repo a (main)

    def test_git_missing_fails_open_not_crash(self):
        # git unreachable at hook runtime (empty PATH) must fail OPEN (exit 0, no decision), never crash
        # non-zero. Old code let FileNotFoundError escape; now _git swallows it → caller defers.
        with tempfile.TemporaryDirectory() as td:
            _repo(td, branch="main")
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ALLOW_DEFAULT_BRANCH"}
            env["PATH"] = "/nonexistent"  # git not findable from inside the hook
            rc, out = _run({"tool_input": {"file_path": str(Path(td, "f.py"))}, "cwd": td}, env=env)
            self.assertEqual(rc, 0)              # never non-zero
            self.assertFalse(_denied(out))      # fails open (defer), does not crash

    def test_non_object_json_fails_open(self):
        # valid JSON that is not an object must fail open, not crash on payload.get(...).
        for payload in (5, [], None, "x"):
            rc, out = _run(payload)  # _run json.dumps() the value; a bare scalar/array is valid JSON
            self.assertEqual((rc, out.strip()), (0, ""), f"non-object payload must defer: {payload!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
