"""Live Windows ownership/atomic-spawn checks, separate from native admission."""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.processes import WindowsProcessTree
from excubitor.runs import RunError
from excubitor.windows_jobs import api, create_job, recover_job

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows kernel objects")
ROOT = str(Path(__file__).resolve().parents[2])


def name():
    return "Global\\Excubitor.Run." + uuid.uuid4().hex


def test_host_only_job_can_reopen_but_never_reuse_existing_object():
    target = name()
    kernel, _ = api()
    handle = create_job(target)
    try:
        # Some Windows builds request additional rights when reopening through
        # CreateJobObject, yielding access denied. Neither result permits reuse.
        with pytest.raises((RunError, PermissionError)):
            create_job(target)
        assert recover_job(target)["evidence"] == "kernel-object-drained"
    finally:
        kernel.CloseHandle(handle)
    assert recover_job(target)["evidence"] == "kernel-object-absent"


def test_changed_job_access_control_is_not_empty_evidence():
    target = name()
    kernel, _ = api()
    handle = kernel.CreateJobObjectW(None, target)
    assert handle
    try:
        with pytest.raises(RunError, match="ownership or access control changed"):
            recover_job(target)
    finally:
        kernel.CloseHandle(handle)


def test_suspended_root_is_already_owned_before_python_can_observe_it(tmp_path):
    import ctypes as c
    from ctypes import wintypes as w

    import excubitor.processes as processes

    kernel, _ = api()
    kernel.IsProcessInJob.argtypes = [w.HANDLE, w.HANDLE, c.c_void_p]
    kernel.IsProcessInJob.restype = w.BOOL
    original = processes.create_process_in_job
    observed = []

    def create(argv, cwd, env, handles, job, **kwargs):
        result = original(argv, cwd, env, handles, job, **kwargs)
        inside = w.BOOL()
        assert kernel.IsProcessInJob(result[0], job, c.byref(inside)) and inside.value
        observed.append(result[2])
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(processes, "create_process_in_job", create)
        result = WindowsProcessTree().run((sys.executable, "-I", "-B", "-c", "print('ok')"), tmp_path)
    assert result.drained and len(observed) == 1


def test_crash_immediately_after_atomic_create_leaves_no_suspended_orphan(tmp_path):
    import _winapi

    marker = tmp_path / "suspended-pid"
    owner = tmp_path / "crash-before-resume.py"
    source = f"""
import os,sys,time
from pathlib import Path
sys.path.insert(0,{ROOT!r})
import excubitor.processes as processes
original=processes.create_process_in_job
def create(*args, **kwargs):
    result=original(*args, **kwargs)
    Path({str(marker)!r}).write_text(str(result[2]))
    time.sleep(.3)
    os._exit(77)
processes.create_process_in_job=create
processes.WindowsProcessTree().run((sys.executable,'-I','-B','-c','import time; time.sleep(30)'),
                                   Path({str(tmp_path)!r}))
"""
    owner.write_text(source, encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", str(owner)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    handle = None
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        handle = _winapi.OpenProcess(0x100000, False, int(marker.read_text()))
        process.communicate(timeout=5)
        assert process.returncode == 77
        assert _winapi.WaitForSingleObject(handle, 5000) == 0
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        if handle is not None:
            _winapi.CloseHandle(handle)
