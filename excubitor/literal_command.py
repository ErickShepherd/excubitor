"""Reject executable formats that implicitly reinterpret literal Windows argv."""

from __future__ import annotations

import os
from pathlib import Path

from excubitor.runs import RunError


class BatchCommandError(RunError):
    """A Windows batch launcher cannot preserve the literal-argument contract."""


def reject_windows_batch(executable):
    """Leave POSIX executable scripts alone; never try to quote for cmd.exe.

    Windows may launch batch files through its command interpreter even without
    shell=True. Check both the supplied path and its resolved target, including
    case variants and Win32 trailing-dot/space normalization.
    """
    if os.name != "nt":
        return
    paths = (os.fspath(executable), str(Path(executable).resolve()))
    if any(Path(path.rstrip(" .")).suffix.casefold() in (".cmd", ".bat") for path in paths):
        raise BatchCommandError(
            "Windows .cmd/.bat launchers cannot preserve literal arguments. "
            "Select the direct native .exe, or use command-json with a native interpreter "
            "such as python.exe or node.exe followed by the client script. "
            "For checks and retention, use the same interpreter-plus-script argv form."
        )
