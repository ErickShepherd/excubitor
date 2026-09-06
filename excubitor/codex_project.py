"""Codex CLI transport for a separately admitted, isolated project backend.

Constructing this driver does not admit a native mode. The host must check the
selected installation, storage and all available tool surfaces before dispatch.
No global registration, native setup, permission escalation, or task spec lives here.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from excubitor.processes import WindowsProcessTree
from excubitor.runs import RunError

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"passed": {"type": "boolean"}, "findings": {"type": "string"}},
    "required": ["passed", "findings"],
}


class CodexProjectRuntime:
    def __init__(
        self,
        codex: Path,
        project: Path,
        output: Path,
        review_schema: Path,
        *,
        environment: dict[str, str],
        admit: Callable[[], None],
        model: str | None = None,
        effort: str | None = None,
    ):
        if not all(path.is_absolute() for path in (codex, project, output, review_schema)):
            raise ValueError("native paths must be absolute")
        if not codex.is_file() or not project.is_dir() or not output.is_dir():
            raise ValueError("native executable, candidate, and private output must already exist")
        if output.resolve().is_relative_to(project.resolve()) or review_schema.resolve().is_relative_to(
            project.resolve()
        ):
            raise RunError("native evidence and review schema must be outside the candidate")
        if not callable(admit):
            raise ValueError("independent native mode admission is required")
        if json.loads(review_schema.read_text(encoding="utf-8")) != REVIEW_SCHEMA:
            raise RunError("unexpected protected native review schema")
        self.codex, self.project, self.output, self.review_schema = codex, project, output, review_schema
        self.environment, self.admission = dict(environment), admit
        self.model, self.effort = model, effort
        self.schema_bytes = review_schema.read_bytes()
        self.tree = WindowsProcessTree()
        self.calls = 0

    def command(self, sandbox):
        if sandbox not in ("workspace-write", "read-only"):
            raise RunError("unsupported project worker permissions")
        command = [
            str(self.codex),
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--sandbox",
            sandbox,
            "--json",
            "--color",
            "never",
            "-C",
            str(self.project),
        ]
        # Keep the host's selected model. These switches narrow this child only;
        # they neither edit the user's settings nor establish native admission.
        for feature in (
            "plugins",
            "apps",
            "memories",
            "browser_use",
            "in_app_browser",
            "computer_use",
            "multi_agent",
        ):
            command.extend(("--disable", feature))
        options = {
            "windows.sandbox": "elevated",
            "web_search": "disabled",
            "approval_policy": "never",
            # The clean profile has no node_repl transport to disable. Adding
            # only enabled=false creates an invalid MCP entry in native Codex.
            "mcp_servers": {},
            "log_dir": str(self.output / "native-logs"),
        }
        if self.model is not None:
            options["model"] = self.model
        if self.effort is not None:
            options["model_reasoning_effort"] = self.effort
        for key, value in options.items():
            command.extend(("-c", key + "=" + json.dumps(value)))
        return command

    def execute(self, label, argv, run, *, stdin=b"", timeout=180, cancel=None):
        self.admission()
        if self.review_schema.read_bytes() != self.schema_bytes:
            raise RunError("protected native review schema changed")
        remaining = run.contract.deadline - time.time()
        if remaining <= 0:
            raise RunError("original deadline reached before native execution")
        result = self.tree.run(
            tuple(argv),
            self.project,
            env=self.environment,
            stdin=stdin,
            timeout=min(timeout, remaining),
            output_limit=2 * 1024 * 1024,
            cancelled=cancel,
        )
        self.calls += 1
        record = {"label": label, **asdict(result)}
        for field in ("stdout", "stderr"):
            record["execution"][field] = record["execution"][field].decode("utf-8", errors="replace")
        with (self.output / f"execution-{self.calls:04d}.json").open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2)
        # A denied native mode is a host blocker, not feedback for another attempt.
        if b"blocked by policy" in result.execution.stderr + result.execution.stdout:
            raise RunError("native policy refused this execution; host admission needs review")
        if (
            label in ("worker", "independent-review")
            and result.execution.exit_code != 0
            and not result.execution.stdout.strip()
            and result.execution.stderr.lstrip().startswith(b"Error loading config.toml:")
        ):
            raise RunError(
                "native configuration failed before model start; correct the host launch configuration"
            )
        return result

    def work(self, run, prompt, cancel):
        return self.execute(
            "worker", [*self.command("workspace-write"), "-"], run, stdin=prompt.encode(), cancel=cancel
        )

    def verify(self, run, oracle, cancel):
        return self.execute(
            "check:" + oracle.name,
            [
                str(self.codex),
                "sandbox",
                "-P",
                ":read-only",
                "-c",
                'windows.sandbox="elevated"',
                "-c",
                "log_dir=" + json.dumps(str(self.output / "native-logs")),
                "-C",
                str(self.project),
                "--",
                *oracle.argv,
            ],
            run,
            stdin=oracle.stdin.encode(),
            timeout=oracle.timeout_seconds,
            cancel=cancel,
        )

    def review(self, run, prompt, cancel):
        result = self.execute(
            "independent-review",
            [*self.command("read-only"), "--output-schema", str(self.review_schema), "-"],
            run,
            stdin=prompt.encode(),
            cancel=cancel,
        )
        try:
            events = [json.loads(line) for line in result.execution.stdout.decode().splitlines()]
            messages = [
                event["item"]["text"]
                for event in events
                if event.get("type") == "item.completed"
                and event.get("item", {}).get("type") == "agent_message"
            ]
            if not any(event.get("type") == "turn.completed" for event in events):
                raise ValueError("reviewer turn did not complete")
            report = json.loads(messages[-1])
            if (
                set(report) != {"passed", "findings"}
                or type(report["passed"]) is not bool
                or not isinstance(report["findings"], str)
            ):
                raise ValueError("malformed independent review")
            return result, report["passed"], report["findings"]
        except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
            return result, False, "The independent reviewer did not return a valid completed review."
