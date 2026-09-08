"""Trusted controller ownership and bounded recovery across reconnects.

Every controller starts atomically inside a named, host-only Windows job. A
replacement watchdog holds the same OS lock and reconciles that exact kernel
object before resuming the original run. No timestamp or PID search grants idle
authority. This is process supervision, not a sandbox or a global dispatcher.
POSIX uses cooperative groups and inherited ownership channels while the outer
watchdog lives. If that owner dies, an unfinished launch cannot prove drainage:
reconnect refuses, without signaling saved PIDs or reusing Windows proofs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from excubitor.host_processes import host_backend, process_tree
from excubitor.runs import Binding, Conflict, Run, RunError, RunStore
from excubitor.supervisor import _exclusive
from excubitor.windows_jobs import recover_job, valid_name


def _append(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _exclusive_after_absent_job(path: Path, *, grace_seconds: float = 1.0):
    """Wait briefly for a controller lock released by a just-destroyed Windows job.

    Job-object absence means Windows has accepted termination after the previous
    watchdog lost its final handle.  It does not make the controller's file lock
    disappear synchronously, and it is not descendant-drainage evidence.  This
    only prevents a replacement from mutating the run until the exact controller
    lock is released.  An overlapping owner still fails closed after the bounded
    handoff window.
    """
    deadline = time.monotonic() + grace_seconds
    lock = None
    while lock is None:
        candidate = _exclusive(path)
        try:
            candidate.__enter__()
        except Conflict:
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
        else:
            lock = candidate
    try:
        yield
    except BaseException as exc:
        lock.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        lock.__exit__(None, None, None)


class ControllerWatchdog:
    """At most three controller launches across ALL watchdog lifetimes.

    argv is a trusted host factory, never a tool argument. Controllers report
    handled errors durably and exit zero, preventing retries of native denials.
    An adapter must contain every tool surface and authenticate the original
    task on reconnect. Old journals without named-job evidence cannot upgrade.
    """

    def __init__(self, store: RunStore, argv: Callable[[Run], tuple[str, ...]], cwd: Path):
        self.store, self.argv, self.cwd = store, argv, cwd

    def _history(self, path, run):
        if not path.exists():
            return []
        try:
            raw = path.read_bytes()
            if not raw.endswith(b"\n") or len(raw) > 128 * 1024:
                raise ValueError("torn or oversized history")
            events = [json.loads(line) for line in raw.splitlines()]
            launched, pending, names = 0, None, set()
            for event in events:
                if (
                    type(event["schema"]) is not int
                    or event["schema"] != (2 if host_backend() == "windows-process" else 3)
                    or event["contract"] != run.contract.digest
                ):
                    raise ValueError("missing named-job authority or mismatched contract")
                if event["schema"] == 2:
                    valid_name(event["job"])
                elif not isinstance(event["job"], str) or not re.fullmatch(
                    r"posix-group-[0-9a-f]{32}", event["job"]
                ):
                    raise ValueError("invalid POSIX launch identity")
                if type(event["launch"]) is not int:
                    raise ValueError("malformed launch count")
                if event["event"] == "launched":
                    if (
                        pending is not None
                        or event["launch"] != launched
                        or launched >= 3
                        or event["job"] in names
                    ):
                        raise ValueError("invalid controller sequence")
                    names.add(event["job"])
                    pending = event
                    launched += 1
                elif event["event"] == "drained":
                    if pending is None or any(event[key] != pending[key] for key in ("launch", "job")):
                        raise ValueError("drainage is not bound to its launch")
                    if type(event["reconciled"]) is not bool or any(
                        type(event[key]) is not bool for key in ("cancelled", "timed_out", "output_limited")
                    ):
                        raise ValueError("malformed drainage facts")
                    if (
                        type(event["revision"]) is not int
                        or not 0 <= event["revision"] <= run.revision
                        or not isinstance(event["journal_sha256"], str)
                        or not re.fullmatch(r"[0-9a-f]{64}", event["journal_sha256"])
                    ):
                        raise ValueError("malformed drainage provenance")
                    proof = event["kernel_evidence"]
                    if event["reconciled"]:
                        if (
                            event["schema"] != 2
                            or not isinstance(proof, dict)
                            or proof.get("job") != event["job"]
                            or type(proof.get("active")) is not int
                            or proof["active"] != 0
                            or proof.get("evidence") not in ("kernel-object-absent", "kernel-object-drained")
                            or event["exit_code"] is not None
                            or any(event[key] for key in ("cancelled", "timed_out", "output_limited"))
                            or event["processes"] != proof.get("processes")
                        ):
                            raise ValueError("malformed kernel drainage evidence")
                    elif proof is not None or (
                        type(event["exit_code"]) is not int
                        and not (event["exit_code"] is None and event["cancelled"])
                    ):
                        raise ValueError("malformed process result")
                    count = event["processes"]
                    absent = event["reconciled"] and proof["evidence"] == "kernel-object-absent"
                    if (absent and count is not None) or (
                        not absent and (type(count) is not int or count < 0)
                    ):
                        raise ValueError("malformed process count")
                    pending = None
                else:
                    raise ValueError("unknown controller history event")
            if not events:
                raise ValueError("empty history")
            return events
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise RunError("controller history cannot prove safe recovery; evidence preserved") from exc

    def _receipt(self, history, directory, run, launch, *, result=None, proof=None):
        journal = directory / (run.id + ".jsonl")
        contents = journal.read_bytes() if journal.exists() else b""
        receipt = {
            **launch,
            "event": "drained",
            "revision": run.revision,
            "journal_sha256": hashlib.sha256(contents).hexdigest(),
            "exit_code": result.execution.exit_code if result else None,
            "cancelled": result.cancelled if result else False,
            "timed_out": result.execution.timed_out if result else False,
            "output_limited": result.execution.output_limited if result else False,
            "processes": result.processes if result else proof.get("processes"),
            "reconciled": proof is not None,
            "kernel_evidence": proof,
        }
        _append(history, receipt)
        return receipt

    def _after_drain(self, directory, run, binding, receipt, cancel):
        if not run.enforces:
            return run
        if receipt["cancelled"] or cancel.is_set() or run.state == "stopping":
            if run.state != "stopping":
                run = self.store.cancel(run)
            return self.store.acknowledge_cancel(run, workers_idle=True)
        if receipt["exit_code"] == 0:
            return self.store.interrupt(run) if run.state == "running" else run
        if run.state == "running":
            run = self.store.interrupt(run)
        if run.state != "interrupted":
            return run
        if self.store.clock() >= run.contract.deadline:
            return self.store.resume(run, binding, workers_idle=True)
        if receipt["launch"] >= 2 or receipt["timed_out"] or receipt["output_limited"]:
            return run
        journal = directory / (run.id + ".jsonl")
        archive = run.id + ".crash-" + uuid.uuid4().hex + ".jsonl"
        contents = journal.read_bytes() if journal.exists() else b""
        # A previous recovery can stop between journal replacement and resume.
        # Preserve this additional boundary too; never overwrite earlier evidence.
        if journal.exists():
            journal.rename(directory / archive)
        _append(
            journal,
            {
                "event": "drained",
                "contract": run.contract.digest,
                "attempt": run.attempts,
                "recovery": {
                    "launch": receipt["launch"],
                    "archive": archive,
                    "journal_sha256": hashlib.sha256(contents).hexdigest(),
                    "job": receipt["job"],
                },
            },
        )
        return self.store.resume(run, binding, workers_idle=True)

    def drive(self, run_id: str, binding: Binding, *, cancel: threading.Event | None = None) -> Run:
        cancel = cancel if cancel is not None else threading.Event()
        run = self.store.get(run_id)
        if run.contract.binding != binding:
            raise Conflict("controller recovery requires the original native task and project")
        directory = self.store.directory / "supervision"
        directory.mkdir(exist_ok=True)
        history = directory / (run.id + ".controller.jsonl")
        with _exclusive(directory / (run.id + ".controller.lock")):
            run = self.store.get(run_id)
            events = self._history(history, run)
            if not events:
                if not run.enforces:
                    return run
                if run.state != "running" or run.attempts:
                    raise RunError("watchdog must own this job from its first controller launch")
            else:
                receipt = events[-1]
                if receipt["event"] == "launched":
                    # Reconcile even if the inner controller recorded completion
                    # before its parent disappeared. The outer tree must drain.
                    if receipt["schema"] == 3:
                        raise RunError(
                            "POSIX watchdog ownership was lost during a launch; drainage cannot be "
                            "proven. Recovery is refused and original limits/evidence are preserved. "
                            "No saved PID will be signaled."
                        )
                    proof = recover_job(receipt["job"])
                    run_lock = (
                        _exclusive_after_absent_job
                        if proof["evidence"] == "kernel-object-absent"
                        else _exclusive
                    )
                    with run_lock(directory / (run.id + ".lock")):
                        run = self.store.get(run_id)
                        receipt = self._receipt(history, directory, run, receipt, proof=proof)
                with _exclusive(directory / (run.id + ".lock")):
                    run = self._after_drain(directory, self.store.get(run_id), binding, receipt, cancel)
                if run.state != "running":
                    return run
            launches = sum(event["event"] == "launched" for event in events)
            for index in range(launches, 3):
                run = self.store.get(run_id)
                if run.state != "running":
                    return run
                remaining = run.contract.deadline - self.store.clock()
                if remaining <= 0:
                    return self.store.begin_attempt(run)
                windows = host_backend() == "windows-process"
                launch = {
                    "schema": 2 if windows else 3,
                    "event": "launched",
                    "launch": index,
                    "contract": run.contract.digest,
                    "job": ("Global\\Excubitor.Run." if windows else "posix-group-") + uuid.uuid4().hex,
                }
                _append(history, launch)
                try:
                    result = process_tree().run(
                        self.argv(run),
                        self.cwd,
                        timeout=min(remaining, 3600),
                        output_limit=2 * 1024 * 1024,
                        cancelled=cancel,
                        terminate_on_root_exit=True,
                        **({"job_name": launch["job"]} if windows else {}),
                    )
                    if not result.drained:
                        raise RunError("controller process tree is not accounted for")
                except BaseException:
                    current = self.store.get(run_id)
                    if current.state == "running":
                        self.store.interrupt(current)
                    raise
                with _exclusive(directory / (run.id + ".lock")):
                    run = self.store.get(run_id)
                    receipt = self._receipt(history, directory, run, launch, result=result)
                    run = self._after_drain(directory, run, binding, receipt, cancel)
                    if run.state != "running":
                        return run
            return run
