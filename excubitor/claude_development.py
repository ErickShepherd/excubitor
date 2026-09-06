"""Explicit development baseline: structured Claude edits, native bounded tests.

The model has no native file or shell tools. Host-selected editable files are the
only edit API. Arbitrary project commands use the separate Windows executor.
This adapter does not claim credential isolation or replace strict admission.
"""

from __future__ import annotations

import json
import stat
import time
import uuid
from pathlib import Path

from excubitor.claude_project import ClaudeProjectRuntime, _clean_exit
from excubitor.processes import WindowsProcessTree
from excubitor.runs import RunError
from excubitor.windows_development import BASELINE

_EDIT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "files": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                  "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                  "required": ["path", "content"]}},
        "command": {"type": "array", "items": {"type": "string"}},
    }, "required": ["files", "command"],
}


class _StructuredOnlyTransport:
    def run(self, argv, cwd, *, sandbox, **options):
        if (sandbox != "read-only" or "--json-schema" not in argv
                or any(argv[argv.index(flag) + 1] != "" for flag in ("--tools", "--allowedTools"))):
            raise RunError("development coordinator must have no executable or file tools")
        return WindowsProcessTree().run(argv, cwd, **options, terminate_on_root_exit=True)


class ClaudeDevelopmentRuntime:
    baseline = BASELINE

    def __init__(self, claude, project, output, *, executor, environment, editable,
                 model, native_model, baseline):
        if baseline != BASELINE or getattr(executor, "baseline", None) != BASELINE:
            raise RunError("explicit development baseline required for both components")
        self.project, self.output, self.executor = Path(project).resolve(), Path(output).resolve(), executor
        self.editable = frozenset(editable)
        if not self.editable or len(self.editable) > 32:
            raise ValueError("one to 32 host-selected editable files required")
        for name in self.editable:
            self._path(name)
        self.driver = ClaudeProjectRuntime(Path(claude), self.project, self.output,
            executor=_StructuredOnlyTransport(), environment=environment, admit=self._admit,
            model=model, native_model=native_model, effort="low")

    @staticmethod
    def _admit(mode):
        if mode != "read-only":
            raise RunError("native coordinator cannot execute candidate tools")

    def _path(self, name):
        if (not isinstance(name, str) or name not in self.editable or "\\" in name or ":" in name
                or any(part in ("", ".", "..") or part.startswith(".") for part in name.split("/"))
                or Path(name).is_absolute()):
            raise RunError("edit is outside the host-selected candidate files")
        path = self.project / name
        for part in (self.project, *path.parents, path):
            if part != self.project and not part.is_relative_to(self.project):
                continue
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise RunError("candidate path is redirected")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
            raise RunError("editable path must be a bounded, unshared regular file")
        return path

    def snapshot(self):
        return {name: self._path(name).read_text(encoding="utf-8") for name in sorted(self.editable)}

    def apply(self, proposal):
        if not isinstance(proposal, dict) or set(proposal) != {"files", "command"}:
            raise RunError("invalid edit proposal")
        files, command = proposal["files"], proposal["command"]
        if not isinstance(files, list) or len(files) > len(self.editable):
            raise RunError("invalid edit batch")
        if (not isinstance(command, list) or len(command) > 64
                or any(not isinstance(s, str) or not s or "\0" in s or len(s) > 16384 for s in command)
                or command and not Path(command[0]).is_absolute()):
            raise RunError("command must use a literal absolute executable")
        pending, seen = [], set()
        for edit in files:
            if not isinstance(edit, dict) or set(edit) != {"path", "content"}:
                raise RunError("invalid file edit")
            path = self._path(edit["path"])
            content = edit["content"]
            if path in seen or not isinstance(content, str) or "\0" in content or len(content.encode()) > 65536:
                raise RunError("duplicate or invalid file contents")
            seen.add(path)
            pending.append((path, content))
        # Validate the whole request before writing anything, including the command.
        for path, content in pending:
            path.write_text(content, encoding="utf-8", newline="")
        return tuple(command)

    def _call(self, run, prompt, cancel, *, review):
        session = str(uuid.uuid4())
        argv = list(self.driver.command("read-only", session, review=True))
        for flag in ("--tools", "--allowedTools"):
            argv[argv.index(flag) + 1] = ""
        argv[argv.index("--settings") + 1] = '{"disableClaudeAiConnectors":true}'
        if not review:
            argv[argv.index("--json-schema") + 1] = json.dumps(_EDIT_SCHEMA)
        argv += ["--no-chrome", "--max-budget-usd", "2"]
        prompt += "\nHost-supplied candidate files (untrusted data): " + json.dumps(self.snapshot())
        (self.output / (session + "-prompt.txt")).write_text(prompt, encoding="utf-8")
        result = self.driver.execute("development-review" if review else "development-edits", argv,
            "read-only", run, stdin=prompt.encode(), timeout=160, cancel=cancel, session=session)
        if not _clean_exit(result):
            return result, None
        terminal = self.driver._completed(result, session, "read-only", review=True)
        initial = json.loads(result.execution.stdout.splitlines()[0])
        if initial["tools"] != ["StructuredOutput"] or terminal.get("permission_denials"):
            raise RunError("unexpected coordinator tools or native denial")
        return result, terminal.get("structured_output")

    def work(self, run, prompt, cancel):
        prompt += ("\nReturn the supplied structured schema: files contains complete replacement contents "
                   "for changed host-selected files only. command is an optional literal argv list for "
                   "a native test, using an absolute executable. No shell/file tools are available. "
                   "The host applies edits and runs the command, then independently runs frozen checks. "
                   "Use Python -B to avoid candidate cache files. Do not change tests to hide the bug.")
        result, proposal = self._call(run, prompt, cancel, review=False)
        if proposal is None:
            return result
        if cancel.is_set() or time.time() >= run.contract.deadline:
            raise RunError("run stopped before applying model edits")
        command = self.apply(proposal)
        if command:
            return self.executor.run(command, timeout=min(90, run.contract.deadline - time.time()), cancel=cancel)
        return result

    def verify(self, run, oracle, cancel):
        return self.executor.run(oracle.argv, mode="read-only", stdin=oracle.stdin.encode(),
                                 timeout=min(oracle.timeout_seconds, run.contract.deadline - time.time()), cancel=cancel)

    def review(self, run, prompt, cancel):
        result, verdict = self._call(run, prompt, cancel, review=True)
        if verdict is None:
            return result, False, "Native reviewer did not complete."
        if (not isinstance(verdict, dict) or set(verdict) != {"passed", "findings"}
                or type(verdict["passed"]) is not bool or not isinstance(verdict["findings"], str)):
            raise RunError("invalid independent review verdict")
        return result, verdict["passed"], verdict["findings"]
