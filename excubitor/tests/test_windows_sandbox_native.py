"""Opt-in native allow/deny witnesses using an explicitly provisioned disposable identity."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.runs import RunError
from excubitor.windows_jobs import api, create_job
from excubitor.windows_sandbox import WindowsSandboxExecutor, _owner_sid, _secure

pytestmark = pytest.mark.skipif(
    os.name != "nt" or not os.environ.get("EXCUBITOR_WINDOWS_NATIVE_ROOT"),
    reason="requires a separately provisioned disposable native Windows identity",
)


@pytest.fixture(scope="module")
def worker():
    return WindowsSandboxExecutor(
        os.environ["EXCUBITOR_WINDOWS_NATIVE_NAME"], Path(os.environ["EXCUBITOR_WINDOWS_NATIVE_ROOT"])
    )


def execute(worker, source, *, sandbox="workspace-write", **kwargs):
    return worker.run(
        (str(worker.tools / "python.exe"), "-I", "-B", "-c", source),
        worker.candidate,
        sandbox=sandbox,
        **kwargs,
    )


def result_json(worker, source, **kwargs):
    result = execute(worker, source, **kwargs)
    assert result.execution.exit_code == 0 and result.drained, result
    return json.loads(result.execution.stdout)


def test_native_token_and_delayed_ctypes_initialization(worker, tmp_path):
    package_shared = tmp_path / "package-shared"
    package_shared.write_text("shared with ordinary AppContainers", encoding="utf8")
    _secure(package_shared, _owner_sid(), "S-1-15-2-1")
    source = """
import time
time.sleep(.1)
import ctypes as c, json
from ctypes import wintypes as w
k=c.WinDLL('kernel32',use_last_error=True); a=c.WinDLL('advapi32',use_last_error=True)
k.GetCurrentProcess.restype=w.HANDLE
a.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,c.c_void_p]
a.GetTokenInformation.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.c_void_p]
k.CloseHandle.argtypes=[w.HANDLE]
t=w.HANDLE(); assert a.OpenProcessToken(k.GetCurrentProcess(),8,c.byref(t))
out={}
for label, info in [('appcontainer',29)]:
 value=w.DWORD(); size=w.DWORD()
 assert a.GetTokenInformation(t,info,c.byref(value),c.sizeof(value),c.byref(size)),(label,c.get_last_error())
 out[label]=value.value
k.CloseHandle(t)
print(json.dumps(out))
"""
    assert result_json(worker, source) == {"appcontainer": 1}
    source = f"""
import json
try:
 with open({str(package_shared)!r}):pass
 out='allowed'
except PermissionError:out='denied'
print(json.dumps(out))
"""
    assert result_json(worker, source) == "denied"


def test_private_desktop_stays_in_noninteractive_session(worker):
    source = """
import ctypes as c,json
from ctypes import wintypes as w
u=c.WinDLL('user32',use_last_error=True);k=c.WinDLL('kernel32')
u.GetThreadDesktop.argtypes=[w.DWORD];u.GetThreadDesktop.restype=w.HANDLE
u.GetUserObjectInformationW.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.c_void_p]
u.OpenDesktopW.argtypes=[w.LPCWSTR,w.DWORD,w.BOOL,w.DWORD];u.OpenDesktopW.restype=w.HANDLE
u.CloseDesktop.argtypes=[w.HANDLE]
u.SetThreadDesktop.argtypes=[w.HANDLE]
k.ProcessIdToSessionId.argtypes=[w.DWORD,c.c_void_p]
session=w.DWORD();assert k.ProcessIdToSessionId(k.GetCurrentProcessId(),c.byref(session))
name=c.create_unicode_buffer(256);size=w.DWORD()
desktop=u.GetThreadDesktop(k.GetCurrentThreadId())
assert u.GetUserObjectInformationW(desktop,2,name,c.sizeof(name),c.byref(size))
out={'name':name.value,'session':session.value}
for label, desktop, rights in [('switch',name.value,0x100)]:
 c.set_last_error(0);handle=u.OpenDesktopW(desktop,0,False,rights)
 out[label]=[bool(handle),c.get_last_error()]
 if handle:
  c.set_last_error(0);out[label+'_attach']=[bool(u.SetThreadDesktop(handle)),c.get_last_error()]
  u.CloseDesktop(handle)
