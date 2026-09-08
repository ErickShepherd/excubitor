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
import uuid
from ctypes import wintypes as w

from excubitor.literal_command import reject_windows_batch
from excubitor.runs import RunError


def require_background_session():
    """User32-compatible workers require the OS noninteractive session boundary.

    A private desktop alone is insufficient: LPAC can reopen the visible desktop
    in the same session. Do not dispatch model-controlled native programs there.
    """
    kernel, _ = api()
    kernel.GetCurrentProcessId.restype = w.DWORD
    kernel.ProcessIdToSessionId.argtypes = [w.DWORD, c.c_void_p]
    kernel.ProcessIdToSessionId.restype = w.BOOL
    session = w.DWORD()
    require(kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), c.byref(session)))
    if session.value != 0:
        raise RunError("Windows sandbox requires an admitted background worker in session 0")


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


def create_process_in_job(
    argv, cwd, env, child_handles, job, *, appcontainer_sid=None, release_resources=None
):
    """Windows creates the suspended process ALREADY assigned to its job.

    PROC_THREAD_ATTRIBUTE_JOB_LIST closes the create-then-assign crash window.
    Only the three explicitly selected standard handles are inherited.
    """
    reject_windows_batch(argv[0])
    kernel, security = api()
    if appcontainer_sid is not None and not isinstance(release_resources, list):
        raise RunError("sandbox desktop lifetime must be owned by the process controller")
    if appcontainer_sid is not None:
        require_background_session()
    sid = c.c_void_p()
    capability_sids, group_sids = c.c_void_p(), c.c_void_p()
    capability_count, group_count = w.DWORD(), w.DWORD()
    desktop, desktop_api = None, None
    size = c.c_size_t()
    count = 2 if appcontainer_sid is None else 5
    kernel.InitializeProcThreadAttributeList(None, count, 0, c.byref(size))
    attributes = c.create_string_buffer(size.value)
    require(kernel.InitializeProcThreadAttributeList(attributes, count, 0, c.byref(size)))
    try:
        if appcontainer_sid is not None:
            security.ConvertStringSidToSidW.argtypes = [w.LPCWSTR, c.c_void_p]
            security.ConvertStringSidToSidW.restype = w.BOOL
            require(security.ConvertStringSidToSidW(appcontainer_sid, c.byref(sid)))
        inherited = (w.HANDLE * len(child_handles))(*child_handles)
        jobs = (w.HANDLE * 1)(job)
        require(
            kernel.UpdateProcThreadAttribute(
                attributes, 0, 0x20002, inherited, c.sizeof(inherited), None, None
            )
        )
        require(kernel.UpdateProcThreadAttribute(attributes, 0, 0x2000D, jobs, c.sizeof(jobs), None, None))
        if sid:

            class Capabilities(c.Structure):
                _fields_ = [
                    ("sid", c.c_void_p),
                    ("capabilities", c.c_void_p),
                    ("count", w.DWORD),
                    ("reserved", w.DWORD),
                ]

            capability_api = c.WinDLL("kernelbase", use_last_error=True)
            capability_api.DeriveCapabilitySidsFromName.argtypes = [w.LPCWSTR] + [c.c_void_p] * 4
            capability_api.DeriveCapabilitySidsFromName.restype = w.BOOL
            require(
                capability_api.DeriveCapabilitySidsFromName(
                    "registryRead",
                    c.byref(group_sids),
                    c.byref(group_count),
                    c.byref(capability_sids),
                    c.byref(capability_count),
                )
            )
            if capability_count.value != 1:
                raise RunError("unexpected Windows registry capability derivation")

            class SidAttributes(c.Structure):
                _fields_ = [("sid", c.c_void_p), ("attributes", w.DWORD)]

            capability = SidAttributes(c.cast(capability_sids, c.POINTER(c.c_void_p))[0], 4)
            capabilities = Capabilities(sid, c.cast(c.byref(capability), c.c_void_p), 1, 0)
            # LPAC excludes the broad ALL APPLICATION PACKAGES grant. No network capabilities.
            package_policy = w.DWORD(1)
            # Native Python's ctypes needs User32 initialization. Session 0 is required above;
            # the private desktop and job UI limits alone did not isolate the visible desktop.
            mitigation = c.c_ulonglong(1 << 32)  # Disable legacy extension-point injection.
            for key, value in ((0x20009, capabilities), (0x2000F, package_policy), (0x20007, mitigation)):
                require(
                    kernel.UpdateProcThreadAttribute(
                        attributes, 0, key, c.byref(value), c.sizeof(value), None, None
                    )
                )
        startup = StartupInfoEx()
        startup.startup.cb = c.sizeof(startup)
        startup.startup.flags = 0x100
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = child_handles
        if sid:
            from excubitor.windows_sandbox import _owner_sid

            desktop_api = c.WinDLL("user32", use_last_error=True)
            desktop_api.CreateDesktopW.argtypes = [
                w.LPCWSTR,
                c.c_void_p,
                c.c_void_p,
                w.DWORD,
                w.DWORD,
                c.c_void_p,
            ]
            desktop_api.CreateDesktopW.restype = w.HANDLE
            desktop_api.CloseDesktop.argtypes, desktop_api.CloseDesktop.restype = [w.HANDLE], w.BOOL
            desktop_api.GetProcessWindowStation.argtypes = []
            desktop_api.GetProcessWindowStation.restype = w.HANDLE
            desktop_api.GetUserObjectInformationW.argtypes = [
                w.HANDLE,
                c.c_int,
                c.c_void_p,
                w.DWORD,
                c.c_void_p,
            ]
            desktop_api.GetUserObjectInformationW.restype = w.BOOL
            station_name = c.create_unicode_buffer(256)
            station_size = w.DWORD()
            require(
                desktop_api.GetUserObjectInformationW(
                    desktop_api.GetProcessWindowStation(),
                    2,
                    station_name,
                    c.sizeof(station_name),
                    c.byref(station_size),
                )
            )
            desktop_name = "Excubitor.Worker." + uuid.uuid4().hex
            sd = c.c_void_p()
            sddl = (
                f"D:P(A;;GA;;;SY)(A;;GA;;;{_owner_sid()})(A;;RC;;;OW)"
                f"(A;;0x200c7;;;{appcontainer_sid})S:(ML;;NW;;;LW)"
            )
            require(security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(sd), None))
            try:
                desktop_attributes = SecurityAttributes(c.sizeof(SecurityAttributes), sd, False)
                desktop = desktop_api.CreateDesktopW(
                    desktop_name, None, None, 0, 0x1F01FF, c.byref(desktop_attributes)
                )
                require(desktop)
            finally:
                kernel.LocalFree(sd)
            startup.startup.desktop = station_name.value + "\\" + desktop_name
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
        if desktop:
            # User32 connects lazily, possibly long after the process starts. Retain the
            # host reference until the entire job drains, not merely until CreateProcess returns.
            release_resources.append(lambda handle=desktop: require(desktop_api.CloseDesktop(handle)))
            desktop = None
        return result.process, result.thread, result.pid
    finally:
        kernel.DeleteProcThreadAttributeList(attributes)
        if desktop:
            desktop_api.CloseDesktop(desktop)
        if sid:
            kernel.LocalFree(sid)
        for array, count in ((capability_sids, capability_count), (group_sids, group_count)):
            if array:
                for index in range(count.value):
                    kernel.LocalFree(c.cast(array, c.POINTER(c.c_void_p))[index])
                kernel.LocalFree(array)
