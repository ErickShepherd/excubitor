"""Explicit trusted-project execution using the selected host process adapter.

This is process lifetime management, NOT a filesystem or network sandbox. It is
never selected as fallback for a denied or unavailable sandboxed executor.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from excubitor.command_model import literal_command, save_result
from excubitor.development_runtime import LOCAL_BASELINE
from excubitor.host_processes import process_tree
from excubitor.runs import RunError


class LocalDevelopmentExecutor:
    baseline = LOCAL_BASELINE

    def __init__(self, project, output, *, environment, baseline, backend=None):
        if baseline != LOCAL_BASELINE:
            raise RunError("local commands require explicit trusted-local-v1 selection")
        self.project, self.output = Path(project), Path(output)
        self.tree = process_tree(backend)
        if (
            not self.project.is_absolute()
            or not self.output.is_absolute()
            or not self.project.is_dir()
            or not self.output.is_dir()
            or self.output.resolve().is_relative_to(self.project.resolve())
        ):
            raise RunError("existing candidate and external execution evidence directories required")
        allowed = {
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "SYSTEMDRIVE",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "PROGRAMDATA",
            "ALLUSERSPROFILE",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "USERNAME",
            "USERDOMAIN",
            "PATH",
            "TEMP",
            "TMP",
            "TMPDIR",
            "PYTHONDONTWRITEBYTECODE",
            "HOME",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "USER",
            "LOGNAME",
            "SHELL",
        }
        self.environment = {k: v for k, v in environment.items() if k.upper() in allowed}

    def run(self, argv, *, mode="workspace-write", stdin=b"", timeout=90, cancel=None):
        if mode not in ("workspace-write", "read-only"):
            raise RunError("unsupported command purpose")
        # Here read-only denotes a verification request, not OS access control.
        # The profile preview explicitly discloses this execution baseline.
        command = literal_command(argv)
        packet = self.output / ("local-command-" + str(uuid.uuid4()))
        packet.mkdir()
        (packet / "request.json").write_text(
            json.dumps({"baseline": self.baseline, "purpose": mode, "argv": command}), encoding="utf-8"
        )
        result = self.tree.run(
            command,
            self.project,
            stdin=stdin,
            env=self.environment,
            timeout=min(300, timeout),
            output_limit=2 * 1024 * 1024,
            cancelled=cancel,
            terminate_on_root_exit=True,
        )
        save_result(packet / "result.json", result)
        return result
