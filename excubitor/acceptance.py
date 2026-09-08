"""Frozen black-box acceptance definitions and host-side output comparison.

This intentionally does not run candidate code with controller privileges. A
native executor must capture the actual bounded subprocess result in its sandbox.
Its output is data, never an instruction, a claimed pytest summary, or a verdict.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from excubitor.runs import Candidate, Check, Conflict, Run, RunError, RunStore


@dataclass(frozen=True)
class OutputOracle:
    name: str
    argv: tuple[str, ...]
    stdin: str
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    timeout_seconds: int = 30
    mode: str = "exact-output"

    def __post_init__(self):
        if self.mode not in ("exact-output", "exit-code"):
            raise ValueError("acceptance mode must be exact-output or exit-code")
        if self.mode == "exit-code" and (self.stdout or self.stderr):
            raise ValueError("exit-code checks cannot also specify expected output")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 200:
            raise ValueError("acceptance check needs a bounded name")
        if not isinstance(self.argv, tuple) or not 1 <= len(self.argv) <= 64:
            raise ValueError("acceptance command must be a nonempty argument tuple")
        for arg in self.argv:
            if not isinstance(arg, str) or not arg or len(arg) > 4096 or "\0" in arg:
                raise ValueError("invalid literal acceptance argument")
        if not Path(self.argv[0]).is_absolute():
            raise ValueError("the native executor must use an absolute, admitted executable")
        for value in (self.stdin, self.stdout, self.stderr):
            if not isinstance(value, str) or len(value.encode("utf-8")) > 65536:
                raise ValueError("acceptance text exceeds the bounded UTF-8 format")
        if type(self.exit_code) is not int or not 0 <= self.exit_code <= 255:
            raise ValueError("invalid expected exit code")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 300:
            raise ValueError("acceptance timeout must be within five minutes")

    @property
    def payload(self) -> bytes:
        fields = asdict(self)
        # Old agreements are byte-addressed: adding a default field must not
        # change their bytes, fingerprint, or ability to resume.
        if self.mode == "exact-output":
            del fields["mode"]
        return json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    @property
    def check(self) -> Check:
        return Check(self.name, hashlib.sha256(self.payload).hexdigest())

    @property
    def description(self) -> str:
        # Escaping keeps terminal control characters out of the owner's preview.
        if self.mode == "exit-code":
            return (
                f"{json.dumps(self.name)}: command {json.dumps(self.argv)}; input {json.dumps(self.stdin)}; "
                f"expect exit {self.exit_code}; output is diagnostic only; timeout {self.timeout_seconds}s"
            )
        return (
            f"{json.dumps(self.name)}: command {json.dumps(self.argv)}; input {json.dumps(self.stdin)}; "
            f"expect exit {self.exit_code}, stdout {json.dumps(self.stdout)}, "
            f"stderr {json.dumps(self.stderr)}; timeout {self.timeout_seconds}s"
        )

    def save(self, store: RunStore) -> None:
        directory = store.directory / "oracles"
        directory.mkdir(exist_ok=True)
        path = directory / (self.check.oracle_digest + ".json")
        try:
            with path.open("xb") as stream:
                stream.write(self.payload)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != self.payload:
                raise RunError("protected acceptance bytes conflict with their fingerprint") from None

    @classmethod
    def load(cls, store: RunStore, check: Check) -> OutputOracle:
        path = store.directory / "oracles" / (check.oracle_digest + ".json")
        try:
            if path.is_symlink() or path.stat().st_size > 1024 * 1024:
                raise ValueError("redirected or oversized acceptance data")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != check.oracle_digest:
                raise ValueError("acceptance bytes changed")
            raw = json.loads(payload)
            raw["argv"] = tuple(raw["argv"])
            oracle = cls(**raw)
            if oracle.check != check or oracle.payload != payload:
                raise ValueError("acceptance identity mismatch")
            return oracle
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise RunError("protected acceptance definition unavailable or invalid") from exc


@dataclass(frozen=True)
class Execution:
    """Actual host-captured subprocess facts; never parse these from worker JSON."""

    exit_code: int | None
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    timed_out: bool = False
    output_limited: bool = False


def record_output(store: RunStore, run: Run, candidate: Candidate, check: Check, execution: Execution) -> Run:
    """Load the original definition and independently compare actual output bytes.

    The host must bind execution to this candidate snapshot, contain the process,
    and recheck current candidate identity. This function does not infer those
    facts or worker shutdown from an exit code and cannot complete the run.
    """
    if check not in run.contract.checks or candidate != run.candidate:
        raise Conflict("execution does not match the run's candidate and agreed check")
    oracle = OutputOracle.load(store, check)
    passed = (
        type(execution.exit_code) is int
        and execution.exit_code == oracle.exit_code
        and type(execution.stdout) is bytes
        and (oracle.mode == "exit-code" or execution.stdout == oracle.stdout.encode("utf-8"))
        and type(execution.stderr) is bytes
        and (oracle.mode == "exit-code" or execution.stderr == oracle.stderr.encode("utf-8"))
        and type(execution.elapsed_seconds) in (float, int)
        and 0 <= execution.elapsed_seconds <= oracle.timeout_seconds
        and execution.timed_out is False
        and execution.output_limited is False
    )
    return store.record_check(run, candidate, check, passed=passed)
