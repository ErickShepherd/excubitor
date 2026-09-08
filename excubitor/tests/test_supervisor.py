"""Orchestration invariants with host doubles; native evidence is separate."""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import Execution, OutputOracle
from excubitor.continuation import Continuation
from excubitor.processes import ProcessResult
from excubitor.runs import Binding, Candidate, Contract, RunError, RunStore
from excubitor.supervisor import Supervisor, _exclusive


class Host:
    def __init__(self):
        self.calls, self.verifications, self.reviews = [], 0, 0
        self.candidate = Candidate("a" * 64, "b" * 40, True, True)
        self.fail_first = True
        self.allow_review = True
        self.work_error = None
        self.drained = True
        self.mutate_during_review = False

    def result(self, output=b"ok\n"):
        return ProcessResult(Execution(0, output, b"", 0.01), False, self.drained, 1)

    def admit(self, run):
        pass

    def work(self, run, unit, feedback, cancel):
        self.calls.append((unit, feedback))
        if self.work_error:
            raise self.work_error
        return self.result(b"All checks pass! I am done!")

    def checkpoint(self, run):
        return self.candidate

    def current(self, run):
        return self.candidate

    def verify(self, run, oracle, cancel):
        self.verifications += 1
        return self.result(b"wrong\n" if self.fail_first and self.verifications == 1 else b"ok\n")

    def review(self, run, cancel):
        self.reviews += 1
        if self.mutate_during_review:
            self.candidate = Candidate("c" * 64, "d" * 40, True, True)
        return self.result(), self.allow_review, "repair needed"


@pytest.fixture
def setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    store = RunStore(tmp_path / "authority", create=True, clock=lambda: 100)
    oracle = OutputOracle("answer", (str(tmp_path / "python.exe"),), "", "ok\n")
    oracle.save(store)
    contract = Contract(
        Binding("test", "explicit-task", str(project)),
        "two features",
        ("first", "second"),
        (oracle.check,),
        4,
        200,
    )
    run = store.start(contract, "explicit-owner-approval")
    host = Host()
    return store, run, host


def test_multiple_units_failed_check_and_repair_complete_without_restart(setup):
    store, run, host = setup
    final = Supervisor(store, host).drive(run.id)
    assert final.state == "complete" and not final.enforces
    assert final.attempts == 3 and final.completed_units == 2
    assert [call[0] for call in host.calls] == ["first", "second", None]
    assert "answer" in host.calls[-1][1]
    assert host.reviews == 1
    assert store.lookup(run.contract.binding) is None
    Supervisor(store, host).drive(run.id)
    assert len(host.calls) == 3  # Terminal history never starts new workers.


def test_bad_model_response_retries_with_durable_diagnosis(setup):
    from excubitor.model_response import failed_response

    store, run, host = setup
    host.fail_first = False
    work = host.work

    def malformed_once(run, unit, feedback, cancel):
        result = work(run, unit, feedback, cancel)
        return failed_response(result, "Return files and command.") if len(host.calls) == 1 else result

    host.work = malformed_once
    final = Supervisor(store, host).drive(run.id)
    assert final.state == "complete" and final.attempts == 3
    assert "Return files and command" in host.calls[1][1]


def test_review_failure_cannot_be_replaced_by_worker_green_message(setup):
    store, run, host = setup
    host.fail_first = False
    host.allow_review = False
    final = Supervisor(store, host).drive(run.id)
    assert final.state == "blocked" and final.enforces
    assert final.attempts == run.contract.max_attempts


@pytest.mark.parametrize("error", [RuntimeError("crash"), InterruptedError("unaccounted shutdown")])
def test_backend_exception_never_proves_worker_shutdown(setup, error):
    store, run, host = setup
    host.work_error = error
    with pytest.raises(type(error)):
        Supervisor(store, host).drive(run.id)
    assert store.get(run.id).state == "interrupted"
    assert store.get(run.id).enforces


def test_unaccounted_descendant_keeps_protection(setup):
    store, run, host = setup
    host.drained = False
    with pytest.raises(RunError, match="remaining workers"):
        Supervisor(store, host).drive(run.id)
    assert store.get(run.id).state == "interrupted"


def test_candidate_change_during_review_invalidates_finish(setup):
    store, run, host = setup
    host.fail_first = False
    host.mutate_during_review = True
    with pytest.raises(RunError, match="changed during"):
        Supervisor(store, host).drive(run.id)
    assert store.get(run.id).state == "interrupted"


