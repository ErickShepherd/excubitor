#!/usr/bin/env python3
"""Direct tests for excubitor.core.policies.self_integrity — the extracted self-integrity policy.

The shipped hook (`hooks/tests/test_guard_self_integrity.py`) exercises this end-to-end through the
Claude Code adapter; this tests the matchers DIRECTLY against an adapter-supplied ProtectedSurface —
guard scripts, marker, settings-under-control-dir, symlink laundering, redirection prefixes, and the
"quoted name is not a false deny" property — plus the neutrality invariant (the core hardcodes no host
control dir).

Stdlib unittest only. Run:
  python3 excubitor/tests/test_core_self_integrity.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from excubitor.core.policies import self_integrity as si  # noqa: E402

SURFACE = si.ProtectedSurface(
    guard_scripts=frozenset({"guard-default-branch.py", "guard-loop-vc.py",
                             "guard-one-unit.py", "guard-self-integrity.py"}),
    marker="allow-default-branch",
    settings_names=frozenset({"settings.json", "settings.local.json"}),
    control_dir=".claude",
)


class TestTargetKillSwitch(unittest.TestCase):
    def test_guard_script_denied(self):
        self.assertIsNotNone(si.target_kill_switch("/repo/hooks/guard-loop-vc.py", "/x", SURFACE))

    def test_marker_denied(self):
        self.assertIsNotNone(si.target_kill_switch("/repo/.claude/allow-default-branch", "/x", SURFACE))

    def test_settings_under_control_dir_denied(self):
        self.assertIsNotNone(si.target_kill_switch("/home/u/.claude/settings.json", "/x", SURFACE))
        self.assertIsNotNone(si.target_kill_switch("/r/.claude/settings.local.json", "/x", SURFACE))

    def test_settings_not_under_control_dir_allowed(self):
        # A settings.json NOT under .claude is not a hook registration → no hit.
        self.assertIsNone(si.target_kill_switch("/repo/settings.json", "/x", SURFACE))

    def test_innocent_allowed(self):
        self.assertIsNone(si.target_kill_switch("/repo/README.md", "/x", SURFACE))

    def test_symlink_laundering_resolved(self):
        # An innocuously-named symlink pointing at a guard script must be caught via realpath.
        with tempfile.TemporaryDirectory() as td:
            guard = os.path.join(td, "guard-loop-vc.py")
            open(guard, "w").close()
            link = os.path.join(td, "innocent.txt")
            os.symlink(guard, link)
            self.assertIsNotNone(si.target_kill_switch(guard, td, SURFACE))  # the guard itself
            self.assertIsNotNone(si.target_kill_switch(link, td, SURFACE))   # laundered via symlink


class TestBashKillSwitch(unittest.TestCase):
    def test_names_a_guard_denied(self):
        self.assertIsNotNone(si.bash_kill_switch("rm hooks/guard-self-integrity.py", "/x", SURFACE))

    def test_redirection_prefix_stripped(self):
        self.assertIsNotNone(si.bash_kill_switch(">guard-loop-vc.py", "/x", SURFACE))
        self.assertIsNotNone(si.bash_kill_switch("2>>guard-one-unit.py", "/x", SURFACE))

    def test_quoted_name_is_not_a_false_deny(self):
        self.assertIsNone(si.bash_kill_switch("git commit -m 'see (guard-loop-vc.py)'", "/x", SURFACE))

    def test_comment_after_hash_not_acted_on(self):
        self.assertIsNone(si.bash_kill_switch("rm foo # see guard-loop-vc.py", "/x", SURFACE))

    def test_unquoted_subshell_caught(self):
        self.assertIsNotNone(si.bash_kill_switch("(rm allow-default-branch)", "/x", SURFACE))

    def test_innocent_allowed(self):
        self.assertIsNone(si.bash_kill_switch("echo hi && ls", "/x", SURFACE))


class TestProtectedRootContainment(unittest.TestCase):
    """The extraction moved the decision logic into the excubitor/ package, so self-integrity must fence
    that DIRECTORY (by realpath-prefix), not only the guard-script basenames — else an armed loop
    disarms every guard by editing the core it imports."""

    def _surface(self, root):
        return si.ProtectedSurface(
            guard_scripts=frozenset({"guard-loop-vc.py"}), marker="allow-default-branch",
            settings_names=frozenset({"settings.json"}), control_dir=".claude", protected_roots=(root,))

    def test_file_inside_root_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.path.realpath(os.path.join(td, "excubitor"))
            os.makedirs(os.path.join(root, "core", "policies"))
            f = os.path.join(root, "core", "policies", "loop_vc.py")
            open(f, "w").close()
            self.assertIsNotNone(si.target_kill_switch(f, td, self._surface(root)))
            self.assertIsNotNone(si.target_kill_switch(root, td, self._surface(root)))  # the dir itself

    def test_new_file_inside_root_denied(self):
        # Creating a NEW module in the package (a Write to a not-yet-existent path) is also denied.
        with tempfile.TemporaryDirectory() as td:
            root = os.path.realpath(os.path.join(td, "excubitor"))
            os.makedirs(root)
            self.assertIsNotNone(si.target_kill_switch(os.path.join(root, "evil.py"), td, self._surface(root)))

    def test_symlink_laundering_into_root_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.path.realpath(os.path.join(td, "excubitor"))
            os.makedirs(root)
            tgt = os.path.join(root, "loop_vc.py")
            open(tgt, "w").close()
            link = os.path.join(td, "innocent.txt")
            os.symlink(tgt, link)
            self.assertIsNotNone(si.target_kill_switch(link, td, self._surface(root)))

    def test_sibling_same_prefix_not_over_matched(self):
        # A directory whose name merely shares the prefix (excubitor-other) must NOT match —
        # commonpath applies a path-component boundary, not a string prefix.
        with tempfile.TemporaryDirectory() as td:
            root = os.path.realpath(os.path.join(td, "excubitor"))
            os.makedirs(root)
            other = os.path.join(td, "excubitor-other")
            os.makedirs(other)
            f = os.path.join(other, "loop_vc.py")
            open(f, "w").close()
            self.assertIsNone(si.target_kill_switch(f, td, self._surface(root)))

    def test_root_with_trailing_separator_still_contains_children(self):
        # Host configuration commonly preserves a trailing separator. It must not silently disable
        # the fence (`root + os.sep + os.sep` was previously an unmatchable raw prefix).
        with tempfile.TemporaryDirectory() as td:
            root = os.path.realpath(os.path.join(td, "excubitor"))
            os.makedirs(root)
            f = os.path.join(root, "loop_vc.py")
            open(f, "w").close()
            self.assertIsNotNone(si.target_kill_switch(f, td, self._surface(root + os.sep)))

    def test_external_hardlink_is_an_accepted_residual(self):
        # realpath cannot reveal that an ordinary-looking path outside the protected root shares the
        # protected file's inode. Keep the residual executable so documentation cannot silently overclaim.
        with tempfile.TemporaryDirectory() as td:
            root = os.path.realpath(os.path.join(td, "excubitor"))
            os.makedirs(root)
            protected = os.path.join(root, "loop_vc.py")
            open(protected, "w").close()
            alias = os.path.join(td, "innocent.py")
            os.link(protected, alias)
            self.assertIsNone(si.target_kill_switch(alias, td, self._surface(root)))

    def test_bash_naming_core_file_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root = os.path.realpath(os.path.join(td, "excubitor"))
            os.makedirs(os.path.join(root, "adapters"))
            f = os.path.join(root, "adapters", "claude_code.py")
            open(f, "w").close()
            self.assertIsNotNone(si.bash_kill_switch(f"rm {f}", td, self._surface(root)))

    def test_no_roots_is_backward_compatible(self):
        # A surface without protected_roots (the default) fences only basenames — unchanged behavior.
        s = si.ProtectedSurface(guard_scripts=frozenset({"guard-loop-vc.py"}), marker="m",
                                settings_names=frozenset(), control_dir=".claude")
        self.assertEqual(s.protected_roots, ())
        self.assertIsNone(si.target_kill_switch("/any/excubitor/core/x.py", "/any", s))


class TestPurity(unittest.TestCase):
    def test_neutral_no_hardcoded_host(self):
        src = (_REPO_ROOT / "excubitor" / "core" / "policies" / "self_integrity.py").read_text("utf-8")
        for token in ("claude", "anthropic", "codex", "openai", "gemini", "copilot"):
            self.assertNotIn(token, src.lower(), f"self_integrity must name no host: {token!r}")
        # No hardcoded host control dir / arming var / env read / subprocess — all adapter-supplied.
        for token in (".claude", "CLAUDE_LOOP_GUARD", "os.environ", "getenv", "subprocess"):
            self.assertNotIn(token, src, f"self_integrity must not hardcode host state: {token!r}")
        # expanduser IS allowed — the documented path-resolution carve-out for the fence.


if __name__ == "__main__":
    unittest.main(verbosity=2)
