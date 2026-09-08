"""Bounded Windows process trees for trusted host adapters. This is NOT a sandbox.

Windows creates the root suspended and already assigned to its job in one call.
No create-then-assign crash window exists. Only stdin/stdout/stderr handles are
inherited. Closing the controller's non-inherited job handle kills descendants.
Native brokers that launch processes outside this tree require separate admission.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from excubitor.acceptance import Execution
from excubitor.runs import RunError
from excubitor.windows_jobs import create_job, create_process_in_job, valid_name


@dataclass(frozen=True)
class ProcessResult:
    execution: Execution
    cancelled: bool
    drained: bool
    processes: int
    observed_pids: tuple[int, ...] = ()
    # Set only by trusted transport/runtime code from service or format evidence.
    # Candidate stdout and reviewer findings cannot set this classification.
    retryable_error: Literal["capacity", "model-output"] | None = None


class WindowsProcessTree:
    """Synchronous, one tree per call; no detached or breakaway descendants allowed.

    A successful return proves this Windows job is empty, not that another native
    service has no workers. The admitting adapter must cover those other surfaces.
    """

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
        env: dict[str, str] | None = None,
        job_name: str | None = None,
        appcontainer_sid: str | None = None,
        memory_bytes: int | None = None,
        process_limit: int = 64,
    ) -> ProcessResult:
        if os.name != "nt":
            raise RunError("process-tree backend currently requires CPython on Windows")
        if (
            not argv
            or not Path(argv[0]).is_absolute()
            or not Path(argv[0]).is_file()
            or not cwd.is_absolute()
            or not cwd.is_dir()
            or not 0 < timeout <= 3600
            or not 0 < output_limit <= 16 * 1024 * 1024
            or not isinstance(stdin, bytes)
            or len(stdin) > 1024 * 1024
            or type(terminate_on_root_exit) is not bool
            or type(process_limit) is not int
            or not 1 <= process_limit <= 64
            or memory_bytes is not None
            and (type(memory_bytes) is not int or not 16 * 1024 * 1024 <= memory_bytes <= 4 * 1024**3)
            or env is not None
            and (
                not isinstance(env, dict)
                or any(
                    not isinstance(key, str)
                    or not isinstance(value, str)
                    or not key
                    or "\x00" in key
                    or "\x00" in value
                    for key, value in env.items()
                )
            )
        ):
            raise ValueError("invalid bounded process request")
        if cancelled is not None and cancelled.is_set():
            return ProcessResult(Execution(None, b"", b"", 0), True, True, 0)
        if job_name is not None:
            valid_name(job_name)
        if appcontainer_sid is not None:
            import re

            if not isinstance(appcontainer_sid, str) or not re.fullmatch(
                r"S-1-15-2(?:-[0-9]+){7}", appcontainer_sid
            ):
                raise ValueError("invalid AppContainer SID")
        return _windows_run(
            argv,
            cwd,
            stdin,
            timeout,
            output_limit,
            cancelled,
            terminate_on_root_exit,
            env,
            job_name,
            appcontainer_sid,
            memory_bytes,
            process_limit,
        )


def _windows_run(
    argv,
    cwd,
    stdin,
    timeout,
    output_limit,
    cancelled,
    terminate_on_root_exit,
    env,
    job_name,
    appcontainer_sid,
    memory_bytes,
    process_limit,
):
    import _winapi
    import ctypes as c
    import msvcrt
    from ctypes import wintypes as w

    class BasicLimits(c.Structure):
        _fields_ = [
            ("process_time", c.c_longlong),
            ("job_time", c.c_longlong),
            ("flags", w.DWORD),
            ("min_ws", c.c_size_t),
            ("max_ws", c.c_size_t),
            ("active_limit", w.DWORD),
            ("affinity", c.c_size_t),
            ("priority", w.DWORD),
            ("scheduling", w.DWORD),
        ]

    class Limits(c.Structure):
        _fields_ = [
            ("basic", BasicLimits),
            ("io", c.c_ulonglong * 6),
            ("process_memory", c.c_size_t),
            ("job_memory", c.c_size_t),
            ("peak_process", c.c_size_t),
            ("peak_job", c.c_size_t),
        ]

    class Accounting(c.Structure):
        _fields_ = [
            ("times", c.c_longlong * 4),
            ("faults", w.DWORD),
            ("total", w.DWORD),
            ("active", w.DWORD),
            ("terminated", w.DWORD),
        ]

    class Members(c.Structure):
        _fields_ = [("assigned", w.DWORD), ("count", w.DWORD), ("ids", c.c_size_t * 64)]

    kernel = c.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "SetInformationJobObject": ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
        "QueryInformationJobObject": ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
        "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
        "ResumeThread": ([w.HANDLE], w.DWORD),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result

    def require(ok):
        if not ok:
            raise c.WinError(c.get_last_error())

    job = create_job(job_name)
    handles, descriptors, threads, release_resources = [], set(), [], []
    process = None
    started = time.monotonic()
    limited = threading.Event()
    io_errors = []
    buffers = [bytearray(), bytearray()]
    budget_lock = threading.Lock()
    stored = 0
    timed_out = was_cancelled = False
    observed_pids = set()

    def pipe():
        pair = os.pipe()
        descriptors.update(pair)
        return pair

    def close_fd(fd):
        if fd in descriptors:
            os.close(fd)
            descriptors.remove(fd)

    def read(fd, target):
        nonlocal stored
        try:
            while chunk := os.read(fd, 65536):
                with budget_lock:
                    keep = min(len(chunk), output_limit - stored)
                    target.extend(chunk[:keep])
                    stored += keep
                    if keep < len(chunk):
                        limited.set()
        except OSError as exc:
            io_errors.append(str(exc))

    def write(fd):
        try:
            remaining = memoryview(stdin)
            while remaining:
                remaining = remaining[os.write(fd, remaining) :]
        except BrokenPipeError:
            pass  # A worker may exit before consuming its input.
        except OSError as exc:
            io_errors.append(str(exc))
        finally:
            close_fd(fd)

    def accounting():
        result = Accounting()
        require(kernel.QueryInformationJobObject(job, 1, c.byref(result), c.sizeof(result), None))

        members = Members()
        require(kernel.QueryInformationJobObject(job, 3, c.byref(members), c.sizeof(members), None))
        observed_pids.update(members.ids[: members.count])
        return result

    try:
        limits = Limits()
        limits.basic.flags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE + ACTIVE_PROCESS; no breakaway flags.
        limits.basic.active_limit = process_limit
        if memory_bytes is not None:
            limits.basic.flags |= 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY: aggregate committed bytes.
            limits.job_memory = memory_bytes
        require(kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)))
        if appcontainer_sid is not None:
            ui_limits = w.DWORD(0xFF)
            require(kernel.SetInformationJobObject(job, 4, c.byref(ui_limits), c.sizeof(ui_limits)))
        input_read, input_write = pipe()
        output_read, output_write = pipe()
        error_read, error_write = pipe()
        child_fds = (input_read, output_write, error_write)
        child_handles = [msvcrt.get_osfhandle(fd) for fd in child_fds]
        for handle in child_handles:
            os.set_handle_inheritable(handle, True)
        process, primary_thread, _ = create_process_in_job(
            argv,
            cwd,
            env,
            child_handles,
            job,
            appcontainer_sid=appcontainer_sid,
            release_resources=release_resources,
        )
        handles.extend((process, primary_thread))
        for fd in child_fds:
            close_fd(fd)
        threads = [
            threading.Thread(target=read, args=(output_read, buffers[0]), daemon=True),
            threading.Thread(target=read, args=(error_read, buffers[1]), daemon=True),
            threading.Thread(target=write, args=(input_write,), daemon=True),
        ]
        for thread in threads:
            thread.start()
        if kernel.ResumeThread(primary_thread) == 0xFFFFFFFF:
            raise c.WinError(c.get_last_error())
        while True:
            state = accounting()
            was_cancelled = cancelled is not None and cancelled.is_set()
            timed_out = time.monotonic() - started >= timeout
            if state.active == 0:
                break
            root_exited = terminate_on_root_exit and _winapi.WaitForSingleObject(process, 0) == 0
            if was_cancelled or timed_out or limited.is_set() or io_errors or root_exited:
                require(kernel.TerminateJobObject(job, 1))
                drain_deadline = time.monotonic() + 5
                while accounting().active:
                    if time.monotonic() >= drain_deadline:
                        raise RunError("worker job did not drain; protection must remain active")
                    time.sleep(0.01)
                break
            time.sleep(0.01)
        for thread in threads:
            thread.join(5)
        if any(thread.is_alive() for thread in threads) or io_errors:
            raise RunError("worker output channels did not close cleanly")
        state = accounting()
        if state.active:
            raise RunError("workers remain in process job")
        execution = Execution(
            _winapi.GetExitCodeProcess(process),
            bytes(buffers[0]),
            bytes(buffers[1]),
            time.monotonic() - started,
            timed_out,
            limited.is_set(),
        )
        return ProcessResult(execution, was_cancelled, True, state.total, tuple(sorted(observed_pids)))
    finally:
        # Even a suspended root already belongs to the job if this controller dies.
        if process is not None and _winapi.GetExitCodeProcess(process) == 259:
            _winapi.TerminateProcess(process, 1)
        kernel.TerminateJobObject(job, 1)
        _winapi.CloseHandle(job)
        for thread in threads:
            if thread.ident is not None:
                thread.join(5)
        for fd in list(descriptors):
            close_fd(fd)
        for handle in handles:
            _winapi.CloseHandle(handle)
        for release in release_resources:
            release()