print(json.dumps(out))
"""
    data = result_json(worker, source)
    assert data["name"].startswith("Excubitor.Worker.")
    assert data["switch"] == [False, 5], data
    assert data["session"] == 0, data


def test_writer_can_create_edit_rename_and_delete(worker):
    name = "writable-" + uuid.uuid4().hex
    source = f"""
from pathlib import Path
import json
p=Path({name!r});p.mkdir(); f=p/'first';f.write_text('one'); f.write_text('two')
f.rename(p/'second'); assert (p/'second').read_text()=='two'
(p/'second').unlink(); p.rmdir(); print(json.dumps(True))
"""
    assert result_json(worker, source) is True


def test_review_denies_write_delete_rename_and_permission_rewrite(worker):
    target = worker.candidate / ("readonly-" + uuid.uuid4().hex)
    target.write_text("original", encoding="utf8")
    source = f"""
from pathlib import Path
import ctypes as c,json
from ctypes import wintypes as w
p=Path({str(target)!r});out={{'read':p.read_text()}}
for label,action in [('write',lambda:p.write_text('bad')),('delete',p.unlink),
                     ('rename',lambda:p.rename(p.with_suffix('.renamed')))]:
 try:action();out[label]='allowed'
 except PermissionError:out[label]='denied'
a=c.WinDLL('advapi32',use_last_error=True);k=c.WinDLL('kernel32')
a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,c.c_void_p,c.c_void_p]
a.SetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,c.c_void_p]
k.LocalFree.argtypes=[c.c_void_p]
sd=c.c_void_p()
assert a.ConvertStringSecurityDescriptorToSecurityDescriptorW('D:(A;;FA;;;WD)',1,c.byref(sd),None)
c.set_last_error(0);changed=a.SetFileSecurityW(str(p),4,sd)
out['permissions']=[bool(changed),c.get_last_error()];k.LocalFree(sd)
print(json.dumps(out))
"""
    data = result_json(worker, source, sandbox="read-only")
    assert data == {
        "read": "original",
        "write": "denied",
        "delete": "denied",
        "rename": "denied",
        "permissions": [False, 5],
    }, data
    assert target.read_text(encoding="utf8") == "original"


def test_private_canary_and_windows_profile_writes_are_denied(worker, tmp_path):
    canary = tmp_path / "private"
    canary.write_text("host secret canary", encoding="utf8")
    profile_target = worker.profile / ("denied-" + uuid.uuid4().hex)
    source = f"""
from pathlib import Path
import json
out=[]
for p,mode in [({str(canary)!r},'r'),({str(canary)!r},'w'),({str(profile_target)!r},'w')]:
 try:
  with open(p,mode):pass
  out.append('allowed')
 except PermissionError:out.append('denied')
print(json.dumps(out))
"""
    assert result_json(worker, source) == ["denied"] * 3
    assert not profile_target.exists()
    assert canary.read_text(encoding="utf8") == "host secret canary"


def test_network_has_an_outside_baseline_and_os_denial(worker):
    with socket.create_connection(("1.1.1.1", 443), timeout=5):
        pass
    source = """
import socket,json
try:
 socket.create_connection(('1.1.1.1',443),timeout=2);out=['allowed']
except OSError as e:out=[e.errno,e.winerror]
print(json.dumps(out))
"""
    assert result_json(worker, source) == [13, 10013]


def test_fresh_temporary_directory_works_and_previous_one_is_revoked(worker):
    first = result_json(
        worker,
        """
import tempfile,json
from pathlib import Path
p=Path(tempfile.mkdtemp())/'sample';p.write_text('temporary');print(json.dumps(str(p)))
""",
        sandbox="read-only",
    )
    assert Path(first).is_relative_to(worker.root)
    source = f"""
