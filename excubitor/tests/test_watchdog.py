"""Real Windows controller crashes; native sandbox admission is tested separately."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import OutputOracle
from excubitor.runs import Binding, Contract, RunError, RunStore
from excubitor.watchdog import ControllerWatchdog

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows controller containment")
ROOT = str(Path(__file__).resolve().parents[2])


def fixture(tmp_path, *, mode="crash", attempts=4):
    project = tmp_path / "project"
    project.mkdir()
    store = RunStore(tmp_path / "authority", create=True)
    oracle = OutputOracle("answer", (sys.executable,), "", "ok\n")
    oracle.save(store)
    run = store.start(
        Contract(
            Binding("fixture", "owner-task", str(project)),
            "test recovery",
            ("first", "second"),
            (oracle.check,),
            attempts,
            int(time.time()) + 20,
        ),
        "explicit-fixture",
    )
    source = f"""
import os, sys, subprocess, time
from pathlib import Path
sys.path.insert(0, {ROOT!r})
from excubitor.runs import RunStore, Candidate
from excubitor.supervisor import Supervisor
from excubitor.processes import ProcessResult
from excubitor.acceptance import Execution
store = RunStore(Path({str(store.directory)!r}))
project = Path({str(project)!r})
mode = {mode!r}
class Host:
    def admit(self, run): pass
    def result(self): return ProcessResult(Execution(0,b'ok\\n',b'',.01),False,True,1)
    def work(self, run, unit, feedback, cancel):
        (project / 'controller-pid').write_text(str(os.getpid()))
        with (project / 'attempts').open('a') as stream: stream.write(str(run.attempts)+'\\n')
        if mode == 'always' or (run.attempts == 1 and mode in ('crash','torn')):
            child = ("from pathlib import Path; import time; time.sleep(.6); Path("
                     +repr(str(project/'orphan'))+").write_text('bad')")
            subprocess.Popen([sys.executable,'-I','-B','-c',child])
            if mode == 'torn':
                with (store.directory/'supervision'/({run.id!r}+'.jsonl')).open('ab') as stream:
                    stream.write(b'{{"event":'); stream.flush(); os.fsync(stream.fileno())
            os._exit(77)
        if mode == 'handled': raise RuntimeError('native admission denied')
        if mode == 'hang': time.sleep(30)
        return self.result()
    def checkpoint(self, run): return Candidate('a'*64,'b'*40,True,True)
    current = checkpoint
    def verify(self, run, oracle, cancel): return self.result()
    def review(self, run, cancel): return self.result(),True,'independent fixture review'
try:
    Supervisor(store,Host()).drive({run.id!r})
except Exception:
    # A handled admission/backend failure is reported and must not be retried.
    pass
"""
    script = tmp_path / "controller.py"
    script.write_text(source, encoding="utf-8")
    watchdog = ControllerWatchdog(store, lambda _: (sys.executable, "-I", "-B", str(script)), tmp_path)
    return store, run, watchdog, project


@pytest.mark.parametrize("mode", ["crash", "torn"])
def test_crashed_controller_and_child_drained_before_automatic_repair(tmp_path, mode):
    store, run, watchdog, project = fixture(tmp_path, mode=mode)
    final = watchdog.drive(run.id, run.contract.binding)
    assert final.state == "complete" and final.attempts == 3
    assert final.contract == run.contract and final.completed_units == 2
    assert final.reviewed and all(value for _, value in final.check_results)
    assert (project / "attempts").read_text().splitlines() == ["1", "2", "3"]
    archives = list((store.directory / "supervision").glob("*.crash-*.jsonl"))
    assert len(archives) == 1
    if mode == "torn":
        assert archives[0].read_bytes().endswith(b'{"event":')
    receipts = [
        json.loads(line)
        for line in (store.directory / "supervision" / (run.id + ".controller.jsonl"))
        .read_text()
        .splitlines()
    ]
    assert receipts[1]["event"] == "drained" and receipts[1]["processes"] >= 2
    time.sleep(0.7)
    assert not (project / "orphan").exists()
    assert store.lookup(run.contract.binding) is None


def test_crashes_cannot_extend_original_attempt_budget(tmp_path):
    store, run, watchdog, project = fixture(tmp_path, mode="always", attempts=2)
    final = watchdog.drive(run.id, run.contract.binding)
    assert final.state == "blocked" and final.attempts == 2
    assert final.contract == run.contract and final.enforces
    assert (project / "attempts").read_text().splitlines() == ["1", "2"]


def test_handled_native_denial_is_not_retried(tmp_path):
    store, run, watchdog, project = fixture(tmp_path, mode="handled")
    final = watchdog.drive(run.id, run.contract.binding)
    assert final.state == "interrupted" and final.attempts == 1
    assert (project / "attempts").read_text().splitlines() == ["1"]


def test_uncertain_watchdog_history_and_other_task_cannot_restart(tmp_path):
    store, run, watchdog, project = fixture(tmp_path)
    with pytest.raises(RunError, match="original native task"):
        watchdog.drive(run.id, Binding("fixture", "unrelated-task", str(project)))
    directory = store.directory / "supervision"
    directory.mkdir(exist_ok=True)
    history = directory / (run.id + ".controller.jsonl")
    history.write_bytes(b'{"event":"launched"')
    with pytest.raises(RunError, match="history already exists"):
        watchdog.drive(run.id, run.contract.binding)
    assert not (project / "attempts").exists() and store.get(run.id).enforces


def test_owner_cancellation_drains_controller_before_release(tmp_path):
    store, run, watchdog, project = fixture(tmp_path, mode="hang")
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    try:
        final = watchdog.drive(run.id, run.contract.binding, cancel=cancel)
        assert final.state == "cancelled" and store.lookup(run.contract.binding) is None
    finally:
        timer.join()


def test_original_deadline_prevents_crash_restart(tmp_path):
    store, run, watchdog, project = fixture(tmp_path)
    store.clock = lambda: run.contract.deadline if (project / "attempts").exists() else time.time()
    final = watchdog.drive(run.id, run.contract.binding)
    assert final.state == "blocked" and final.attempts == 1
    assert final.contract == run.contract


def test_watchdog_death_leaves_fence_and_kills_controller(tmp_path):
    import _winapi

    store, run, watchdog, project = fixture(tmp_path, mode="hang")
    owner = tmp_path / "watchdog-owner.py"
    owner.write_text(
        f"import sys; sys.path.insert(0,{ROOT!r})\n"
        "from pathlib import Path\n"
        "from excubitor.runs import RunStore\n"
        "from excubitor.watchdog import ControllerWatchdog\n"
        f"store=RunStore(Path({str(store.directory)!r}))\n"
        f"run=store.get({run.id!r})\n"
        f"ControllerWatchdog(store,lambda _: {watchdog.argv(run)!r},Path({str(tmp_path)!r}))"
        ".drive(run.id,run.contract.binding)\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", str(owner)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    handle = None
    try:
        deadline = time.monotonic() + 5
        marker = project / "controller-pid"
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        handle = _winapi.OpenProcess(0x100000, False, int(marker.read_text()))
        process.kill()
        process.communicate(timeout=5)
        assert _winapi.WaitForSingleObject(handle, 5000) == 0
        with pytest.raises(RunError, match="history already exists"):
            watchdog.drive(run.id, run.contract.binding)
        assert store.get(run.id).enforces
        assert (project / "attempts").read_text().splitlines() == ["1"]
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        if handle is not None:
            _winapi.CloseHandle(handle)
