"""Host-side confirmation and output-oracle contracts; native transport tested separately."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import Execution, OutputOracle, record_output  # noqa: E402
from excubitor.approval import StartHandshake, codex_binding  # noqa: E402
from excubitor.runs import Binding, Candidate, Conflict, Contract, NotReady, RunError, RunStore  # noqa: E402


class TestApprovalAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # macOS exposes its temporary directory through /var, a system symlink to
        # /private/var. Resolve that fixture root so these approval tests do not
        # accidentally exercise the separate symlink-rejection contract.
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.binding = Binding("codex-cli", "native-task", str(self.project))
        self.oracle = OutputOracle("double", (sys.executable, "program.py"), "2\n", "4\n")
        self.contract = Contract(
            self.binding, "Implement doubling", ("double",), (self.oracle.check,), 3, 200
        )
        self.now = 10
        self.store = RunStore(self.root / "authority", create=True, clock=lambda: self.now)
        self.gate = StartHandshake(self.store, clock=lambda: self.now)
        self.accept = {"action": "accept", "content": {"confirm": True}}

    def prepare(self):
        return self.gate.prepare(self.binding, self.contract, (self.oracle,))

    def active_candidate(self):
        pending = self.prepare()
        run = self.gate.answer(pending.id, self.accept)
        run = self.store.begin_attempt(run)
        candidate = Candidate("a" * 64, "b" * 40, True, True)
        return self.store.checkpoint(run, candidate, unit="double"), candidate

    def test_prepare_does_not_activate_or_write_an_approval(self):
        pending = self.prepare()
        self.assertIsNone(self.store.lookup(self.binding))
        self.assertIn("4\\n", pending.request["message"])
        self.assertEqual(pending.request["requestedSchema"]["properties"]["confirm"]["default"], False)
        self.assertFalse((self.store.directory / "oracles").exists())

    def test_accept_freezes_original_checks_and_starts_exact_scope(self):
        pending = self.prepare()
        run = self.gate.answer(pending.id, self.accept)
        self.assertEqual(run.contract, self.contract)
        self.assertEqual(OutputOracle.load(self.store, self.oracle.check), self.oracle)
        self.assertIsNone(self.store.lookup(replace(self.binding, session="ordinary")))
        with self.assertRaises(Conflict):
            self.gate.answer(pending.id, self.accept)

    def test_cancel_decline_missing_or_false_response_never_start(self):
        for response in (
            {"action": "cancel"},
            {"action": "decline"},
            {},
            None,
            {"action": "accept", "content": {"confirm": False}},
            {"action": "accept", "content": {"confirm": 1}},
            {"action": "accept", "content": {"confirm": True, "max_attempts": 99}},
        ):
            with self.subTest(response=response):
                pending = self.prepare()
                self.assertIsNone(self.gate.answer(pending.id, response))
                self.assertIsNone(self.store.lookup(self.binding))
                with self.assertRaises(Conflict):
                    self.gate.answer(pending.id, self.accept)

    def test_other_connection_cannot_consume_pending_confirmation(self):
        pending = self.prepare()
        with self.assertRaises(Conflict):
            StartHandshake(self.store).answer(pending.id, self.accept)
        self.assertIsNotNone(self.gate.answer(pending.id, self.accept))

    def test_job_and_check_swaps_cannot_reuse_preview(self):
        with self.assertRaises(Conflict):
            self.gate.prepare(replace(self.binding, session="other"), self.contract, (self.oracle,))
        with self.assertRaises(Conflict):
            self.gate.prepare(self.binding, self.contract, (replace(self.oracle, stdout="anything"),))
        with self.assertRaises(ValueError):
            self.gate.prepare(self.binding, self.contract, [self.oracle])

    def test_no_second_prompt_or_second_active_run_for_same_scope(self):
        pending = self.prepare()
        with self.assertRaises(Conflict):
            self.prepare()
        self.gate.answer(pending.id, self.accept)
        with self.assertRaises(Conflict):
            self.prepare()

    def test_cancelled_transport_and_eof_cannot_accept_late_response(self):
        pending = self.prepare()
        self.gate.discard(pending.id)
        with self.assertRaises(Conflict):
            self.gate.answer(pending.id, self.accept)
        pending = self.prepare()
        self.gate.close()
        with self.assertRaises(Conflict):
            self.gate.answer(pending.id, self.accept)
        with self.assertRaises(NotReady):
            self.prepare()

    def test_expired_confirmation_or_contract_cannot_start(self):
        pending = self.prepare()
        self.now = 400
        with self.assertRaises(NotReady):
            self.gate.answer(pending.id, self.accept)
        self.assertIsNone(self.store.lookup(self.binding))
        with self.assertRaises(NotReady):
            self.prepare()

    def test_broken_frozen_blob_prevents_activation(self):
        self.oracle.save(self.store)
        path = self.store.directory / "oracles" / (self.oracle.check.oracle_digest + ".json")
        path.write_text("broken")
        pending = self.prepare()
        with self.assertRaises(RunError):
            self.gate.answer(pending.id, self.accept)
        self.assertIsNone(self.store.lookup(self.binding))

    def test_real_output_bytes_pass_without_completing_the_run(self):
        run, candidate = self.active_candidate()
        updated = record_output(self.store, run, candidate, self.oracle.check, Execution(0, b"4\n", b"", 0.5))
        self.assertEqual(dict(updated.check_results), {"double": True})
        self.assertEqual(updated.state, "running")
        self.assertFalse(updated.reviewed)
        with self.assertRaises(NotReady):
            self.store.finish(updated, candidate, workers_idle=True)

    def test_forged_green_summary_and_early_zero_exit_fail(self):
        run, candidate = self.active_candidate()
        for output in (b"", b"All tests passed!\n", b'{"passed": true}', b"5\n", b"4\r\n"):
            run = record_output(self.store, run, candidate, self.oracle.check, Execution(0, output, b"", 0.5))
            self.assertEqual(dict(run.check_results), {"double": False})

    def test_correct_output_does_not_hide_failure_timeout_or_truncation(self):
        run, candidate = self.active_candidate()
        correct = Execution(0, b"4\n", b"", 0.5)
        for result in (
            replace(correct, exit_code=1),
            replace(correct, timed_out=True),
            replace(correct, output_limited=True),
            replace(correct, elapsed_seconds=31),
            replace(correct, stderr=b"error"),
            replace(correct, elapsed_seconds=float("nan")),
        ):
            run = record_output(self.store, run, candidate, self.oracle.check, result)
            self.assertFalse(dict(run.check_results)["double"])

    def test_changed_or_missing_oracle_cannot_be_reported_as_passing(self):
        run, candidate = self.active_candidate()
        path = self.store.directory / "oracles" / (self.oracle.check.oracle_digest + ".json")
        path.write_bytes(replace(self.oracle, stdout="5\n").payload)
        with self.assertRaises(RunError):
            record_output(self.store, run, candidate, self.oracle.check, Execution(0, b"5\n", b"", 1))
        path.unlink()
        with self.assertRaises(RunError):
            OutputOracle.load(self.store, self.oracle.check)

    def test_metadata_parser_uses_native_scope_and_rejects_conflicts(self):
        meta = {
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
        self.assertEqual(codex_binding(meta), self.binding)
        for key, value in (
            ("session_id", "different"),
            ("thread_id", "different"),
            ("sandbox", "windows_unelevated"),
            ("sandbox", "none"),
            ("sandbox_mode", "danger-full-access"),
            ("auto_review_enabled", True),
            ("workspaces", {}),
            ("workspaces", {str(self.project): {}, str(self.root): {}}),
        ):
            changed = json.loads(json.dumps(meta))
            changed["x-codex-turn-metadata"][key] = value
            with self.assertRaises(NotReady):
                codex_binding(changed)
        with self.assertRaises(NotReady):
            codex_binding({"arguments": meta})
        # Observed app-server direct MCP calls have no active-turn envelope.
        # Their task ID alone must never acquire the CLI approval path's authority.
        with self.assertRaises(NotReady):
            codex_binding({"threadId": "native-task", "progressToken": 1})


if __name__ == "__main__":
    unittest.main()
