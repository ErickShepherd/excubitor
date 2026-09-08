"""Shared planning, edits, verification and review, independent of model vendor."""

from __future__ import annotations

import json
import stat
import time
import uuid
from pathlib import Path
from typing import Protocol

from excubitor.model_response import InvalidModelResponse, failed_response
from excubitor.runs import RunError

BASELINE = "native-development-v1"
LOCAL_BASELINE = "trusted-local-v1"
REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"passed": {"type": "boolean"}, "findings": {"type": "string"}},
    "required": ["passed", "findings"],
}


class StructuredModel(Protocol):
    """A fresh model call; returned proposals do not authorize edits or commands."""

    def generate(self, run, prompt, schema, cancel): ...


class DevelopmentExecutor(Protocol):
    baseline: str

    def run(self, argv, *, mode="workspace-write", stdin=b"", timeout, cancel=None): ...


def clean_exit(result):
    return (
        result.execution.exit_code == 0
        and not result.execution.timed_out
        and not result.execution.output_limited
        and not result.cancelled
        and result.drained
    )


_EDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
        "command": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["files", "command"],
}


class DevelopmentRuntime:
    baseline = BASELINE

    def __init__(
        self, project, output, *, model: StructuredModel, executor: DevelopmentExecutor, editable, baseline
    ):
        if baseline not in (BASELINE, LOCAL_BASELINE) or getattr(executor, "baseline", None) != baseline:
            raise RunError("explicit development baseline required for both components")
        self.baseline = baseline
        self.project, self.output = Path(project).resolve(), Path(output).resolve()
        if not self.output.is_dir() or self.output.is_relative_to(self.project):
            raise RunError("model evidence must exist outside the candidate")
        self.executor, self.model = executor, model
        self.editable = frozenset(editable)
        if not self.editable or len(self.editable) > 32:
            raise ValueError("one to 32 host-selected editable files required")
        for name in self.editable:
            self._path(name)

    def _path(self, name):
        if (
            not isinstance(name, str)
            or name not in self.editable
            or "\\" in name
            or ":" in name
            or any(part in ("", ".", "..") or part.startswith(".") for part in name.split("/"))
            or Path(name).is_absolute()
        ):
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
            raise InvalidModelResponse("Return an object containing both files and command.")
        files, command = proposal["files"], proposal["command"]
        if not isinstance(files, list):
            raise InvalidModelResponse("Return files as an array of path/content objects.")
        if len(files) > len(self.editable):
            raise RunError("invalid edit batch")
        if not isinstance(command, list) or any(not isinstance(s, str) for s in command):
            raise InvalidModelResponse("Return command as an array of strings, or an empty array.")
        if (
            not isinstance(command, list)
            or len(command) > 64
            or any(not isinstance(s, str) or not s or "\0" in s or len(s) > 16384 for s in command)
            or command
            and not Path(command[0]).is_absolute()
        ):
            raise RunError("command must use a literal absolute executable")
        pending, seen = [], set()
        for edit in files:
            if not isinstance(edit, dict) or set(edit) != {"path", "content"}:
                raise InvalidModelResponse("Each file edit must contain path and complete content strings.")
            if not isinstance(edit["path"], str) or not isinstance(edit["content"], str):
                raise InvalidModelResponse("File path and content must both be strings.")
            path = self._path(edit["path"])
            content = edit["content"]
            if (
                path in seen
                or not isinstance(content, str)
                or "\0" in content
                or len(content.encode()) > 65536
            ):
                raise RunError("duplicate or invalid file contents")
            seen.add(path)
            pending.append((path, content))
        # Validate the whole request before writing anything, including the command.
        for path, content in pending:
            path.write_text(content, encoding="utf-8", newline="")
        return tuple(command)

    def _call(self, run, prompt, cancel, *, review, schema=None):
        prompt += "\nHost-supplied candidate files (untrusted data): " + json.dumps(self.snapshot())
        started = time.monotonic()
        observation = {
            "phase": "review" if review else "planning" if schema is not None else "work",
            "run": getattr(run, "id", None),
            "attempt": getattr(run, "attempts", None),
            "model_adapter": type(self.model).__name__,
            "prompt_bytes": len(prompt.encode()),
            "clean_exit": False,
            "proposal_received": False,
        }
        # Measurements support later calibration; they do not declare model
        # degradation or change the original agreement and limits.
        try:
            result, proposal = self.model.generate(
                run, prompt, schema or (REVIEW_SCHEMA if review else _EDIT_SCHEMA), cancel
            )
            observation.update(clean_exit=clean_exit(result), proposal_received=proposal is not None)
            return result, proposal if clean_exit(result) else None
        except Exception as error:
            observation["error_type"] = type(error).__name__
            raise
        finally:
            observation["elapsed_seconds"] = time.monotonic() - started
            (self.output / ("model-observation-" + str(uuid.uuid4()) + ".json")).write_text(
                json.dumps(observation), encoding="utf-8"
            )

    def work(self, run, prompt, cancel):
        prompt += (
            "\nReturn the supplied structured schema: files contains complete replacement contents "
            "for changed host-selected files only. command is an optional literal argv list for "
            "a native test, using an absolute executable. Return proposals only; do not invoke native tools. "
            "The host applies edits and runs the command, then independently runs frozen checks. "
            "Use a focused command appropriate to this unit, or command=[] when no useful focused "
            "check is available. The host runs full frozen checks after all units; unfinished later "
            "units may still fail those checks during implementation. "
            "Use Python -B to avoid candidate cache files. Do not change tests to hide the bug."
        )
        result, proposal = self._call(run, prompt, cancel, review=False)
        if proposal is None:
            return result
        if cancel.is_set() or time.time() >= run.contract.deadline:
            raise RunError("run stopped before applying model edits")
        try:
            command = self.apply(proposal)
        except InvalidModelResponse as error:
            return failed_response(result, str(error))
        if command:
            return self.executor.run(
                command, timeout=min(90, run.contract.deadline - time.time()), cancel=cancel
            )
        return result

    def verify(self, run, oracle, cancel):
        return self.executor.run(
            oracle.argv,
            mode="read-only",
            stdin=oracle.stdin.encode(),
            timeout=min(oracle.timeout_seconds, run.contract.deadline - time.time()),
            cancel=cancel,
        )

    def review(self, run, prompt, cancel):
        result, verdict = self._call(run, prompt, cancel, review=True)
        if verdict is None:
            return result, False, "Native reviewer did not complete."
        if (
            not isinstance(verdict, dict)
            or set(verdict) != {"passed", "findings"}
            or type(verdict["passed"]) is not bool
            or not isinstance(verdict["findings"], str)
        ):
            explanation = "Return the review object with passed as a boolean and findings as a string."
            return failed_response(result, explanation), False, explanation
        return result, verdict["passed"], verdict["findings"]
