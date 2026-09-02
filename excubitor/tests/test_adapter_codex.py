#!/usr/bin/env python3
"""Golden and process-contract tests for the native Codex ``PreToolUse`` adapter.

Stdlib unittest only. Run:
  python excubitor/tests/test_adapter_codex.py
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from excubitor.adapters import codex  # noqa: E402

_FIXTURES = _REPO_ROOT / "runtime" / "tests" / "fixtures" / "codex_pretooluse.json"


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _repo(path: str, branch: str = "main") -> None:
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "dev@erickshepherd.com")
    _git(path, "config", "user.name", "Fixture")
    Path(path, "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(path, "add", "seed.txt")
    _git(path, "commit", "-qm", "seed")
    if branch != "main":
        _git(path, "switch", "-qc", branch)


def _replace_repo(value: object, repo: str) -> object:
    """Replace fixture placeholders structurally, preserving Windows JSON escaping."""
    if isinstance(value, str):
        return value.replace("{REPO}", repo)
    if isinstance(value, list):
        return [_replace_repo(item, repo) for item in value]
    if isinstance(value, dict):
        return {key: _replace_repo(item, repo) for key, item in value.items()}
    return value


class TestCodexGoldenFixtures(unittest.TestCase):
    def test_golden_fixtures(self) -> None:
        cases = json.loads(_FIXTURES.read_text(encoding="utf-8"))
        for source_case in cases:
            with self.subTest(case=source_case["name"]), tempfile.TemporaryDirectory() as repo:
                case = _replace_repo(copy.deepcopy(source_case), repo)
                assert isinstance(case, dict)
                _repo(repo, str(case["repo_branch"]))
                payload = case["payload"]
                environment = case["env"]
                assert isinstance(payload, dict) and isinstance(environment, dict)

                decision = codex.decide(payload, environment)
                self.assertEqual(decision.outcome.value, case["expected_decision"])
                self.assertEqual(decision.policy, case.get("expected_policy"))

                rendered = codex.render(decision)
                if decision.is_pass:
                    self.assertIsNone(rendered)
                else:
                    assert rendered is not None
                    native = rendered["hookSpecificOutput"]
                    assert isinstance(native, dict)
                    self.assertEqual(native["hookEventName"], "PreToolUse")
                    self.assertEqual(native["permissionDecision"], "deny")
                    self.assertTrue(native["permissionDecisionReason"])

                if "expected_targets" in case:
                    normalized = codex.normalize(payload, environment)
                    self.assertIsNotNone(normalized)
                    assert normalized is not None
                    self.assertEqual(list(normalized[0].targets), case["expected_targets"])

    def test_one_unit_policy_is_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            _repo(repo, "feature")
            _git(repo, "commit", "--allow-empty", "-qm", "feat(alpha): unit")
            payload = {
                "session_id": "thr_fixture",
                "cwd": repo,
                "hook_event_name": "PreToolUse",
                "tool_name": "mcp__example__read",
                "tool_input": {"path": "README.md"},
            }
            environment = {
                "ONE_UNIT_CAP_SCOPE": "alpha",
                "ONE_UNIT_CAP_BASELINE": "0",
                "ONE_UNIT_CAP_REPO": repo,
            }
            decision = codex.decide(payload, environment)
            self.assertTrue(decision.is_deny)
            self.assertEqual(decision.policy, "one-unit")

    def test_explicit_default_branch_opt_out_defers(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            _repo(repo, "main")
            payload = {
                "session_id": "thr_fixture",
                "cwd": repo,
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Begin Patch\n*** Add File: allowed.py\n+allowed\n*** End Patch"
                },
            }
            decision = codex.decide(payload, {"EXCUBITOR_ALLOW_DEFAULT_BRANCH": "1"})
            self.assertTrue(decision.is_pass)

    def test_armed_patch_cannot_rewrite_installed_policy_core(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            _repo(repo, "feature")
            adapter_path = Path(codex.__file__).resolve().as_posix()
            payload = {
                "session_id": "thr_fixture",
                "cwd": repo,
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": (
                        f"*** Begin Patch\n*** Update File: {adapter_path}\n"
                        "@@\n-old\n+new\n*** End Patch"
                    )
                },
            }
            decision = codex.decide(payload, {"EXCUBITOR_LOOP_GUARD": "conservative"})
            self.assertTrue(decision.is_deny)
            self.assertEqual(decision.policy, "self-integrity")


class TestCodexPatchParsing(unittest.TestCase):
    def _decision(self, command: str):
        payload = {
            "cwd": str(_REPO_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": command},
        }
        return codex.decide(payload, {"EXCUBITOR_ALLOW_DEFAULT_BRANCH": "1"})

    def test_supported_end_of_file_marker_and_duplicate_targets_pass(self) -> None:
        decision = self._decision(
            "*** Begin Patch\n*** Update File: note.txt\n*** End of File\n"
            "*** Update File: note.txt\n@@\n-old\n+new\n*** End Patch\n"
        )
        self.assertTrue(decision.is_pass)

    def test_ambiguous_patch_shapes_deny(self) -> None:
        cases = (
            "*** Begin Patch\n*** End Patch",
            "*** Begin Patch\n*** Move to: orphan.py\n*** End Patch",
            "*** Begin Patch\n*** Rename File: a.py\n*** End Patch",
            "*** Begin Patch\n*** Update File: \n*** End Patch",
            "*** Begin Patch\n*** Update File: bad\x00.py\n*** End Patch",
            "*** Begin Patch\n*** Update File: a.py",
        )
        for command in cases:
            with self.subTest(command=command):
                decision = self._decision(command)
                self.assertTrue(decision.is_deny)
                self.assertEqual(decision.policy, "adapter-input")


class TestCodexProcessContract(unittest.TestCase):
    def _run(self, stdin: str, environment: "dict[str, str] | None" = None) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        for name in (
            "EXCUBITOR_LOOP_GUARD",
            "CLAUDE_LOOP_GUARD",
            "ONE_UNIT_CAP_SCOPE",
            "ONE_UNIT_CAP_BASELINE",
            "ONE_UNIT_CAP_REPO",
        ):
            env.pop(name, None)
        env.update(environment or {})
        return subprocess.run(
            [sys.executable, "-m", "excubitor.adapters.codex"],
            input=stdin,
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
            env=env,
        )

    def test_pass_is_empty_stdout(self) -> None:
        payload = {
            "cwd": str(_REPO_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        }
        result = self._run(json.dumps(payload), {"EXCUBITOR_LOOP_GUARD": "conservative"})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_deny_is_native_json(self) -> None:
        payload = {
            "cwd": str(_REPO_ROOT),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin main"},
        }
        result = self._run(json.dumps(payload), {"EXCUBITOR_LOOP_GUARD": "conservative"})
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        native = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(native["permissionDecision"], "deny")

    def test_malformed_outer_input_fails_open(self) -> None:
        for stdin in ("not json {{{", "[]", json.dumps({"hook_event_name": "PostToolUse"})):
            with self.subTest(stdin=stdin):
                result = self._run(stdin)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
