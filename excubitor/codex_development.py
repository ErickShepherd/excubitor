"""Codex structured proposals; command execution belongs to the selected executor."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path

from excubitor.codex_project import _capacity_failure
from excubitor.development_runtime import clean_exit
from excubitor.host_processes import process_tree
from excubitor.literal_command import reject_windows_batch
from excubitor.runs import RunError


def completed_proposal(stdout):
    """Accept only a completed native turn, never a tool's JSON-shaped output."""
    try:
        events = [json.loads(line) for line in stdout.decode().splitlines()]
        if not events or any(not isinstance(e, dict) for e in events):
            raise ValueError("invalid event stream")
        if events[0].get("type") != "thread.started" or events[-1].get("type") != "turn.completed":
            raise ValueError("incomplete native turn")
        messages = []
        for event in events:
            kind = event.get("type")
            if kind in ("item.started", "item.updated", "item.completed"):
                item = event.get("item", {})
                if item.get("type") not in ("reasoning", "agent_message"):
                    raise ValueError("native tool use is outside the structured proposal contract")
                if kind == "item.completed" and item["type"] == "agent_message":
                    messages.append(item["text"])
            elif kind not in ("thread.started", "turn.started", "turn.completed"):
                raise ValueError("unexpected native event")
        if len(messages) != 1 or sum(e.get("type") == "turn.completed" for e in events) != 1:
            raise ValueError("expected one completed proposal")
        proposal = json.loads(messages[0])
        if not isinstance(proposal, dict):
            raise ValueError("expected a JSON object")
        return proposal
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        raise RunError("Codex did not return a valid structured proposal: " + str(error)) from error


class CodexStructuredModel:
    def __init__(self, executable, project, output, *, environment, model, home):
        reject_windows_batch(executable)
        self.executable, self.project, self.output = map(Path, (executable, project, output))
        self.model = model
        self.environment = dict(environment)
        self.environment.update(CODEX_HOME=str(home), CODEX_SQLITE_HOME=str(home))

    def command(self, schema):
        argv = [
            str(self.executable),
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--json",
            "--color",
            "never",
            "-C",
            str(self.project),
        ]
        for feature in (
            "plugins",
            "apps",
            "memories",
            "browser_use",
            "in_app_browser",
            "computer_use",
            "multi_agent",
            "shell_tool",
        ):
            argv.extend(("--disable", feature))
        options = {
            "web_search": "disabled",
            "approval_policy": "never",
            "mcp_servers": {},
            "log_dir": str(self.output / "native-logs"),
            "model": self.model,
            "model_reasoning_effort": "low",
        }
        if os.name == "nt":
            options["windows.sandbox"] = "elevated"
        for key, value in options.items():
            argv.extend(("-c", key + "=" + json.dumps(value)))
        return (*argv, "--output-schema", str(schema), "-")

    def generate(self, run, prompt, schema, cancel):
        remaining = run.contract.deadline - time.time()
        if remaining <= 0 or cancel.is_set():
            raise RunError("run stopped before model dispatch")
        call = self.output / ("model-" + str(uuid.uuid4()))
        call.mkdir()
        schema_file = call / "schema.json"
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        prompt = (
            "Return only a JSON object matching the supplied schema. Use the supplied file "
            "snapshot. Do not use tools or modify files; the host applies your proposal.\n" + prompt
        )
        (call / "prompt.txt").write_text(prompt, encoding="utf-8")
        argv = self.command(schema_file)
        (call / "request.json").write_text(
            json.dumps({"adapter": "codex-cli", "model": self.model, "argv": argv}), encoding="utf-8"
        )
        result = process_tree().run(
            argv,
            self.project,
            env=self.environment,
            stdin=prompt.encode(),
            timeout=min(160, remaining),
            output_limit=2 * 1024 * 1024,
            cancelled=cancel,
            terminate_on_root_exit=True,
        )
        if _capacity_failure(result):
            result = replace(result, retryable_error="capacity")
        record = asdict(result)
        for field in ("stdout", "stderr"):
            record["execution"][field] = record["execution"][field].decode("utf-8", errors="replace")
        (call / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        if b"blocked by policy" in result.execution.stdout + result.execution.stderr:
            raise RunError("native policy refused the model request; host configuration needs review")
        if not clean_exit(result):
            return result, None
        return result, completed_proposal(result.execution.stdout)
