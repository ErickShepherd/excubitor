"""The single trusted-local process dispatch seam; never sandbox fallback."""

import os
import subprocess
import sys

from excubitor.processes import WindowsProcessTree
from excubitor.runs import RunError


def host_backend():
    if os.name == "nt":
        return "windows-process"
    if os.name == "posix" and sys.platform in ("linux", "darwin"):
        return "posix-process"
    raise RunError("development process management requires Windows, Linux or macOS")


def process_tree(backend=None):
    actual = host_backend()
    if backend is not None and backend != actual:
        raise RunError("selected process backend is unavailable on this operating system")
    if actual == "windows-process":
        return WindowsProcessTree()
    from excubitor.posix_processes import PosixProcessTree

    return PosixProcessTree()


def background_options():
    if host_backend() == "windows-process":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
