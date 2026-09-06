"""Vendor-neutral orchestration of an already authorized run.

Backends are trusted host code, never worker-supplied callbacks or JSON facts.
They must admit the native mode, contain all worker/verifier/reviewer surfaces,
commit through the authorized Git path, and independently collect evidence.
This module adds no activation endpoint, registration, or ordinary-work policy.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from excubitor.acceptance import OutputOracle, record_output
from excubitor.processes import ProcessResult
from excubitor.runs import Candidate, Conflict, NotReady, Run, RunError, RunStore


class Backend(Protocol):
    def admit(self, run: Run) -> None:
        """Raise unless this exact run and every executable/tool surface are admitted."""

    def work(self, run: Run, unit: str | None, feedback: str, cancel: threading.Event) -> ProcessResult:
        """Re-read the durable contract, execute one bounded worker, and drain it."""

    def checkpoint(self, run: Run) -> Candidate:
        """Retain the actual work using the authorized commit path; independently inspect it."""

    def current(self, run: Run) -> Candidate:
        """Independently inspect current bytes, index, commit, branch, and isolation."""

    def verify(self, run: Run, oracle: OutputOracle, cancel: threading.Event) -> ProcessResult:
        """Execute the ORIGINAL oracle in a contained candidate sandbox and drain it."""

    def review(self, run: Run, cancel: threading.Event) -> tuple[ProcessResult, bool, str]:
        """Fresh independent review bound to run.candidate; never the implementer's self-report."""


class _CancelledAfterDrain(Exception):
    pass


