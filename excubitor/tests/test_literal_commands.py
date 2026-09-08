"""Batch shims must never turn literal Windows arguments into shell execution."""

import json
import os
import subprocess
import sys

import pytest

from excubitor import development_init, development_plan, development_setup, git_retention
from excubitor.claude_development import ClaudeStructuredModel
from excubitor.codex_development import CodexStructuredModel
from excubitor.command_model import CommandStructuredModel, literal_command
from excubitor.development_runtime import DevelopmentRuntime
from excubitor.host_processes import process_tree
from excubitor.literal_command import BatchCommandError
from excubitor.windows_jobs import create_process_in_job


@pytest.fixture(params=[".cmd", ".bat", ".CmD", ".BAT"])
def batch(tmp_path, request):
    if os.name != "nt":
        pytest.skip("native Windows implicit command-interpreter behavior")
    script = tmp_path / ("bridge" + request.param)
    marker = tmp_path / "batch-ran.txt"
    witness = tmp_path / "injected.txt"
    script.write_text(f'@echo ran>"{marker}"\n@echo %1\n')
    argv = [str(script), "safe&echo.injected>" + str(witness)]
    yield argv
    assert not marker.exists(), "batch launcher executed before rejection"
    assert not witness.exists(), "literal argument was interpreted as a shell command"


def profile_for(surface, argv, tmp_path):
    profile = development_setup.example_profile("command-json", "local-process", "fixture")
    profile["llm"]["command"] = [sys.executable, "-V"]
    profile["git"] = sys.executable
    profile["retain_command"] = [sys.executable, "-V"]
    profile["checks"][0]["argv"] = [sys.executable, "-V"]
    if surface in ("claude-cli", "codex-cli"):
        selected = {"adapter": surface, "executable": argv[0], "model": argv[1]}
        if surface == "codex-cli":
            selected["home"] = str(tmp_path)
        profile["llm"] = selected
    elif surface == "codex-windows":
        profile["executor"] = {"adapter": surface, "executable": argv[0], "home": str(tmp_path)}
    elif surface == "command-json":
        profile["llm"]["command"] = argv
    elif surface == "checks":
        profile["checks"][0]["argv"] = argv
    elif surface == "retain_command":
        profile[surface] = argv
    else:
        profile["git"] = argv[0]
    return profile


@pytest.mark.parametrize(
    "surface",
    [
        "claude-cli",
        "codex-cli",
        "codex-windows",
        "command-json",
        "checks",
        "retain_command",
        "git",
    ],
)
def test_every_profile_surface_fails_before_planning_or_model_dispatch(batch, tmp_path, monkeypatch, surface):
    profile = profile_for(surface, batch, tmp_path)

    def unexpected(*args, **kwargs):
        pytest.fail("unsafe profile reached a model or process factory")

    monkeypatch.setattr(development_plan, "make_runtime", unexpected)
    monkeypatch.setattr(development_plan, "process_tree", unexpected)
    root = tmp_path / "uncreated-plan"
    with pytest.raises(BatchCommandError, match="direct native .exe"):
        development_plan.prepare(profile, tmp_path, root, "preserve literal arguments")
    assert not root.exists()


@pytest.mark.parametrize(
    "surface",
    [
        "claude-cli",
        "codex-cli",
        "codex-windows",
        "command-json",
        "checks",
        "retain_command",
        "git",
    ],
)
def test_doctor_explains_batch_rejection_without_running_it(batch, tmp_path, monkeypatch, surface):
    profile = profile_for(surface, batch, tmp_path)

    def unexpected(*args, **kwargs):
        pytest.fail("doctor dispatched a batch Git executable")

    # Other surfaces may read the selected safe Git executable. No real process
    # is needed here; the preflight diagnostic is the behavior under test.
    if surface == "git":
        monkeypatch.setattr(development_setup.subprocess, "run", unexpected)
    else:

        def unavailable(*args, **kwargs):
            raise OSError("fixture has no Git repository")

        monkeypatch.setattr(development_setup.subprocess, "run", unavailable)
    report = development_setup.inspect(profile, tmp_path, tmp_path / "plan")
    assert not report["ok"]
    assert any(".cmd/.bat" in error and "native .exe" in error for error in report["errors"])


