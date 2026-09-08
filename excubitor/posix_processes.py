"""Bounded trusted-local POSIX groups, not hostile-process containment.

Programs must not escape their group, tamper with the guardian, or close/reuse
Excubitor's inherited lineage descriptor. A lifeline guardian kills each group
on caller loss. The outer owner also waits for nested guardians' lineage EOF
before returning, including after an inner controller crash. SIGKILL and closed
channels establish cooperative drainage, not a kernel process-tree inventory.
The process count reports observed launches, not an exhaustive descendant count.
"""

from __future__ import annotations

import base64
import json
import os
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

from excubitor.acceptance import Execution
from excubitor.processes import ProcessResult
from excubitor.runs import RunError

LINEAGE = "_EXCUBITOR_POSIX_LINEAGE_FD"


class PosixProcessTree:
    def run(
        self,
        argv,
        cwd,
        *,
        stdin=b"",
        timeout=60,
        output_limit=1024 * 1024,
        cancelled=None,
        terminate_on_root_exit=False,
        env=None,
    ):
        if os.name != "posix" or sys.platform not in ("linux", "darwin"):
            raise RunError("trusted POSIX process groups require Linux or macOS")
        if (
            not isinstance(argv, (tuple, list))
            or not 1 <= len(argv) <= 64
            or any(not isinstance(s, str) or not s or "\0" in s or len(s) > 16384 for s in argv)
            or not Path(argv[0]).is_absolute()
            or not Path(argv[0]).is_file()
            or not os.access(argv[0], os.X_OK)
            or not cwd.is_absolute()
            or not cwd.is_dir()
            or not 0 < timeout <= 3600
            or not 0 < output_limit <= 16 * 1024 * 1024
            or not isinstance(stdin, bytes)
            or len(stdin) > 1024 * 1024
            or type(terminate_on_root_exit) is not bool
            or env is not None
            and (
                not isinstance(env, dict)
                or any(
                    not isinstance(k, str)
                    or not isinstance(v, str)
                    or not k
                    or "\0" in k
                    or "=" in k
                    or "\0" in v
                    for k, v in env.items()
                )
            )
        ):
            raise ValueError("invalid bounded POSIX process request")
        if cancelled is not None and cancelled.is_set():
            return ProcessResult(Execution(None, b"", b"", 0), True, True, 0)
        return _run(argv, cwd, stdin, timeout, output_limit, cancelled, env)


def _run(argv, cwd, stdin, timeout, output_limit, cancelled, env):
    # Always stop remaining cooperative descendants on root exit. Unlike the
    # Windows job adapter, POSIX has no portable total-descendant accounting.
    started = time.monotonic()
    environment = dict(os.environ if env is None else env)
    inherited = os.environ.get(LINEAGE)
    lineage_read = lineage_write = None
    if inherited is None:
        lineage_read, lineage_write = os.pipe()
        lineage = lineage_write
    else:
        try:
            lineage = int(inherited)
            if lineage < 3 or not stat.S_ISFIFO(os.fstat(lineage).st_mode):
                raise ValueError("not a lineage pipe")
        except (ValueError, OSError) as error:
            raise RunError("invalid inherited process ownership channel") from error
    environment[LINEAGE] = str(lineage)
    status_read, status_write = os.pipe()
    process = None
    selector = selectors.DefaultSelector()
    buffers = [bytearray(), bytearray()]
    status_buffer = bytearray()
    code, target_pid = None, None
    timed_out = was_cancelled = limited = killed = False
    payload = memoryview(
        json.dumps({"argv": argv, "stdin": base64.b64encode(stdin).decode()}).encode() + b"\n"
    )
    owned = {status_read, status_write}
    if lineage_read is not None:
        owned.update((lineage_read, lineage_write))

    def close_fd(fd):
        if fd in owned:
            owned.remove(fd)
            os.close(fd)

    def kill():
        nonlocal killed
        if process is not None and not killed:
            # Popen.poll/wait must NOT precede this signal. An unreaped leader
            # reserves this identity even when the guardian exited unexpectedly.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            killed = True

    try:
        process = subprocess.Popen(
            (
                sys.executable,
                "-I",
                "-B",
                str(Path(__file__).with_name("portable_guardian.py")),
                str(status_write),
            ),
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            pass_fds=(status_write, lineage),
            start_new_session=True,
        )
        close_fd(status_write)
        if lineage_write is not None:
            close_fd(lineage_write)
        channels = [(process.stdout.fileno(), 0), (process.stderr.fileno(), 1), (status_read, "status")]
        if lineage_read is not None:
            channels.append((lineage_read, "lineage"))
        for fd, kind in channels:
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ, kind)
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin.fileno(), selectors.EVENT_WRITE, "input")
        drain_deadline = None
        while selector.get_map():
            was_cancelled = was_cancelled or cancelled is not None and cancelled.is_set()
            timed_out = timed_out or time.monotonic() - started >= timeout
            if code is not None or was_cancelled or timed_out or limited:
                kill()
            if killed and drain_deadline is None:
                drain_deadline = time.monotonic() + 5
                if process.stdin.fileno() in selector.get_map():
                    selector.unregister(process.stdin.fileno())
            if drain_deadline is not None and time.monotonic() >= drain_deadline:
                raise RunError("POSIX process ownership channels did not drain; safe resume is unproven")
            for key, _ in selector.select(0.01):
                if key.data == "input":
                    try:
                        payload = payload[os.write(key.fd, payload) :]
                        if not payload:
                            selector.unregister(key.fd)
                    except BrokenPipeError:
                        selector.unregister(key.fd)
                        kill()
                    continue
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fd)
                    if key.data == "status" and code is None:
                        kill()
                    continue
                if key.data == "status":
                    status_buffer.extend(chunk)
                    if len(status_buffer) > 4096:
                        raise RunError("invalid guardian response")
                    while b"\n" in status_buffer:
                        line, _, rest = status_buffer.partition(b"\n")
                        status_buffer[:] = rest
                        message = json.loads(line)
                        if set(message) == {"pid"} and type(message["pid"]) is int:
                            target_pid = message["pid"]
                        elif set(message) == {"exit_code"} and type(message["exit_code"]) is int:
                            code = message["exit_code"]
                        else:
                            raise RunError("invalid guardian response")
                elif key.data == "lineage":
                    raise RunError("invalid process ownership channel data")
                else:
                    keep = min(len(chunk), output_limit - sum(map(len, buffers)))
                    buffers[key.data].extend(chunk[:keep])
                    limited = limited or keep < len(chunk)
        kill()
        process.wait(timeout=5)
        if code is None and not (was_cancelled or timed_out or limited):
            raise RunError("POSIX guardian failed before a program result; evidence preserved")
        return ProcessResult(
            Execution(
                code, bytes(buffers[0]), bytes(buffers[1]), time.monotonic() - started, timed_out, limited
            ),
            was_cancelled,
            True,
            1 if target_pid is not None else 0,
            (target_pid,) if target_pid is not None else (),
        )
    finally:
        kill()
        selector.close()
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
            process.wait(timeout=5)
        for fd in tuple(owned):
            close_fd(fd)