@contextmanager
def _exclusive(path: Path):
    # OS ownership, not a timestamp lease. A crashed owner releases the lock;
    # the durable in-flight record below still prevents an unsafe automatic restart.
    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Conflict("another supervisor owns this run") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class Supervisor:
    def __init__(self, store: RunStore, backend: Backend):
        self.store, self.backend = store, backend

    def drive(self, run_id: str, *, cancel: threading.Event | None = None) -> Run:
        cancel = cancel if cancel is not None else threading.Event()
        run = self.store.get(run_id)
        if not run.enforces:
            return run
        directory = self.store.directory / "supervision"
        directory.mkdir(exist_ok=True)
        journal = directory / (run.id + ".jsonl")
        with _exclusive(directory / (run.id + ".lock")):
            run = self.store.get(run_id)
            if run.state != "running":
                return run
            self.backend.admit(run)
            if journal.exists():
                # An incomplete last line is an unresolved crash, not idle evidence.
                try:
                    events = [json.loads(line) for line in journal.read_text().splitlines()]
                    if not events or events[-1]["event"] not in ("drained", "complete", "stopped"):
                        return self.store.interrupt(run)
                    if any(event["contract"] != run.contract.digest for event in events):
                        raise RunError("supervisor history does not match the authorized contract")
                except (ValueError, KeyError) as exc:
                    self.store.interrupt(run)
                    raise RunError(
                        "incomplete supervisor history; reconcile worker shutdown before resume"
                    ) from exc

            def record(event, **details):
                with journal.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            {
                                "event": event,
                                "contract": run.contract.digest,
                                "attempt": run.attempts,
                                **details,
                            }
                        )
                        + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())

            def drained(result):
                if not result.drained:
                    raise RunError("native backend cannot account for remaining workers")
                record(
                    "drained",
                    exit_code=result.execution.exit_code,
                    timed_out=result.execution.timed_out,
                    output_limited=result.execution.output_limited,
                )
                if result.cancelled or cancel.is_set():
                    raise _CancelledAfterDrain("owner cancelled the run")

            feedback = ""
            capacity_failures = 0

            def wait_for_capacity(phase):
                nonlocal capacity_failures, run
                run = self.store.record_capacity_failure(run, phase)
                capacity_failures += 1
                # Every launch is charged, even if the service fails midway
                # through a turn. Waiting never buys another attempt or model.
                delay = min(30 * 2 ** min(capacity_failures - 1, 2), 120)
                remaining = run.contract.deadline - self.store.clock()
                if run.attempts >= run.contract.max_attempts or remaining <= 0:
                    record("capacity_exhausted", phase=phase)
                    return
                until = self.store.clock() + min(delay, remaining)
                record("capacity_wait", phase=phase, retry_at=until)
                while (remaining := min(until, run.contract.deadline) - self.store.clock()) > 0:
                    if cancel.wait(min(remaining, 0.25)):
                        raise _CancelledAfterDrain("owner cancelled during capacity backoff")
                # A crash inside the wait leaves an unresolved journal entry.
                # Recovery must reconcile it before another controller can run.
                record("drained")

            try:
                while run.state == "running":
                    if cancel.is_set():
                        raise _CancelledAfterDrain("owner cancelled before the next worker")
                    self.backend.admit(run)
                    # Re-read and authenticate the original checks on every attempt.
                    for check in run.contract.checks:
                        OutputOracle.load(self.store, check)
                    run = self.store.begin_attempt(run)
                    if run.state != "running":
                        record("stopped", reason="original attempt or time budget exhausted")
                        return run
                    unit = (
                        run.contract.units[run.completed_units]
                        if run.completed_units < len(run.contract.units)
                        else None
                    )
                    record("work_started", unit=unit)
                    work = self.backend.work(run, unit, feedback, cancel)
                    drained(work)
                    if work.retryable_error == "capacity":
                        wait_for_capacity("work")
                        # Preserve any existing check/review feedback. Service
                        # availability is not evidence that code needs repair.
                        continue
                    execution = work.execution
                    if execution.exit_code != 0 or execution.timed_out or execution.output_limited:
                        feedback = (
                            "The worker failed or exceeded its execution limits. Repair the current unit."
                        )
                        continue
                    # Unit checkpoints record progress, not semantic acceptance. All
                    # frozen acceptance checks and independent review gate the finish.
                    candidate = self.backend.checkpoint(run)
                    if not candidate.clean or not candidate.isolated:
                        raise RunError("checkpoint is not a clean committed isolated candidate")
                    run = self.store.checkpoint(run, candidate, unit=unit)
                    if run.completed_units < len(run.contract.units):
                        feedback = ""
                        continue
                    failures = []
                    for check in run.contract.checks:
                        oracle = OutputOracle.load(self.store, check)
                        if self.backend.current(run) != candidate:
                            raise Conflict("candidate changed before verification")
                        record("verification_started", check=check.name)
                        result = self.backend.verify(run, oracle, cancel)
                        drained(result)
                        if self.backend.current(run) != candidate:
                            raise Conflict("candidate changed during verification")
                        run = record_output(self.store, run, candidate, check, result.execution)
                        if not dict(run.check_results)[check.name]:
                            failures.append(
                                {
                                    "check": check.name,
                                    "expected": oracle.description,
                                    "actual_exit": result.execution.exit_code,
                                    "actual_stdout": repr(result.execution.stdout[:1024]),
                                    "actual_stderr": repr(result.execution.stderr[:1024]),
                                }
                            )
                    if failures:
                        feedback = "Original acceptance checks failed: " + json.dumps(failures)
                        record("checks_failed", checks=failures)
                        # This event is a stable, drained checkpoint for crash recovery.
                        record("drained")
                        continue
                    while True:
                        for check in run.contract.checks:
                            OutputOracle.load(self.store, check)
                        self.backend.admit(run)
                        if self.backend.current(run) != candidate:
                            raise Conflict("candidate changed before independent review")
                        record("review_started", candidate=candidate.digest)
                        result, passed, explanation = self.backend.review(run, cancel)
                        drained(result)
                        if self.backend.current(run) != candidate:
                            raise Conflict("candidate changed during independent review")
                        if result.retryable_error != "capacity":
                            break
                        wait_for_capacity("review")
                        run = self.store.retry_review(run, candidate)
                        if run.state != "running":
                            record("stopped", reason="model capacity; original attempt budget exhausted")
                            return run
                    passed = (
                        passed is True
                        and result.execution.exit_code == 0
                        and not result.execution.timed_out
                        and not result.execution.output_limited
                    )
                    run = self.store.record_review(run, candidate, passed=passed)
                    if not passed:
                        feedback = "Independent review requires repair: " + explanation[:4096]
                        continue
                    run = self.store.finish(run, self.backend.current(run), workers_idle=True)
                    record("complete", candidate=candidate.digest)
                    return run
            except _CancelledAfterDrain:
                # Backends must return only after cancellation drained their tree.
                # An exception instead leaves unresolved supervision, handled below.
                current = self.store.get(run.id)
                if current.state == "running":
                    current = self.store.cancel(current)
                if current.state == "stopping":
                    current = self.store.acknowledge_cancel(current, workers_idle=True)
                record("stopped", reason="cancelled after worker drainage")
                return current
            except NotReady:
                current = self.store.get(run.id)
                if current.state == "blocked":
                    record("stopped", reason="original deadline reached")
                    return current
                if current.state == "running":
                    self.store.interrupt(current)
                raise
            except BaseException:
                current = self.store.get(run.id)
                if current.state == "running":
                    self.store.interrupt(current)
                # Do not invent idle or terminal evidence for a failing backend.
                raise
        return self.store.get(run_id)