from pathlib import Path
import json
try:Path({first!r}).read_text();out='allowed'
except PermissionError:out='denied'
print(json.dumps(out))
"""
    assert result_json(worker, source, sandbox="read-only") == "denied"


def test_worker_cannot_keep_the_host_job_alive(worker):
    name = "Global\\Excubitor.Run." + uuid.uuid4().hex
    kernel, _ = api()
    handle = create_job(name)
    source = f"""
import ctypes as c,json
from ctypes import wintypes as w
k=c.WinDLL('kernel32',use_last_error=True)
k.OpenJobObjectW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR];k.OpenJobObjectW.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE];out=[]
for rights in [4,8,2,0x20000,0x1f003f]:
 c.set_last_error(0);handle=k.OpenJobObjectW(rights,False,{name!r})
 out.append([bool(handle),c.get_last_error()])
 if handle:k.CloseHandle(handle)
print(json.dumps(out))
"""
    try:
        assert result_json(worker, source) == [[False, 5]] * 5
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.parametrize("stop", ["deadline", "cancel"])
def test_detached_children_are_drained(worker, stop):
    late = worker.candidate / ("late-" + uuid.uuid4().hex)
    child = f"import time;from pathlib import Path;time.sleep(1);Path({str(late)!r}).write_text('orphan')"
    source = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable,'-I','-B','-c',{child!r}],creationflags=8);"
        "time.sleep(30)"
    )
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    if stop == "cancel":
        timer.start()
    try:
        result = execute(worker, source, timeout=0.3 if stop == "deadline" else 5, cancelled=cancel)
    finally:
        if stop == "cancel":
            timer.join()
    assert result.drained and result.processes >= 2
    assert result.cancelled if stop == "cancel" else result.execution.timed_out
    time.sleep(1.1)
    assert not late.exists()


def test_output_flood_is_bounded(worker):
    result = execute(worker, "import os\nwhile True:os.write(1,b'x'*65536)", output_limit=4096)
    assert result.drained and result.execution.output_limited
    assert len(result.execution.stdout) + len(result.execution.stderr) <= 4096


def test_memory_bound_is_applied_to_the_actual_sandbox(worker):
    source = """
import json
try:x=bytearray(1024**3);out='allocated'
except MemoryError:out='limited'
print(json.dumps(out))
"""
    assert result_json(worker, source) == "limited"


def test_hostile_requests_do_not_dispatch(worker, tmp_path):
    argv = (str(worker.tools / "python.exe"), "-I", "-B", "-c", "raise SystemExit(99)")
    for cwd, mode, env in [
        (tmp_path, "workspace-write", None),
        (worker.candidate, "unknown", None),
        (worker.candidate, "read-only", {"EXAMPLE_TOKEN": "rejected"}),
    ]:
        with pytest.raises(RunError):
            worker.run(argv, cwd, sandbox=mode, env=env)


def test_controller_death_drains_native_worker(worker, tmp_path):
    ready = worker.candidate / ("ready-" + uuid.uuid4().hex)
    late = worker.candidate / ("late-" + uuid.uuid4().hex)
    body = (
        f"from pathlib import Path;import time;Path({str(ready)!r}).write_text('ready');"
        f"time.sleep(2);Path({str(late)!r}).write_text('orphan')"
    )
    source = f"""
import sys
from pathlib import Path
sys.path.insert(0,{str(Path(__file__).resolve().parents[2])!r})
from excubitor.windows_sandbox import WindowsSandboxExecutor
w=WindowsSandboxExecutor({worker.name!r},Path({str(worker.root)!r}))
w.run(({str(worker.tools / "python.exe")!r},'-I','-B','-c',{body!r}),w.candidate,sandbox='workspace-write')
"""
    owner = subprocess.Popen(
        [sys._base_executable, "-I", "-B", "-c", source],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 8
        while not ready.exists() and owner.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), owner.communicate(timeout=2) if owner.poll() is not None else "not ready"
        owner.kill()
        owner.communicate(timeout=5)
        time.sleep(2.1)
        assert not late.exists()
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=5)
