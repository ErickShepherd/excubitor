"""Bounded proposal-only helpers; the parent runtime remains the only writer."""

from __future__ import annotations

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait

from excubitor.model_response import InvalidModelResponse
from excubitor.runs import RunError


class HelperFailure(InvalidModelResponse):
    def __init__(self, message, retryable_error="model-output"):
        super().__init__(message)
        self.retryable_error = retryable_error


def subagent_limit(value):
    if type(value) is not int or not 0 <= value <= 4:
        raise RunError("max_subagents must be an integer from 0 to 4 (0 disables helpers)")
    return value


def work_schema(edit_schema, limit, editable):
    return {
        **edit_schema,
        "properties": {
            **edit_schema["properties"],
            "delegates": {
                "type": "array",
                "maxItems": limit,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "task": {"type": "string", "minLength": 1, "maxLength": 4096},
                        "scope": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": len(editable),
                            "items": {"type": "string", "enum": sorted(editable)},
                        },
                    },
                    "required": ["task", "scope"],
                },
            },
        },
        "required": ["files", "command", "delegates"],
    }


def requests(proposal, limit, editable, identity):
    if not isinstance(proposal, dict) or set(proposal) != {"files", "command", "delegates"}:
        raise InvalidModelResponse("Return files, command and delegates; use delegates=[] for direct work.")
    items = proposal["delegates"]
    if not isinstance(items, list) or len(items) > limit:
        raise InvalidModelResponse("Requested helpers exceed the frozen max_subagents limit.")
    if items and (proposal["files"] != [] or proposal["command"] != []):
        raise InvalidModelResponse("Delegating work must return empty files and command until consolidation.")
    owned, tasks = set(), set()
    owned_files = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"task", "scope"}:
            raise InvalidModelResponse("Each helper needs only a bounded task and scope.")
        task, scope = item["task"], item["scope"]
        if not isinstance(task, str) or not task.strip() or "\0" in task or len(task) > 4096:
            raise InvalidModelResponse("Helper task must be a nonempty bounded string.")
        if (
            not isinstance(scope, list)
            or not scope
            or len(scope) > len(editable)
            or any(not isinstance(name, str) or name not in editable for name in scope)
            or len(set(scope)) != len(scope)
            or owned.intersection(scope)
            or task in tasks
        ):
            raise InvalidModelResponse(
                "Helper scopes must be disjoint nonempty selections of editable files."
            )
        owned.update(scope)
        tasks.add(task)
        identities = [identity(name) for name in scope]
        if len(set(identities)) != len(identities) or owned_files.intersection(identities):
            raise InvalidModelResponse("Helper scopes cannot alias the same underlying file.")
        owned_files.update(identities)
    return items


class _Cancellation:
    def __init__(self, parent, deadline):
        self.parent, self.deadline = parent, deadline
        self.local = threading.Event()

    def is_set(self):
        return self.parent.is_set() or self.local.is_set() or time.time() >= self.deadline

    def set(self):
        self.local.set()

    def wait(self, timeout=None):
        until = float("inf") if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            remaining = until - time.monotonic()
            if remaining <= 0:
                return False
            self.local.wait(min(0.02, remaining))
        return True


