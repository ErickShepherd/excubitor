"""Claude CLI transport for a separately admitted, isolated project executor.

This adapter never launches a process itself. The trusted executor must enforce
the requested filesystem mode, network boundary and complete process drainage,
including native file tools and detached children. CLI flags are defense in depth,
not admission evidence. No registration, credentials or task specification live here.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from threading import Event
from typing import Callable, Literal, Protocol

from excubitor.processes import ProcessResult
from excubitor.runs import RunError

Mode = Literal["workspace-write", "read-only"]
_READ_TOOLS = ("Read", "Glob", "Grep")
_WRITE_TOOLS = (*_READ_TOOLS, "Bash", "Edit", "Write")
_SETTINGS = {
    "sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False},
    "disableClaudeAiConnectors": True,
}
_REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"passed": {"type": "boolean"}, "findings": {"type": "string"}},
    "required": ["passed", "findings"],
}


class IsolatedExecutor(Protocol):
    def run(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        *,
        sandbox: Mode,
        stdin: bytes,
        timeout: float,
        output_limit: int,
        cancelled: Event | None,
        env: dict[str, str],
    ) -> ProcessResult: ...


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate native JSON key")
        result[key] = value
    return result


def _clean_exit(result):
    return (
        result.execution.exit_code == 0
        and not result.execution.timed_out
        and not result.execution.output_limited
        and not result.cancelled
        and result.drained
    )


def _authentication_failure(result, session):
    """Recognize the observed native auth failure, never nested candidate text."""
    if (
        not session
        or result.execution.exit_code != 1
        or result.execution.timed_out
        or result.execution.output_limited
        or result.cancelled
        or not result.drained
    ):
        return False
    try:
        events = [
            json.loads(line, object_pairs_hook=_unique_object)
            for line in result.execution.stdout.decode().splitlines()
        ]
        if len(events) < 3 or not all(isinstance(event, dict) for event in events):
            return False
        initial, terminal = events[0], events[-1]
        return (
            initial.get("type") == "system"
            and initial.get("subtype") == "init"
            and all(event.get("session_id") == session for event in events)
            and terminal.get("type") == "result"
            and terminal.get("is_error") is True
            and terminal.get("terminal_reason") == "api_error"
            and not any(event.get("type") == "result" for event in events[:-1])
            and any(
                event.get("type") == "assistant"
                and event.get("error") == "authentication_failed"
                and event.get("is_api_error_message") is True
                for event in events[1:-1]
            )
        )
    except (ValueError, UnicodeError, TypeError):
        return False


class ClaudeProjectRuntime:
    def __init__(
        self,
        claude: Path,
        project: Path,
        output: Path,
        *,
        executor: IsolatedExecutor,
        environment: dict[str, str],
        admit: Callable[[Mode], None],
        model: str,
        native_model: str,
        effort: str | None = None,
    ):
        if not all(path.is_absolute() for path in (claude, project, output)):
            raise ValueError("native paths must be absolute")
        if not claude.is_file() or not project.is_dir() or not output.is_dir():
            raise ValueError("native executable, candidate and private output must already exist")
        if (
            output.resolve().is_relative_to(project.resolve())
            or project.resolve().is_relative_to(output.resolve())
            or claude.resolve().is_relative_to(project.resolve())
        ):
            raise RunError("native executable and private evidence must be separate from the candidate")
        if not callable(admit) or not callable(getattr(executor, "run", None)):
            raise ValueError("independent native admission and an isolated executor are required")
        if any(not isinstance(value, str) or not value.strip() for value in (model, native_model)):
            raise ValueError("the selected model and its admitted native identity are required")
        if effort not in (None, "low", "medium", "high", "xhigh", "max"):
            raise ValueError("unsupported Claude effort")
        self.claude, self.project, self.output = claude, project, output
        self.executor, self.admission = executor, admit
        self.environment = dict(environment)
        self.model, self.native_model, self.effort = model, native_model, effort
        # Inline arguments avoid a worker-controlled settings/schema file or a
        # file replacement race. The host must protect this adapter's own code.
        self.settings = json.dumps(_SETTINGS, separators=(",", ":"))
        self.schema = json.dumps(_REVIEW_SCHEMA, separators=(",", ":"))

    def command(self, mode: Mode, session: str, *, review: bool = False):
        if mode not in ("workspace-write", "read-only") or review and mode != "read-only":
            raise RunError("unsupported project worker permissions")
        tools = _WRITE_TOOLS if mode == "workspace-write" else _READ_TOOLS
        command = [
            str(self.claude),
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--session-id",
            session,
            "--safe-mode",
            "--disable-slash-commands",
            "--restricted",
            "--setting-sources",
            "",
            "--settings",
            self.settings,
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--tools",
            ",".join(tools),
            "--allowedTools",
            ",".join(tools),
            "--permission-mode",
            "dontAsk",
            "--permission-prompts",
            "none",
            "--model",
            self.model,
        ]
        if self.effort is not None:
            command.extend(("--effort", self.effort))
        if review:
            command.extend(("--json-schema", self.schema))
        return tuple(command)

    def execute(self, label, argv, mode, run, *, stdin=b"", timeout=180, cancel=None, session=None):
        self.admission(mode)
        remaining = run.contract.deadline - time.time()
        if remaining <= 0:
            raise RunError("original deadline reached before native execution")
        # Reserve create-only evidence before dispatch. A restarted adapter cannot
        # overwrite an earlier launch or discover a filename collision afterwards.
        path = self.output / f"execution-{uuid.uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as stream:
            record = {"label": label, "sandbox": mode, "session_id": session}
            try:
                result = self.executor.run(
                    tuple(argv),
                    self.project,
                    sandbox=mode,
                    env=dict(self.environment),
                    stdin=stdin,
                    timeout=min(timeout, remaining),
                    output_limit=2 * 1024 * 1024,
                    cancelled=cancel,
                )
            except Exception as error:
                json.dump({**record, "executor_error": type(error).__name__}, stream, indent=2)
                raise
            record.update(asdict(result))
            for field in ("stdout", "stderr"):
                record["execution"][field] = record["execution"][field].decode("utf-8", errors="replace")
            json.dump(record, stream, indent=2)
        if _authentication_failure(result, session):
            raise RunError(
                "native Claude needs sign-in; preserve the original job and restore authentication"
            )
        return result

    def _completed(self, result, session, mode, *, review=False):
        """Validate native framing, never a tool's nested stdout or prose verdict.

        This post-execution check detects configuration/protocol drift. It cannot
        replace the executor's admission checks before the first model tool runs.
        """
        try:
            events = [
                json.loads(line, object_pairs_hook=_unique_object)
                for line in result.execution.stdout.decode("utf-8").splitlines()
            ]
            if len(events) < 2 or not all(isinstance(event, dict) for event in events):
                raise ValueError("incomplete native stream")
            initial, terminal = events[0], events[-1]
            allowed = set(_WRITE_TOOLS if mode == "workspace-write" else _READ_TOOLS)
            if review:
                allowed.add("StructuredOutput")
            actual_tools = initial.get("tools")
            if (
                initial.get("type") != "system"
                or initial.get("subtype") != "init"
                or initial.get("session_id") != session
                or initial.get("model") != self.native_model
                or initial.get("permissionMode") != "dontAsk"
                or not isinstance(actual_tools, list)
                or any(not isinstance(tool, str) for tool in actual_tools)
                or not set(actual_tools).issubset(allowed)
                or len(set(actual_tools)) != len(actual_tools)
                or initial.get("mcp_servers") != []
                or initial.get("plugins") != []
                or initial.get("plugin_errors", []) != []
                or initial.get("mcp_server_errors", []) != []
                or initial.get("skills", []) != []
            ):
                raise ValueError("native context differs from the admitted mode")
            if (
                terminal.get("type") != "result"
                or terminal.get("subtype") != "success"
                or terminal.get("is_error") is not False
                or terminal.get("session_id") != session
                or any(event.get("type") == "result" for event in events[:-1])
                or any(
                    event.get("type") == "system" and event.get("subtype") == "init" for event in events[1:]
                )
                or any(event.get("session_id", session) != session for event in events)
            ):
                raise ValueError("no unique successful terminal result for this invocation")
            return terminal
        except (ValueError, UnicodeError, TypeError) as error:
            raise RunError(
                "native Claude context or completion evidence is invalid; review host admission"
            ) from error

    def work(self, run, prompt, cancel):
        session = str(uuid.uuid4())
        result = self.execute(
            "worker",
            self.command("workspace-write", session),
            "workspace-write",
            run,
            stdin=prompt.encode("utf-8"),
            cancel=cancel,
            session=session,
        )
        if _clean_exit(result):
            self._completed(result, session, "workspace-write")
        return result

    def verify(self, run, oracle, cancel):
        # ProjectBackend binds this exact argv/stdin to the original frozen check.
        # No model interprets its result or substitutes a different test command.
        return self.execute(
            "check:" + oracle.name,
            oracle.argv,
            "read-only",
            run,
            stdin=oracle.stdin.encode("utf-8"),
            timeout=oracle.timeout_seconds,
            cancel=cancel,
        )

    def review(self, run, prompt, cancel):
        session = str(uuid.uuid4())
        result = self.execute(
            "independent-review",
            self.command("read-only", session, review=True),
            "read-only",
            run,
            stdin=prompt.encode("utf-8"),
            cancel=cancel,
            session=session,
        )
        if not _clean_exit(result):
            return result, False, "The independent Claude reviewer did not complete."
        report = self._completed(result, session, "read-only", review=True).get("structured_output")
        if (
            not isinstance(report, dict)
            or set(report) != {"passed", "findings"}
            or type(report["passed"]) is not bool
            or not isinstance(report["findings"], str)
        ):
            raise RunError("native Claude reviewer did not return the required structured report")
        return result, report["passed"], report["findings"]
