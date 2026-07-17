#!/usr/bin/env python3
"""Tests for excubitor.core.dispatch — the model-blind policy dispatcher.

Covers per-policy arming/gating, the deterministic deny precedence when more than one policy would
deny, the neutral telemetry record, and the neutrality invariant.

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_dispatch.py
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

from excubitor.core import dispatch  # noqa: E402
from excubitor.core.events import Capability, LoopMode, PreToolEvent  # noqa: E402
from excubitor.core.policies.self_integrity import ProtectedSurface  # noqa: E402

SURFACE = ProtectedSurface(
    guard_scripts=frozenset({"guard-default-branch.py", "guard-loop-vc.py",
                             "guard-one-unit.py", "guard-self-integrity.py"}),
    marker="allow-default-branch",
    settings_names=frozenset({"settings.json", "settings.local.json"}),
    control_dir=".claude",
)
MARKER = "/".join((".claude", "allow-default-branch"))


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def shell(cmd, mode=LoopMode.CONSERVATIVE, cwd="/x"):
    return PreToolEvent(capability=Capability.SHELL_EXECUTE, command=cmd, cwd=cwd, loop_mode=mode)


def edit(target, mode=None, cwd="/repo"):
    return PreToolEvent(capability=Capability.FILE_MUTATE, targets=(target,), cwd=cwd, loop_mode=mode)


class TestLoopVcGating(unittest.TestCase):
    def test_unarmed_passes_dangerous(self):
        self.assertTrue(dispatch.decide_loop_vc(shell("git push", mode=None)).is_pass)

    def test_armed_denies_push(self):
        d = dispatch.decide_loop_vc(shell("git push"))
        self.assertTrue(d.is_deny)
        self.assertEqual(d.policy, "loop-vc")

    def test_armed_allows_safe(self):
        self.assertTrue(dispatch.decide_loop_vc(shell("echo hi")).is_pass)

    def test_non_shell_passes(self):
        self.assertTrue(dispatch.decide_loop_vc(edit("/repo/f.py", mode=LoopMode.CONSERVATIVE)).is_pass)


class TestSelfIntegrityGating(unittest.TestCase):
    def test_unarmed_passes_kill_switch(self):
        self.assertTrue(dispatch.decide_self_integrity(edit("/r/guard-loop-vc.py", mode=None), SURFACE).is_pass)

    def test_no_surface_passes(self):
        e = edit("/r/guard-loop-vc.py", mode=LoopMode.CONSERVATIVE)
        self.assertTrue(dispatch.decide_self_integrity(e, None).is_pass)

    def test_armed_denies_target(self):
        d = dispatch.decide_self_integrity(edit("/r/hooks/guard-loop-vc.py", mode=LoopMode.CONSERVATIVE), SURFACE)
        self.assertTrue(d.is_deny)
        self.assertEqual(d.policy, "self-integrity")

    def test_armed_denies_bash_naming_switch(self):
        d = dispatch.decide_self_integrity(shell("rm hooks/guard-self-integrity.py"), SURFACE)
        self.assertTrue(d.is_deny)

    def test_armed_allows_innocent(self):
        self.assertTrue(dispatch.decide_self_integrity(edit("/r/README.md", mode=LoopMode.CONSERVATIVE), SURFACE).is_pass)


class TestOneUnitAndDefaultBranchGating(unittest.TestCase):
    def test_one_unit_no_cap_passes(self):
        self.assertTrue(dispatch.decide_one_unit(shell("echo hi"), None).is_pass)

    def test_one_unit_over_cap_denies(self):
        with tempfile.TemporaryDirectory() as td:
            _git(td, "init", "-q"); _git(td, "config", "user.email", "t@t"); _git(td, "config", "user.name", "t")
            _git(td, "commit", "--allow-empty", "-qm", "chore: root")
            _git(td, "commit", "--allow-empty", "-qm", "feat(alpha): unit")
            cap = dispatch.UnitCap(scope="alpha", baseline=0, repo_dir=td)
            d = dispatch.decide_one_unit(shell("echo hi", cwd=td), cap)
            self.assertTrue(d.is_deny)
            self.assertEqual(d.policy, "one-unit")

    def test_default_branch_no_marker_passes(self):
        self.assertTrue(dispatch.decide_default_branch(edit("/repo/f.py", mode=None), None).is_pass)

    def test_default_branch_on_main_denies(self):
        with tempfile.TemporaryDirectory() as td:
            _git(td, "init", "-q", "-b", "main"); _git(td, "config", "user.email", "t@t"); _git(td, "config", "user.name", "t")
            Path(td, "seed").write_text("x"); _git(td, "add", "-A"); _git(td, "commit", "-qm", "seed")
            e = PreToolEvent(capability=Capability.FILE_MUTATE, targets=(str(Path(td, "f.py")),), cwd=td)
            d = dispatch.decide_default_branch(e, MARKER)
            self.assertTrue(d.is_deny)
            self.assertEqual(d.policy, "default-branch")


class TestDispatchPrecedence(unittest.TestCase):
    def test_self_integrity_wins_over_loop_vc(self):
        # armed Bash that BOTH is a fenced VC act AND names a guard script → self-integrity precedence.
        e = shell("git push && rm hooks/guard-loop-vc.py")
        cfg = dispatch.DispatchConfig(protected_surface=SURFACE)
        d = dispatch.dispatch(e, cfg)
        self.assertTrue(d.is_deny)
        self.assertEqual(d.policy, "self-integrity")

    def test_loop_vc_when_no_surface(self):
        e = shell("git push && rm hooks/guard-loop-vc.py")
        d = dispatch.dispatch(e, dispatch.DispatchConfig())  # no surface → self-integrity inactive
        self.assertTrue(d.is_deny)
        self.assertEqual(d.policy, "loop-vc")

    def test_all_pass(self):
        d = dispatch.dispatch(shell("echo hi"), dispatch.DispatchConfig(protected_surface=SURFACE))
        self.assertTrue(d.is_pass)

    def test_precedence_order_constant(self):
        self.assertEqual(dispatch.DENY_PRECEDENCE, ("self-integrity", "loop-vc", "default-branch", "one-unit"))


class TestDenialRecord(unittest.TestCase):
    def test_neutral_record_shape(self):
        e = shell("git push", cwd="/x")
        d = dispatch.decide_loop_vc(e)
        rec = dispatch.denial_record(e, d)
        self.assertEqual(rec["policy"], "loop-vc")
        self.assertEqual(rec["capability"], "shell.execute")
        self.assertEqual(rec["command"], "git push")
        self.assertEqual(rec["targets"], [])
        self.assertIn("reason", rec)


class TestPurity(unittest.TestCase):
    def test_neutral_no_host_no_io(self):
        src = (_REPO_ROOT / "excubitor" / "core" / "dispatch.py").read_text("utf-8")
        for token in ("claude", "anthropic", "codex", "openai", "gemini", "copilot"):
            self.assertNotIn(token, src.lower(), f"dispatch must name no host: {token!r}")
        for token in (".claude", "CLAUDE_LOOP_GUARD", "os.environ", "getenv", "subprocess",
                      "sys.stdin", "sys.stdout", "sys.exit"):
            self.assertNotIn(token, src, f"dispatch must do no host I/O: {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
