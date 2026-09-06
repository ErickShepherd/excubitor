"""Native Windows offline execution candidate; no WSL or vendor login.

Requires a separately provisioned, exact AppContainer identity. This module never
registers a profile, changes shared runtime ACLs, or falls back to an ordinary token.
The host supplies an exclusively leased candidate and a private copy of its tools.
Native admission remains separate from this executor's existence.
"""

from __future__ import annotations

import ctypes as c
import os
import re
import stat
import threading
import uuid
from ctypes import wintypes as w
from pathlib import Path

from excubitor.processes import ProcessResult, WindowsProcessTree
from excubitor.runs import RunError
from excubitor.windows_jobs import api, require, require_background_session


def identity_name(name: str) -> None:
    if not isinstance(name, str) or not re.fullmatch(r"Excubitor\.Worker\.[0-9a-f]{32}", name):
        raise RunError("invalid dedicated Windows sandbox identity")


def derive_sid(name: str) -> str:
    """Derive only; does not register or create a Windows profile."""
    identity_name(name)
    kernel, security = api()
    userenv = c.WinDLL("userenv", use_last_error=True)
    userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [w.LPCWSTR, c.c_void_p]
    userenv.DeriveAppContainerSidFromAppContainerName.restype = c.c_long
    security.FreeSid.argtypes, security.FreeSid.restype = [c.c_void_p], c.c_void_p
    sid, text = c.c_void_p(), w.LPWSTR()
    hr = userenv.DeriveAppContainerSidFromAppContainerName(name, c.byref(sid))
    if hr < 0:
        raise RunError(f"cannot derive Windows sandbox identity: {hr}")
    try:
        require(security.ConvertSidToStringSidW(sid, c.byref(text)))
        return text.value
    finally:
        if text:
            kernel.LocalFree(text)
        security.FreeSid(sid)


def _owner_sid() -> str:
    kernel, security = api()
    token, size, text = w.HANDLE(), w.DWORD(), w.LPWSTR()
    require(security.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)))
    try:
        security.GetTokenInformation(token, 1, None, 0, c.byref(size))
        data = c.create_string_buffer(size.value)
        require(security.GetTokenInformation(token, 1, data, size, c.byref(size)))
        require(security.ConvertSidToStringSidW(c.cast(data, c.POINTER(c.c_void_p))[0], c.byref(text)))
        return text.value
    finally:
        if text:
            kernel.LocalFree(text)
        kernel.CloseHandle(token)


def profile_path(name: str) -> Path:
    """Read Windows' registered folder; an absent profile is a setup requirement."""
    sid = derive_sid(name)
    userenv = c.WinDLL("userenv", use_last_error=True)
    userenv.GetAppContainerFolderPath.argtypes = [w.LPCWSTR, c.c_void_p]
    userenv.GetAppContainerFolderPath.restype = c.c_long
    ole = c.WinDLL("ole32")
    ole.CoTaskMemFree.argtypes, ole.CoTaskMemFree.restype = [c.c_void_p], None
    folder = w.LPWSTR()
    hr = userenv.GetAppContainerFolderPath(sid, c.byref(folder))
    if hr < 0:
        raise RunError("Windows sandbox identity requires separate profile provisioning")
    try:
        path = Path(folder.value)
        if not path.is_dir():
            raise RunError("registered Windows sandbox profile is missing")
        _tree(path)
        return path
    finally:
        if folder:
            ole.CoTaskMemFree(folder)


def _tree(path: Path) -> list[Path]:
    """Refuse redirects, hard links and special entries before any ACL operation.

    The host's exclusive lease must prevent simultaneous mutation. This check
    cannot replace that lease or stop a separate trusted process changing paths.
    """
    if not path.is_absolute() or path.drive.startswith("\\") or path.resolve(strict=True) != path:
        raise RunError("sandbox path must be canonical local storage")
    for parent in (path, *path.parents):
        if parent.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RunError("sandbox path has a reparse-point ancestor")
    entries, pending = [], [path]
    while pending:
        current = pending.pop()
        info = current.lstat()
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT or info.st_nlink > 1:
            raise RunError("sandbox tree contains a reparse point or hard link")
        if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
            raise RunError("sandbox tree contains a special entry")
        entries.append(current)
        if len(entries) > 100_000:
            raise RunError("sandbox tree exceeds its entry limit")
        if stat.S_ISDIR(info.st_mode):
            pending.extend(current.iterdir())
    return entries


def _secure(path: Path, owner: str, sid: str | None, *, writable=False, root=False) -> None:
    """Replace permissions only on exclusively owned sandbox material."""
    kernel, security = api()
    for name in ("GetSecurityDescriptorDacl", "GetSecurityDescriptorSacl"):
        fn = getattr(security, name)
        fn.argtypes, fn.restype = [c.c_void_p] * 4, w.BOOL
    security.SetNamedSecurityInfoW.argtypes = [
        w.LPWSTR,
        c.c_int,
        w.DWORD,
        c.c_void_p,
        c.c_void_p,
        c.c_void_p,
        c.c_void_p,
    ]
    security.SetNamedSecurityInfoW.restype = w.DWORD
    access = "0x1301bf" if writable else "0x1200a9"
    grant = ""
    if sid:
        if writable and root:
            grant = f"(A;;0x1201bf;;;{sid})(A;OICIIO;{access};;;{sid})"
        else:
            grant = f"(A;OICI;{access};;;{sid})"
    # OWNER RIGHTS suppresses the token user's implicit WRITE_DAC on owned files.
    sddl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{owner})(A;OICI;RC;;;OW){grant}"
    if sid:
        sddl += "S:(ML;OICI;NW;;;LW)"
    sd, dacl, sacl = c.c_void_p(), c.c_void_p(), c.c_void_p()
    present, defaulted = w.BOOL(), w.BOOL()
    require(security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(sd), None))
    try:
        require(security.GetSecurityDescriptorDacl(sd, c.byref(present), c.byref(dacl), c.byref(defaulted)))
        # Grant the owner WRITE_OWNER first; an inherited Modify grant lacks it.
        masks = [4 | 0x80000000]
        if sid:
            require(
                security.GetSecurityDescriptorSacl(sd, c.byref(present), c.byref(sacl), c.byref(defaulted))
            )
            masks.append(0x10)
        for mask in masks:
            error = security.SetNamedSecurityInfoW(str(path), 1, mask, None, None, dacl, sacl)
            if error:
                raise c.WinError(error)
    finally:
        kernel.LocalFree(sd)


