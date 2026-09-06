"""Orchestration invariants with host doubles; native evidence is separate."""

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import Execution, OutputOracle
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
