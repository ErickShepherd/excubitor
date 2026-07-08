#!/usr/bin/env python3
"""Tests for runtime/spec_adapter.py — the runtime-neutral adapter.

The load-bearing test is TestRuntimeEquivalence: it drives the SAME decision core through TWO
envelopes — the Claude Code PreToolUse hook (as a subprocess, the real host path) and the generic
`decide()` adapter — over a representative command set in both arming modes, and asserts they reach
byte-identical deny/allow decisions. That is the executable proof behind "portable to any runtime that
can intercept tool calls": one core, two front-ends, no forked security logic. The unit tests pin the
adapter's own envelope/arming glue (inactive unless armed, no-command allows, fail-open on junk).

Stdlib unittest only. Run:
  python3 runtime/tests/test_spec_adapter.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # runtime/ (spec_adapter.py)
import spec_adapter as sa  # noqa: E402

_HOOK = _HERE.parents[2] / "hooks" / "guard-loop-vc.py"


def _cc_denies(command: str, loop_mode: "str | None", cwd: "str | None" = None) -> bool:
    """Run the real Claude Code hook as a subprocess and report whether it DENIED (the host path)."""
    env = dict(os.environ)
    env.pop("CLAUDE_LOOP_GUARD", None)
    if loop_mode:
        env["CLAUDE_LOOP_GUARD"] = loop_mode
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    p = subprocess.run([sys.executable, str(_HOOK)], input=payload, capture_output=True, text=True,
                       env=env, cwd=cwd)
    try:
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    except (ValueError, KeyError):
        return False


def _adapter_denies(command: str, loop_mode: "str | None", cwd: "str | None" = None) -> bool:
    return sa.decide({"command": command, "cwd": cwd, "loop_mode": loop_mode})["decision"] == "deny"


class TestRuntimeEquivalence(unittest.TestCase):
    """One core, two envelopes → the same decision. This is the portability claim, made executable."""

    # Repo-independent commands (their verdict does not depend on branch detection), so the two
    # adapters can be compared without standing up a git repo — deny-set and allow-set, both modes.
    COMMANDS = [
        "git push origin main",
        "git merge topic",
        "git branch -D feature",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "git worktree remove ../wt",
        "gh pr merge 5",
        "git remote set-head origin develop",
        "git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/develop",
        "(git push)",                                   # unquoted subshell → caught
        'git commit -m "mentions (git push) in prose"', # quoted → NOT a false deny
        "git commit -m done",
        "git status && git diff",
        "git symbolic-ref HEAD",                        # read form → allow
        "echo hi",
        "git pus{h,} origin main",                      # documented brace-expansion residual → allow
    ]

    def test_cc_and_generic_adapter_agree(self):
        for mode in ("1", "yolo"):
            for cmd in self.COMMANDS:
                cc = _cc_denies(cmd, mode)
                gen = _adapter_denies(cmd, mode)
                self.assertEqual(
                    cc, gen,
                    f"adapters DIVERGED (mode={mode!r}, cmd={cmd!r}): "
                    f"Claude Code hook {'DENY' if cc else 'allow'} vs generic adapter "
                    f"{'DENY' if gen else 'allow'} — the decision core is not runtime-neutral")

    def test_inactive_mode_agrees_too(self):
        # With no arming signal, BOTH adapters must allow even a dangerous command.
        for cmd in ("git push", "git clean -fd", "git branch -D x"):
            self.assertFalse(_cc_denies(cmd, None))
            self.assertFalse(_adapter_denies(cmd, None))


class TestAdapterGlue(unittest.TestCase):
    """The per-runtime envelope/arming glue the adapter is responsible for."""

    def test_inactive_unless_armed(self):
        self.assertEqual(sa.decide({"command": "git push"})["decision"], "allow")
        self.assertEqual(sa.decide({"command": "git push", "loop_mode": None})["decision"], "allow")

    def test_armed_denies_and_gives_reason(self):
        d = sa.decide({"command": "git push", "loop_mode": "1"})
        self.assertEqual(d["decision"], "deny")
        self.assertIn("push", d["reason"])

    def test_no_command_allows(self):
        self.assertEqual(sa.decide({"loop_mode": "1"})["decision"], "allow")
        self.assertEqual(sa.decide({"command": "", "loop_mode": "1"})["decision"], "allow")

    def test_yolo_mode_recognized(self):
        # A fast-forward merge is denied in yolo (only --no-ff into a non-default branch is allowed).
        self.assertEqual(sa.decide({"command": "git merge topic", "loop_mode": "yolo"})["decision"], "deny")

    def test_cli_fail_open_on_junk(self):
        p = subprocess.run([sys.executable, str(_HERE.parents[1] / "spec_adapter.py")],
                           input="not json {{{", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["decision"], "allow")  # fail-open process contract

    def test_wrongly_typed_fields_do_not_crash(self):
        # a valid-JSON envelope with wrong-typed fields must be handled, not raise (the core does
        # len(command)) — the adapter's fail-open promise covers schema violations, not just bad JSON.
        # A non-string/empty command has nothing to classify → allow:
        for event in ({"command": 123, "loop_mode": "1"},
                      {"command": None, "loop_mode": "1"},
                      {"command": [], "loop_mode": "1"}):
            self.assertEqual(sa.decide(event)["decision"], "allow", f"non-string command → allow: {event}")
        # A valid command with a wrong-typed cwd must still classify (cwd coerced to None), not crash:
        self.assertEqual(sa.decide({"command": "git push", "cwd": [], "loop_mode": "1"})["decision"], "deny")
        # and the CLI on a wrong-typed command envelope stays fail-open (no crash):
        p = subprocess.run([sys.executable, str(_HERE.parents[1] / "spec_adapter.py")],
                           input=json.dumps({"command": 123, "loop_mode": "1"}), capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)["decision"]), (0, "allow"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
