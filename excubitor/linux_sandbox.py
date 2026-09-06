"""Offline project executor for a dedicated, bounded Linux systemd service.

The trusted host provisions the service with service_command(), owns the candidate's
parent and admits the system/tool inputs. No account profile, host network, hook or
service registration is exposed. This is not yet an authenticated Claude launcher.
"""

from __future__ import annotations

import math
import os
import re
import stat
import subprocess
import sys
import threading
from pathlib import Path, PurePosixPath

from excubitor.linux_processes import LinuxProcessTree
from excubitor.runs import RunError

_UNIT = re.compile(r"excubitor-worker-[0-9a-f]{32}\.service\Z")
_HOST_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/nonexistent"}
_ENV = {
    "PATH": "/tools/usr/bin:/usr/bin:/bin",
    "LD_LIBRARY_PATH": "/tools/usr/lib/x86_64-linux-gnu",
    "HOME": "/home/worker",
    "TMPDIR": "/tmp",
    "LANG": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "DISABLE_AUTOUPDATER": "1",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
    "CLAUDE_CODE_SAFE_MODE": "1",
}

# Only this fixed bootstrap receives capabilities inside the private namespace.
# An initialized, empty binfmt_misc table shadows inherited handlers (including
# WSL's pinned Windows loader). Unmounting hides the control files, but leaves
# the namespace's table initialized. No worker code runs until all caps are gone.
_BOOTSTRAP = r"""
import ctypes, os, pathlib, sys
if any(os.readlink('/proc/self/ns/'+kind) == inherited
       for kind, inherited in zip(('user','mnt'),sys.argv[1:3])):
    raise RuntimeError('refuse inherited namespace mutation')
if pathlib.Path('/proc/self/uid_map').read_text().split() != ['0',sys.argv[3],'1']:
    raise RuntimeError('unexpected worker user mapping')
libc = ctypes.CDLL(None, use_errno=True)
target = b'/tmp/private-binary-formats'
os.mkdir(target, 0o700)
if libc.mount(b'none',target,b'binfmt_misc',0,None) != 0:
    raise OSError(ctypes.get_errno(),'cannot initialize private binary formats')
table = pathlib.Path(os.fsdecode(target))
if {p.name for p in table.iterdir()} - {'status','register'}:
    raise RuntimeError('inherited binary format handler')
(table/'status').write_text('0')
if libc.umount2(target,0) != 0:
    raise OSError(ctypes.get_errno(),'cannot hide private binary formats')
os.rmdir(target)
for capability in range(64):
    if libc.prctl(24,capability,0,0,0) != 0 and ctypes.get_errno() != 22:
        raise OSError(ctypes.get_errno(),'cannot drop capability bound')
class Header(ctypes.Structure):
    _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Caps(ctypes.Structure):
    _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),
             ('inheritable',ctypes.c_uint32)]
header, data = Header(0x20080522,0), (Caps*2)()
if libc.capset(ctypes.byref(header),ctypes.byref(data)) != 0:
    raise OSError(ctypes.get_errno(),'cannot clear capabilities')
status = dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines()
              if ':' in line)
if (any(int(status[key].strip(),16) for key in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
        or status['NoNewPrivs'].strip() != '1'):
    raise RuntimeError('worker privileges were not removed')
os.execv(sys.argv[4],sys.argv[4:])
"""


def _limits(seconds, memory_bytes, process_limit):
    if (
        type(seconds) not in (int, float)
        or not math.isfinite(seconds)
        or not 0 < seconds <= 3600
        or type(memory_bytes) is not int
        or not 128 * 1024**2 <= memory_bytes <= 4 * 1024**3
        or type(process_limit) is not int
        or not 8 <= process_limit <= 256
    ):
        raise ValueError("invalid bounded service limits")


def service_command(unit, argv, directory, *, seconds, memory_bytes, process_limit):
    """Build a transient service command; never enable/install a persistent unit.

    The controller must be trusted code separate from the candidate. Its host must
    still stop this exact unit on cancellation/disconnection and observe removal.
    RuntimeMaxSec is a backstop if that host disappears; it is not restart recovery.
    """
    _limits(seconds, memory_bytes, process_limit)
    if (
        not isinstance(unit, str)
        or not _UNIT.fullmatch(unit)
        or not isinstance(argv, tuple)
        or not argv
        or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
        or not PurePosixPath(argv[0]).is_absolute()
        or not PurePosixPath(directory).is_absolute()
        or "\0" in str(directory)
    ):
        raise ValueError("invalid private service identity or controller command")
    return (
        "/usr/bin/systemd-run",
        "--unit=" + unit,
        "--wait",
        "--pipe",
        "--collect",
        "--property=Type=exec",
        "--property=Delegate=yes",
        "--property=User=root",
        f"--property=RuntimeMaxSec={seconds}s",
        f"--property=MemoryMax={memory_bytes}",
        "--property=MemorySwapMax=0",
        f"--property=TasksMax={process_limit}",
        "--property=KillMode=control-group",
        "--property=SendSIGKILL=yes",
        "--property=TimeoutStopSec=2s",
        "--property=Restart=no",
        "--property=WorkingDirectory=" + str(directory),
        "/usr/bin/env",
        "-i",
        *(f"{key}={value}" for key, value in _HOST_ENV.items()),
        "PYTHONDONTWRITEBYTECODE=1",
        *argv,
    )


