"""Ralph start/status protocol for an admitted native MCP connection.

The native adapter supplies authenticated metadata, a trusted planner and a
nonblocking host launcher. No tool argument grants approval or selects executable
code, storage, run identity, recovery evidence, or completion authority.
Installing this Python module does not register a tool in any app.
"""

from __future__ import annotations

import uuid
from typing import Callable

from excubitor.acceptance import OutputOracle
from excubitor.approval import StartHandshake
from excubitor.runs import Binding, Contract, Run, RunError, RunStore


class RalphAction:
    def __init__(
        self,
        store: RunStore,
        emit: Callable[[dict], None],
        binding: Callable[[dict], Binding],
        plan: Callable[[Binding], tuple[Contract, tuple[OutputOracle, ...]]],
        launch: Callable[[Run], None],
    ):
        self.gate, self.emit = StartHandshake(store), emit
        self.binding, self.plan, self.launch = binding, plan, launch
        self.pending = {}
        self.form_supported = False

    def reply(self, request_id, text, *, error=False):
        self.emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "isError": error,
                    "content": [{"type": "text", "text": text}],
                },
            }
        )

    def receive(self, message: dict) -> None:
        method, request_id = message.get("method"), message.get("id")
        if method == "initialize":
            params = message["params"]
            elicitation = params.get("capabilities", {}).get("elicitation", {})
            self.form_supported = isinstance(elicitation, dict) and "form" in elicitation
            self.emit(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": params["protocolVersion"],
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "excubitor-ralph", "version": "0.1"},
                    },
                }
            )
        elif method == "tools/list":
            self.emit(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": name,
                                "description": description,
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "additionalProperties": False,
                                },
                                "annotations": {
                                    "readOnlyHint": name == "ralph_status",
                                    "openWorldHint": False,
                                },
                            }
                            for name, description in (
                                (
                                    "ralph_start",
                                    "Preview the agreed Ralph job and request native owner confirmation. "
                                "Starts only after acceptance. Ordinary development needs no Ralph action.",
                                ),
                                (
                                    "ralph_status",
                                    "Read the active Ralph state for this exact native task and project.",
                                ),
                            )
                        ]
                    },
                }
            )
        elif method == "tools/call":
            try:
                params = message.get("params", {})
                if params.get("arguments", {}) != {}:
                    raise RunError("Ralph actions accept no approval or authority arguments")
                name = params.get("name")
                if name not in ("ralph_start", "ralph_status"):
                    raise RunError("unknown Ralph action")
                binding = self.binding(params.get("_meta", {}))
                if name == "ralph_status":
                    run = self.gate.store.lookup(binding)
                    self.reply(
                        request_id, f"Ralph is {run.state}." if run else "No active Ralph job in this task."
                    )
                else:
                    if not self.form_supported:
                        raise RunError("this native connection does not provide owner form confirmation")
                    contract, oracles = self.plan(binding)
                    confirmation = self.gate.prepare(binding, contract, oracles)
                    token = "ralph-confirm-" + uuid.uuid4().hex
                    self.pending[token] = (request_id, confirmation.id)
                    self.emit(
                        {
                            "jsonrpc": "2.0",
                            "id": token,
                            "method": "elicitation/create",
                            "params": confirmation.request,
                        }
                    )
            except (RunError, ValueError) as exc:
                self.reply(request_id, str(exc), error=True)
        elif method is None and request_id in self.pending:
            original, confirmation = self.pending.pop(request_id)
            run = None
            try:
                run = self.gate.answer(confirmation, {} if "error" in message else message.get("result", {}))
                if run is None:
                    self.reply(original, "Ralph was not started.")
                else:
                    self.launch(run)
                    self.reply(
                        original, "Ralph started for the confirmed job. It will run within the agreed limits."
                    )
            except Exception as exc:
                if run is not None:
                    current = self.gate.store.get(run.id)
                    if current.state == "running":
                        self.gate.store.interrupt(current)
                self.reply(original, f"Ralph start could not finish: {exc}", error=True)
        elif method == "notifications/cancelled":
            original = message.get("params", {}).get("requestId")
            for token, (pending, confirmation) in list(self.pending.items()):
                if pending == original:
                    del self.pending[token]
                    self.gate.discard(confirmation)
        elif method == "ping":
            self.emit({"jsonrpc": "2.0", "id": request_id, "result": {}})
        elif method and not method.startswith("notifications/") and request_id is not None:
            self.emit(
                {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Unknown method"}}
            )

    def close(self):
        # Connection closure retires pending offers, never attests worker drainage
        # or ends already accepted authority. The host supervisor owns those facts.
        self.pending.clear()
        self.gate.close()
