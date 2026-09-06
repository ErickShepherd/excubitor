"""Bounded Linux cgroup execution inside an independently admitted worker VM.

This is process containment, not filesystem/network isolation. The trusted caller
must supply a sandbox command and an outer lifetime owner (for example the VM's
host process job). A Linux controller crash alone does not destroy its cgroup.
Never use this runner to launch a model directly on an unisolated host.
"""

from __future__ import annotations

import os
import selectors
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from excubitor.acceptance import Execution
from excubitor.processes import ProcessResult
from excubitor.runs import RunError

# Only this fixed, isolated interpreter bootstrap runs before cgroup membership.
# It cannot fork or execute the requested program until membership is established.
# Closing the inherited control FD before exec keeps it away from the worker.
_JOIN = """
import ctypes, os, sys
fd, uid, gid = map(int, sys.argv[1:4])
os.write(fd, b'0')
os.close(fd)
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(38, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), 'cannot set no_new_privs')
os.setgroups([])
os.setgid(gid)
os.setuid(uid)
os.execv(sys.argv[4], sys.argv[4:])
"""


class LinuxProcessTree:
    """Root-owned cgroup v2, unprivileged workload, independently observed drain.

    The caller provisions a private cgroup parent in its disposable Linux VM.
    Worker UID/GID must differ from the controller. Detached descendants remain
    in the kernel-owned group, including children that close all captured pipes.
    """

    def __init__(self, parent: Path, *, uid: int, gid: int):
        if sys.platform != "linux" or os.geteuid() != 0:
            raise RunError("Linux cgroup execution requires the isolated guest's trusted root controller")
        if type(uid) is not int or type(gid) is not int or uid <= 0 or gid <= 0:
            raise ValueError("a separate unprivileged worker UID and GID are required")
        if not parent.is_absolute() or parent.resolve() != parent:
            raise ValueError("cgroup parent must be an absolute canonical path")
        mount = Path("/sys/fs/cgroup")
        if parent == mount or not parent.is_relative_to(mount):
            raise RunError("a dedicated cgroup parent beneath the cgroup v2 mount is required")
        mounts = Path("/proc/self/mountinfo").read_text().splitlines()
        if not any(line.split()[4] == str(mount) and " - cgroup2 " in line for line in mounts):
            raise RunError("the expected cgroup v2 filesystem is unavailable")
        for path in (parent, *parent.parents):
            if path == mount.parent:
                break
            info = path.stat()
            if info.st_uid != 0 or info.st_mode & 0o002 or info.st_gid != 0 and info.st_mode & 0o020:
                raise RunError("worker-writable cgroup authority")
        if not (parent / "cgroup.controllers").is_file():
            raise RunError("cgroup parent is not provisioned")
        self.parent, self.uid, self.gid = parent, uid, gid

    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        *,
        stdin: bytes = b"",
        timeout: float = 60,
        output_limit: int = 1024 * 1024,
        cancelled: threading.Event | None = None,
        terminate_on_root_exit: bool = False,
        env: dict[str, str],
        memory_bytes: int = 1024 * 1024 * 1024,
        process_limit: int = 64,
    ) -> ProcessResult:
        if (
            not isinstance(argv, tuple)
            or not argv
            or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
            or not Path(argv[0]).is_absolute()
            or not Path(argv[0]).is_file()
            or not cwd.is_absolute()
            or not cwd.is_dir()
            or not 0 < timeout <= 3600
            or not 0 < output_limit <= 16 * 1024 * 1024
            or not isinstance(stdin, bytes)
            or len(stdin) > 1024 * 1024
            or type(terminate_on_root_exit) is not bool
            or type(memory_bytes) is not int
            or not 16 * 1024 * 1024 <= memory_bytes <= 4 * 1024 * 1024 * 1024
            or type(process_limit) is not int
            or not 1 <= process_limit <= 256
            or not isinstance(env, dict)
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                or not key
                or "=" in key
                or "\0" in key + value
                for key, value in env.items()
            )
        ):
            raise ValueError("invalid bounded Linux process request")
        if cancelled is not None and cancelled.is_set():
            return ProcessResult(Execution(None, b"", b"", 0), True, True, 0)
        group = self.parent / ("run-" + uuid.uuid4().hex)
        group.mkdir(mode=0o700)
        process, selector, control = None, selectors.DefaultSelector(), None
        started = time.monotonic()
        outputs, observed = [bytearray(), bytearray()], set()
        timed_out = limited = was_cancelled = False
        exit_code = None

        def populated():
            return (
                dict(line.split() for line in (group / "cgroup.events").read_text().splitlines())["populated"]
                != "0"
            )

        try:
            if not (group / "cgroup.kill").is_file():
                raise RunError("kernel cgroup.kill is required before starting a worker")
            (group / "pids.max").write_text(str(process_limit))
            (group / "memory.max").write_text(str(memory_bytes))
            (group / "memory.swap.max").write_text("0")
            control = os.open(group / "cgroup.procs", os.O_WRONLY | os.O_CLOEXEC)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    _JOIN,
                    str(control),
                    str(self.uid),
                    str(self.gid),
                    *argv,
                ],
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(control,),
                start_new_session=True,
            )
            os.close(control)
            control = None
            observed.add(process.pid)
            for index, stream in enumerate((process.stdout, process.stderr)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, index)
            pending = memoryview(stdin)
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 2)
            else:
                process.stdin.close()
            while True:
                observed.update(int(pid) for pid in (group / "cgroup.procs").read_text().split())
                exit_code = process.poll()
                was_cancelled = cancelled is not None and cancelled.is_set()
                timed_out = time.monotonic() - started >= timeout
                if was_cancelled or timed_out or limited:
                    break
                if exit_code is not None:
                    if terminate_on_root_exit or not populated() and not selector.get_map():
                        break
                for key, _ in selector.select(0.02):
                    if key.data == 2:
                        try:
                            pending = pending[os.write(key.fd, pending[:16384]) :]
                        except BrokenPipeError:
                            pending = memoryview(b"")
                        if not pending:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                        continue
                    data = os.read(key.fd, 16384)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    else:
                        available = output_limit - sum(map(len, outputs))
                        outputs[key.data].extend(data[:available])
                        limited = limited or len(data) > available
        finally:
            if control is not None:
                os.close(control)
            try:
                # Reap the fixed launcher first: it can no longer join this group
                # after a kill, even if cancellation raced its initial bootstrap.
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=3)
                    if exit_code is None:
                        exit_code = process.returncode
                if populated():
                    (group / "cgroup.kill").write_text("1")
                deadline = time.monotonic() + 3
                while populated() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if populated():
                    raise RunError("Linux workers did not drain; preserve the cgroup and stop the owning VM")
                group.rmdir()
            finally:
                selector.close()
                if process is not None:
                    for stream in (process.stdin, process.stdout, process.stderr):
                        stream.close()
        return ProcessResult(
            Execution(
                exit_code,
                bytes(outputs[0]),
                bytes(outputs[1]),
                time.monotonic() - started,
                timed_out=timed_out,
                output_limited=limited,
            ),
            cancelled=was_cancelled,
            drained=True,
            processes=len(observed),
            observed_pids=tuple(sorted(observed)),
        )
