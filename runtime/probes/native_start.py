"""Disposable MCP confirmation observer. Never starts or authorizes a Ralph run.

Launch with the native CLI's process-only MCP configuration overrides. The single
tool requests a harmless native form and records transport observations. It has
no lifecycle store, privileged mutation endpoint, registration, or trust writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Observer:
    def __init__(self, emit, record):
        self.emit = emit
        self.record = record
        self.client = None
        self.pending = {}
        self.counter = 0

    def reply(self, request_id, result):
        self.emit({"jsonrpc": "2.0", "id": request_id, "result": result})

    def receive(self, message):
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            params = message["params"]
            self.client = params.get("capabilities", {})
            self.record(
                {"event": "initialize", "client": params.get("clientInfo"), "capabilities": self.client}
            )
            self.reply(
                request_id,
                {
                    "protocolVersion": params["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "excubitor-start-observer", "version": "0.1"},
                },
            )
        elif method == "tools/list":
            self.reply(
                request_id,
                {
                    "tools": [
                        {
                            "name": "confirm_probe",
                            "description": "Request a harmless native confirmation test. "
                            "Does not start Ralph or grant access.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": False,
                            },
                            "annotations": {"readOnlyHint": True, "openWorldHint": False},
                        }
                    ]
                },
            )
        elif method == "tools/call":
            params = message.get("params", {})
            self.record(
                {
                    "event": "tool_call",
                    "keys": sorted(params),
                    "meta": params.get("_meta", {}),
                    "arguments": params.get("arguments"),
                }
            )
            if params.get("name") != "confirm_probe" or params.get("arguments", {}) != {}:
                self.reply(
                    request_id,
                    {"isError": True, "content": [{"type": "text", "text": "Unexpected probe arguments."}]},
                )
                return
            if self.client is None or "elicitation" not in self.client:
                self.reply(
                    request_id,
                    {
                        "isError": True,
                        "content": [{"type": "text", "text": "Native elicitation unavailable."}],
                    },
                )
                return
            self.counter += 1
            token = f"probe-confirmation-{self.counter}"
            self.pending[token] = request_id
            self.emit(
                {
                    "jsonrpc": "2.0",
                    "id": token,
                    "method": "elicitation/create",
                    "params": {
                        "mode": "form",
                        "message": "Excubitor disposable confirmation test. This records your response only. "
                        "It starts no Ralph run and grants no filesystem, merge, or publishing permission.",
                        "requestedSchema": {
                            "type": "object",
                            "properties": {
                                "confirm": {
                                    "type": "boolean",
                                    "title": "Confirm the harmless test",
                                    "default": False,
                                },
                            },
                            "required": ["confirm"],
                        },
                    },
                }
            )
        elif method == "ping":
            self.reply(request_id, {})
        elif method is None and request_id in self.pending:
            original = self.pending.pop(request_id)
            result = message.get("result", {})
            accepted = result.get("action") == "accept" and result.get("content") == {"confirm": True}
            self.record(
                {
                    "event": "confirmation_result",
                    "result": result,
                    "error": message.get("error"),
                    "accepted": accepted,
                }
            )
            self.reply(
                original,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "confirmation_observed": accepted,
                                    "ralph_started": False,
                                    "limitation": "UI observation only; no owner authority established.",
                                }
                            ),
                        }
                    ]
                },
            )
        elif method and not method.startswith("notifications/") and request_id is not None:
            self.emit(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Unknown probe method"},
                }
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error("output must be an absolute create-only file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as log:

        def record(value):
            log.write(json.dumps(value, sort_keys=True) + "\n")
            log.flush()

        def emit(value):
            print(json.dumps(value), flush=True)

        record(
            {
                "event": "process_start",
                "native_identity_environment": {
                    name: fingerprint(os.environ[name])
                    for name in ("CODEX_THREAD_ID", "CLAUDE_SESSION_ID")
                    if name in os.environ
                },
            }
        )
        observer = Observer(emit, record)
        for line in sys.stdin:
            observer.receive(json.loads(line))
        record({"event": "stdin_closed", "pending": len(observer.pending)})


if __name__ == "__main__":
    main()
