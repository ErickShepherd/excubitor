"""Vendor-independent, fresh-process JSON bridge for a host-selected model client."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from excubitor.development_runtime import clean_exit
from excubitor.model_response import failed_response
from excubitor.processes import WindowsProcessTree
from excubitor.runs import RunError

PROTOCOL = "excubitor.model.v1"


def literal_command(value):
    if (
        not isinstance(value, (list, tuple))
        or not 1 <= len(value) <= 64
        or any(not isinstance(s, str) or not s or "\0" in s or len(s) > 16384 for s in value)
        or not Path(value[0]).is_absolute()
        or not Path(value[0]).is_file()
    ):
        raise RunError("select an existing absolute executable and bounded literal arguments")
    return tuple(value)


def save_result(path, result):
    record = asdict(result)
    for key in ("stdout", "stderr"):
        record["execution"][key] = record["execution"][key].decode("utf-8", errors="replace")
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


class CommandStructuredModel:
    """The owner supplies a client, not a model-generated executable or shell string.

    Each invocation receives the complete current prompt on stdin. The client
    must start a fresh conversation and reserve stdout for one response envelope.
    Client code is trusted host integration, not an isolated untrusted plugin.
    """

    def __init__(self, command, output, *, environment, model):
        self.command = literal_command(command)
        self.output, self.environment, self.model = Path(output), dict(environment), model

    def generate(self, run, prompt, schema, cancel):
        remaining = run.contract.deadline - time.time()
        if remaining <= 0 or cancel.is_set():
            raise RunError("run stopped before model dispatch")
        identifier = str(uuid.uuid4())
        packet = self.output / ("model-" + identifier)
        packet.mkdir()
        request = {
            "protocol": PROTOCOL,
            "id": identifier,
            "model": self.model,
            "prompt": prompt,
            "schema": schema,
        }
        payload = json.dumps(request).encode()
        (packet / "request.json").write_bytes(payload)
        result = WindowsProcessTree().run(
            self.command,
            packet,
            stdin=payload,
            env=self.environment,
            timeout=min(160, remaining),
            output_limit=2 * 1024 * 1024,
            cancelled=cancel,
            terminate_on_root_exit=True,
        )
        save_result(packet / "result.json", result)
        if not clean_exit(result):
            return result, None
        try:
            response = json.loads(result.execution.stdout)
        except (ValueError, UnicodeError):
            message = "Return one complete JSON response matching the supplied schema."
            return failed_response(result, message), None
        if (
            not isinstance(response, dict)
            or any(response.get(key) != request[key] for key in ("protocol", "id", "model"))
        ):
            raise RunError("model bridge returned an invalid response: request identity does not match")
        if set(response) != {"protocol", "id", "model", "output"} or not isinstance(response["output"], dict):
            message = "Return the requested JSON object in the response output field."
            return failed_response(result, message), None
        return result, response["output"]
