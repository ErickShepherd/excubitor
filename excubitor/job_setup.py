"""Turn an untrusted job proposal into the existing native confirmation preview.

The host supplies reusable limits and admitted verification commands. A draft can
propose work and input/output checks, never approval, native identity, storage,
worker executables, or completion powers. Nothing here runs a command or starts a
job. The admitted adapter must still isolate verification and collect evidence.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable

from excubitor.acceptance import OutputOracle
from excubitor.runs import Binding, Contract, NotReady

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}\Z")


def _object(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys():
        raise ValueError("job proposal is missing required fields")
    if value.keys() - set(required) - set(optional):
        raise ValueError("job proposal contains unsupported fields")


def _integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


@dataclass(frozen=True)
class LaunchDefaults:
    """Reusable host preferences, not an approval or a source of recovery limits."""

    attempts: int
    seconds: int
    maximum_attempts: int
    maximum_seconds: int

    def __post_init__(self):
        _integer(self.maximum_attempts, 1, 10000, "host attempt ceiling")
        _integer(self.maximum_seconds, 1, 604800, "host duration ceiling")
        _integer(self.attempts, 1, self.maximum_attempts, "default attempts")
        _integer(self.seconds, 1, self.maximum_seconds, "default duration")


@dataclass(frozen=True)
class CheckRunner:
    """A host-admitted command executed only in the verifier's native sandbox.

    It must exercise candidate behavior, not delegate success to mutable tests or
    a worker-written verdict. Command registration/admission belongs to the host;
    an absolute path alone does not prove that it or its dependencies are trusted.
    """

    name: str
    argv: tuple[str, ...]
    timeout_seconds: int = 30

    def __post_init__(self):
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise ValueError("verification runner needs a short stable name")
        # Reuse the executor/argument/timeout bounds of the actual frozen oracle.
        OutputOracle(self.name, self.argv, "", "", timeout_seconds=self.timeout_seconds)


class JobPlanner:
    """Connection-local proposal conversion; accepted contracts live in RunStore."""

    def __init__(
        self,
        defaults: LaunchDefaults,
        runners: tuple[CheckRunner, ...],
        *,
        admit: Callable[[Contract, tuple[OutputOracle, ...]], None],
        clock: Callable[[], float] = time.time,
    ):
        if not isinstance(defaults, LaunchDefaults):
            raise ValueError("host launch defaults are required")
        if not isinstance(runners, tuple) or not runners or len(runners) > 32:
            raise ValueError("one to 32 admitted verification runners are required")
        if any(not isinstance(runner, CheckRunner) for runner in runners):
            raise ValueError("invalid host verification runner")
        if len({runner.name for runner in runners}) != len(runners):
            raise ValueError("duplicate host verification runner")
        if not callable(admit):
            raise ValueError("an independent host admission check is required for proposed jobs")
        self.defaults, self.runners, self.clock, self.admit = defaults, runners, clock, admit

    @property
    def schema(self) -> dict:
        text = {"type": "string", "maxLength": 65536}
        limits = self.defaults
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["goal", "units", "checks"],
            "properties": {
                "goal": {"type": "string", "minLength": 1, "maxLength": 4096},
                "units": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 64,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1, "maxLength": 4096},
                },
                "checks": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 64,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "runner", "stdin", "stdout"],
                        "properties": {
                            "name": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,63}$"},
                            "runner": {"type": "string", "enum": [r.name for r in self.runners]},
                            "stdin": dict(text),
                            "stdout": dict(text),
                            "stderr": dict(text),
                            "exit_code": {"type": "integer", "minimum": 0, "maximum": 255},
                            "timeout_seconds": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": max(r.timeout_seconds for r in self.runners),
                                "description": "May only shorten the selected runner's timeout: "
                                + ", ".join(f"{r.name}={r.timeout_seconds}s" for r in self.runners),
                            },
                        },
                    },
                },
                "attempts": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": limits.maximum_attempts,
                    "default": limits.attempts,
                },
                "seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": limits.maximum_seconds,
                    "default": limits.seconds,
                },
            },
        }

    def __call__(self, binding: Binding, draft: dict) -> tuple[Contract, tuple[OutputOracle, ...]]:
        _object(draft, ("goal", "units", "checks"), ("attempts", "seconds"))
        units, checks = draft["units"], draft["checks"]
        if not isinstance(units, list) or not 1 <= len(units) <= 64:
            raise ValueError("propose one to 64 work units")
        if any(not isinstance(unit, str) for unit in units):
            raise ValueError("work units must be text")
        if not isinstance(checks, list) or not 1 <= len(checks) <= 64:
            raise ValueError("propose one to 64 input/output acceptance checks")
        attempts = _integer(
            draft.get("attempts", self.defaults.attempts),
            len(units),
            self.defaults.maximum_attempts,
            "attempts",
        )
        seconds = _integer(
            draft.get("seconds", self.defaults.seconds),
            1,
            self.defaults.maximum_seconds,
            "duration",
        )
        runners = {runner.name: runner for runner in self.runners}
        oracles = []
        for check in checks:
            _object(check, ("name", "runner", "stdin", "stdout"), ("stderr", "exit_code", "timeout_seconds"))
            if not isinstance(check["name"], str) or not _NAME.fullmatch(check["name"]):
                raise ValueError("acceptance check needs a short stable name")
            runner_name = check["runner"]
            if not isinstance(runner_name, str) or runner_name not in runners:
                raise NotReady("the requested verification runner is not admitted by this host")
            runner = runners[runner_name]
            timeout = _integer(
                check.get("timeout_seconds", runner.timeout_seconds),
                1,
                runner.timeout_seconds,
                "check timeout",
            )
            oracles.append(
                OutputOracle(
                    check["name"],
                    runner.argv,
                    check["stdin"],
                    check["stdout"],
                    check.get("stderr", ""),
                    check.get("exit_code", 0),
                    timeout,
                )
            )
        frozen = tuple(oracles)
        contract = Contract(
            binding,
            draft["goal"],
            tuple(units),
            tuple(oracle.check for oracle in frozen),
            attempts,
            int(self.clock()) + seconds,
        )
        # The old trusted plan callback may have supplied project/mode checks.
        # Proposal conversion cannot silently bypass those host prerequisites.
        self.admit(contract, frozen)
        return contract, frozen
