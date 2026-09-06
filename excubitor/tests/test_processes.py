"""Live local process-tree tests; not vendor sandbox admission."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.processes import WindowsProcessTree

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows process backend")


def command(source):
    return (sys.executable, "-I", "-B", "-c", source)


def test_captures_actual_bytes_and_drains(tmp_path):
    result = WindowsProcessTree().run(
        command("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"),
        tmp_path,
        stdin=b"exact\x00bytes\n",
    )
    assert result.execution.stdout == b"exact\x00bytes\n"
    assert result.execution.exit_code == 0 and result.drained
    assert not result.execution.timed_out and result.observed_pids


def test_explicit_environment_does_not_inherit_removed_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("EXCUBITOR_TEST_PARENT_ONLY", "parent")
    env = dict(os.environ)
    del env["EXCUBITOR_TEST_PARENT_ONLY"]
    env["EXCUBITOR_TEST_CHILD_ONLY"] = "child"
    result = WindowsProcessTree().run(
        command(
            "import os; print(os.getenv('EXCUBITOR_TEST_PARENT_ONLY')); "
            "print(os.getenv('EXCUBITOR_TEST_CHILD_ONLY'))"
        ),
        tmp_path,
        env=env,
    )
    assert result.drained and result.execution.stdout.splitlines() == [b"None", b"child"]


def test_parent_exit_does_not_hide_child(tmp_path):
    child = "import time; time.sleep(.25); print('child finished')"
    source = f"import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c',{child!r}])"
    result = WindowsProcessTree().run(command(source), tmp_path)
    assert result.execution.elapsed_seconds >= 0.25
    assert b"child finished" in result.execution.stdout
    assert result.drained and result.processes >= 2


def test_timeout_kills_lingering_descendant(tmp_path):
    child = "import time; time.sleep(30)"
    source = f"import subprocess,sys; subprocess.Popen([sys.executable,'-I','-B','-c',{child!r}])"
    result = WindowsProcessTree().run(command(source), tmp_path, timeout=0.2)
    assert result.execution.timed_out and result.drained
    assert result.execution.elapsed_seconds < 5


def test_output_flood_is_bounded(tmp_path):
    result = WindowsProcessTree().run(
        command("import os\nwhile True: os.write(1,b'x'*65536)"), tmp_path, output_limit=4096
    )
    assert result.execution.output_limited and result.drained
    assert len(result.execution.stdout) + len(result.execution.stderr) <= 4096


def test_cancellation_drains_tree(tmp_path):
    cancel = threading.Event()
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    try:
        result = WindowsProcessTree().run(command("import time; time.sleep(30)"), tmp_path, cancelled=cancel)
        assert result.cancelled and result.drained
    finally:
        timer.join()


def test_controller_death_kills_its_child(tmp_path):
    ready, late = tmp_path / "ready", tmp_path / "late"
    child = (
        f"from pathlib import Path; import os,time; Path({str(ready)!r}).write_text(str(os.getpid())); "
        f"time.sleep(2); Path({str(late)!r}).write_text('orphan')"
    )
    owner = (
        f"import sys; sys.path.insert(0,{str(Path(__file__).resolve().parents[2])!r}); "
        "from pathlib import Path; from excubitor.processes import WindowsProcessTree; "
        f"WindowsProcessTree().run({command(child)!r},Path({str(tmp_path)!r}))"
    )
    process = subprocess.Popen(command(owner), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), process.poll()
        process.kill()
        process.communicate(timeout=5)
        time.sleep(2.2)
        assert not late.exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_breakaway_request_cannot_escape_supervisor_job(tmp_path):
    child = "import os,json,time; print(json.dumps({'pid':os.getpid()}),flush=True); time.sleep(30)"
    source = (
        "import subprocess,sys,json\ntry:\n"
        f" subprocess.Popen([sys.executable,'-I','-B','-c',{child!r}],creationflags=0x01000000)\n"
        "except OSError:\n print(json.dumps({'denied':True}))\n"
    )
    result = WindowsProcessTree().run(command(source), tmp_path, timeout=0.8)
    observation = json.loads(result.execution.stdout)
    if observation != {"denied": True}:
        # Nested native jobs may accept the flag while retaining this ancestor
        # job. Verify actual membership and termination, not an assumed error.
        assert observation["pid"] in result.observed_pids
        assert result.execution.timed_out
    assert result.drained