class WindowsSandboxExecutor:
    """Offline LPAC workers with bounded jobs and fresh, private temporary storage.

    All input directories must be dedicated to this identity beneath a private
    host-owned root. Never pass an installed tool directory or an ordinary checkout.
    Provisioning must establish that the identity has no grants outside that root,
    its read-only Windows profile, and Windows' built-in LPAC system resources.
    """

    def __init__(self, name: str, root: Path, *, memory_bytes=512 * 1024**2, process_limit=32):
        if os.name != "nt":
            raise RunError("native Windows isolation is unavailable on this platform")
        require_background_session()
        identity_name(name)
        if type(memory_bytes) is not int or not 128 * 1024**2 <= memory_bytes <= 4 * 1024**3:
            raise RunError("invalid Windows sandbox memory limit")
        if type(process_limit) is not int or not 2 <= process_limit <= 64:
            raise RunError("invalid Windows sandbox process limit")
        self.name, self.sid, self.root = name, derive_sid(name), root
        self.profile = profile_path(name)
        self.candidate, self.tools = root / "candidate", root / "tools"
        self.memory_bytes, self.process_limit = memory_bytes, process_limit
        self._owner, self._lock = _owner_sid(), threading.Lock()
        _tree(root)
        if not self.candidate.is_dir() or not self.tools.is_dir():
            raise RunError("sandbox root requires dedicated candidate and tools directories")
        self._root_identity = (root.stat().st_dev, root.stat().st_ino)
        # Make controller state private before granting any worker path.
        _secure(root, self._owner, None)
        # A terminated controller cannot revoke its temporary grants. The host lease and
        # previously drained job permit the replacement controller to revoke them before reuse.
        for old in root.iterdir():
            if re.fullmatch(r"scratch-[0-9a-f]{32}", old.name):
                for path in _tree(old):
                    _secure(path, self._owner, None)
        for path in _tree(self.tools):
            _secure(path, self._owner, self.sid)

    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        *,
        sandbox: str,
        stdin: bytes = b"",
        timeout: float = 60,
        output_limit: int = 1024 * 1024,
        cancelled: threading.Event | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult:
        if sandbox not in ("workspace-write", "read-only") or env not in (None, {}):
            raise RunError("Windows sandbox refuses unknown modes and caller environment")
        if cwd != self.candidate or not argv or not isinstance(argv, tuple):
            raise RunError("Windows sandbox requires its exact candidate and literal arguments")
        executable = Path(argv[0])
        if (
            not executable.is_absolute()
            or executable.resolve(strict=True) != executable
            or not executable.is_file()
        ):
            raise RunError("sandbox executable must be a canonical file")
        if not any(executable.is_relative_to(path) for path in (self.tools, self.candidate)):
            raise RunError("sandbox executable is outside the dedicated tools and candidate")
        with self._lock:
            info = self.root.stat()
            if (info.st_dev, info.st_ino) != self._root_identity:
                raise RunError("sandbox root identity changed")
            _tree(self.root)
            if cancelled is not None and cancelled.is_set():
                from excubitor.acceptance import Execution

                return ProcessResult(Execution(None, b"", b"", 0), True, True, 0)
            for path in _tree(self.candidate):
                _secure(
                    path,
                    self._owner,
                    self.sid,
                    writable=sandbox == "workspace-write",
                    root=path == self.candidate,
                )
            scratch = self.root / ("scratch-" + uuid.uuid4().hex)
            scratch.mkdir()
            _secure(scratch, self._owner, self.sid, writable=True, root=True)
            # CreateProcess rewrites LPAC TEMP beneath the supplied LOCALAPPDATA.
            native_temp = scratch / "Packages" / self.name.lower() / "AC" / "Temp"
            native_temp.mkdir(parents=True)
            system = Path(os.environ["SystemRoot"])
            environment = {
                "SystemRoot": str(system),
                "WINDIR": str(system),
                "PATH": str(self.tools),
                "PATHEXT": ".EXE;.CMD;.BAT",
                "TEMP": str(scratch),
                "TMP": str(scratch),
                "TMPDIR": str(scratch),
                "USERPROFILE": str(scratch),
                "HOME": str(scratch),
                "LOCALAPPDATA": str(scratch),
                "APPDATA": str(scratch),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
            try:
                result = WindowsProcessTree().run(
                    argv,
                    cwd,
                    stdin=stdin,
                    timeout=timeout,
                    output_limit=output_limit,
                    cancelled=cancelled,
                    env=environment,
                    job_name="Global\\Excubitor.Run." + uuid.uuid4().hex,
                    appcontainer_sid=self.sid,
                    memory_bytes=self.memory_bytes,
                    process_limit=self.process_limit,
                )
                _tree(self.root)
                return result
            finally:
                # Keep evidence, but revoke old temporary-directory access before another call.
                # Any unexpected redirect or inaccessible object stops reuse instead of traversing it.
                for path in _tree(scratch):
                    _secure(path, self._owner, None)
