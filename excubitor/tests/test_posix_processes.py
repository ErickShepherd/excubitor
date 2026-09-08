"""Native cooperative POSIX lifetime evidence; never simulated Mac support."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from excubitor.posix_processes import PosixProcessTree
from excubitor.runs import Conflict, RunError
from excubitor.tests.test_watchdog import fixture, owner_script

pytestmark = pytest.mark.skipif(os.name != "posix", reason="native POSIX groups")
ROOT = str(Path(__file__).resolve().parents[2])


def command(source):
    return (sys.executable, "-I", "-B", "-c", source)


def wait_file(path):
    deadline = time.monotonic() + 10
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.exists(), "fixture did not reach the intended running state"


def test_bytes_stdin_and_environment_are_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("PARENT_ONLY", "secret")
    env = {k: v for k, v in os.environ.items() if k != "PARENT_ONLY"}
    data = b"exact\0bytes\n" * 8192
    result = PosixProcessTree().run(
        command(
            "import os,sys; assert 'PARENT_ONLY' not in os.environ; "
            "sys.stdout.buffer.write(sys.stdin.buffer.read())"
        ),
        tmp_path,
        stdin=data,
        env=env,
        timeout=15,
    )
    assert result.execution.stdout == data and result.execution.exit_code == 0
    assert result.drained and not result.execution.timed_out


@pytest.mark.parametrize("kind", ["timeout", "cancel", "output"])
def test_bounded_failures_drain(tmp_path, kind):
    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set)
    source = "import time; time.sleep(30)"
    if kind == "output":
        source = "import os\nwhile True: os.write(1,b'x'*65536); os.write(2,b'y'*65536)"
    if kind == "cancel":
        timer.start()
    try:
        result = PosixProcessTree().run(
            command(source),
            tmp_path,
            timeout=0.2 if kind == "timeout" else 10,
            cancelled=cancel,
            output_limit=4096,
        )
        assert result.drained
        assert result.execution.timed_out if kind == "timeout" else True
        assert result.cancelled if kind == "cancel" else True
        assert result.execution.output_limited if kind == "output" else True
        assert len(result.execution.stdout) + len(result.execution.stderr) <= 4096
    finally:
        if kind == "cancel":
            timer.join()


def test_root_exit_kills_even_descendant_that_closed_output(tmp_path):
    late = tmp_path / "late"
    child = f"import time; from pathlib import Path; time.sleep(1); Path({str(late)!r}).write_text('bad')"
    source = (
        "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c',"
        f"{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
    )
    result = PosixProcessTree().run(command(source), tmp_path)
    assert result.drained and result.execution.exit_code == 0
    time.sleep(1.1)
    assert not late.exists()


def test_nested_guardian_drain_precedes_outer_return_after_controller_crash(tmp_path):
    ready, late = tmp_path / "ready", tmp_path / "late"
    child = (
        f"from pathlib import Path; import time; Path({str(ready)!r}).touch(); "
        f"time.sleep(1); Path({str(late)!r}).write_text('bad')"
    )
    controller = f"""
import sys, threading, os, time
sys.path.insert(0, {ROOT!r})
from pathlib import Path
from excubitor.posix_processes import PosixProcessTree
threading.Thread(target=lambda: PosixProcessTree().run({command(child)!r},Path({str(tmp_path)!r}))).start()
while not Path({str(ready)!r}).exists(): time.sleep(.01)
os._exit(77)
"""
    result = PosixProcessTree().run(command(controller), tmp_path, timeout=15)
    assert result.execution.exit_code == 77 and result.drained
    time.sleep(1.1)
    assert not late.exists()


@pytest.mark.parametrize("mode", ["crash", "torn", "always"])
def test_controller_crash_retries_keep_original_agreement(tmp_path, mode):
    store, run, watchdog, project = fixture(tmp_path, mode=mode, attempts=2 if mode == "always" else 4)
    final = watchdog.drive(run.id, run.contract.binding)
    assert final.contract == run.contract
    assert final.state == ("blocked" if mode == "always" else "complete")
    assert final.attempts == (2 if mode == "always" else 3)
    time.sleep(0.7)
    assert not (project / "orphan").exists()


def test_owner_loss_is_cleaned_but_reconnect_refuses_uncertain_proof(tmp_path):
    store, run, watchdog, project = fixture(tmp_path, mode="hang")
    owner = owner_script(tmp_path, store, run, watchdog)
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", str(owner)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        wait_file(project / "controller-pid")
        with pytest.raises(Conflict, match="another supervisor"):
            watchdog.drive(run.id, run.contract.binding)
        process.kill()
        process.communicate(timeout=10)
        saved = store.get(run.id)
        for _ in range(2):
            with pytest.raises(RunError, match="ownership was lost"):
                watchdog.drive(run.id, run.contract.binding)
            assert store.get(run.id) == saved
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_active_and_saved_cancellation_preserve_limits(tmp_path):
    for saved in (False, True):
        location = tmp_path / str(saved)
        location.mkdir()
        store, run, watchdog, project = fixture(location, mode="hang")
        cancel = threading.Event()
        if saved:
            cancel.set()
        timer = threading.Timer(0.3, cancel.set)
        timer.start()
        try:
            final = watchdog.drive(run.id, run.contract.binding, cancel=cancel)
        finally:
            timer.join()
        assert final.state == "cancelled" and final.contract == run.contract
        assert store.lookup(run.contract.binding) is None
        assert watchdog.drive(run.id, run.contract.binding) == final


@pytest.mark.parametrize("corruption", ["torn", "schema", "launch", "proof"])
def test_malformed_history_never_signals_or_restarts(tmp_path, corruption, monkeypatch):
    store, run, watchdog, project = fixture(tmp_path, mode="handled")
    interrupted = watchdog.drive(run.id, run.contract.binding)
    history = store.directory / "supervision" / (run.id + ".controller.jsonl")
    events = [json.loads(line) for line in history.read_text().splitlines()]
    if corruption == "schema":
        events[0]["schema"] = 2
    elif corruption == "launch":
        events[0]["launch"] = True
    elif corruption == "proof":
        events[1]["reconciled"] = True
    raw = "".join(json.dumps(event) + "\n" for event in events)
    history.write_text(raw[:-2] if corruption == "torn" else raw)
    monkeypatch.setattr(os, "killpg", lambda *_: pytest.fail("must not signal from saved identity"))
    with pytest.raises(RunError, match="cannot prove safe recovery"):
        watchdog.drive(run.id, run.contract.binding)
    assert store.get(run.id) == interrupted


def test_group_escape_is_an_explicit_uncontained_limit(tmp_path):
    # Deliberately leave the cooperative contract with a bounded disposable
    # sentinel that exits by itself; never signal a PID read from a receipt.
    late = tmp_path / "escaped"
    child = f"import time; from pathlib import Path; time.sleep(.7); Path({str(late)!r}).touch()"
    source = (
        "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c',"
        f"{child!r}],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
    )
    result = PosixProcessTree().run(command(source), tmp_path)
    assert result.drained  # Within the declared cooperative group, only.
    wait_file(late)
