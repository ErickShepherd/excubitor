"""Protocol regression tests; these do not authenticate a synthetic MCP client."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.approval import codex_binding  # noqa: E402
from excubitor.runs import RunStore  # noqa: E402
from runtime.probes.native_session_end import observe  # noqa: E402
from runtime.probes.native_start_record import RecordObserver  # noqa: E402


class TestNativeStartRecord(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # macOS exposes this temporary root via /var, a system link to
        # /private/var. Resolve the fixture so RunStore's link-rejection
        # contract remains exercised only by its dedicated tests.
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.store = RunStore(self.root / "authority", create=True)
        self.messages, self.records = [], []
        self.observer = RecordObserver(self.messages.append, self.records.append, self.store)
        self.meta = {
            "threadId": "native-task",
            "x-codex-turn-metadata": {
                "thread_id": "native-task",
                "session_id": "native-task",
                "sandbox": "windows_elevated",
                "sandbox_mode": "workspace-write",
                "auto_review_enabled": False,
                "thread_source": "user",
                "workspaces": {str(self.project): {}},
            },
        }
        self.binding = codex_binding(self.meta)
        self.observer.receive(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "clientInfo": {"name": "fixture"},
                    "capabilities": {"elicitation": {"form": {}}},
                },
            }
        )

    def call(self, arguments=None, meta=None):
        self.observer.receive(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "confirm_probe",
                    "arguments": arguments or {},
                    "_meta": self.meta if meta is None else meta,
                },
            }
        )
        return self.messages[-1]

    def answer(self, token, content):
        self.observer.receive({"jsonrpc": "2.0", "id": token, "result": content})

    def test_only_pending_native_response_creates_fixture_record(self):
        self.answer("invented", {"action": "accept", "content": {"confirm": True}})
        self.assertIsNone(self.store.lookup(self.binding))
        request = self.call()
        self.assertEqual(request["method"], "elicitation/create")
        self.assertIsNone(self.store.lookup(self.binding))
        self.answer(request["id"], {"action": "accept", "content": {"confirm": True}})
        run = self.store.lookup(self.binding)
        self.assertIsNotNone(run)
        self.answer(request["id"], {"action": "accept", "content": {"confirm": True}})
        self.assertEqual(self.store.lookup(self.binding), run)
        self.observer.close()
        self.assertIsNone(self.store.lookup(self.binding))

    def test_arguments_cannot_supply_approval_or_replace_native_context(self):
        response = self.call({"approved": True, "_meta": self.meta})
        self.assertTrue(response["result"]["isError"])
        self.assertFalse(self.observer.pending)
        response = self.call(meta={"arguments": self.meta})
        self.assertTrue(response["result"]["isError"])
        self.assertIsNone(self.store.lookup(self.binding))

    def test_cancel_response_can_be_followed_by_a_new_explicit_confirmation(self):
        request = self.call()
        self.answer(request["id"], {"action": "cancel"})
        self.assertIsNone(self.store.lookup(self.binding))
        request = self.call()
        self.answer(request["id"], {"action": "accept", "content": {"confirm": True}})
        self.assertIsNotNone(self.store.lookup(self.binding))
        self.observer.close()

    def test_transport_cancellation_ignores_late_accept(self):
        request = self.call()
        self.observer.receive(
            {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}
        )
        self.answer(request["id"], {"action": "accept", "content": {"confirm": True}})
        self.assertIsNone(self.store.lookup(self.binding))
        self.assertFalse(self.observer.gate.pending)

    def test_native_session_end_interrupts_without_claiming_completion_or_drain(self):
        request = self.call()
        self.answer(request["id"], {"action": "accept", "content": {"confirm": True}})
        payload = {
            "hook_event_name": "SessionEnd",
            "session_id": self.binding.session,
            "cwd": str(self.project),
        }
        result = observe(payload, self.store, self.project)
        self.assertEqual(result["result"], "interrupted")
        self.assertTrue(result["retains_protection"])
        self.assertFalse(result["workers_drained"])
        self.assertFalse(result["completion_claimed"])
        revision = self.store.lookup(self.binding).revision
        self.assertEqual(observe(payload, self.store, self.project), result)
        self.assertEqual(self.store.lookup(self.binding).revision, revision)
        self.observer.close()

    def test_session_end_does_not_capture_ordinary_task_or_other_project(self):
        request = self.call()
        self.answer(request["id"], {"action": "accept", "content": {"confirm": True}})
        original = self.store.lookup(self.binding)
        payload = {"hook_event_name": "SessionEnd", "session_id": "ordinary", "cwd": str(self.project)}
        self.assertEqual(observe(payload, self.store, self.project)["result"], "inactive")
        payload.update(session_id=self.binding.session, cwd=str(self.root))
        self.assertEqual(observe(payload, self.store, self.project)["result"], "outside-selected-project")
        self.assertEqual(self.store.lookup(self.binding), original)
        self.observer.close()


if __name__ == "__main__":
    unittest.main()