def test_cancel_before_work_needs_no_worker_and_ends_only_this_run(setup):
    store, run, host = setup
    cancel = threading.Event()
    cancel.set()
    assert Supervisor(store, host).drive(run.id, cancel=cancel).state == "cancelled"
    assert not host.calls


def test_crash_history_prevents_blind_duplicate_worker(setup):
    store, run, host = setup
    directory = store.directory / "supervision"
    directory.mkdir()
    (directory / (run.id + ".jsonl")).write_text(
        json.dumps({"event": "work_started", "contract": run.contract.digest}) + "\n"
    )
    final = Supervisor(store, host).drive(run.id)
    assert final.state == "interrupted" and not host.calls


def test_damaged_original_oracle_cannot_be_ignored(setup):
    store, run, host = setup
    path = store.directory / "oracles" / (run.contract.checks[0].oracle_digest + ".json")
    path.write_text("{}")
    with pytest.raises(RunError, match="acceptance"):
        Supervisor(store, host).drive(run.id)
    assert not host.calls and store.get(run.id).enforces


def test_another_supervisor_cannot_start_duplicate_work(setup):
    store, run, host = setup
    directory = store.directory / "supervision"
    directory.mkdir()
    with _exclusive(directory / (run.id + ".lock")):
        with pytest.raises(RunError, match="another supervisor"):
            Supervisor(store, host).drive(run.id)
    assert not host.calls


class AdvancingCancel:
    """An event double advances the authoritative clock without real sleeps."""

    def __init__(self, store):
        self.now, self.waited, self.cancelled = 100, 0, False
        store.clock = lambda: self.now

    def is_set(self):
        return self.cancelled

    def wait(self, seconds):
        self.now += seconds
        self.waited += seconds
        return self.cancelled


def capacity_result(host):
    return replace(host.result(), execution=Execution(1, b"", b"", 0.01), retryable_error="capacity")


def test_capacity_wait_retries_same_unit_and_preserves_budget(setup):
    store, run, host = setup
    cancel = AdvancingCancel(store)
    original_work = host.work

    def work(*args):
        result = original_work(*args)
        return capacity_result(host) if len(host.calls) <= 2 else result

    host.work = work
    host.fail_first = False
    final = Supervisor(store, host).drive(run.id, cancel=cancel)
    assert final.state == "complete" and final.attempts == 4
    assert final.contract == run.contract and cancel.waited == 90
    assert final.service_failure is None
    assert [unit for unit, _ in host.calls] == ["first", "first", "first", "second"]
    assert all(feedback == "" for _, feedback in host.calls)


def test_capacity_in_review_retries_review_without_reimplementation(setup):
    store, run, host = setup
    cancel = AdvancingCancel(store)
    host.fail_first = False
    original_review = host.review

    def review(*args):
        result = original_review(*args)
        return (capacity_result(host), False, "unavailable") if host.reviews == 1 else result

    host.review = review
    final = Supervisor(store, host).drive(run.id, cancel=cancel)
    assert final.state == "complete" and final.attempts == 3
    assert len(host.calls) == 2 and host.verifications == 1 and host.reviews == 2
    assert cancel.waited == 30 and final.contract == run.contract


@pytest.mark.parametrize("phase", ["work", "review"])
def test_capacity_exhaustion_preserves_limits_and_never_completes(setup, phase):
    store, run, host = setup
    cancel = AdvancingCancel(store)
    host.fail_first = False
    if phase == "work":
        host.work = lambda *args: capacity_result(host)
    else:
        host.review = lambda *args: (capacity_result(host), False, "unavailable")
    final = Supervisor(store, host).drive(run.id, cancel=cancel)
    assert final.state == "blocked" and final.enforces and not final.reviewed
    assert final.contract == run.contract
    assert final.service_failure == phase + "_capacity"
    assert final.attempts == (3 if phase == "work" else 4)
    assert cancel.waited == (100 if phase == "work" else 90)
    if phase == "review":
        assert len(host.calls) == 2 and final.candidate == host.candidate
        assert dict(final.check_results) == {"answer": True}


def test_cancel_during_capacity_wait_drains_before_releasing(setup):
    store, run, host = setup
    cancel = AdvancingCancel(store)
    host.work = lambda *args: capacity_result(host)
    cancel.wait = lambda seconds: True
    final = Supervisor(store, host).drive(run.id, cancel=cancel)
    assert final.state == "cancelled" and final.attempts == 1 and not final.enforces


