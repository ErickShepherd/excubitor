#!/usr/bin/env python3
"""Tests for the guard-one-unit.py PreToolUse hook.

Drives the hook as a subprocess against a real temp git repo, asserting the deny/defer contract:
deny = exit 0 + JSON permissionDecision=deny; defer = exit 0 with no decision. Pins the load-bearing
properties: INACTIVE unless BOTH env knobs are set; DENIES once the scope-matched commit count exceeds
the baseline (the session's one unit landed); is SCOPE-MATCHED so a sibling stage's commit does NOT
trip the cap (parallel two-worker safety); and FAILS OPEN on unparseable input or a non-git dir.

Stdlib unittest only. Run:
  python3 hooks/tests/test_guard_one_unit.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "guard-one-unit.py"


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)


def _commit(repo: str, subject: str) -> None:
    # An empty commit is enough; we only care about the subject (scope) and the count.
    _git(repo, "commit", "--allow-empty", "-m", subject)


def _new_repo() -> str:
    d = tempfile.mkdtemp(prefix="one-unit-")
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    _commit(d, "chore: root")
    return d


def _run(
    *,
    scope: "str | None",
    baseline: "str | None",
    repo: "str | None",
    tool: str = "Bash",
    raw: "str | None" = None,
) -> "tuple[int, str]":
    env = dict(os.environ)
    for k in ("ONE_UNIT_CAP_SCOPE", "ONE_UNIT_CAP_BASELINE", "ONE_UNIT_CAP_REPO"):
        env.pop(k, None)
    # Keep test denies out of the real telemetry log (every deny appends — see hooks/_denial_log.py).
    env.setdefault("EXCUBITOR_DENIAL_LOG", os.devnull)
    if scope is not None:
        env["ONE_UNIT_CAP_SCOPE"] = scope
    if baseline is not None:
        env["ONE_UNIT_CAP_BASELINE"] = baseline
    if repo is not None:
        env["ONE_UNIT_CAP_REPO"] = repo
    payload = raw if raw is not None else json.dumps({"tool_name": tool, "tool_input": {"command": "x"}, "cwd": repo})
    p = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


def _denied(stdout: str) -> bool:
    if not stdout.strip():
        return False
    try:
        d = json.loads(stdout)
    except json.JSONDecodeError:
        return False
    return d.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


class GuardOneUnit(unittest.TestCase):
    def test_inert_without_env(self):
        repo = _new_repo()
        _commit(repo, "feat(content-review): a unit")
        # No env at all → no-op (allow), even though a scoped commit exists.
        rc, out = _run(scope=None, baseline=None, repo=repo)
        self.assertEqual(rc, 0)
        self.assertFalse(_denied(out))

    def test_inert_with_only_one_knob(self):
        repo = _new_repo()
        _commit(repo, "feat(content-review): a unit")
        self.assertFalse(_denied(_run(scope="content-review", baseline=None, repo=repo)[1]))
        self.assertFalse(_denied(_run(scope=None, baseline="0", repo=repo)[1]))

    def test_allows_before_the_unit_commit(self):
        repo = _new_repo()  # 0 content-review commits
        rc, out = _run(scope="content-review", baseline="0", repo=repo)
        self.assertEqual(rc, 0)
        self.assertFalse(_denied(out))  # count == baseline → still doing the unit → allow

    def test_denies_after_the_unit_commit(self):
        repo = _new_repo()
        _commit(repo, "feat(content-review): the one unit")  # count now 1 > baseline 0
        rc, out = _run(scope="content-review", baseline="0", repo=repo)
        self.assertEqual(rc, 0)
        self.assertTrue(_denied(out))

    def test_scope_matched_sibling_commit_does_not_trip(self):
        # Two workers in parallel: a sibling-scope commit must NOT end this worker's session.
        repo = _new_repo()
        _commit(repo, "feat(stage-b): sibling unit")  # different scope
        rc, out = _run(scope="stage-a", baseline="0", repo=repo)
        self.assertEqual(rc, 0)
        self.assertFalse(_denied(out))  # stage-a scoped-count still 0 == baseline → allow

    def test_fail_open_unparseable_stdin(self):
        repo = _new_repo()
        _commit(repo, "feat(content-review): a unit")
        rc, out = _run(scope="content-review", baseline="0", repo=repo, raw="}{ not json")
        self.assertEqual(rc, 0)
        self.assertFalse(_denied(out))

    def test_fail_open_non_git_dir(self):
        d = tempfile.mkdtemp(prefix="one-unit-nogit-")
        rc, out = _run(scope="content-review", baseline="0", repo=d)
        self.assertEqual(rc, 0)
        self.assertFalse(_denied(out))  # git fails → fail open

    def test_denies_non_bash_tool_post_commit(self):
        # matcher is "*": the post-commit tool to deny may be ANY tool (e.g. Edit), not just Bash.
        repo = _new_repo()
        _commit(repo, "feat(content-review): the one unit")
        rc, out = _run(scope="content-review", baseline="0", repo=repo, tool="Edit")
        self.assertEqual(rc, 0)
        self.assertTrue(_denied(out))

    def test_inert_non_numeric_baseline(self):
        # A malformed baseline must be treated as "not armed" (inert), never crash or mis-deny.
        repo = _new_repo()
        _commit(repo, "feat(content-review): a unit")
        self.assertFalse(_denied(_run(scope="content-review", baseline="not-a-number", repo=repo)[1]))
        self.assertFalse(_denied(_run(scope="content-review", baseline="-1", repo=repo)[1]))
        # non-ASCII "digits" that str.isdigit() accepts but int() rejects must be inert, not crash.
        rc, out = _run(scope="content-review", baseline="²", repo=repo)  # superscript two
        self.assertEqual(rc, 0)
        self.assertFalse(_denied(out))

    def test_non_object_json_fails_open(self):
        # valid JSON that is not an object must fail open, not crash on payload.get("cwd").
        for raw in ("5", "[]", "null"):
            rc, out = _run(scope="content-review", baseline="0", repo=None, raw=raw)
            self.assertEqual((rc, out.strip()), (0, ""), f"non-object payload must defer: {raw!r}")


if __name__ == "__main__":
    unittest.main()
