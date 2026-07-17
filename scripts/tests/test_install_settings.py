#!/usr/bin/env python3
"""Tests for install_settings.py — the R-07 exact-tuple settings merge.

Every test runs against an ISOLATED settings file (a temp dir; one case additionally isolates $HOME
to prove the default path). Pins the R-07 contract: full nested validation before reading (malformed
→ precise diagnostic, no write), ownership by parsed command target (substring near-misses are NOT
ours), semantic matcher comparison (alternative-set, not string), repair of wrong-matcher /
wrong-path / wrong-timeout Excubitor-owned entries, preservation of unrelated and co-grouped user
entries, and clean/repeat idempotence.

Stdlib unittest only. Run:
  python3 scripts/tests/test_install_settings.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "install_settings.py"

spec = importlib.util.spec_from_file_location("install_settings", MODULE)
assert spec is not None and spec.loader is not None
ins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ins)

CANON_DB = {"matcher": "Edit|Write|NotebookEdit",
            "hooks": [{"type": "command",
                       "command": "python3 ~/.claude/hooks/guard-default-branch.py",
                       "timeout": 10}]}


def _cli(settings: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MODULE), "--settings", str(settings)],
                          capture_output=True, text=True)


def _entries_for(data: dict, script: str) -> list[dict]:
    return [e for e in data["hooks"]["PreToolUse"]
            if any(script in h.get("command", "") for h in e.get("hooks", []))]


class TestCleanAndRepeat(unittest.TestCase):
    def test_clean_install_registers_all_four_canonically(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            r = _cli(p)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(p.read_text())
            pre = data["hooks"]["PreToolUse"]
            self.assertEqual(len(pre), 4)
            for script, matcher in ins.WANTED:
                owned = _entries_for(data, script)
                self.assertEqual(len(owned), 1, script)
                self.assertTrue(ins._entry_is_canonical(owned[0], script, matcher), script)

    def test_repeat_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            _cli(p)
            first = p.read_text()
            r = _cli(p)
            self.assertEqual(p.read_text(), first, "second run must not change the file")
            self.assertNotIn("wrote", r.stdout, "second run must not write")
            self.assertEqual(r.stdout.count("ok      "), 4)

    def test_default_path_used_under_isolated_home(self):
        # The plan's isolated-home case: no --settings; $HOME redirected to a temp dir.
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ, HOME=td)
            r = subprocess.run([sys.executable, str(MODULE)], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            written = Path(td) / ".claude" / "settings.json"
            self.assertTrue(written.is_file(), "must write to $HOME/.claude/settings.json")
            self.assertEqual(len(json.loads(written.read_text())["hooks"]["PreToolUse"]), 4)


class TestValidationNoWrite(unittest.TestCase):
    def _assert_no_write(self, before: dict, expect_fragment: str):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            p.write_text(json.dumps(before))
            raw_before = p.read_text()
            r = _cli(p)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(p.read_text(), raw_before, "malformed input must never be rewritten")
            self.assertIn(expect_fragment, r.stderr)

    def test_non_object_entry_is_precise_and_no_write(self):
        self._assert_no_write({"hooks": {"PreToolUse": ["not-an-object"]}}, "PreToolUse[0]")

    def test_non_object_nested_handler_is_precise_and_no_write(self):
        # THE R-07 CRASH: a nested non-object handler used to raise inside the substring scan.
        self._assert_no_write({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [42]}]}},
                              "hooks[0]")

    def test_non_string_matcher_is_precise_and_no_write(self):
        self._assert_no_write({"hooks": {"PreToolUse": [{"matcher": 7, "hooks": []}]}}, "matcher")

    def test_non_list_hooks_shape_skips(self):
        self._assert_no_write({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": "nope"}]}},
                              "hooks")


class TestOwnershipAndRepair(unittest.TestCase):
    def _merged(self, pre: list) -> dict:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            p.write_text(json.dumps({"hooks": {"PreToolUse": pre}}))
            r = _cli(p)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(p.read_text())

    def test_wrong_matcher_is_repaired(self):
        stale = {"matcher": "Bash",  # wrong: ours is Edit|Write|NotebookEdit
                 "hooks": [{"type": "command",
                            "command": "python3 ~/.claude/hooks/guard-default-branch.py",
                            "timeout": 10}]}
        data = self._merged([stale])
        owned = _entries_for(data, "guard-default-branch.py")
        self.assertEqual(len(owned), 1)
        self.assertTrue(ins._entry_is_canonical(owned[0], "guard-default-branch.py",
                                                "Edit|Write|NotebookEdit"))

    def test_wrong_command_path_is_repaired(self):
        stale = {"matcher": "Edit|Write|NotebookEdit",
                 "hooks": [{"type": "command",
                            "command": "python3 /stale/elsewhere/guard-default-branch.py",
                            "timeout": 10}]}
        data = self._merged([stale])
        owned = _entries_for(data, "guard-default-branch.py")
        self.assertEqual(len(owned), 1)
        self.assertEqual(owned[0]["hooks"][0]["command"],
                         "python3 ~/.claude/hooks/guard-default-branch.py")

    def test_wrong_timeout_is_repaired(self):
        stale = {"matcher": "Edit|Write|NotebookEdit",
                 "hooks": [{"type": "command",
                            "command": "python3 ~/.claude/hooks/guard-default-branch.py",
                            "timeout": 99}]}
        data = self._merged([stale])
        self.assertEqual(_entries_for(data, "guard-default-branch.py")[0]["hooks"][0]["timeout"], 10)

    def test_matcher_alternative_order_is_not_repaired(self):
        # semantic matcher comparison: a cosmetic ordering difference is already canonical
        reordered = {"matcher": "Write|NotebookEdit|Edit",
                     "hooks": [{"type": "command",
                                "command": "python3 ~/.claude/hooks/guard-default-branch.py",
                                "timeout": 10}]}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            p.write_text(json.dumps({"hooks": {"PreToolUse": [reordered]}}))
            r = _cli(p)
            data = json.loads(p.read_text())
        self.assertIn("ok      guard-default-branch.py", r.stdout)
        owned = _entries_for(data, "guard-default-branch.py")
        self.assertEqual(len(owned), 1)
        self.assertEqual(owned[0]["matcher"], "Write|NotebookEdit|Edit", "cosmetic order preserved")

    def test_substring_near_miss_is_not_ownership(self):
        # THE R-07 SUBSTRING BUG: a user command whose basename merely CONTAINS our script name used
        # to count as "already registered", silently leaving the guard unregistered.
        user = {"matcher": "Bash",
                "hooks": [{"type": "command",
                           "command": "python3 /home/u/bin/xguard-loop-vc.py.bak",
                           "timeout": 5}]}
        data = self._merged([user])
        pre = data["hooks"]["PreToolUse"]
        self.assertIn(user, pre, "the user's near-miss entry is untouched")
        real = [e for e in pre
                if any(h.get("command") == "python3 ~/.claude/hooks/guard-loop-vc.py"
                       for h in e.get("hooks", []))]
        self.assertEqual(len(real), 1, "the REAL guard must still get registered")

    def test_mixed_entry_keeps_user_handler_in_place(self):
        mixed = {"matcher": "Bash",
                 "hooks": [{"type": "command", "command": "my-linter --check", "timeout": 3},
                           {"type": "command",
                            "command": "python3 /stale/guard-loop-vc.py", "timeout": 10}]}
        data = self._merged([mixed])
        pre = data["hooks"]["PreToolUse"]
        self.assertEqual(pre[0]["hooks"],
                         [{"type": "command", "command": "my-linter --check", "timeout": 3}],
                         "the user's co-grouped handler stays exactly in place")
        owned = _entries_for(data, "guard-loop-vc.py")
        self.assertEqual(len(owned), 1)
        self.assertTrue(ins._entry_is_canonical(owned[0], "guard-loop-vc.py", "Bash"))

    def test_duplicate_owned_entries_collapse_to_one(self):
        dup = {"matcher": "Bash",
               "hooks": [{"type": "command",
                          "command": "python3 ~/.claude/hooks/guard-loop-vc.py", "timeout": 10}]}
        data = self._merged([dup, json.loads(json.dumps(dup))])
        self.assertEqual(len(_entries_for(data, "guard-loop-vc.py")), 1)

    def test_unrelated_user_entries_are_preserved_verbatim(self):
        user_entries = [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "audit-log --json",
                                           "timeout": 30}]},
            {"matcher": "*", "hooks": [{"type": "command", "command": "metrics-tick"}]},
        ]
        data = self._merged(list(user_entries))
        pre = data["hooks"]["PreToolUse"]
        for e in user_entries:
            self.assertIn(e, pre, "unrelated entries must survive the merge unaltered")


class TestOwnershipIsLaunchShapeNotTokenMembership(unittest.TestCase):
    """2026-07-16 independent review, finding 3: `_command_target` treated ANY token with a guard
    basename as ownership, so unrelated user hooks were removed and replaced with the canonical
    guard. Ownership must be a launch shape; argument data is never ownership."""

    def _merged(self, pre: list) -> dict:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "settings.json"
            p.write_text(json.dumps({"hooks": {"PreToolUse": pre}}))
            r = _cli(p)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(p.read_text())

    def _assert_survives(self, user_entry: dict):
        data = self._merged([json.loads(json.dumps(user_entry))])
        self.assertIn(user_entry, data["hooks"]["PreToolUse"],
                      "the user's handler must survive the merge byte-for-byte")
        # and every real guard still got its own canonical registration
        for script, matcher in ins.WANTED:
            canon = [e for e in data["hooks"]["PreToolUse"]
                     if ins._entry_is_canonical(e, script, matcher)]
            self.assertEqual(len(canon), 1, script)

    def test_review_repro_echo_guard_name_survives(self):
        # THE REPRODUCTION: `echo guard-loop-vc.py` was classified Excubitor-owned, removed, and
        # replaced with the canonical guard.
        self._assert_survives({"matcher": "Bash",
                               "hooks": [{"type": "command", "command": "echo guard-loop-vc.py",
                                          "timeout": 5}]})

    def test_wrapper_with_guard_name_argument_survives(self):
        # the guard basename in a NON-script argument position is user data, not ownership
        self._assert_survives({"matcher": "Bash",
                               "hooks": [{"type": "command",
                                          "command": "python3 some-wrapper.py guard-loop-vc.py",
                                          "timeout": 5}]})

    def test_python_c_and_m_forms_are_never_ours(self):
        self._assert_survives({"matcher": "Bash",
                               "hooks": [{"type": "command",
                                          "command": "python3 -c 'print(\"guard-loop-vc.py\")'",
                                          "timeout": 5}]})
        self._assert_survives({"matcher": "Bash",
                               "hooks": [{"type": "command",
                                          "command": "python3 -m mytool guard-loop-vc.py",
                                          "timeout": 5}]})

    def test_near_miss_basenames_survive(self):
        for cmd in ("python3 /home/u/bin/xguard-loop-vc.py.bak",
                    "python3 /home/u/bin/guard-loop-vc.py2",
                    "guard-loop-vc.py.orig --check"):
            with self.subTest(cmd=cmd):
                self._assert_survives({"matcher": "Bash",
                                       "hooks": [{"type": "command", "command": cmd,
                                                  "timeout": 5}]})

    def test_mixed_group_user_handler_with_guard_name_argument_survives_in_place(self):
        # a user handler carrying the guard name as an ARGUMENT, co-grouped with a genuinely stale
        # OURS handler: repair must strip only ours and keep the user handler exactly in place
        user_handler = {"type": "command", "command": "echo guard-loop-vc.py", "timeout": 5}
        mixed = {"matcher": "Bash",
                 "hooks": [dict(user_handler),
                           {"type": "command",
                            "command": "python3 /stale/guard-loop-vc.py", "timeout": 10}]}
        data = self._merged([mixed])
        pre = data["hooks"]["PreToolUse"]
        self.assertEqual(pre[0]["hooks"], [user_handler],
                         "only OUR stale handler is stripped; the user's stays in place")
        owned = _entries_for(data, "guard-loop-vc.py")
        canon = [e for e in owned if ins._entry_is_canonical(e, "guard-loop-vc.py", "Bash")]
        self.assertEqual(len(canon), 1)

    def test_stale_interpreter_launch_is_still_repaired(self):
        # the genuine stale-registration repair must keep working: an interpreter launch of OUR
        # script at a wrong path is ours
        stale = {"matcher": "Bash",
                 "hooks": [{"type": "command",
                            "command": "python3 -u /stale/guard-loop-vc.py", "timeout": 10}]}
        data = self._merged([stale])
        pre = data["hooks"]["PreToolUse"]
        self.assertNotIn(stale, pre, "our stale registration must be repaired, not preserved")
        canon = [e for e in pre if ins._entry_is_canonical(e, "guard-loop-vc.py", "Bash")]
        self.assertEqual(len(canon), 1)

    def test_direct_execution_of_our_script_is_ours(self):
        stale = {"matcher": "Bash",
                 "hooks": [{"type": "command",
                            "command": "/stale/hooks/guard-loop-vc.py", "timeout": 10}]}
        data = self._merged([stale])
        self.assertNotIn(stale, data["hooks"]["PreToolUse"])
        canon = [e for e in data["hooks"]["PreToolUse"]
                 if ins._entry_is_canonical(e, "guard-loop-vc.py", "Bash")]
        self.assertEqual(len(canon), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