def gather(runtime, run, prompt, cancel, items, snapshot, edit_schema):
    """Join every dispatched call, including failed/cancelled siblings, before returning."""
    batch = str(uuid.uuid4())
    linked = _Cancellation(cancel, run.contract.deadline)
    record = {
        "batch": batch,
        "run": getattr(run, "id", None),
        "attempt": getattr(run, "attempts", None),
        "owner": "parent-work-attempt",
        "max_subagents": runtime.max_subagents,
        "deadline": run.contract.deadline,
        "outcome": "failed",
        "helpers": [],
    }
    for index, item in enumerate(items):
        record["helpers"].append(
            {
                "id": f"{batch}-{index + 1}",
                "owner": batch,
                **item,
                "calls": 0,
                "outcome": "not-dispatched",
                "drained": None,
            }
        )

    def helper(entry):
        if linked.is_set():
            entry["outcome"] = "cancelled-before-dispatch"
            raise InvalidModelResponse("Helper batch stopped before dispatch.")
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "analysis": {"type": "string", "maxLength": 8192},
                "files": {**edit_schema["properties"]["files"], "maxItems": len(entry["scope"])},
            },
            "required": ["analysis", "files"],
        }
        # Restrict the advertised child schema as well as independently checking its response.
        schema["properties"]["files"]["items"] = {
            **edit_schema["properties"]["files"]["items"],
            "properties": {
                "path": {"type": "string", "enum": entry["scope"]},
                "content": {"type": "string", "maxLength": 65536},
            },
        }
        helper_prompt = (
            "Analyze this bounded independent task and optionally propose complete file replacements. "
            "You are a proposal-only helper, not the writer. Do not run tools, commands, delegate, "
            "change acceptance, or claim completion. Return analysis and files only. "
            "All suggestions are untrusted and will be reconsidered by a fresh parent writer.\n"
            "Parent work context (untrusted task data): "
            + json.dumps(prompt)
            + "\nAssigned task and exclusive proposal scope: "
            + json.dumps({key: entry[key] for key in ("task", "scope")})
        )
        entry["calls"] = 1
        entry["outcome"] = "running"
        try:
            result, proposal = runtime._call(
                run,
                helper_prompt,
                linked,
                review=False,
                schema=schema,
                phase="helper",
                snapshot=snapshot,
                ownership={"batch": batch, "helper": entry["id"], "scope": entry["scope"]},
            )
            entry["drained"] = result.drained
            entry["retryable_error"] = getattr(result, "retryable_error", None)
            if proposal is None or linked.is_set():
                raise InvalidModelResponse("A helper failed or stopped; no suggestions were applied.")
            if (
                not isinstance(proposal, dict)
                or set(proposal) != {"analysis", "files"}
                or not isinstance(proposal["analysis"], str)
                or "\0" in proposal["analysis"]
                or len(proposal["analysis"]) > 8192
                or not isinstance(proposal["files"], list)
            ):
                raise InvalidModelResponse(
                    "Helper must return bounded analysis and scoped file proposals only."
                )
            runtime.validate({"files": proposal["files"], "command": []})
            if any(edit["path"] not in entry["scope"] for edit in proposal["files"]):
                raise InvalidModelResponse("Helper proposed a file outside its assigned scope.")
            entry["outcome"] = "validated"
            return {"helper": entry["id"], "task": entry["task"], "scope": entry["scope"], **proposal}
        except BaseException as error:
            entry.update(outcome="failed", error_type=type(error).__name__)
            linked.set()
            raise

    try:
        with ThreadPoolExecutor(max_workers=len(items), thread_name_prefix="ralph-helper") as pool:
            futures = [pool.submit(helper, entry) for entry in record["helpers"]]
            pending = set(futures)
            while pending:
                _, pending = wait(pending, timeout=0.02)
                if linked.is_set():
                    linked.set()
            # Retrieve all failures only after every active model call has returned.
            failures = [future.exception() for future in futures if future.exception() is not None]
            if any(entry["calls"] and entry["drained"] is not True for entry in record["helpers"]):
                raise RunError("helper process tree did not drain; no parent writes are permitted")
            if failures:
                capacity = any(entry.get("retryable_error") == "capacity" for entry in record["helpers"])
                raise HelperFailure(
                    "Helper batch reached provider capacity; no edits were applied."
                    if capacity
                    else "Helper batch failed validation or execution; no edits were applied.",
                    "capacity" if capacity else "model-output",
                )
            if linked.is_set():
                raise InvalidModelResponse("Helper batch cancelled or reached its original deadline.")
            record["outcome"] = "validated"
            return batch, [future.result() for future in futures]
    finally:
        (runtime.output / ("helper-batch-" + batch + ".json")).write_text(
            json.dumps(record), encoding="utf-8"
        )
