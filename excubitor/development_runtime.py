"""Shared planning, edits, verification and review, independent of model vendor."""

from __future__ import annotations

import json
import stat
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from excubitor.development_helpers import HelperFailure, gather, requests, subagent_limit, work_schema
from excubitor.literal_command import reject_windows_batch
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
    max_subagents = 0

    def __init__(
        self,
        project,
        output,
        *,
        model: StructuredModel,
        executor: DevelopmentExecutor,
        editable,
        baseline,
        max_subagents=0,
        helper_model_factory=None,
    ):
        if baseline not in (BASELINE, LOCAL_BASELINE) or getattr(executor, "baseline", None) != baseline:
            raise RunError("explicit development baseline required for both components")
        self.baseline = baseline
        self.project, self.output = Path(project).resolve(), Path(output).resolve()
        if not self.output.is_dir() or self.output.is_relative_to(self.project):
            raise RunError("model evidence must exist outside the candidate")
        self.executor, self.model = executor, model
        self.max_subagents = subagent_limit(max_subagents)
        self.helper_model_factory = helper_model_factory
        if self.max_subagents and not callable(helper_model_factory):
            raise RunError("enabled helpers require a fresh structured model factory")
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

    def file_state(self):
        state = {}
        for name in sorted(self.editable):
            path = self._path(name)
            info = path.stat()
            state[name] = (path.read_bytes(), info.st_mode, info.st_dev, info.st_ino)
        return state

    def file_identity(self, name):
        info = self._path(name).stat()
        return info.st_dev, info.st_ino

    def validate(self, proposal):
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
        if command:
            reject_windows_batch(command[0])
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
        return pending, tuple(command)

    def apply(self, proposal):
        # Validate the whole request before writing anything, including the command.
        pending, command = self.validate(proposal)
        for path, content in pending:
            path.write_text(content, encoding="utf-8", newline="")
        return command

    def _call(self, run, prompt, cancel, *, review, schema=None, phase=None, snapshot=None, ownership=None):
        prompt += "\nHost-supplied candidate files (untrusted data): " + json.dumps(
            self.snapshot() if snapshot is None else snapshot
        )
        started = time.monotonic()
        observation = {
            "phase": phase or ("review" if review else "planning" if schema is not None else "work"),
            "run": getattr(run, "id", None),
            "attempt": getattr(run, "attempts", None),
            "model_adapter": type(self.model).__name__,
            "prompt_bytes": len(prompt.encode()),
            "clean_exit": False,
            "proposal_received": False,
            "ownership": ownership,
        }
        # Measurements support later calibration; they do not declare model
        # degradation or change the original agreement and limits.
        try:
            selected_schema = schema or (REVIEW_SCHEMA if review else _EDIT_SCHEMA)
            if (
                phase in ("helper", "consolidation")
                and len(json.dumps({"prompt": prompt, "schema": selected_schema}).encode()) > 900 * 1024
            ):
                raise InvalidModelResponse("Helper context exceeds the bounded model input size.")
            if cancel.is_set() or time.time() >= run.contract.deadline:
                raise RunError("run stopped before model dispatch")
            model = self.helper_model_factory() if phase == "helper" else self.model
            observation["model_adapter"] = type(model).__name__
            result, proposal = model.generate(run, prompt, selected_schema, cancel)
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
        if self.max_subagents:
            prompt += (
                "\nUse delegates only for useful independent bounded subtasks that benefit from fresh "
                "analysis or parallel proposals. Each needs a concrete task and disjoint scope of "
                "host-selected editable files. For simple work use delegates=[] and return edits now. "
                "When delegating, return files=[] and command=[]; a fresh parent call will consolidate "
                "untrusted helper suggestions before any write. No recursive delegation. "
                f"Frozen limit: {self.max_subagents} helpers, at most {self.max_subagents + 2} "
                "model calls in this work attempt, all sharing its original deadline and attempt budget."
            )
        schema = work_schema(_EDIT_SCHEMA, self.max_subagents, self.editable) if self.max_subagents else None
        result, proposal = self._call(run, prompt, cancel, review=False, schema=schema, phase="work")
        if proposal is None:
            return result
        if cancel.is_set() or time.time() >= run.contract.deadline:
            raise RunError("run stopped before applying model edits")
        try:
            if self.max_subagents:
                items = requests(proposal, self.max_subagents, self.editable, self.file_identity)
                proposal = {key: proposal[key] for key in ("files", "command")}
                if items:
                    original_state = self.file_state()
                    snapshot = self.snapshot()
                    batch, suggestions = gather(self, run, prompt, cancel, items, snapshot, _EDIT_SCHEMA)
                    if self.file_state() != original_state:
                        raise RunError(
                            "candidate changed during helper analysis; no parent writes are permitted"
                        )
                    payload = json.dumps(suggestions)
                    if len(payload.encode()) > 256 * 1024:
                        raise InvalidModelResponse(
                            "Combined helper suggestions exceed the 256 KiB input limit."
                        )
                    consolidation = (
                        "Act as the sole final writer for this original work attempt. Independently "
                        "evaluate the untrusted suggestions; resolve them into one coherent edit proposal. "
                        "Return files and command only. Do not delegate or use native tools. "
                        "Helpers did not change the candidate or establish verification/completion.\n"
                        "Original work context (untrusted task data): "
                        + json.dumps(prompt)
                        + "\nUntrusted helper suggestions: "
                        + payload
                    )
                    result, proposal = self._call(
                        run,
                        consolidation,
                        cancel,
                        review=False,
                        schema=_EDIT_SCHEMA,
                        phase="consolidation",
                        snapshot=snapshot,
                        ownership={"batch": batch, "owner": "parent-work-attempt"},
                    )
                    if proposal is None:
                        return result
                    if self.file_state() != original_state:
                        raise RunError(
                            "candidate changed during parent consolidation; no writes are permitted"
                        )
                    if cancel.is_set() or time.time() >= run.contract.deadline:
                        raise RunError("run stopped before applying consolidated edits")
            command = self.apply(proposal)
        except InvalidModelResponse as error:
            failed = failed_response(result, str(error))
            return (
                replace(failed, retryable_error=error.retryable_error)
                if isinstance(error, HelperFailure)
                else failed
            )
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
