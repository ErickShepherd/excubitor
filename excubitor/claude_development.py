"""Claude structured-output adapter and compatibility constructor."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from excubitor.claude_project import ClaudeProjectRuntime, _clean_exit
from excubitor.development_runtime import DevelopmentRuntime
from excubitor.host_processes import process_tree
from excubitor.literal_command import reject_windows_batch
from excubitor.runs import RunError


class _StructuredOnlyTransport:
    def run(self, argv, cwd, *, sandbox, **options):
        if (
            sandbox != "read-only"
            or "--json-schema" not in argv
            or any(argv[argv.index(flag) + 1] != "" for flag in ("--tools", "--allowedTools"))
        ):
            raise RunError("development coordinator must have no executable or file tools")
        return process_tree().run(argv, cwd, **options, terminate_on_root_exit=True)


class ClaudeStructuredModel:
    def __init__(self, executable, project, output, *, environment, model, native_model):
        reject_windows_batch(executable)
        self.output = Path(output)
        environment = dict(environment)
        environment.update(
            CLAUDE_CODE_TMPDIR=environment.get("TEMP", str(output)),
            CLAUDE_CODE_DEBUG_LOGS_DIR=str(self.output / "debug"),
            CLAUDE_CODE_DISABLE_AUTO_MEMORY="1",
            CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
            CLAUDE_CODE_MAX_TURNS="4",
            DISABLE_AUTOUPDATER="1",
        )
        self.driver = ClaudeProjectRuntime(
            Path(executable),
            Path(project),
            self.output,
            executor=_StructuredOnlyTransport(),
            environment=environment,
            admit=self._admit,
            model=model,
            native_model=native_model,
            effort="low",
        )

    @staticmethod
    def _admit(mode):
        if mode != "read-only":
            raise RunError("native coordinator cannot execute candidate tools")

    def generate(self, run, prompt, schema, cancel):
        session = str(uuid.uuid4())
        argv = list(self.driver.command("read-only", session, review=True))
        for flag in ("--tools", "--allowedTools"):
            argv[argv.index(flag) + 1] = ""
        argv[argv.index("--settings") + 1] = '{"disableClaudeAiConnectors":true}'
        argv[argv.index("--json-schema") + 1] = json.dumps(schema)
        argv += ["--no-chrome", "--max-budget-usd", "2"]
        (self.output / (session + "-prompt.txt")).write_text(prompt, encoding="utf-8")
        result = self.driver.execute(
            "structured-model",
            argv,
            "read-only",
            run,
            stdin=prompt.encode(),
            timeout=160,
            cancel=cancel,
            session=session,
        )
        if not _clean_exit(result):
            return result, None
        terminal = self.driver._completed(result, session, "read-only", review=True)
        initial = json.loads(result.execution.stdout.splitlines()[0])
        if initial["tools"] != ["StructuredOutput"] or terminal.get("permission_denials"):
            raise RunError("unexpected coordinator tools or native denial")
        return result, terminal.get("structured_output")


class ClaudeDevelopmentRuntime(DevelopmentRuntime):
    """Keep previously prepared Claude jobs and callers compatible."""

    def __init__(
        self, claude, project, output, *, executor, environment, editable, model, native_model, baseline
    ):
        adapter = ClaudeStructuredModel(
            claude, project, output, environment=environment, model=model, native_model=native_model
        )
        super().__init__(
            project, output, model=adapter, executor=executor, editable=editable, baseline=baseline
        )
