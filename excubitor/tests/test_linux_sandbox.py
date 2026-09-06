"""Service validation plus opt-in real kernel tests in a dedicated worker service."""

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.linux_sandbox import LinuxSandboxExecutor, _seconds, service_command
from excubitor.runs import RunError


@pytest.mark.parametrize("value", ["infinity", "", "nan", "-2s", "1d", "1s;touch", "0x10s"])
def test_unknown_service_lifetimes_are_rejected(value):
    with pytest.raises(RunError):
        _seconds(value)


def test_service_duration_units():
    assert _seconds("1min 2s 3ms 4us") == pytest.approx(62.003004)


@pytest.mark.parametrize(
    "change",
    [
        {"unit": "sshd.service"},
        {"seconds": float("nan")},
        {"seconds": float("inf")},
        {"seconds": True},
        {"seconds": 3601},
        {"memory_bytes": 0},
        {"process_limit": 300},
        {"argv": ("relative",)},
        {"directory": "relative"},
    ],
)
def test_service_cannot_reuse_an_unrelated_unit_or_run_unbounded(change):
    request = dict(
        unit="excubitor-worker-" + "a" * 32 + ".service",
        argv=("/usr/bin/python3", "controller.py"),
        directory="/private",
        seconds=60,
        memory_bytes=512 * 1024**2,
        process_limit=64,
    )
    request.update(change)
    with pytest.raises(ValueError):
        service_command(**request)


@pytest.fixture(scope="module")
def native():
    config = os.environ.get("EXCUBITOR_SANDBOX_TEST_CONFIG")
    if sys.platform != "linux" or not config:
        pytest.skip("requires an explicitly provisioned bounded Linux test service")
    data = json.loads(Path(config).read_text())
    assert data["schema"] == "excubitor.sandbox-tests.v1"
    with LinuxSandboxExecutor(
        data["unit"],
        Path(data["candidate"]),
        Path(data["tools"]),
        Path(data["native"]),
        memory_bytes=192 * 1024**2,
        process_limit=32,
    ) as executor:
        yield executor, data
    assert not executor.parent.exists()


def execute(native, program, mode="workspace-write", **kwargs):
    executor, _ = native
    return executor.run(
        ("/usr/bin/python3", "-I", "-B", "-c", program),
        executor.candidate,
        sandbox=mode,
        env={},
        **kwargs,
    )


def success(result):
    assert result.execution.exit_code == 0, result.execution.stderr.decode(errors="replace")
    assert result.drained and not result.cancelled
    assert not result.execution.timed_out and not result.execution.output_limited


def test_native_exact_bytes_and_no_worker_capabilities(native):
    result = execute(
        native,
        "import pathlib,sys; s=dict(line.split(':',1) for line in "
        "pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line); "
        "assert all(int(s[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb')); "
        "assert s['NoNewPrivs'].strip()=='1'; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        stdin=b"exact\0bytes\n",
    )
    success(result)
    assert result.execution.stdout == b"exact\0bytes\n"


def test_native_project_write_and_read_only_enforcement(native):
    success(execute(native, "open('/workspace/retained','w').write('original')"))
    result = execute(
        native,
        "import errno,pathlib; p=pathlib.Path('/workspace/retained'); "
        "assert p.read_text()=='original'\n"
        "for change in (lambda:p.write_text('changed'),lambda:p.unlink(),lambda:p.chmod(0o777)):\n"
        " try: change()\n"
        " except OSError as e: assert e.errno==errno.EROFS\n"
        " else: raise AssertionError('reviewer changed the candidate')\n",
        "read-only",
    )
    success(result)
    assert (native[0].candidate / "retained").read_text() == "original"


def test_native_host_paths_symlinks_and_network_are_unavailable(native):
    executor, data = native
    (executor.candidate / "outside-link").symlink_to(data["canary"])
    paths = [
        data["canary"],
        data["native"],
        data["tools"],
        str(executor.group),
        "/mnt/c",
        "/mnt/d",
        "/init",
        "/workspace/outside-link",
        "/etc/passwd",
    ]
    try:
        result = execute(
            native,
            "import pathlib,socket\n"
            f"for name in {paths!r}:\n"
            " assert not pathlib.Path(name).exists(), name\n"
            "for address in [('1.1.1.1',443),('127.0.0.1',22)]:\n"
            " try: socket.create_connection(address,timeout=.2)\n"
            " except OSError: pass\n"
            " else: raise AssertionError('host network accessible')\n",
            "read-only",
        )
        success(result)
    finally:
        (executor.candidate / "outside-link").unlink()
    assert Path(data["canary"]).read_text() == "host-only canary\n"


def test_native_windows_executable_is_rejected_before_interop(native):
    if not native[1]["interop_available"]:
        pytest.skip("ordinary Windows interop was unavailable before the executor started")
    result = execute(
        native,
        "import errno,subprocess\n"
        "try: subprocess.run(['/workspace/cmd.exe','/d','/c','exit 0'],capture_output=True,timeout=3)\n"
        "except OSError as e: assert e.errno==errno.ENOEXEC\n"
        "else: raise AssertionError('Windows binary loader was reached')\n",
        "read-only",
    )
    success(result)