def _seconds(value):
    """Parse systemctl's bounded duration display; reject unknown/infinite values."""
    scales = {"h": 3600, "min": 60, "s": 1, "ms": 0.001, "us": 0.000001}
    parts = value.split()
    if not parts:
        raise RunError("missing service lifetime")
    total = 0.0
    for part in parts:
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(min|ms|us|h|s)", part)
        if not match:
            raise RunError("unbounded or unsupported service lifetime")
        total += float(match[1]) * scales[match[2]]
    return total


def _service_group(unit):
    if sys.platform != "linux" or os.geteuid() != 0 or not _UNIT.fullmatch(unit):
        raise RunError("a dedicated Linux worker service is required")
    names = (
        "MainPID",
        "ControlGroup",
        "KillMode",
        "SendSIGKILL",
        "Delegate",
        "Restart",
        "RuntimeMaxUSec",
        "TimeoutStopUSec",
        "MemoryMax",
        "MemorySwapMax",
        "TasksMax",
    )
    result = subprocess.run(
        ("/usr/bin/systemctl", "show", unit, "--property=" + ",".join(names)),
        env=_HOST_ENV,
        capture_output=True,
        timeout=5,
        check=True,
    )
    properties = dict(line.split("=", 1) for line in result.stdout.decode().splitlines())
    current = next(
        line[3:] for line in Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::")
    )
    if (
        properties.get("MainPID") != str(os.getpid())
        or properties.get("ControlGroup") != current
        or PurePosixPath(current).name != unit
        or properties.get("KillMode") != "control-group"
        or properties.get("SendSIGKILL") != "yes"
        or properties.get("Delegate") != "yes"
        or properties.get("Restart") != "no"
        or not 0 < _seconds(properties.get("RuntimeMaxUSec", "")) <= 3600
        or not 0 < _seconds(properties.get("TimeoutStopUSec", "")) <= 5
        or properties.get("MemorySwapMax") != "0"
        or not properties.get("MemoryMax", "").isdigit()
        or not properties.get("TasksMax", "").isdigit()
    ):
        raise RunError("worker service lacks a bounded lifetime and complete group cleanup")
    _limits(1, int(properties["MemoryMax"]), int(properties["TasksMax"]))
    return Path("/sys/fs/cgroup") / current.lstrip("/")


def _canonical(path, *, directory):
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or path.resolve(strict=True) != path
        or not (path.is_dir() if directory else path.is_file())
    ):
        raise ValueError("existing canonical executor paths are required")
    return path


