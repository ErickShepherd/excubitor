"""Ralph start/status protocol for an admitted native MCP connection.

The native adapter supplies authenticated metadata, a trusted planner and a
nonblocking host launcher. An optional planner accepts untrusted job proposals for
native confirmation. No tool argument grants approval or selects host executable
code, storage, run identity, recovery evidence, or completion authority.
Installing this Python module does not register a tool in any app.
"""

from __future__ import annotations

import json
import uuid
from typing import Callable

from excubitor.acceptance import OutputOracle
from excubitor.approval import StartHandshake
from excubitor.job_setup import JobPlanner
from excubitor.runs import Binding, Contract, Run, RunError, RunStore


class RalphAction:
    def __init__(
        self,
        store: RunStore,
        emit: Callable[[dict], None],
        binding: Callable[[dict], Binding],
        plan: Callable[[Binding], tuple[Contract, tuple[OutputOracle, ...]]],
        launch: Callable[[Run], None],
        reconnect: Callable[[Run], None] | None = None,
        is_attached: Callable[[Run], bool] | None = None,
        drafts: JobPlanner | None = None,
    ):
        self.gate, self.emit = StartHandshake(store), emit
        self.binding, self.plan, self.launch = binding, plan, launch
        self.reconnect = reconnect
        self.is_attached = is_attached
        self.drafts = drafts
        self.attached = set()
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

    def status(self, binding: Binding) -> str:
        active = self.gate.store.lookup(binding)
        if self.drafts is None:
            return f"Ralph is {active.state}." if active else "No active Ralph job in this task."
        if active is not None:
            return (
                f"Ralph is {active.state}: {active.completed_units} of {len(active.contract.units)} units; "
                f"{active.attempts} of {active.contract.max_attempts} attempts used."
            )
        previous = self.gate.store.latest(binding)
        text = "No active Ralph job in this task."
        if previous is not None and previous.state == "complete":
            text += (
                f" Last job completed: {json.dumps(previous.contract.goal)}. "
                f"{previous.completed_units} units; {previous.attempts} of "
                f"{previous.contract.max_attempts} attempts used. All original checks and independent "
                "review passed; verified work was retained on an isolated committed branch. "
                "This is the recorded completion result, not a check of later ordinary edits."
            )
        elif previous is not None and previous.state == "cancelled":
            text += " The last job was cancelled; no completion is claimed."
        return text

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
                                    "properties": {"job": self.drafts.schema}
                                    if name == "ralph_start" and self.drafts is not None
                                    else {},
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
                                    "Confirm a new Ralph job or reconnect this task's existing job "
                                    "within its original limits. Ordinary development needs no Ralph action."
                                    + (
                                        " For a new job, propose goal, units, and checks in job; "
                                        "omit limits to reuse host defaults. Only native owner confirmation "
                                        "starts work. To reconnect, call with no arguments."
                                        if self.drafts is not None
                                        else ""
                                    ),
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
                if self.gate.closed:
                    raise RunError("this native connection is closed")
                params = message.get("params", {})
                if not isinstance(params, dict):
                    raise RunError("Ralph action parameters must be an object")
                name = params.get("name")
                if name not in ("ralph_start", "ralph_status"):
                    raise RunError("unknown Ralph action")
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict) or (
                    arguments and (name != "ralph_start" or self.drafts is None or set(arguments) != {"job"})
                ):
                    raise RunError("Ralph actions accept only job proposals, never approval or authority")
                binding = self.binding(params.get("_meta", {}))
                if name == "ralph_status":
                    self.reply(request_id, self.status(binding))
                else:
                    existing = self.gate.store.lookup(binding)
                    if existing is not None:
                        if arguments:
                            raise RunError(
                                "this task already has an agreed job; reconnect with no arguments "
                                "to preserve its original scope and limits"
                            )
                        attached = (
                            self.is_attached(existing)
                            if self.is_attached is not None
                            else existing.id in self.attached
                        )
                        if attached:
                            self.reply(
                                request_id, f"Ralph is already attached to this task: {existing.state}."
                            )
                        elif existing.state not in ("running", "interrupted"):
                            self.reply(
                                request_id, f"Ralph is {existing.state}; its original limits remain in force."
                            )
                        elif self.reconnect is None:
                            raise RunError(
                                "this native adapter does not yet support reconnecting an existing job"
                            )
                        else:
                            self.reconnect(existing)
                            self.attached.add(existing.id)
                            self.reply(
                                request_id,
                                "Reconnecting the agreed Ralph job. The controller will check "
                                "old-worker shutdown before proceeding within the original limits.",
                            )
                        return
                    if not self.form_supported:
                        raise RunError("this native connection does not provide owner form confirmation")
                    if self.pending:
                        raise RunError("finish or cancel the pending native confirmation first")
                    if self.drafts is not None:
                        if not arguments:
                            raise RunError(
                                "propose the new job's goal, units, and checks through Ralph Start"
                            )
                        contract, oracles = self.drafts(binding, arguments["job"])
                    else:
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
                    self.attached.add(run.id)
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
