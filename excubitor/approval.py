"""One-shot owner confirmation on a host-owned native transport.

This is an internal controller component, not a general MCP authorization server.
Only a native adapter with an independently trusted connection may supply context
or deliver elicitation responses. Client names, JSON metadata, and an `accept`
string alone do not authenticate a peer or attest complete worker containment.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from excubitor.acceptance import OutputOracle
from excubitor.runs import Binding, Conflict, Contract, NotReady, Run, RunStore


def codex_binding(meta: dict) -> Binding:
    """Normalize host-supplied MCP metadata, never a tool's arguments or JSON file.

    Only the observed Windows interactive CLI envelope is handled. These checks
    reject conflicting context; they do not authenticate arbitrary JSON input.
    """
    try:
        context = meta["x-codex-turn-metadata"]
        session = meta["threadId"]
        if (
            not isinstance(session, str)
            or not session
            or context["thread_id"] != session
            or context["session_id"] != session
            or context["sandbox"] != "windows_elevated"
            or context["sandbox_mode"] != "workspace-write"
            or context["auto_review_enabled"] is not False
            or context["thread_source"] != "user"
        ):
            raise ValueError("unsupported or conflicting native context")
        workspaces = context["workspaces"]
        if not isinstance(workspaces, dict) or len(workspaces) != 1:
            raise ValueError("this adapter requires one exact native workspace")
        return Binding("codex-cli", session, next(iter(workspaces)))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise NotReady("native Codex context is missing, conflicting, or outside the observed mode") from exc


@dataclass(frozen=True)
class Confirmation:
    id: str
    contract: Contract
    oracles: tuple[OutputOracle, ...]
    expires_at: float

    @property
    def request(self) -> dict:
        contract = self.contract
        deadline = datetime.fromtimestamp(contract.deadline, tz=timezone.utc).isoformat()
        message = "\n".join(
            [
                "Start this Ralph job in this task?",
                f"Project: {json.dumps(contract.binding.project)}",
                f"Work: {json.dumps(contract.goal)}",
                "Units: " + ", ".join(json.dumps(unit) for unit in contract.units),
                f"Limits: {contract.max_attempts} attempts; deadline {deadline}.",
                "Completion: verified, reviewed work retained on an isolated branch.",
                "Acceptance checks:",
                *(oracle.description for oracle in self.oracles),
            ]
        )
        return {
            "mode": "form",
            "message": message,
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean", "title": "Start the agreed job", "default": False},
                },
                "required": ["confirm"],
            },
        }


class StartHandshake:
    """One instance per trusted connection. Responses cannot cross instances.

    Native transport cancellation and EOF must call discard/close. No start occurs
    during prepare, a timeout, malformed replies, or a rejected confirmation.
    """

    def __init__(self, store: RunStore, *, clock: Callable[[], float] = time.monotonic):
        self.store = store
        self.clock = clock
        self.pending: dict[str, Confirmation] = {}
        self.closed = False

    def prepare(
        self, binding: Binding, contract: Contract, oracles: tuple[OutputOracle, ...]
    ) -> Confirmation:
        if self.closed or contract.deadline <= self.store.clock():
            raise NotReady("connection is closed or the proposed job already expired")
        if not isinstance(oracles, tuple) or any(not isinstance(oracle, OutputOracle) for oracle in oracles):
            raise ValueError("acceptance definitions must be an immutable tuple")
        if binding != contract.binding or tuple(oracle.check for oracle in oracles) != contract.checks:
            raise Conflict("owner preview does not match the exact native scope and frozen acceptance bytes")
        if self.store.lookup(binding) is not None:
            raise Conflict("this native task already has an active job")
        if self.pending:
            raise Conflict("finish the pending owner decision before requesting another")
        confirmation = Confirmation(str(uuid.uuid4()), contract, oracles, self.clock() + 300)
        if len(json.dumps(confirmation.request).encode()) > 32768:
            raise NotReady("the job preview is too large for this confirmation form")
        self.pending[confirmation.id] = confirmation
        return confirmation

    def answer(self, request_id: str, result: dict) -> Run | None:
        confirmation = self.pending.pop(request_id, None)
        if confirmation is None:
            raise Conflict("confirmation is unknown, cancelled, consumed, or belongs to another connection")
        if self.clock() >= confirmation.expires_at:
            raise NotReady("owner confirmation expired; no job started")
        if (
            not isinstance(result, dict)
            or set(result) != {"action", "content"}
            or result["action"] != "accept"
            or result["content"] != {"confirm": True}
            or type(result["content"].get("confirm")) is not bool
        ):
            return None
        # Create immutable definitions before the active record. Interrupted
        # preparation may leave unused blobs, but can never arm a partial job.
        for oracle in confirmation.oracles:
            oracle.save(self.store)
        return self.store.start(confirmation.contract, confirmation.id)

    def discard(self, request_id: str) -> None:
        self.pending.pop(request_id, None)

    def close(self) -> None:
        self.closed = True
        self.pending.clear()
