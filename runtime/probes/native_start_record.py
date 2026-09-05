"""Exercise the shared start handshake through a disposable native MCP connection.

Creates only its selected log and sibling authority folder. A confirmed test
creates a lifecycle record, never a worker or hook. EOF cancels the dummy record.
This is a CLI experiment, not production activation or complete mode admission.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from excubitor.acceptance import OutputOracle  # noqa: E402
from excubitor.approval import StartHandshake, codex_binding  # noqa: E402
from excubitor.runs import Contract, RunError, RunStore  # noqa: E402
from runtime.probes.native_start import Observer  # noqa: E402


class RecordObserver(Observer):
    def __init__(self, emit, record, store):
        super().__init__(self.route, record)
        self.transport_emit = emit
        self.gate = StartHandshake(store)
        self.next_confirmation = None
        self.confirmations = {}
        self.created = []

    def route(self, message):
        if message.get("method") == "elicitation/create":
            confirmation = self.next_confirmation
            if confirmation is None:
                raise RunError("missing exact owner preview")
            self.next_confirmation = None
            self.confirmations[message["id"]] = confirmation.id
            request = confirmation.request
            request["message"] = (
                "DISPOSABLE TEST: confirm a temporary lifecycle record. No Ralph worker or hook will start.\n"
                + request["message"]
            )
            request["requestedSchema"]["properties"]["confirm"]["title"] = "Confirm the disposable record"
            message["params"] = request
        self.transport_emit(message)

    def receive(self, message):
        method = message.get("method")
        request_id = message.get("id")
        if method == "tools/call":
            params = message.get("params", {})
            if (
                params.get("name") == "confirm_probe"
                and params.get("arguments", {}) == {}
                and self.client is not None
                and "elicitation" in self.client
            ):
                try:
                    binding = codex_binding(params.get("_meta", {}))
                    oracle = OutputOracle(
                        "fixture-output",
                        (
                            sys.executable,
                            "-I",
                            "-B",
                            "-c",
                            "import sys; sys.stdout.buffer.write(b'fixture-ok\\n')",
                        ),
                        "",
                        "fixture-ok\n",
                    )
                    contract = Contract(
                        binding,
                        "Exercise a disposable confirmation record",
                        ("fixture-only",),
                        (oracle.check,),
                        2,
                        int(time.time()) + 300,
                    )
                    self.next_confirmation = self.gate.prepare(binding, contract, (oracle,))
                    self.record({"event": "prepared", "active_before": False, "contract": contract.digest})
                except (RunError, ValueError) as exc:
                    self.reply(request_id, {"isError": True, "content": [{"type": "text", "text": str(exc)}]})
                    return
        elif method is None and request_id in self.confirmations:
            confirmation = self.confirmations.pop(request_id)
            run = self.gate.answer(confirmation, message.get("result", {}))
            if run is not None:
                self.created.append(run)
            self.record(
                {"event": "record_result", "started": run is not None, "run_id": run.id if run else None}
            )
        elif method == "notifications/cancelled":
            original = message.get("params", {}).get("requestId")
            for token, pending in list(self.pending.items()):
                if pending == original:
                    del self.pending[token]
                    confirmation = self.confirmations.pop(token, None)
                    if confirmation is not None:
                        self.gate.discard(confirmation)
                    self.record({"event": "transport_cancelled"})
        super().receive(message)

    def close(self):
        self.gate.close()
        for run in self.created:
            store = self.gate.store
            ended = store.acknowledge_cancel(store.cancel(store.get(run.id)), workers_idle=True)
            self.record({"event": "fixture_record_closed", "enforces": ended.enforces})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error("output must be an absolute create-only log file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as log:

        def record(value):
            log.write(json.dumps(value, sort_keys=True) + "\n")
            log.flush()

        def emit(value):
            print(json.dumps(value), flush=True)

        store = RunStore(args.output.with_suffix(".authority"), create=True)
        observer = RecordObserver(emit, record, store)
        try:
            for line in sys.stdin:
                observer.receive(json.loads(line))
        finally:
            observer.close()


if __name__ == "__main__":
    main()