def test_init_rejects_path_shims_and_absolute_commands(batch, monkeypatch):
    monkeypatch.setattr(development_init.shutil, "which", lambda _: batch[0])
    with pytest.raises(BatchCommandError):
        development_init.executable("bridge")
    with pytest.raises(BatchCommandError):
        development_init.command(json.dumps(batch))
    with pytest.raises(BatchCommandError):
        literal_command(batch)


@pytest.mark.parametrize("adapter", ["claude-cli", "codex-cli", "command-json"])
def test_direct_model_construction_rejects_batch(batch, tmp_path, adapter):
    output = tmp_path / "model-evidence"
    with pytest.raises(BatchCommandError):
        if adapter == "claude-cli":
            ClaudeStructuredModel(
                batch[0], tmp_path, output, environment={}, model=batch[1], native_model=batch[1]
            )
        elif adapter == "codex-cli":
            CodexStructuredModel(batch[0], tmp_path, output, environment={}, model=batch[1], home=tmp_path)
        else:
            CommandStructuredModel(batch, output, environment={}, model="fixture")
    assert not output.exists()


def test_direct_windows_process_entry_points_reject_batch(batch, tmp_path):
    with pytest.raises(BatchCommandError):
        process_tree().run(tuple(batch), tmp_path, timeout=5)
    # Rejection precedes touching handles or constructing kernel resources.
    with pytest.raises(BatchCommandError):
        create_process_in_job(batch, tmp_path, None, None, None)


def test_model_proposal_batch_rejected_before_edit(batch, tmp_path):
    runtime = object.__new__(DevelopmentRuntime)
    runtime.project = tmp_path
    runtime.editable = frozenset({"main.py"})
    source = tmp_path / "main.py"
    source.write_text("original")
    with pytest.raises(BatchCommandError):
        runtime.apply({"files": [{"path": "main.py", "content": "changed"}], "command": batch})
    assert source.read_text() == "original"


def test_standalone_retention_and_direct_git_calls_reject_batch(batch, tmp_path):
    with pytest.raises(git_retention.RetentionError, match="native git.exe"):
        git_retention._git(batch[0], tmp_path, batch[1])
    # The direct isolated script must reject --git before reading request JSON;
    # it cannot depend on source-tree imports or the package being installed.
    result = subprocess.run(
        [sys.executable, "-I", "-B", git_retention.__file__, "--git", batch[0], "--origin", str(tmp_path)],
        cwd=tmp_path,
        input=b"not JSON",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert b"native git.exe" in result.stderr


def test_direct_native_interpreter_preserves_metacharacters(tmp_path):
    witness = tmp_path / "injected.txt"
    argument = "safe&echo.injected>" + str(witness)
    command = literal_command([sys.executable, "-I", "-B", "-c", "import sys; print(sys.argv[1])", argument])
    result = process_tree().run(command, tmp_path)
    assert result.execution.exit_code == 0
    assert result.execution.stdout.decode().strip() == argument
    assert not witness.exists()


@pytest.mark.skipif(os.name != "posix", reason="native POSIX shebang execution")
@pytest.mark.parametrize("suffix", ["", ".sh", ".cmd", ".BAT"])
def test_posix_shebang_scripts_remain_literal_and_executable(tmp_path, suffix):
    script = tmp_path / ("bridge" + suffix)
    script.write_text('#!/bin/sh\nprintf "%s\\n" "$1"\n')
    script.chmod(0o700)
    witness = tmp_path / "injected.txt"
    argument = "safe; touch " + str(witness)
    command = literal_command([str(script), argument])
    result = process_tree().run(command, tmp_path)
    assert result.execution.exit_code == 0
    assert result.execution.stdout.decode().strip() == argument
    assert not witness.exists()
