"""Host-controller tests, not native activation or verifier-backend certification."""

from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.runs import (  # noqa: E402
    Binding,
    Candidate,
    Check,
    Conflict,
    Contract,
    NotReady,
    RunError,
    RunStore,
)


class TestRuns(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.binding = Binding("native-runtime", "owner-task", str(self.project))
        self.check = Check("acceptance", "a" * 64)
        self.contract = Contract(
            self.binding, "Implement both features", ("first", "second"), (self.check,), 4, 200
        )
        self.now = 100
        self.store = RunStore(self.root / "authority", create=True, clock=lambda: self.now)
        self.candidate = Candidate("b" * 64, "c" * 40, True, True)

    def start(self):
        return self.store.start(self.contract, "owner-authorization-once")

    def ready(self):
        run = self.start()
        for unit in self.contract.units:
            run = self.store.begin_attempt(run)
            run = self.store.checkpoint(run, self.candidate, unit=unit)
        run = self.store.record_check(run, self.candidate, self.check, passed=True)
        return self.store.record_review(run, self.candidate, passed=True)

    def test_installation_is_inactive_without_an_owner_start(self):
        self.assertIsNone(self.store.lookup(self.binding))

    def test_binding_does_not_capture_other_tasks_or_projects(self):
        run = self.start()
        other_project = self.root / "other"
        other_project.mkdir()
        for binding in (
            replace(self.binding, session="ordinary"),
            replace(self.binding, runtime="other-host"),
            Binding("native-runtime", "owner-task", str(other_project)),
            Binding("native-runtime", "owner-task", str(self.root)),
        ):
            self.assertIsNone(self.store.lookup(binding))
        self.assertEqual(self.store.lookup(self.binding), run)

    def test_contract_is_immutable_and_changed_copy_is_rejected(self):
        run = self.start()
        with self.assertRaises(Conflict):
            self.store.begin_attempt(replace(run, contract=replace(self.contract, max_attempts=50)))
        self.assertEqual(self.store.get(run.id).contract, self.contract)

    def test_authorization_cannot_be_replayed_even_after_cancellation(self):
        run = self.store.cancel(self.start())
        self.store.acknowledge_cancel(run, workers_idle=True)
        with self.assertRaises(Conflict):
            self.start()

    def test_same_binding_cannot_have_two_active_runs(self):
        self.start()
        with self.assertRaises(Conflict):
            self.store.start(self.contract, "different-owner-authorization")

    def test_multiple_units_advance_and_finish_without_reauthorizing(self):
        run = self.ready()
        finished = self.store.finish(run, self.candidate, workers_idle=True)
        self.assertEqual(finished.attempts, 2)
        self.assertFalse(finished.enforces)
        self.assertIsNone(self.store.lookup(self.binding))
        self.assertEqual(self.store.get(finished.id).state, "complete")

    def test_failed_check_can_be_repaired_inside_remaining_budget(self):
        run = self.ready()
        run = self.store.record_check(run, self.candidate, self.check, passed=False)
        with self.assertRaises(NotReady):
            self.store.finish(run, self.candidate, workers_idle=True)
        run = self.store.begin_attempt(run)
        run = self.store.checkpoint(run, self.candidate)
        run = self.store.record_check(run, self.candidate, self.check, passed=True)
        run = self.store.record_review(run, self.candidate, passed=True)
        self.assertEqual(self.store.finish(run, self.candidate, workers_idle=True).state, "complete")

    def test_late_result_from_old_worker_cannot_change_current_attempt(self):
        old = self.store.begin_attempt(self.start())
        current = self.store.begin_attempt(old)
        with self.assertRaises(Conflict):
            self.store.checkpoint(old, self.candidate, unit="first")
        self.assertEqual(self.store.get(current.id), current)

    def test_duplicate_parallel_completion_has_only_one_winner(self):
        run = self.ready()

        def finish(_):
            try:
                self.store.finish(run, self.candidate, workers_idle=True)
                return "finished"
            except Conflict:
                return "stale"

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(finish, range(4)))
        self.assertEqual(results.count("finished"), 1)

    def test_cannot_drop_units_or_replace_acceptance_checks(self):
        run = self.store.begin_attempt(self.start())
        with self.assertRaises(Conflict):
            self.store.checkpoint(run, self.candidate, unit="second")
        run = self.store.checkpoint(run, self.candidate, unit="first")
        with self.assertRaises(Conflict):
            self.store.record_check(run, self.candidate, Check("acceptance", "d" * 64), passed=True)
        run = self.store.record_check(run, self.candidate, self.check, passed=True)
        run = self.store.record_review(run, self.candidate, passed=True)
        with self.assertRaises(NotReady):
            self.store.finish(run, self.candidate, workers_idle=True)

    def test_evidence_is_invalidated_when_candidate_changes(self):
        run = self.ready()
        replacement = replace(self.candidate, digest="d" * 64)
        run = self.store.checkpoint(run, replacement)
        self.assertFalse(run.reviewed)
        self.assertEqual(run.check_results, ())
        with self.assertRaises(Conflict):
            self.store.record_review(run, self.candidate, passed=True)
        with self.assertRaises(NotReady):
            self.store.finish(run, replacement, workers_idle=True)

    def test_current_candidate_must_still_match_verified_result(self):
        run = self.ready()
        with self.assertRaises(NotReady):
            self.store.finish(run, replace(self.candidate, commit="d" * 40), workers_idle=True)

    def test_review_and_worker_shutdown_are_required(self):
        run = self.ready()
        with self.assertRaises(NotReady):
            self.store.finish(run, self.candidate, workers_idle=False)
        run = self.store.record_review(run, self.candidate, passed=False)
        with self.assertRaises(NotReady):
            self.store.finish(run, self.candidate, workers_idle=True)

    def test_dirty_or_shared_candidate_cannot_complete(self):
        for candidate in (replace(self.candidate, clean=False), replace(self.candidate, isolated=False)):
            with self.subTest(candidate=candidate):
                run = self.store.lookup(self.binding) or self.ready()
                run = self.store.checkpoint(run, candidate)
                run = self.store.record_check(run, candidate, self.check, passed=True)
                run = self.store.record_review(run, candidate, passed=True)
                with self.assertRaises(NotReady):
                    self.store.finish(run, candidate, workers_idle=True)

    def test_cancel_keeps_protection_until_workers_are_drained(self):
        run = self.store.cancel(self.start())
        self.assertTrue(self.store.lookup(self.binding).enforces)
        with self.assertRaises(NotReady):
            self.store.acknowledge_cancel(run, workers_idle=False)
        with self.assertRaises(NotReady):
            self.store.begin_attempt(run)
        self.store.acknowledge_cancel(run, workers_idle=True)
        self.assertIsNone(self.store.lookup(self.binding))

    def test_attempt_budget_blocks_without_silently_disarming(self):
        run = self.start()
        for _ in range(4):
            run = self.store.begin_attempt(run)
        run = self.store.begin_attempt(run)
        self.assertEqual(run.state, "blocked")
        self.assertTrue(run.enforces)
        with self.assertRaises(NotReady):
            self.store.begin_attempt(run)

    def test_resume_preserves_progress_and_remaining_attempts(self):
        run = self.store.begin_attempt(self.start())
        run = self.store.checkpoint(run, self.candidate, unit="first")
        interrupted = self.store.interrupt(run)
        self.assertTrue(interrupted.enforces)
        reopened = RunStore(self.store.directory, clock=lambda: self.now)
        run = reopened.resume(reopened.get(run.id), self.binding, workers_idle=True)
        self.assertEqual(run.completed_units, 1)
        self.assertEqual(run.attempts, 1)
        self.assertEqual(run.contract, self.contract)
        run = reopened.begin_attempt(run)
        self.assertEqual(run.attempts, 2)

    def test_resume_cannot_move_to_another_task_or_leave_old_workers(self):
        run = self.store.interrupt(self.store.begin_attempt(self.start()))
        with self.assertRaises(NotReady):
            self.store.resume(run, replace(self.binding, session="other"), workers_idle=True)
        with self.assertRaises(NotReady):
            self.store.resume(run, self.binding, workers_idle=False)
        self.assertEqual(self.store.get(run.id), run)

    def test_resume_cannot_reset_an_exhausted_budget_or_expired_deadline(self):
        run = self.start()
        for _ in range(4):
            run = self.store.begin_attempt(run)
        run = self.store.interrupt(run)
        run = self.store.resume(run, self.binding, workers_idle=True)
        self.assertEqual(self.store.begin_attempt(run).state, "blocked")
        # A separate, newly authorized run proves time is also preserved.
        run = self.store.cancel(self.store.get(run.id))
        self.store.acknowledge_cancel(run, workers_idle=True)
        run = self.store.start(self.contract, "new-owner-authorization")
        run = self.store.interrupt(self.store.begin_attempt(run))
        self.now = 200
        self.assertEqual(self.store.resume(run, self.binding, workers_idle=True).state, "blocked")

    def test_expired_run_cannot_complete_or_extend_its_deadline(self):
        run = self.ready()
        self.now = 200
        with self.assertRaises(NotReady):
            self.store.finish(run, self.candidate, workers_idle=True)
        run = self.store.get(run.id)
        self.assertEqual(run.state, "blocked")
        self.now = 101
        with self.assertRaises(NotReady):
            self.store.begin_attempt(run)
        with self.assertRaises(NotReady):
            self.store.finish(run, self.candidate, workers_idle=True)
        self.assertTrue(run.enforces)

    def test_missing_store_is_not_an_inactive_signal(self):
        self.start()
        self.store.path.unlink()
        with self.assertRaises(RunError):
            self.store.lookup(self.binding)

    def test_damaged_record_is_not_an_inactive_signal(self):
        run = self.start()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("UPDATE runs SET state = 'complete' WHERE id = ?", (run.id,))
        with self.assertRaises(RunError):
            self.store.lookup(self.binding)

    def test_damaged_cancellation_cannot_release_live_workers(self):
        self.start()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("UPDATE runs SET state = 'cancelled'")
        with self.assertRaises(RunError):
            self.store.lookup(self.binding)

    def test_changed_contract_bytes_are_rejected(self):
        run = self.start()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            contract = json.loads(db.execute("SELECT contract FROM runs").fetchone()[0])
            contract["max_attempts"] = 99
            db.execute("UPDATE runs SET contract = ?", (json.dumps(contract),))
        with self.assertRaises(RunError):
            self.store.get(run.id)

    def test_unknown_store_version_cannot_claim_inactive(self):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("UPDATE metadata SET version = 100")
        with self.assertRaises(RunError):
            self.store.lookup(self.binding)

    def test_inside_project_storage_is_refused(self):
        store = RunStore(self.project / "authority", create=True, clock=lambda: 100)
        with self.assertRaises(RunError):
            store.start(self.contract, "owner-authorization")

    def test_replaced_project_cannot_inherit_prior_directory_identity(self):
        run = self.start()
        self.project.rename(self.root / "old-project")
        self.project.mkdir()
        with self.assertRaises(RunError):
            self.store.get(run.id)
        with self.assertRaises(RunError):
            self.store.lookup(Binding("native-runtime", "owner-task", str(self.project)))

    def test_ended_run_history_does_not_capture_a_recreated_project(self):
        ended = self.store.finish(self.ready(), self.candidate, workers_idle=True)
        self.project.rename(self.root / "old-project")
        self.assertEqual(self.store.get(ended.id), ended)
        self.project.mkdir()
        binding = Binding("native-runtime", "owner-task", str(self.project))
        self.assertIsNone(self.store.lookup(binding))
        fresh = self.store.start(replace(self.contract, binding=binding), "fresh-owner-approval")
        self.assertEqual(self.store.lookup(binding), fresh)

    def test_merge_and_outward_permissions_cannot_be_invented(self):
        for action in ("merge", "publish", "deploy"):
            with self.assertRaises(ValueError):
                replace(self.contract, completion=action)


if __name__ == "__main__":
    unittest.main()
