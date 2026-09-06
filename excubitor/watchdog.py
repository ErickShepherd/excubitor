"""Trusted Windows parent for a disposable/host-admitted controller process.

The controller and its descendants run inside one kill-on-close Windows job.
Only an observed empty job permits recovery. A watchdog crash leaves a durable
in-flight fence: a replacement watchdog MUST NOT infer drainage from its age.
This is process supervision, not native sandbox or transport authentication.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Callable

from excubitor.processes import WindowsProcessTree
from excubitor.runs import Binding, Conflict, Run, RunError, RunStore
from excubitor.supervisor import _exclusive


def _append(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class ControllerWatchdog:
    """Run only an already authorized job, with at most two crash restarts.

    argv is a trusted host factory, never a tool argument. A controller should
    report handled failures durably and exit zero; nonzero termination triggers
    crash reconciliation. This parent must own EVERY controller launch for the
    run. Native services outside its Windows job need separate admission.
    """

    def __init__(self, store: RunStore, argv: Callable[[Run], tuple[str, ...]], cwd: Path):
        self.store, self.argv, self.cwd = store, argv, cwd

    def drive(self, run_id: str, binding: Binding, *, cancel: threading.Event | None = None) -> Run:
        cancel = cancel if cancel is not None else threading.Event()
        run = self.store.get(run_id)
        if run.contract.binding != binding:
            raise Conflict("controller recovery requires the original native task and project")
        if not run.enforces:
            return run
        directory = self.store.directory / "supervision"
        directory.mkdir(exist_ok=True)
        history = directory / (run.id + ".controller.jsonl")
        with _exclusive(directory / (run.id + ".controller.lock")):
            # No restarts across uncertain watchdog lifetimes, including a crash
            # between OS drainage and durable acknowledgement. Preserve evidence.
            if history.exists():
                raise RunError("controller history already exists; unattended takeover is not admitted")
            if run.state != "running" or run.attempts:
                raise RunError("watchdog must own this job from its first controller launch")
            for launch in range(3):
                run = self.store.get(run.id)
                if not run.enforces:
                    return run
                if run.state != "running":
                    return run
                remaining = run.contract.deadline - self.store.clock()
                if remaining <= 0:
                    return self.store.begin_attempt(run)
                _append(history, {"event": "launched", "launch": launch, "contract": run.contract.digest})
                try:
                    result = WindowsProcessTree().run(
                        self.argv(run),
                        self.cwd,
                        timeout=min(remaining, 3600),
                        output_limit=2 * 1024 * 1024,
                        cancelled=cancel,
                        terminate_on_root_exit=True,
                    )
                    if not result.drained:
                        raise RunError("controller process tree is not accounted for")
                except BaseException:
                    current = self.store.get(run.id)
                    if current.state == "running":
                        self.store.interrupt(current)
                    raise
                with _exclusive(directory / (run.id + ".lock")):
                    run = self.store.get(run.id)
                    journal = directory / (run.id + ".jsonl")
                    contents = journal.read_bytes() if journal.exists() else b""
                    receipt = {
                        "event": "drained",
                        "launch": launch,
                        "contract": run.contract.digest,
                        "revision": run.revision,
                        "journal_sha256": hashlib.sha256(contents).hexdigest(),
                        "exit_code": result.execution.exit_code,
                        "cancelled": result.cancelled,
                        "timed_out": result.execution.timed_out,
                        "output_limited": result.execution.output_limited,
                        "processes": result.processes,
                    }
                    _append(history, receipt)
                    if not run.enforces:
                        return run
                    if result.cancelled or cancel.is_set() or run.state == "stopping":
                        if run.state != "stopping":
                            run = self.store.cancel(run)
                        return self.store.acknowledge_cancel(run, workers_idle=True)
                    if result.execution.exit_code == 0:
                        # Handled errors and ordinary blocked results are final for
                        # this watchdog; never retry a native permission rejection.
                        return self.store.interrupt(run) if run.state == "running" else run
                    if run.state == "running":
                        run = self.store.interrupt(run)
                    if run.state != "interrupted":
                        return run
                    if self.store.clock() >= run.contract.deadline:
                        return self.store.resume(run, binding, workers_idle=True)
                    if launch == 2 or result.execution.timed_out or result.execution.output_limited:
                        return run
                    # Retain even a torn last journal line byte-for-byte. The new
                    # journal starts ONLY after this parent's actual drainage.
                    archive = run.id + ".crash-" + uuid.uuid4().hex + ".jsonl"
                    if journal.exists():
                        journal.rename(directory / archive)
                    _append(
                        journal,
                        {
                            "event": "drained",
                            "contract": run.contract.digest,
                            "attempt": run.attempts,
                            "recovery": {
                                "launch": launch,
                                "archive": archive,
                                "journal_sha256": receipt["journal_sha256"],
                            },
                        },
                    )
                    run = self.store.resume(run, binding, workers_idle=True)
                    # begin_attempt in the restarted supervisor consumes the next
                    # ORIGINAL attempt and clears stale check/review evidence.
            return run