class LinuxSandboxExecutor:
    """One exclusive candidate, one bounded service, fresh namespaces per execution.

    Caller-owned system/tool inputs must be immutable to workers. The candidate's
    parent must be private to the trusted host: concurrent host-side replacement
    or mutation is not supported. Source symlinks resolve only inside the sandbox.
    Credentials and provider access are deliberately unavailable in this version.
    """

    def __init__(
        self,
        unit,
        candidate,
        tools,
        native,
        *,
        uid=65534,
        gid=65534,
        memory_bytes=512 * 1024**2,
        process_limit=64,
    ):
        self.candidate = _canonical(candidate, directory=True)
        self.tools = _canonical(tools, directory=True)
        self.native = _canonical(native, directory=False)
        self.bwrap = _canonical(tools / "usr/bin/bwrap", directory=False)
        for protected in (Path("/usr"), Path("/etc"), Path(__file__).resolve().parent, tools, native):
            if candidate.is_relative_to(protected) or protected.is_relative_to(candidate):
                raise RunError("candidate overlaps trusted executor inputs")
        _limits(1, memory_bytes, process_limit)
        self.memory_bytes, self.process_limit = memory_bytes, process_limit
        self.group = _service_group(unit)
        if (
            int((self.group / "memory.max").read_text()) < memory_bytes + 64 * 1024**2
            or int((self.group / "pids.max").read_text()) < process_limit + 8
        ):
            raise RunError("service needs reserved controller memory and process capacity")
        self._identity = candidate.stat().st_dev, candidate.stat().st_ino
        self._lock = threading.Lock()
        self._closed = False
        self._candidate_entries()
        controller = self.group / "controller"
        controller.mkdir()
        (controller / "cgroup.procs").write_text(str(os.getpid()))
        (self.group / "cgroup.subtree_control").write_text("+memory +pids")
        self.parent = self.group / "workloads"
        self.parent.mkdir(mode=0o700)
        (self.parent / "cgroup.subtree_control").write_text("+memory +pids")
        self.tree = LinuxProcessTree(self.parent, uid=uid, gid=gid)

    def _candidate_entries(self):
        # Pre-existing hardlinks/sockets/devices could expose authority despite a
        # private mount tree. The worker cannot create links to invisible host paths.
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            mounted = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), line.split()[4]))
            if mounted.is_relative_to(self.candidate):
                raise RunError("candidate contains a host mount")

        def unreadable(error):
            raise RunError("candidate cannot be inspected") from error

        count = 0
        for root, directories, files in os.walk(self.candidate, followlinks=False, onerror=unreadable):
            for name in directories + files:
                count += 1
                info = (Path(root) / name).lstat()
                if count > 100_000 or not (
                    stat.S_ISDIR(info.st_mode)
                    or stat.S_ISLNK(info.st_mode)
                    or stat.S_ISREG(info.st_mode)
                    and info.st_nlink == 1
                ):
                    raise RunError("candidate has unsupported shared or special entries")

    def _command(self, argv, mode, env):
        if mode not in ("workspace-write", "read-only"):
            raise RunError("unsupported project permission mode")
        if not isinstance(env, dict) or any(
            key not in _ENV or value != _ENV[key] for key, value in env.items()
        ):
            raise RunError("offline executor does not admit custom environment or authentication")
        if (
            not isinstance(argv, tuple)
            or not argv
            or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
            or not Path(argv[0]).is_absolute()
        ):
            raise ValueError("an absolute sandbox executable and literal arguments are required")
        executable = Path(argv[0])
        if executable == self.native:
            argv = ("/opt/claude", *argv[1:])
        elif executable.is_relative_to(self.candidate):
            argv = (str(Path("/workspace") / executable.relative_to(self.candidate)), *argv[1:])
        return (
            str(self.bwrap),
            "--unshare-user",
            "--uid",
            "0",
            "--gid",
            "0",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--unshare-cgroup",
            "--unshare-net",
            "--die-with-parent",
            "--new-session",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CAP_SYS_ADMIN",
            "--cap-add",
            "CAP_SETPCAP",
            "--clearenv",
            *(part for key, value in _ENV.items() for part in ("--setenv", key, value)),
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--dir",
            "/etc",
            "--ro-bind",
            "/etc/ld.so.cache",
            "/etc/ld.so.cache",
            "--ro-bind",
            "/etc/ssl",
            "/etc/ssl",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/home/worker",
            "--ro-bind",
            str(self.tools),
            "/tools",
            "--ro-bind",
            str(self.native),
            "/opt/claude",
            "--bind" if mode == "workspace-write" else "--ro-bind",
            str(self.candidate),
            "/workspace",
            "--remount-ro",
            "/",
            "--chdir",
            "/workspace",
            "--",
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            "-c",
            _BOOTSTRAP,
            os.readlink("/proc/self/ns/user"),
            os.readlink("/proc/self/ns/mnt"),
            str(self.tree.uid),
            *argv,
        )

    def run(
        self, argv, cwd, *, sandbox, stdin=b"", timeout=60, output_limit=1024 * 1024, cancelled=None, env
    ):
        if not self._lock.acquire(blocking=False):
            raise RunError("overlapping candidate executions are not admitted")
        try:
            if self._closed or cwd != self.candidate or self.candidate.resolve() != self.candidate:
                raise RunError("executor is closed or candidate identity changed")
            info = self.candidate.stat()
            if (info.st_dev, info.st_ino) != self._identity:
                raise RunError("candidate directory was replaced")
            command = self._command(argv, sandbox, env)
            self._candidate_entries()
            return self.tree.run(
                command,
                self.candidate,
                stdin=stdin,
                timeout=timeout,
                output_limit=output_limit,
                cancelled=cancelled,
                env=_HOST_ENV,
                memory_bytes=self.memory_bytes,
                process_limit=self.process_limit,
            )
        finally:
            self._lock.release()

    def close(self):
        if not self._lock.acquire(blocking=False):
            raise RunError("stop the owning service before closing an active executor")
        try:
            if not self._closed:
                self.parent.rmdir()  # Refuse to declare closure with any remaining workload group.
                self._closed = True
        finally:
            self._lock.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
