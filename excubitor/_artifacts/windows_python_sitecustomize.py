"""Scoped CPython AppContainer compatibility for a private worker runtime only.

CPython's Windows mkdir(mode=0o700) drops the package SID from its explicit DACL
(upstream issue 134587), making tempfile directories inaccessible to their creator.
Retain owner/system/admin access and add the actual package identity at creation.
Parent directory access still comes from the OS sandbox; no existing ACL is edited.
Provisioners may copy this file to sitecustomize.py in their dedicated runtime.
Never install it into a user's ordinary Python environment.
"""

import os


def _install():
    if os.name != "nt":
        return
    import ctypes as c
    import operator
    import sys
    from ctypes import wintypes as w

    kernel = c.WinDLL("kernel32", use_last_error=True)
    security = c.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [c.c_void_p]
    security.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.c_void_p]
    security.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
    security.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.c_void_p]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        c.c_void_p,
        c.c_void_p,
    ]
    kernel.CreateDirectoryW.argtypes = [w.LPCWSTR, c.c_void_p]

    def check(ok):
        if not ok:
            raise c.WinError(c.get_last_error())

    token, size, app = w.HANDLE(), w.DWORD(), w.DWORD()
    check(security.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)))
    try:
        check(security.GetTokenInformation(token, 29, c.byref(app), c.sizeof(app), c.byref(size)))
        if not app.value:
            return
        sids = []
        for info in (1, 31):  # TOKEN_USER and TOKEN_APPCONTAINER_INFORMATION start with PSID.
            security.GetTokenInformation(token, info, None, 0, c.byref(size))
            data = c.create_string_buffer(size.value)
            check(security.GetTokenInformation(token, info, data, size, c.byref(size)))
            text = w.LPWSTR()
            check(security.ConvertSidToStringSidW(c.cast(data, c.POINTER(c.c_void_p))[0], c.byref(text)))
            try:
                sids.append(text.value)
            finally:
                kernel.LocalFree(text)
    finally:
        kernel.CloseHandle(token)
    sddl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{sids[0]})(A;OICI;FA;;;{sids[1]})"

    class Attributes(c.Structure):
        _fields_ = [("size", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]

    original = os.mkdir

    def mkdir(path, mode=0o777, *, dir_fd=None):
        if operator.index(mode) != 0o700 or dir_fd is not None:
            return original(path, mode, dir_fd=dir_fd)
        target = os.fspath(path)
        sys.audit("os.mkdir", target, mode, -1)
        target = os.fsdecode(target)
        if "\x00" in target:
            raise ValueError("embedded null character")
        descriptor = c.c_void_p()
        check(
            security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(descriptor), None)
        )
        try:
            attributes = Attributes(c.sizeof(Attributes), descriptor, False)
            if not kernel.CreateDirectoryW(target, c.byref(attributes)):
                error = c.WinError(c.get_last_error())
                error.filename = target
                raise error
        finally:
            kernel.LocalFree(descriptor)

    os.mkdir = mkdir


_install()
del _install
