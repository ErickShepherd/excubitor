"""Preflight and OS resource-limit checks; authenticated LPAC admission is separate."""

import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.processes import WindowsProcessTree
from excubitor.runs import RunError
from excubitor.windows_jobs import require_background_session
from excubitor.windows_sandbox import _owner_sid, _secure, _tree, derive_sid, identity_name, profile_path


@pytest.mark.parametrize(
    "name", ["", "ordinary", "Excubitor.Worker.test", "Excubitor.Worker." + "A" * 32, None]
)
def test_refuses_unowned_identity_names(name):
    with pytest.raises(RunError):
        identity_name(name)


native = pytest.mark.skipif(os.name != "nt", reason="requires native Windows APIs")


@native
def test_interactive_session_cannot_admit_a_native_worker():
    import ctypes as c
    from ctypes import wintypes as w

    k = c.WinDLL("kernel32")
    k.ProcessIdToSessionId.argtypes = [w.DWORD, c.c_void_p]
    session = w.DWORD()
    assert k.ProcessIdToSessionId(os.getpid(), c.byref(session))
    if session.value == 0:
        pytest.skip("already in the noninteractive Windows session")
    with pytest.raises(RunError, match="session 0"):
        require_background_session()


@native
def test_derivation_does_not_register_a_profile():
    name = "Excubitor.Worker." + uuid.uuid4().hex
    sid = derive_sid(name)
    assert derive_sid(name) == sid and sid.startswith("S-1-15-2-")
    with pytest.raises(RunError):
        profile_path(name)
    assert not (Path(os.environ["LOCALAPPDATA"]) / "Packages" / name).exists()


@native
def test_host_retains_access_after_dedicated_acl_setup(tmp_path):
    sid = derive_sid("Excubitor.Worker." + uuid.uuid4().hex)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _secure(candidate, _owner_sid(), sid, writable=True, root=True)
    child = candidate / "example.txt"
    child.write_text("host can write", encoding="utf8")
    _secure(child, _owner_sid(), sid)
    child.write_text("host can still write", encoding="utf8")
    assert child.read_text(encoding="utf8") == "host can still write"


@native
def test_hardlink_is_refused_before_permission_changes(tmp_path):
    source, target = tmp_path / "outside", tmp_path / "candidate"
    source.write_text("canary", encoding="utf8")
    target.mkdir()
    os.link(source, target / "linked")
    with pytest.raises(RunError, match="hard link"):
        _tree(target)
    assert source.read_text(encoding="utf8") == "canary"


@native
def test_memory_limit_is_enforced_by_windows(tmp_path):
    source = "try:\n x=bytearray(256*1024**2)\nexcept MemoryError:\n print('limited')\n"
    result = WindowsProcessTree().run(
        (sys.executable, "-I", "-B", "-c", source),
        tmp_path,
        memory_bytes=128 * 1024**2,
    )
    assert result.execution.exit_code == 0
    assert result.execution.stdout.strip() == b"limited" and result.drained


@native
def test_process_limit_is_enforced_by_windows(tmp_path):
    source = (
        "import subprocess,sys\ntry:\n"
        " subprocess.Popen([sys.executable,'-I','-B','-c','print(123)'])\n"
        "except OSError:\n print('limited')\n"
    )
    result = WindowsProcessTree().run(
        (sys._base_executable, "-I", "-B", "-c", source),
        tmp_path,
        process_limit=1,
    )
    assert result.execution.stdout.strip() == b"limited" and result.drained, result
    assert result.execution.exit_code == 0


@native
@pytest.mark.parametrize(
    "kwargs",
    [
        {"process_limit": 0},
        {"process_limit": 65},
        {"process_limit": True},
        {"memory_bytes": 0},
        {"memory_bytes": 5 * 1024**3},
        {"memory_bytes": True},
        {"appcontainer_sid": "S-1-15-2-1"},
    ],
)
def test_bad_security_requests_never_launch(tmp_path, kwargs):
    with pytest.raises(ValueError):
        WindowsProcessTree().run(
            (sys.executable, "-I", "-B", "-c", "raise SystemExit(99)"), tmp_path, **kwargs
        )