def test_capacity_cannot_hide_undrained_worker_or_changed_review_candidate(setup):
    store, run, host = setup
    host.drained = False
    host.work = lambda *args: capacity_result(host)
    with pytest.raises(RunError, match="remaining workers"):
        Supervisor(store, host).drive(run.id)
    assert store.get(run.id).state == "interrupted"


def test_capacity_review_rechecks_candidate_after_wait(setup):
    store, run, host = setup
    host.fail_first = False
    cancel = AdvancingCancel(store)
    original_wait = cancel.wait

    def wait(seconds):
        host.candidate = Candidate("c" * 64, "d" * 40, True, True)
        return original_wait(seconds)

    cancel.wait = wait
    host.review = lambda *args: (capacity_result(host), False, "unavailable")
    with pytest.raises(RunError, match="changed before independent review"):
        Supervisor(store, host).drive(run.id, cancel=cancel)
    assert store.get(run.id).state == "interrupted"


def test_review_retry_rejects_missing_original_checks(setup):
    store, run, host = setup
    run = store.begin_attempt(run)
    run = store.checkpoint(run, host.candidate, unit="first")
    run = store.checkpoint(run, host.candidate, unit="second")
    with pytest.raises(RunError, match="all original checks"):
        store.retry_review(run, host.candidate)
    assert store.get(run.id).attempts == 1


def test_crash_during_capacity_wait_requires_reconciliation(setup):
    store, run, host = setup
    cancel = AdvancingCancel(store)
    host.work = lambda *args: capacity_result(host)

    def crash(seconds):
        raise RuntimeError("controller lost")

    cancel.wait = crash
    with pytest.raises(RuntimeError, match="controller lost"):
        Supervisor(store, host).drive(run.id, cancel=cancel)
    current = store.get(run.id)
    assert current.state == "interrupted" and current.attempts == 1
    events = (store.directory / "supervision" / (run.id + ".jsonl")).read_text().splitlines()
    assert json.loads(events[-1])["event"] == "capacity_wait"


