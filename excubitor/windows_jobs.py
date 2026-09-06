"""Windows kernel ownership primitives; no service or hook registration.

Named jobs are ephemeral, exact-run resources. Their access list grants only the
creating host account. An adapter must prove workers cannot open even a query
handle: same-account write-restricted tokens can retain read access and keep the
job alive. Names and Windows process jobs are not sandboxes.
"""

from __future__ import annotations

import ctypes as c
import os
import re
import subprocess
import time
from ctypes import wintypes as w

from excubitor.runs import RunError


class SecurityAttributes(c.Structure):
    _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]


class StartupInfo(c.Structure):
    _fields_ = [
        ("cb", w.DWORD),
        ("reserved", w.LPWSTR),
        ("desktop", w.LPWSTR),
        ("title", w.LPWSTR),
        ("x", w.DWORD),
        ("y", w.DWORD),
        ("width", w.DWORD),
        ("height", w.DWORD),
        ("chars_x", w.DWORD),
        ("chars_y", w.DWORD),
        ("fill", w.DWORD),
        ("flags", w.DWORD),
        ("show", w.WORD),
        ("reserved_size", w.WORD),
        ("reserved_bytes", c.c_void_p),
        ("stdin", w.HANDLE),
        ("stdout", w.HANDLE),
        ("stderr", w.HANDLE),
    ]


class StartupInfoEx(c.Structure):
    _fields_ = [("startup", StartupInfo), ("attributes", c.c_void_p)]


class ProcessInformation(c.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]


class Accounting(c.Structure):
    _fields_ = [
        ("times", c.c_longlong * 4),
        ("faults", w.DWORD),
        ("total", w.DWORD),
        ("active", w.DWORD),
        ("terminated", w.DWORD),
    ]


