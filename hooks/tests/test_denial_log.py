#!/usr/bin/env python3
"""Tests for denial telemetry (hooks/_denial_log.py + the four guards' _deny wiring).

Drives each guard as a subprocess into a real deny and asserts the telemetry contract:
  * every deny appends exactly ONE valid JSON line (schema excubitor.denial.v1) to
    $EXCUBITOR_DENIAL_LOG, with the guard/tool/target/reason/mode/session_id fields;
  * the deny decision NEVER depends on telemetry — an unwritable log path, a log path that is a
    directory, or a copied guard with no sibling module all still emit the deny JSON, exit 0,
    and print nothing to stderr (the fault is swallowed, not just non-fatal);
  * commands/reasons containing newlines and control characters stay ONE line (json escaping);
  * the ~/.claude symlink install layout resolves back to the repo sibling (run via a symlink);
  * BIDIRECTIONAL PIN (KNOWN-BYPASSES.md): guard-self-integrity does NOT fence the telemetry
    log while armed — the log is observability, not evidence — while the same command shape
    against a real kill-switch path still denies. If either direction flips, the documented
    scope changed silently and this test must be updated together with KNOWN-BYPASSES.md.

Stdlib unittest only. Run:
  python3 hooks/tests/test_denial_log.py
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

HOOKS = Path(__file__).resolve().parents[1]
MODULE = HOOKS / "_denial_log.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_denial_log_under_test", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _base_env(log_path: str) -> dict:
    env = dict(os.environ)
    for k in ("CLAUDE_LOOP_GUARD", "CLAUDE_ALLOW_DEFAULT_BRANCH",
              "ONE_UNIT_CAP_SCOPE", "ONE_UNIT_CAP_BASELINE", "ONE_UNIT_CAP_REPO"):
        env.pop(k, None)
    env["EXCUBITOR_DENIAL_LOG"] = log_path
    return env


def _run(hook: Path, payload: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


def _denied(stdout: str) -> "str | None":
    """The deny reason if stdout carries a deny decision, else None."""
    try:
        out = json.loads(stdout)["hookSpecificOutput"]
        return out["permissionDecisionReason"] if out["permissionDecision"] == "deny" else None
    except (ValueError, KeyError):
        return None


def _git(args: list, cwd: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _main_repo(td: str) -> str:
    """A repo on `main` with one commit whose subject carries scope `(s1)` — a deny state for
    both guard-default-branch (on the default branch) and guard-one-unit (baseline 0 < 1)."""
    os.makedirs(td, exist_ok=True)
    _git(["init", "-q", "-b", "main"], td)
    _git(["config", "user.email", "t@t"], td)
    _git(["config", "user.name", "t"], td)
    Path(td, "seed.txt").write_text("x")
    _git(["add", "-A"], td)
    _git(["commit", "-qm", "feat(s1): seed"], td)
    return td


def _deny_scenarios(repo: str):
    """(guard basename, payload, extra env, expected mode) — one real deny per guard."""
    return [
        ("guard-default-branch.py",
         {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(repo, "seed.txt")},
          "cwd": repo, "session_id": "sess-test"},
         {}, None, os.path.join(repo, "seed.txt")),
        ("guard-one-unit.py",
         {"tool_name": "Bash", "tool_input": {"command": "echo next"},
          "cwd": repo, "session_id": "sess-test"},
         {"ONE_UNIT_CAP_SCOPE": "s1", "ONE_UNIT_CAP_BASELINE": "0"}, None, "echo next"),
        ("guard-loop-vc.py",
         {"tool_name": "Bash", "tool_input": {"command": "git push origin main"},
          "cwd": repo, "session_id": "sess-test"},
         {"CLAUDE_LOOP_GUARD": "1"}, "1", "git push origin main"),
        ("guard-self-integrity.py",
         {"tool_name": "Write", "tool_input": {"file_path": "/x/.claude/settings.json"},
          "cwd": repo, "session_id": "sess-test"},
         {"CLAUDE_LOOP_GUARD": "1"}, "1", "/x/.claude/settings.json"),
    ]


class TestDenialLogModule(unittest.TestCase):
    def test_record_appends_one_valid_line(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "nested", "dir", "denials.jsonl")  # parents created on demand
            payload = {"tool_name": "Bash", "tool_input": {"command": "git push"},
                       "cwd": "/w", "session_id": "s"}
            env_log = os.environ.get("EXCUBITOR_DENIAL_LOG")
            os.environ["EXCUBITOR_DENIAL_LOG"] = log
            try:
                self.assertTrue(mod.record("guard-loop-vc", "why", payload))
                self.assertTrue(mod.record("guard-loop-vc", "why2", payload))
            finally:
                if env_log is None:
                    os.environ.pop("EXCUBITOR_DENIAL_LOG", None)
                else:
                    os.environ["EXCUBITOR_DENIAL_LOG"] = env_log
            lines = Path(log).read_text().splitlines()
            self.assertEqual(len(lines), 2)  # append, not truncate
            event = json.loads(lines[0])
            self.assertEqual(event["schema"], mod.SCHEMA)
            self.assertEqual(event["guard"], "guard-loop-vc")
            self.assertEqual(event["target"], "git push")
            self.assertEqual(event["reason"], "why")
            self.assertEqual(event["session_id"], "s")

    def test_record_never_raises(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as td:
            blocker = os.path.join(td, "blocker")
            Path(blocker).write_text("")  # a FILE where a parent dir is needed → makedirs fails
            env_log = os.environ.get("EXCUBITOR_DENIAL_LOG")
            os.environ["EXCUBITOR_DENIAL_LOG"] = os.path.join(blocker, "denials.jsonl")
            try:
                self.assertFalse(mod.record("g", "r", {"tool_name": "Bash"}))
                self.assertFalse(mod.record("g", "r", "not-a-dict"))  # bad payload → False, not raise
            finally:
                if env_log is None:
                    os.environ.pop("EXCUBITOR_DENIAL_LOG", None)
                else:
                    os.environ["EXCUBITOR_DENIAL_LOG"] = env_log


class TestGuardsLogDenials(unittest.TestCase):
    def test_every_guard_appends_one_event_per_deny(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _main_repo(os.path.join(td, "repo"))
            for hook, payload, extra, mode, target in _deny_scenarios(repo):
                with self.subTest(hook=hook):
                    log = os.path.join(td, "logs", hook, "denials.jsonl")
                    env = _base_env(log)
                    env.update(extra)
                    p = _run(HOOKS / hook, payload, env)
                    reason = _denied(p.stdout)
                    self.assertEqual(p.returncode, 0)
                    self.assertIsNotNone(reason, f"{hook} did not deny")
                    self.assertEqual(p.stderr, "")
                    lines = Path(log).read_text().splitlines()
                    self.assertEqual(len(lines), 1)
                    event = json.loads(lines[0])
                    self.assertEqual(event["schema"], "excubitor.denial.v1")
                    self.assertEqual(event["guard"], hook.removesuffix(".py"))
                    self.assertEqual(event["mode"], mode)
                    self.assertEqual(event["tool"], payload["tool_name"])
                    self.assertEqual(event["target"], target)
                    self.assertEqual(event["reason"], reason)  # log matches what the harness saw
                    self.assertEqual(event["cwd"], repo)
                    self.assertEqual(event["session_id"], "sess-test")
                    self.assertIn("T", event["ts"])  # ISO-8601

    def test_allow_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "denials.jsonl")
            env = _base_env(log)
            env["CLAUDE_LOOP_GUARD"] = "1"
            p = _run(HOOKS / "guard-loop-vc.py",
                     {"tool_name": "Bash", "tool_input": {"command": "git status"}}, env)
            self.assertEqual(p.returncode, 0)
            self.assertIsNone(_denied(p.stdout))
            self.assertFalse(Path(log).exists())

    def test_control_characters_stay_one_line(self):
        cmd = "git push origin main\nrm -rf /\x1b[31mred\x07"
        with tempfile.TemporaryDirectory() as td:
            log = os.path.join(td, "denials.jsonl")
            env = _base_env(log)
            env["CLAUDE_LOOP_GUARD"] = "1"
            p = _run(HOOKS / "guard-loop-vc.py",
                     {"tool_name": "Bash", "tool_input": {"command": cmd}}, env)
            self.assertIsNotNone(_denied(p.stdout))
            raw = Path(log).read_text()
            lines = raw.splitlines()
            self.assertEqual(len(lines), 1)  # embedded newline escaped, not literal
            self.assertEqual(json.loads(lines[0])["target"], cmd)  # round-trips exactly

    # --- telemetry faults must never touch the decision -------------------------------------

    def test_unwritable_log_path_still_denies(self):
        with tempfile.TemporaryDirectory() as td:
            blocker = os.path.join(td, "blocker")
            Path(blocker).write_text("")  # parent "dir" is a file → makedirs fails
            for bad in (os.path.join(blocker, "denials.jsonl"),  # unmakeable parent
                        td):                                     # log path IS a directory
                with self.subTest(bad=bad):
                    env = _base_env(bad)
                    env["CLAUDE_LOOP_GUARD"] = "1"
                    p = _run(HOOKS / "guard-loop-vc.py",
                             {"tool_name": "Bash", "tool_input": {"command": "git push"}}, env)
                    self.assertEqual(p.returncode, 0)
                    self.assertIsNotNone(_denied(p.stdout))
                    self.assertEqual(p.stderr, "")  # fault swallowed, no traceback

    def test_copied_guard_without_sibling_still_denies(self):
        # A guard COPIED out of the repo (no _denial_log.py sibling anywhere in its resolved
        # dir) must deny exactly as before — telemetry silently absent, never a crash.
        with tempfile.TemporaryDirectory() as td:
            copied = Path(td, "guard-loop-vc.py")
            copied.write_text((HOOKS / "guard-loop-vc.py").read_text())
            log = os.path.join(td, "denials.jsonl")
            env = _base_env(log)
            env["CLAUDE_LOOP_GUARD"] = "1"
            p = _run(copied, {"tool_name": "Bash", "tool_input": {"command": "git push"}}, env)
            self.assertEqual(p.returncode, 0)
            self.assertIsNotNone(_denied(p.stdout))
            self.assertEqual(p.stderr, "")
            self.assertFalse(Path(log).exists())

    def test_symlinked_guard_finds_repo_sibling(self):
        # The install layout: ~/.claude/hooks/<guard> is a symlink into the repo. The resolved
        # __file__ must land back in repo hooks/ so the sibling module is found and logging works.
        with tempfile.TemporaryDirectory() as td:
            linked = Path(td, "guard-loop-vc.py")
            os.symlink(HOOKS / "guard-loop-vc.py", linked)
            log = os.path.join(td, "denials.jsonl")
            env = _base_env(log)
            env["CLAUDE_LOOP_GUARD"] = "1"
            p = _run(linked, {"tool_name": "Bash", "tool_input": {"command": "git push"}}, env)
            self.assertIsNotNone(_denied(p.stdout))
            event = json.loads(Path(log).read_text().splitlines()[0])
            self.assertEqual(event["guard"], "guard-loop-vc")


class TestLogIsNotAKillSwitch(unittest.TestCase):
    """Bidirectional pin for the KNOWN-BYPASSES.md entry: the telemetry log is deliberately NOT
    fenced by guard-self-integrity — an armed agent CAN touch its own denial history (the log is
    observability, not evidence). If fencing is ever added, this pin fails and the entry (plus
    hooks/_denial_log.py's contract docstring) must be updated in the same change."""

    def _run_armed_bash(self, command: str) -> "str | None":
        env = _base_env(os.devnull)
        env["CLAUDE_LOOP_GUARD"] = "1"
        p = _run(HOOKS / "guard-self-integrity.py",
                 {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/w"}, env)
        return _denied(p.stdout)

    def test_armed_loop_may_touch_the_denial_log(self):
        self.assertIsNone(self._run_armed_bash("rm ~/.claude/excubitor/denials.jsonl"))

    def test_same_shape_against_a_real_kill_switch_still_denies(self):
        # The other direction: the non-deny above is about the LOG, not a hole in the fence.
        self.assertIsNotNone(self._run_armed_bash("rm ~/.claude/settings.json"))


if __name__ == "__main__":
    unittest.main()
