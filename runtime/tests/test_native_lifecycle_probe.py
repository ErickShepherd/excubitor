"""Offline apparatus checks. These do not certify any native host or Ralph run."""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "probes" / "native_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("native_lifecycle_probe", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class TestNativeLifecycleProbe(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / "fixture"
        self.root.mkdir()
        self.database = self.parent / "evidence" / "events.sqlite3"

    def call(self, event, *, runtime="codex", exercise=True, now=100, **overrides):
        payload = {"hook_event_name": event, "cwd": str(self.root), "session_id": "session-one"}
        payload.update(overrides)
        return probe.handle(runtime, event, payload, self.root, self.database, exercise=exercise, now=now)

    def start(self, **overrides):
        return self.call("UserPromptSubmit", prompt=probe.START_PROMPT, **overrides)

    def target(self, **overrides):
        return self.call("PreToolUse", tool_name="apply_patch",
                         tool_input={"command": "*** Add File: probe-denied.txt\n+probe"}, **overrides)

    def records(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT observation FROM events")]

    def test_observer_never_interferes_even_with_start_and_test_target(self):
        self.assertEqual(self.start(exercise=False), {})
        self.assertEqual(self.target(exercise=False), {})
        self.assertEqual(self.call("Stop", exercise=False), {})

    def test_prompt_mention_is_not_the_exact_exercise_trigger(self):
        self.call("UserPromptSubmit", prompt="Please discuss: " + probe.START_PROMPT)
        self.assertEqual(self.target(), {})
        self.assertEqual(self.call("Stop"), {})

    def test_known_synthetic_continuation_is_observable_but_does_not_start(self):
        self.call("UserPromptSubmit", prompt=probe.CONTINUATIONS[0])
        self.assertEqual(self.call("Stop"), {})
        self.assertEqual(self.records()[0]["continuation_prompt"], 1)

    def test_unstarted_session_is_ordinary(self):
        self.assertEqual(self.target(), {})
        self.assertEqual(self.call("Stop"), {})

    def test_two_continuations_and_same_session_returns_to_ordinary(self):
        self.start()
        self.assertEqual(self.target(), probe.render_deny("codex"))
        for reason in probe.CONTINUATIONS:
            self.assertEqual(self.call("Stop"), {"decision": "block", "reason": reason})
        self.assertEqual(self.call("Stop"), {})
        self.assertEqual(self.target(), {})
        self.start()  # A copied trigger cannot extend this experiment's cap.
        self.assertEqual(self.call("Stop"), {})

    def test_interleaved_second_task_is_ordinary(self):
        self.start()
        self.assertEqual(self.target(session_id="session-two"), {})
        self.assertEqual(self.call("Stop", session_id="session-two"), {})
        self.assertEqual(self.target(), probe.render_deny("codex"))

    def test_parent_sibling_nested_repo_and_worktree_are_not_in_scope(self):
        self.start()
        for name in ("sibling", "separate-worktree", "fixture/nested-repo"):
            directory = self.parent / name
            directory.mkdir()
            (directory / ".git").write_text("gitdir: disposable\n")
            self.assertEqual(self.target(cwd=str(directory)), {})
        self.assertEqual(self.target(cwd=str(self.parent)), {})
        self.assertEqual(self.target(), probe.render_deny("codex"))

    def test_plain_subdirectory_in_same_fixture_is_in_scope(self):
        self.start()
        sub = self.root / "sub"
        sub.mkdir()
        self.assertEqual(self.target(cwd=str(sub)), probe.render_deny("codex"))

    def test_empty_or_missing_identity_cannot_start_the_experiment(self):
        for identity in (None, "", 42):
            self.start(session_id=identity)
            self.assertEqual(self.target(session_id=identity), {})
        self.assertEqual(self.target(), {})

    def test_cancellation_ends_experiment_without_restart(self):
        self.start()
        self.assertEqual(self.call("Interrupt"), {})
        self.start()
        self.assertEqual(self.call("Stop"), {})
        self.assertEqual(self.target(), {})

    def test_expiry_ends_test_not_a_production_lease(self):
        self.start()
        self.assertEqual(self.target(now=700), {})
        self.assertEqual(self.call("Stop", now=701), {})

    def test_clock_rollback_ends_the_experiment(self):
        self.start()
        self.assertEqual(self.call("Stop", now=99), {})

    def test_parallel_stops_cannot_exceed_two_continuations(self):
        self.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.call("Stop"), range(12)))
        self.assertEqual(sum(bool(result) for result in results), 2)
        self.assertEqual(self.target(), {})

    def test_text_and_paths_are_not_retained(self):
        self.call("UserPromptSubmit", prompt="private prompt", transcript_path="private transcript path")
        self.call("PreToolUse", tool_name="Bash", tool_input={"command": "private command"})
        encoded = json.dumps(self.records())
        private_values = (
            "private prompt", "private transcript path", "private command", "session-one", str(self.root),
        )
        for private in private_values:
            self.assertNotIn(private, encoded)
        self.assertIn("transcript_path", encoded)  # The field name, never its content.

    def test_agent_writable_payload_is_explicitly_not_owner_authority(self):
        # This intentionally pins a LIMITATION. Synthetic hook input starts the
        # exercise. No test or downstream report may call this secure activation.
        self.start()
        self.assertTrue(self.call("Stop"))

    def test_claude_observation_preserves_field_shape_without_exercise(self):
        self.call("UserPromptSubmit", runtime="claude-code", exercise=False, prompt=probe.START_PROMPT)
        self.assertEqual(self.call("Stop", runtime="claude-code", exercise=False), {})
        self.assertEqual(self.records()[0]["runtime"], "claude-code")
        with self.assertRaises(ValueError):
            self.start(runtime="claude-code")

    def test_antigravity_uses_its_own_field_names(self):
        payload = {"conversationId": "agy-fixture", "workspacePaths": [str(self.root)],
                   "fullyIdle": False, "toolCall": {"name": "run_command", "args": {"command": "echo test"}}}
        result = probe.handle("antigravity", "Stop", payload, self.root, self.database)
        self.assertEqual(result, {})
        record = self.records()[0]
        self.assertEqual(record["session"], probe.digest("agy-fixture"))
        self.assertEqual(record["tool"], "run_command")
        self.assertFalse(record["fully_idle"])
        self.assertTrue(record["in_scope"])

    def test_mismatched_hook_binding_is_rejected(self):
        with self.assertRaises(ValueError):
            self.call("Stop", hook_event_name="PreToolUse")

    def test_real_subprocess_protocol_and_invalid_input(self):
        arguments = [sys.executable, "-B", str(SCRIPT), "--runtime", "codex", "--event", "Stop",
                     "--root", str(self.root), "--database", str(self.database)]
        for value, code in ((json.dumps({"cwd": str(self.root), "session_id": "fixture"}), 0), ("[]", 1),
                            ("invalid json", 1), (" " * (probe.MAX_INPUT + 1), 1)):
            result = subprocess.run(arguments, input=value, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
            self.assertEqual(bool(result.stderr), bool(code))


if __name__ == "__main__":
    unittest.main()
