"""Host-selected model and executor factories, shared by every Ralph entry point.

Descriptors are saved with the agreement. Recovery does not change a backend or
model. A new adapter implements one interface here, not another loop controller.
"""

from __future__ import annotations

import sys
from pathlib import Path

from excubitor.claude_development import ClaudeStructuredModel
from excubitor.codex_development import CodexStructuredModel
from excubitor.command_model import CommandStructuredModel, literal_command
from excubitor.development_runtime import BASELINE, LOCAL_BASELINE, DevelopmentRuntime
from excubitor.http_model_client import validate_endpoint
from excubitor.local_development import LocalDevelopmentExecutor
from excubitor.runs import RunError
from excubitor.windows_development import WindowsDevelopmentExecutor

LEGACY_FIELDS = {"claude", "codex", "codex_home", "model"}
ADAPTER_FIELDS = {"llm", "executor"}
DESCRIPTORS = {
    "claude-cli": {"adapter", "executable", "model"},
    "codex-cli": {"adapter", "executable", "model", "home"},
    "command-json": {"adapter", "command", "model"},
    "chat-completions": {"adapter", "endpoint", "api_key_env", "response_format", "model"},
    "codex-windows": {"adapter", "executable", "home"},
    "windows-process": {"adapter"},
}


def normalize(settings):
    """Read old Claude profiles without rewriting any saved agreement bytes."""
    if not isinstance(settings, dict):
        raise RunError("settings must be a JSON object")
    settings = dict(settings)
    if LEGACY_FIELDS <= settings.keys() and not ADAPTER_FIELDS & settings.keys():
        settings["llm"] = {
            "adapter": "claude-cli",
            "executable": settings["claude"],
            "model": settings["model"],
        }
        settings["executor"] = {
            "adapter": "codex-windows",
            "executable": settings["codex"],
            "home": settings["codex_home"],
        }
        for key in LEGACY_FIELDS:
            del settings[key]
    if LEGACY_FIELDS & settings.keys() or not ADAPTER_FIELDS <= settings.keys():
        raise RunError("select separate llm and executor descriptors, or a complete legacy Claude profile")
    for key in ("llm", "executor"):
        descriptor = settings[key]
        if not isinstance(descriptor, dict):
            raise RunError(key + " must be an adapter descriptor")
        adapter = descriptor.get("adapter")
        allowed = (
            ("claude-cli", "codex-cli", "command-json", "chat-completions")
            if key == "llm"
            else ("codex-windows", "windows-process")
        )
        if adapter not in allowed or set(descriptor) != DESCRIPTORS[adapter]:
            raise RunError("unsupported " + key + " adapter or descriptor fields")
        if key == "llm" and (not isinstance(descriptor["model"], str) or not descriptor["model"].strip()):
            raise RunError("select an explicit model before preparing the agreement")
        if adapter == "command-json":
            literal_command(descriptor["command"])
        if adapter == "chat-completions":
            try:
                validate_endpoint(descriptor["endpoint"])
            except (ValueError, TypeError) as error:
                raise RunError("invalid model endpoint") from error
            if not isinstance(descriptor["api_key_env"], str) or descriptor["response_format"] not in (
                "json_schema",
                "json_object",
            ):
                raise RunError("select an API-key environment name and supported JSON response format")
        for field in ("executable", "home"):
            if field not in descriptor:
                continue
            value = descriptor[field]
            if not isinstance(value, str):
                raise RunError(key + "." + field + " must be an absolute path")
            path = Path(value)
            if not path.is_absolute() or not (path.is_file() if field == "executable" else path.is_dir()):
                raise RunError("refresh the existing absolute path: " + key + "." + field)
    return settings


def baseline_for(settings):
    return LOCAL_BASELINE if settings["executor"]["adapter"] == "windows-process" else BASELINE


def make_executor(settings, project, output, *, environment, baseline):
    selected = normalize(settings)["executor"]
    if selected["adapter"] == "windows-process":
        return LocalDevelopmentExecutor(project, output, environment=environment, baseline=baseline)
    return WindowsDevelopmentExecutor(
        selected["executable"],
        project,
        output,
        codex_home=selected["home"],
        environment=environment,
        baseline=baseline,
    )


def make_runtime(settings, project, output, *, executor, environment, baseline=BASELINE):
    selected = normalize(settings)["llm"]
    options = {"environment": environment, "model": selected["model"]}
    if selected["adapter"] == "claude-cli":
        adapter = ClaudeStructuredModel(
            selected["executable"], project, output, native_model=selected["model"], **options
        )
    elif selected["adapter"] == "codex-cli":
        adapter = CodexStructuredModel(
            selected["executable"], project, output, home=selected["home"], **options
        )
    elif selected["adapter"] == "command-json":
        adapter = CommandStructuredModel(selected["command"], output, **options)
    else:
        command = (
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("http_model_client.py")),
            "--endpoint",
            selected["endpoint"],
            "--response-format",
            selected["response_format"],
        )
        if selected["api_key_env"]:
            command += ("--api-key-env", selected["api_key_env"])
        adapter = CommandStructuredModel(command, output, **options)
    return DevelopmentRuntime(
        project, output, model=adapter, executor=executor, editable=settings["editable"], baseline=baseline
    )