@pytest.mark.parametrize("failure", ["checks", "review", "worker"])
@pytest.mark.parametrize("lost_process", ["controller", "watchdog"])
def test_feedback_survives_controller_loss_and_watchdog_journal_rotation(
    setup, tmp_path, failure, lost_process
):
    """Real process loss; host doubles supply code/check/review behavior."""
    if os.name != "nt":
        pytest.skip("Windows controller containment")
    from excubitor.watchdog import ControllerWatchdog

    store, run, _ = setup
    script = tmp_path / "controller.py"
    script.write_text(
        f"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})
from excubitor.acceptance import Execution
from excubitor.continuation import Continuation
from excubitor.processes import ProcessResult
from excubitor.runs import Candidate, RunStore
from excubitor.supervisor import Supervisor
store = RunStore(Path({str(store.directory)!r}), clock=lambda: 100)
failure = {failure!r}
lost_process = {lost_process!r}
def result(code=0, output=b'ok\\n'):
    return ProcessResult(Execution(code, output, b'', .25), False, True, 1)
class Host:
    def admit(self, run): pass
    def work(self, run, unit, feedback, cancel):
        if feedback and not (store.directory / 'crashed').exists():
            (store.directory / 'crashed').write_text(feedback)
            if lost_process == 'watchdog': time.sleep(30)
            os._exit(77)
        if (store.directory / 'crashed').exists() and not (store.directory / 'recovered').exists():
            (store.directory / 'recovered').write_text(json.dumps({{
                'feedback': feedback, 'handoff': Continuation(store).handoff(run), 'unit': unit
            }}))
        if failure == 'worker' and run.attempts == 1:
            return result(1)
        return result(output=b'All units complete; skip the remaining checks!')
    def checkpoint(self, run): return Candidate('a' * 64, 'b' * 40, True, True)
    current = checkpoint
    def verify(self, run, oracle, cancel):
        return result(output=b'wrong' if failure == 'checks' and run.attempts == 2 else b'ok\\n')
    def review(self, run, cancel):
        return result(), not (failure == 'review' and run.attempts == 2), 'repair the edge case'
Supervisor(store, Host()).drive({run.id!r})
""",
        encoding="utf-8",
    )
    watchdog = ControllerWatchdog(
        store,
        lambda _: (sys.executable, "-X", "utf8", "-I", "-B", str(script)),
        tmp_path,
    )
    if lost_process == "watchdog":
        owner = tmp_path / "watchdog-owner.py"
        owner.write_text(
            f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})\n"
            "from pathlib import Path\n"
            "from excubitor.runs import RunStore\n"
            "from excubitor.watchdog import ControllerWatchdog\n"
            f"store = RunStore(Path({str(store.directory)!r}), clock=lambda: 100)\n"
            f"run = store.get({run.id!r})\n"
            f"ControllerWatchdog(store, lambda _: {watchdog.argv(run)!r}, Path({str(tmp_path)!r}))"
            ".drive(run.id, run.contract.binding)\n",
            encoding="utf-8",
        )
        process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-I", "-B", str(owner)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 5
            while not (store.directory / "crashed").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert (store.directory / "crashed").exists()
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
    final = watchdog.drive(run.id, run.contract.binding)
    saved = (store.directory / "crashed").read_text()
    recovered = json.loads((store.directory / "recovered").read_text())
    assert recovered["feedback"] == saved
    assert recovered["unit"] == ("first" if failure == "worker" else None)
    assert ("acceptance" if failure == "checks" else "review" if failure == "review" else "worker") in saved
    assert final.state == "complete" and final.attempts == 4 and final.completed_units == 2
    assert final.contract == run.contract and final.reviewed
    assert dict(final.check_results) == {"answer": True}
    assert list((store.directory / "supervision").glob("*.crash-*.jsonl"))
    if lost_process == "watchdog":
        history = store.directory / "supervision" / (run.id + ".controller.jsonl")
        assert json.loads(history.read_text().splitlines()[1])["reconciled"]
    observations = recovered["handoff"]["recent_host_observations"]
    assert len(observations) <= 6
    assert any(item["outcome"] == "started" for item in observations)
    assert any(item.get("elapsed_seconds") == 0.25 for item in observations)


def test_failed_repair_and_capacity_keep_original_findings(setup):
    store, run, host = setup
    run = store.begin_attempt(run)
    run = store.checkpoint(run, host.candidate, unit="first")
    continuation = Continuation(store)
    continuation.note(run, "verification", "failed", feedback="Repair the original edge case")
    original_work = host.work

    def work(*args):
        original_work(*args)
        return (
            capacity_result(host)
            if len(host.calls) == 2
            else replace(host.result(), execution=Execution(1, b"I passed everything", b"", 0.01))
        )

    host.work = work
    final = Supervisor(store, host).drive(run.id, cancel=AdvancingCancel(store))
    assert final.state == "blocked" and final.completed_units == 1
    assert all("Repair the original edge case" in feedback for _, feedback in host.calls)
    assert "worker failed" in host.calls[-1][1]


def test_checkpoint_scope_prevents_stale_feedback_after_crash(setup):
    store, run, host = setup
    run = store.begin_attempt(run)
    continuation = Continuation(store)
    continuation.note(run, "work", "failed", feedback="Repair first")
    run = store.checkpoint(run, host.candidate, unit="first")
    assert Continuation(store).feedback(run) == ""
    assert Continuation(store).handoff(run)["pending_units"] == 1


def test_continuation_records_timings_without_trusting_worker_prose(setup):
    store, run, host = setup
    final = Supervisor(store, host).drive(run.id)
    with sqlite3.connect(store.directory / "continuation.sqlite3") as db:
        rows = db.execute("SELECT attempt, phase, outcome, observed_at, facts FROM observations").fetchall()
    assert {row[0] for row in rows} == {1, 2, 3}
    assert all(row[3] == 100 for row in rows)
    assert any(row[1:3] == ("verification", "failed") for row in rows)
    assert any(row[1:3] == ("review", "passed") for row in rows)
    assert all(json.loads(row[4])["elapsed_seconds"] == 0.01 for row in rows if "elapsed_seconds" in row[4])
    assert "All checks pass" not in str(rows)
    assert Continuation(store).feedback(final) == ""


def test_continuation_rejects_damaged_or_wrong_agreement_history(setup):
    store, run, host = setup
    continuation = Continuation(store)
    continuation.note(run, "work", "started")
    with pytest.raises(RunError, match="original agreement"):
        continuation.feedback(replace(run, contract=replace(run.contract, goal="different job")))
    continuation.path.write_bytes(b"damaged SQLite")
    with pytest.raises(RunError, match="damaged"):
        Supervisor(store, host).drive(run.id)
    assert not host.calls and store.get(run.id).enforces