def test_native_nested_namespace_cannot_make_review_writable(native):
    result = execute(
        native,
        "import errno,pathlib,subprocess; "
        "p=subprocess.run(['/usr/bin/unshare','--user','--map-root-user','--mount',"
        "'/usr/bin/mount','-o','remount,rw','/workspace'],capture_output=True,timeout=3); "
        "assert p.returncode!=0, p.stdout\n"
        "try: pathlib.Path('/workspace/retained').write_text('changed')\n"
        "except OSError as e: assert e.errno==errno.EROFS\n"
        "else: raise AssertionError('read-only mount escaped')\n",
        "read-only",
    )
    success(result)


def test_native_home_and_temporary_files_do_not_persist(native):
    success(
        execute(
            native,
            "from pathlib import Path; (Path.home()/'private').write_text('previous'); "
            "Path('/tmp/private').write_text('previous')",
        )
    )
    success(
        execute(
            native,
            "from pathlib import Path; assert not (Path.home()/'private').exists(); "
            "assert not Path('/tmp/private').exists()",
        )
    )


def test_native_rejects_loader_injection_wrong_candidate_and_unknown_mode(native):
    executor, data = native
    for changes in (
        {"env": {"LD_PRELOAD": "/workspace/payload.so"}},
        {"env": {"CLAUDE_CODE_OAUTH_TOKEN": "not-a-token"}},
        {"sandbox": "unrestricted"},
        {"cwd": Path(data["canary"]).parent},
    ):
        request = dict(argv=("/usr/bin/true",), cwd=executor.candidate, sandbox="read-only", env={})
        request.update(changes)
        with pytest.raises(RunError):
            executor.run(**request)


def test_native_preexisting_hardlink_is_rejected(native):
    executor, data = native
    link = executor.candidate / "hardlink"
    os.link(data["canary"], link)
    try:
        with pytest.raises(RunError, match="shared or special"):
            execute(native, "raise AssertionError('must not execute')")
    finally:
        link.unlink()


def test_native_preexisting_socket_is_rejected(native):
    import errno
    import socket

    executor, _ = native
    address = executor.candidate / "host.socket"
    with socket.socket(socket.AF_UNIX) as endpoint:
        previous = Path.cwd()
        try:
            os.chdir(executor.candidate)
            try:
                endpoint.bind(address.name)
            except OSError as error:
                if error.errno == errno.EOPNOTSUPP:
                    pytest.skip("candidate filesystem itself refuses Unix sockets")
                raise
        finally:
            os.chdir(previous)
        try:
            with pytest.raises(RunError, match="shared or special"):
                execute(native, "raise AssertionError('must not execute')")
        finally:
            address.unlink()


def test_native_timeout_and_cancel_drain_detached_children(native):
    for name, cancel_after in (("timeout-late", None), ("cancel-late", 0.25)):
        child = f"import time,pathlib; time.sleep(1); pathlib.Path('/workspace/{name}').touch()"
        program = (
            "import subprocess,time; subprocess.Popen(['/usr/bin/python3','-I','-B','-c',"
            + repr(child)
            + "],start_new_session=True,stdin=subprocess.DEVNULL,"
            "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(30)"
        )
        cancel = threading.Event()
        timer = threading.Timer(cancel_after, cancel.set) if cancel_after else None
        if timer:
            timer.start()
        try:
            result = execute(native, program, timeout=0.5, cancelled=cancel)
        finally:
            if timer:
                timer.join()
        assert result.drained
        assert result.cancelled if timer else result.execution.timed_out
    time.sleep(1.1)
    assert not any((native[0].candidate / name).exists() for name in ("timeout-late", "cancel-late"))
    assert not list(native[0].parent.glob("run-*"))


def test_native_output_memory_and_process_limits(native):
    result = execute(native, "import os\nwhile True: os.write(1,b'x'*65536)", output_limit=4096)
    assert result.drained and result.execution.output_limited
    assert len(result.execution.stdout) + len(result.execution.stderr) <= 4096
    result = execute(native, "data=bytearray(512*1024*1024)")
    assert result.drained and result.execution.exit_code != 0 and not result.execution.timed_out
    result = execute(
        native,
        "import os,time\nfor i in range(80):\n"
        " try: pid=os.fork()\n"
        " except BlockingIOError: print('bounded',flush=True); break\n"
        " if pid==0: time.sleep(30); os._exit(0)\n"
        "else: raise AssertionError('process cap not enforced')\n"
        "time.sleep(30)",
        timeout=1,
    )
    assert result.drained and result.execution.timed_out
    assert b"bounded" in result.execution.stdout
    success(execute(native, "print('controller survived')"))


def test_native_cancellation_before_dispatch_and_claude_binary_mapping(native):
    event = threading.Event()
    event.set()
    result = execute(native, "open('/workspace/unexpected','w').write('ran')", cancelled=event)
    assert result.cancelled and result.drained and result.processes == 0
    assert not (native[0].candidate / "unexpected").exists()
    executor, _ = native
    result = executor.run(
        (str(executor.native), "--version"), executor.candidate, sandbox="read-only", env={}
    )
    success(result)
    assert b"Claude Code" in result.execution.stdout
