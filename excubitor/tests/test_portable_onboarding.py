"""Project setup resolves real tracked files and literal commands without models."""

import argparse
import json
import sys

import pytest

from excubitor import development_init as setup
from excubitor.tests.test_git_retention import repository  # noqa: F401


def arguments(origin, output, **changes):
    values = dict(
        project=origin,
        output=output,
        llm="command-json",
        model="explicit-fixture-model",
        executable=None,
        codex_home=None,
        model_command=json.dumps([sys.executable, "-I", "-B", "bridge.py"]),
        endpoint=None,
        api_key_env="RALPH_MODEL_API_KEY",
        response_format="json_schema",
        git="git",
        editable=["main*.py"],
        check_file=["tests/*.py"],
        check_argv=[json.dumps([sys.executable, "-B", "{checks}/tests/acceptance.py"])],
        check_timeout=60,
        max_attempts=12,
        time_limit_seconds=3600,
        retain_command=None,
    )
    values.update(changes)
    return argparse.Namespace(**values)


def test_setup_is_concrete_create_only_and_does_not_touch_original(repository, tmp_path):  # noqa: F811
    git, origin, _, _, _, _, _, call, _ = repository
    before = call(origin, "status", "--porcelain")
    output = tmp_path / "profile.json"
    args = arguments(origin, output)
    assert setup._init(args) == 0
    profile = json.loads(output.read_text())
    assert profile["git"] == git
    assert profile["editable"] == ["main.py"]
    assert profile["check_files"] == ["tests/acceptance.py"]
    assert profile["executor"] == {"adapter": "local-process"}
    assert profile["max_subagents"] == 2
    assert profile["checks"][0]["mode"] == "exit-code"
    assert profile["checks"][0]["argv"][0] == sys.executable
    assert "git_retention.py" in profile["retain_command"][3]
    assert call(origin, "status", "--porcelain") == before == b""
    payload = output.read_bytes()
    assert setup._init(args) == 1
    assert output.read_bytes() == payload


def test_shell_strings_are_not_parsed_and_metacharacters_remain_literal():
    with pytest.raises(ValueError):
        setup.command("python -m pytest && echo passed")
    argv = setup.command(
        json.dumps([sys.executable, "-c", "print('literal')", "$(touch not-a-command)", "a b"])
    )
    assert argv[-2:] == ["$(touch not-a-command)", "a b"]


@pytest.mark.parametrize(
    "changes",
    [
        {"editable": ["../*.py"]},
        {"editable": ["missing*.py"]},
        {"editable": ["tests/*.py"]},
        {"check_file": ["missing/*.py"]},
        {"check_argv": ['["python", "-m", "pytest"]']},
        {"max_attempts": 0},
        {"max_subagents": True},
        {"max_subagents": 5},
        {"time_limit_seconds": 86401},
        {"model": " "},
    ],
)
def test_invalid_selection_fails_before_writing(repository, tmp_path, changes):  # noqa: F811
    _, origin, _, _, _, _, _, _, _ = repository
    output = tmp_path / "profile.json"
    assert setup._init(arguments(origin, output, **changes)) == 1
    assert not output.exists()


def test_http_setup_keeps_secret_separate_and_rejects_credentials_in_environment_name(
    repository,  # noqa: F811 - imported fixture
    tmp_path,
    monkeypatch,  # noqa: F811
):
    _, origin, _, _, _, _, _, _, _ = repository
    monkeypatch.setenv("PROVIDER_KEY", "fixture-secret-must-never-be-saved")
    args = arguments(
        origin,
        tmp_path / "profile.json",
        llm="chat-completions",
        endpoint="https://provider.example/v1/chat/completions",
        api_key_env="PROVIDER_KEY",
    )
    profile = setup.create_profile(args)
    assert profile["llm"]["api_key_env"] == "PROVIDER_KEY"
    assert "fixture-secret" not in json.dumps(profile)
    args.api_key_env = "PROVIDER_KEY=secret"
    assert setup._init(args) == 1


def test_dirty_original_and_in_project_output_are_refused(repository, tmp_path):  # noqa: F811
    _, origin, _, _, _, _, _, _, _ = repository
    assert setup._init(arguments(origin, origin / "profile.json")) == 1
    (origin / "main.py").write_text("preserve my unfinished work\n")
    assert setup._init(arguments(origin, tmp_path / "profile.json")) == 1
    assert (origin / "main.py").read_text() == "preserve my unfinished work\n"


def test_external_committer_stays_explicit(repository, tmp_path):  # noqa: F811
    _, origin, _, _, _, _, _, _, _ = repository
    explicit = [sys.executable, "-I", "-B", "owner-broker.py"]
    args = arguments(origin, tmp_path / "profile.json", retain_command=json.dumps(explicit))
    assert setup.create_profile(args)["retain_command"] == explicit
