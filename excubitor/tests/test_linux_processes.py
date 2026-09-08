"""Real Linux cgroup tests, opt-in only inside the dedicated disposable guest."""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.linux_processes import LinuxProcessTree
from excubitor.runs import RunError


@pytest.fixture
def linux(tmp_path):
    parent = os.environ.get("EXCUBITOR_LINUX_TEST_CGROUP")
    if sys.platform != "linux" or not parent or os.geteuid() != 0:
        pytest.skip("requires explicit cgroup test enrollment in an isolated Linux guest")
    if Path("/etc/excubitor-worker-id").read_text() != "excubitor-private-vm-20260906\n":
        pytest.fail("the disposable guest identity is missing")
    if not tmp_path.resolve().is_relative_to(Path("/tmp")):
        pytest.fail("use a new test directory beneath the disposable guest's /tmp")
    # Only this new test directory becomes accessible to the guest worker UID.
    tmp_path.chmod(0o755)
    directory = tmp_path / "candidate"
    directory.mkdir()
    os.chown(directory, 1001, 1001)
    for path in tmp_path.parents:
        if path == Path("/tmp"):
            break
        path.chmod(0o755)
    return LinuxProcessTree(Path(parent), uid=1001, gid=1001), directory


def run(linux, source, **kwargs):
    tree, directory = linux
    return tree.run(
        (sys.executable, "-I", "-B", "-c", source),
        directory,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        **kwargs,
    )


def test_exact_input_output_and_unprivileged_identity(linux):
    result = run(
        linux,
        "import os,sys; assert os.getuid()==1001; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        stdin=b"exact\0bytes\n",
    )
    assert result.execution.stdout == b"exact\0bytes\n"
    assert result.execution.exit_code == 0 and result.drained


def test_detached_child_with_closed_pipes_cannot_hide(linux):
    child = "import time; time.sleep(.3); open('finished','w').write('done')"
    result = run(
        linux,
        "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-c',"
        + repr(child)
        + "],start_new_session=True,stdin=subprocess.DEVNULL,"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)",
    )
    assert result.execution.elapsed_seconds >= 0.3
    assert (linux[1] / "finished").read_text() == "done"
    assert result.execution.exit_code == 0 and result.drained


def test_timeout_stops_detached_descendant(linux):
    child = "import time; time.sleep(1); open('late','w').write('orphan')"
    result = run(
        linux,
        "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-c',"
        + repr(child)
        + "],start_new_session=True,stdin=subprocess.DEVNULL,"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)",
        timeout=0.2,
    )
    assert result.execution.timed_out and result.drained
    time.sleep(1.1)
    assert not (linux[1] / "late").exists()


def test_cancellation_and_output_flood_are_bounded(linux):
    cancellation = threading.Event()
    timer = threading.Timer(0.15, cancellation.set)
    timer.start()
    try:
        result = run(linux, "import time; time.sleep(30)", cancelled=cancellation)
    finally:
        timer.join()
    assert result.cancelled and result.drained
    result = run(linux, "import os\nwhile True: os.write(1,b'x'*65536)", output_limit=4096)
    assert result.execution.output_limited and result.drained
    assert len(result.execution.stdout) + len(result.execution.stderr) <= 4096


def test_worker_cannot_move_out_of_cgroup_or_change_controller_authority(linux):
    tree, _ = linux
    result = run(
        linux,
        "from pathlib import Path\n"
        f"targets=[Path({str(tree.parent / 'cgroup.procs')!r}),Path('/etc/excubitor-worker-id')]\n"
        "for path in targets:\n"
        " try: path.open('w')\n"
        " except PermissionError: print('denied')\n"
        " else: raise AssertionError('worker could mutate authority')\n",
    )
    assert result.execution.exit_code == 0 and result.drained
    assert result.execution.stdout == b"denied\ndenied\n"


def test_early_cancellation_never_starts_a_program(linux):
    cancellation = threading.Event()
    cancellation.set()
    result = run(linux, "open('unexpected','w').write('ran')", cancelled=cancellation)
    assert result.cancelled and result.drained and result.processes == 0
    assert not (linux[1] / "unexpected").exists()


def test_kernel_process_limit_is_enforced(linux):
    source = (
        "import os,time\n"
        "for index in range(20):\n"
        " try: pid=os.fork()\n"
        " except BlockingIOError: print('process limit reached',flush=True); break\n"
        " if pid==0: time.sleep(30); os._exit(0)\n"
        "else: raise AssertionError('process cap was not enforced')\n"
    )
    result = run(linux, source, process_limit=8, timeout=0.5)
    assert b"process limit reached" in result.execution.stdout
    assert result.execution.timed_out and result.drained


def test_kernel_memory_limit_stops_only_the_worker(linux):
    result = run(linux, "data=bytearray(256*1024*1024)", memory_bytes=64 * 1024 * 1024)
    assert result.execution.exit_code != 0 and result.drained
    assert not result.execution.timed_out


def test_no_root_workload_or_nonprivate_parent(linux):
    tree, _ = linux
    with pytest.raises(ValueError):
        LinuxProcessTree(tree.parent, uid=0, gid=1001)
    with pytest.raises(RunError):
        LinuxProcessTree(Path("/sys/fs/cgroup"), uid=1001, gid=1001)
