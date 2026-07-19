#!/usr/bin/env python3
"""Golden Claude Code PreToolUse fixtures runner (C1.8) — the adapter drift oracle.

Drives each native PreToolUse payload in fixtures/claude_code_pretooluse.json through the REAL guard
hook subprocess (with any per-case temp-repo + env setup) and asserts the pinned decision. A decision
change here is a regression, NEVER a fixture update. This complements the per-hook differential suites
by pinning the payload→decision contract of the shared claude_code adapter glue across refactors.

Stdlib unittest only. Run:
  python3 hooks/tests/test_adapter_fixtures.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "claude_code_pretooluse.json"


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, text=True)


def _make_repo(td: str, spec: dict) -> str:
    _git(td, "init", "-q", "-b", spec.get("branch", "main"))
    _git(td, "config", "user.email", "t@t")
    _git(td, "config", "user.name", "t")
    Path(td, "seed.txt").write_text("x")
    _git(td, "add", "-A")
    _git(td, "commit", "-qm", "chore: root")
    for subj in spec.get("commits", []):
        _git(td, "commit", "--allow-empty", "-qm", subj)
    if spec.get("switch_to"):
        _git(td, "switch", "-qc", spec["switch_to"])
    if spec.get("origin_head"):
        _git(td, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{spec['origin_head']}")
    return td


def _sub(obj, repo: "str | None"):
    return json.loads(json.dumps(obj).replace("{REPO}", repo)) if repo else obj


def _base_env() -> dict:
    env = dict(os.environ)
    for k in ("CLAUDE_LOOP_GUARD", "CLAUDE_ALLOW_DEFAULT_BRANCH",
              "ONE_UNIT_CAP_SCOPE", "ONE_UNIT_CAP_BASELINE", "ONE_UNIT_CAP_REPO"):
        env.pop(k, None)
    env["EXCUBITOR_DENIAL_LOG"] = os.devnull  # keep test denies out of the real telemetry log
    return env


def _deny_reason(stdout: str) -> "str | None":
    try:
        out = json.loads(stdout)["hookSpecificOutput"]
        return out["permissionDecisionReason"] if out["permissionDecision"] == "deny" else None
    except (ValueError, KeyError):
        return None


class TestClaudeCodeGoldenFixtures(unittest.TestCase):
    def test_golden_fixtures(self):
        data = json.loads(FIXTURES.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["cases"]), 12, "fixtures shrank unexpectedly")
        for case in data["cases"]:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as td:
                repo = _make_repo(td, case["repo"]) if "repo" in case else None
                payload = _sub(case["payload"], repo)
                env = _base_env()
                for k, v in case.get("env", {}).items():
                    env[k] = v.replace("{REPO}", repo) if repo else v
                p = subprocess.run([sys.executable, str(HOOKS / case["hook"])],
                                   input=json.dumps(payload), capture_output=True, text=True, env=env)
                self.assertEqual(p.returncode, 0, f"{case['name']}: rc={p.returncode} stderr={p.stderr!r}")
                self.assertEqual(p.stderr, "", f"{case['name']}: unexpected stderr {p.stderr!r}")
                reason = _deny_reason(p.stdout)
                if case["deny"]:
                    self.assertIsNotNone(reason, f"{case['name']}: expected DENY, got allow")
                    if "reason_contains" in case:
                        self.assertIn(case["reason_contains"], reason, f"{case['name']}: deny-reason drift")
                else:
                    self.assertIsNone(reason, f"{case['name']}: expected allow, got deny: {reason!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