def api():
    if os.name != "nt":
        raise RunError("Windows job ownership is unavailable on this platform")
    kernel, security = c.WinDLL("kernel32", use_last_error=True), c.WinDLL("advapi32", use_last_error=True)
    for library, name, args, result in (
        (kernel, "GetCurrentProcess", [], w.HANDLE),
        (kernel, "CloseHandle", [w.HANDLE], w.BOOL),
        (kernel, "OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        (kernel, "WaitForSingleObject", [w.HANDLE, w.DWORD], w.DWORD),
        (kernel, "IsProcessInJob", [w.HANDLE, w.HANDLE, c.c_void_p], w.BOOL),
        (kernel, "LocalFree", [c.c_void_p], c.c_void_p),
        (kernel, "CreateJobObjectW", [c.c_void_p, w.LPCWSTR], w.HANDLE),
        (kernel, "OpenJobObjectW", [w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
        (kernel, "QueryInformationJobObject", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
        (kernel, "TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL),
        (kernel, "InitializeProcThreadAttributeList", [c.c_void_p, w.DWORD, w.DWORD, c.c_void_p], w.BOOL),
        (
            kernel,
            "UpdateProcThreadAttribute",
            [c.c_void_p, w.DWORD, c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p, c.c_void_p],
            w.BOOL,
        ),
        (kernel, "DeleteProcThreadAttributeList", [c.c_void_p], None),
        (
            kernel,
            "CreateProcessW",
            [
                w.LPCWSTR,
                w.LPWSTR,
                c.c_void_p,
                c.c_void_p,
                w.BOOL,
                w.DWORD,
                c.c_void_p,
                w.LPCWSTR,
                c.c_void_p,
                c.c_void_p,
            ],
            w.BOOL,
        ),
        (security, "OpenProcessToken", [w.HANDLE, w.DWORD, c.c_void_p], w.BOOL),
        (security, "GetTokenInformation", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
        (security, "ConvertSidToStringSidW", [c.c_void_p, c.c_void_p], w.BOOL),
        (
            security,
            "ConvertStringSecurityDescriptorToSecurityDescriptorW",
            [w.LPCWSTR, w.DWORD, c.c_void_p, c.c_void_p],
            w.BOOL,
        ),
        (
            security,
            "ConvertSecurityDescriptorToStringSecurityDescriptorW",
            [c.c_void_p, w.DWORD, w.DWORD, c.c_void_p, c.c_void_p],
            w.BOOL,
        ),
        (
            security,
            "GetSecurityInfo",
            [w.HANDLE, c.c_int, w.DWORD, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p],
            w.DWORD,
        ),
    ):
        function = getattr(library, name)
        function.argtypes, function.restype = args, result
    return kernel, security


def require(ok):
    if not ok:
        raise c.WinError(c.get_last_error())


def valid_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"Global\\Excubitor\.Run\.[0-9a-f]{32}", name):
        raise RunError("invalid protected process-job name")


def descriptor(kernel, security):
    token, size, text, result = w.HANDLE(), w.DWORD(), w.LPWSTR(), c.c_void_p()
    require(security.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)))
    try:
        security.GetTokenInformation(token, 1, None, 0, c.byref(size))
        data = c.create_string_buffer(size.value)
        require(security.GetTokenInformation(token, 1, data, size, c.byref(size)))
        sid = c.cast(data, c.POINTER(c.c_void_p))[0]
        require(security.ConvertSidToStringSidW(sid, c.byref(text)))
        sddl = f"O:{text.value}D:P(A;;0x1f001f;;;{text.value})"
        require(security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(result), None))
        return result
    finally:
        kernel.CloseHandle(token)
        if text:
            kernel.LocalFree(text)


def security_text(kernel, security, value):
    text = w.LPWSTR()
    require(
        security.ConvertSecurityDescriptorToStringSecurityDescriptorW(value, 1, 1 | 4, c.byref(text), None)
    )
    try:
        return text.value
    finally:
        kernel.LocalFree(text)


def create_job(name=None):
    kernel, security = api()
    if name is None:
        handle = kernel.CreateJobObjectW(None, None)
        require(handle)
        return handle
    valid_name(name)
    sd = descriptor(kernel, security)
    try:
        attributes = SecurityAttributes(c.sizeof(SecurityAttributes), sd, False)
        c.set_last_error(0)
        handle = kernel.CreateJobObjectW(c.byref(attributes), name)
        error = c.get_last_error()
        require(handle)
        if error == 183:
            kernel.CloseHandle(handle)
            raise RunError("process-job name already exists; never reuse another kernel object")
        return handle
    finally:
        kernel.LocalFree(sd)


def recover_job(name):
    """Under the run's exclusive host lock, drain its exact previously named job.

    Global namespace avoids false absence after switching Windows sessions. The
    job's destruction includes termination of its associated processes. Access
    denied, wrong object types and changed owners/DACLs are never absence evidence.
    """
    valid_name(name)
    kernel, security = api()
    handle = kernel.OpenJobObjectW(0x20000 | 4 | 8, False, name)
    if not handle:
        error = c.get_last_error()
        if error == 2:
            return {"job": name, "evidence": "kernel-object-absent", "active": 0}
        raise c.WinError(error)
    actual, expected, processes = c.c_void_p(), None, []
    try:
        error = security.GetSecurityInfo(handle, 6, 1 | 4, None, None, None, None, c.byref(actual))
        if error:
            raise c.WinError(error)
        expected = descriptor(kernel, security)
        if security_text(kernel, security, actual) != security_text(kernel, security, expected):
            raise RunError("process-job ownership or access control changed; recovery refused")

        class Members(c.Structure):
            _fields_ = [("assigned", w.DWORD), ("count", w.DWORD), ("ids", c.c_size_t * 64)]

        members = Members()
        require(kernel.QueryInformationJobObject(handle, 3, c.byref(members), c.sizeof(members), None))
        for pid in members.ids[: members.count]:
            process = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
            if not process:
                if c.get_last_error() == 87:  # Exited between the kernel snapshot and opening it.
                    continue
                require(process)
            inside = w.BOOL()
            if not kernel.IsProcessInJob(process, handle, c.byref(inside)):
                kernel.CloseHandle(process)
                raise RunError("cannot establish recovered process membership")
            if inside.value:
                processes.append(process)
            else:
                kernel.CloseHandle(process)
        require(kernel.TerminateJobObject(handle, 1))
        deadline = time.monotonic() + 5
        while True:
            state = Accounting()
            require(kernel.QueryInformationJobObject(handle, 1, c.byref(state), c.sizeof(state), None))
            if not state.active:
                for process in processes:
                    remaining = max(0, int((deadline - time.monotonic()) * 1000))
                    if kernel.WaitForSingleObject(process, remaining) != 0:
                        raise RunError("recovered process has not finished termination")
                return {
                    "job": name,
                    "evidence": "kernel-object-drained",
                    "active": 0,
                    "processes": state.total,
                }
            if time.monotonic() >= deadline:
                raise RunError("recovered job did not drain; protection remains active")
            time.sleep(0.01)
    finally:
        for process in processes:
            kernel.CloseHandle(process)
        if actual:
            kernel.LocalFree(actual)
        if expected:
            kernel.LocalFree(expected)
        kernel.CloseHandle(handle)


def create_process_in_job(argv, cwd, env, child_handles, job):
    """Windows creates the suspended process ALREADY assigned to its job.

    PROC_THREAD_ATTRIBUTE_JOB_LIST closes the create-then-assign crash window.
    Only the three explicitly selected standard handles are inherited.
    """
    kernel, _ = api()
    size = c.c_size_t()
    kernel.InitializeProcThreadAttributeList(None, 2, 0, c.byref(size))
    attributes = c.create_string_buffer(size.value)
    require(kernel.InitializeProcThreadAttributeList(attributes, 2, 0, c.byref(size)))
    try:
        inherited = (w.HANDLE * len(child_handles))(*child_handles)
        jobs = (w.HANDLE * 1)(job)
        require(
            kernel.UpdateProcThreadAttribute(
                attributes, 0, 0x20002, inherited, c.sizeof(inherited), None, None
            )
        )
        require(kernel.UpdateProcThreadAttribute(attributes, 0, 0x2000D, jobs, c.sizeof(jobs), None, None))
        startup = StartupInfoEx()
        startup.startup.cb = c.sizeof(startup)
        startup.startup.flags = 0x100
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = child_handles
        startup.attributes = c.cast(attributes, c.c_void_p)
        command = c.create_unicode_buffer(subprocess.list2cmdline(argv))
        environment = (
            None
            if env is None
            else c.create_unicode_buffer(
                "\0".join(
                    f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0].upper())
                )
                + "\0\0"
            )
        )
        result = ProcessInformation()
        require(
            kernel.CreateProcessW(
                argv[0],
                command,
                None,
                None,
                True,
                0x4 | 0x08000000 | 0x80000 | 0x400,
                environment,
                str(cwd),
                c.byref(startup),
                c.byref(result),
            )
        )
        return result.process, result.thread, result.pid
    finally:
        kernel.DeleteProcThreadAttributeList(attributes)
