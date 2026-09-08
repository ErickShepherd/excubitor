"""Preflight catches launch failures without paid calls or original-repo writes."""

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from excubitor import development_setup as setup
from excubitor.cli import main


@pytest.fixture
def configured(tmp_path):
    project = tmp_path / "original"
    project.mkdir()
    (project / "main.py").write_text("print('original')\n", encoding="utf-8")
    (project / "tests").mkdir()
    (project / "tests" / "acceptance.py").write_text("print('ok')\n", encoding="utf-8")
    git = shutil.which("git")
    assert git
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c",
            "user.name=Erick Shepherd",
            "-c",
            "user.email=dev@erickshepherd.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "Disposable preflight fixture",
        ),
    ):
        subprocess.run([git, "-C", str(project), *args], env=env, check=True, capture_output=True)
    profile = setup.example_profile("command-json", "windows-process", "fixture-model")
    profile["git"] = git
    profile["llm"]["command"] = [sys.executable, "-I", "-B", "bridge.py"]
    profile["checks"][0]["argv"][0] = sys.executable
    profile["retain_command"] = [sys.executable, "-I", "-B", "retainer.py"]
    return profile, project, tmp_path / "fresh-plan"


def snapshot(project):
    return {
        str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in project.rglob("*")
        if p.is_file()
    }


@pytest.mark.skipif(os.name != "nt", reason="native Windows launcher")
def test_doctor_is_read_only_and_executes_only_git(configured, monkeypatch, capsys, tmp_path):
    profile, project, root = configured
    before = snapshot(project)
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    calls = []
    run = subprocess.run

    def observe(argv, **options):
        assert argv[0] == profile["git"]
        assert options["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert "core.fsmonitor=false" in argv
        calls.append(argv)
        return run(argv, **options)

    monkeypatch.setattr(setup.subprocess, "run", observe)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong-repository"))
    assert (
        main(
            [
                "ralph",
                "doctor",
                "--profile",
                str(path),
                "--project",
                str(project),
                "--root",
                str(root),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["baseline"] == "trusted-local-v1"
    assert len(calls) == 3
    assert snapshot(project) == before
    assert not root.exists()
    assert json.loads(path.read_text()) == profile


def test_dirty_original_preserved(configured):
    profile, project, root = configured
    (project / "main.py").write_text("precious dirty work")
    (project / "untracked.txt").write_text("also precious")
    before = snapshot(project)
    report = setup.inspect(profile, project, root)
    assert any("dirty" in error for error in report["errors"])
    assert snapshot(project) == before and not root.exists()


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("max_attempts", True, "max_attempts"),
        ("time_limit_seconds", 86401, "time_limit_seconds"),
        ("editable", ["../outside.py"], "editable[0]"),
        ("editable", ["missing.py"], "editable[0]"),
        ("editable", ["main.py"] * 33, "editable must"),
        ("check_files", ["tests/../../outside.py"], "check_files[0]"),
        ("check_files", [], "check_files must"),
        ("checks", [], "acceptance check"),
        ("checks", [{"argv": [123]}], "checks[0]"),
        ("retain_command", ["missing.exe"], "retain_command"),
    ],
)
def test_bad_profile_fields(configured, field, value, message):
    profile, project, root = configured
    profile[field] = value
    report = setup.inspect(profile, project, root)
    assert not report["ok"] and any(message in e for e in report["errors"])
    assert not root.exists()


@pytest.mark.parametrize("case", ["empty-model", "missing-client", "missing-git", "placeholder", "key"])
def test_missing_model_executable_or_secret_is_reported_without_echo(configured, monkeypatch, case):
    profile, project, root = configured
    marker = "sensitive-value-never-print"
    if case == "empty-model":
        profile["llm"]["model"] = ""
    elif case == "missing-client":
        profile["llm"]["command"][0] = str(root / "missing.exe")
    elif case == "missing-git":
        profile["git"] = str(root / "missing-git.exe")
    elif case == "placeholder":
        profile["llm"]["model"] = "REPLACE_MODEL"
    else:
        profile["llm"] = {
            "adapter": "chat-completions",
            "endpoint": "https://example.invalid/v1/chat/completions",
            "model": "local-model",
            "api_key_env": marker,
            "response_format": "json_schema",
        }
        monkeypatch.delenv(marker, raising=False)
    report = setup.inspect(profile, project, root)
    assert not report["ok"] and report["errors"]
    assert marker not in json.dumps(report)


def test_key_value_is_never_returned(configured, monkeypatch):
    profile, project, root = configured
    profile["llm"] = {
        "adapter": "chat-completions",
        "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
        "model": "local-model",
        "api_key_env": "TEST_RALPH_KEY",
        "response_format": "json_object",
    }
    monkeypatch.setenv("TEST_RALPH_KEY", "secret-marker")
    report = setup.inspect(profile, project, root)
    assert not any("API-key" in e for e in report["errors"])
    assert "secret-marker" not in json.dumps(report)


@pytest.mark.parametrize("placement", ["inside", "ancestor", "existing"])
def test_planning_root_must_be_fresh_and_separate(configured, placement):
    profile, project, root = configured
    root = {"inside": project / "plan", "ancestor": project.parent, "existing": project / "tests"}[placement]
    assert any("Planning root" in e for e in setup.inspect(profile, project, root)["errors"])


def test_legacy_profile_remains_readable_and_unchanged(configured):
    profile, project, root = configured
    profile.pop("llm")
    profile.pop("executor")
    profile.update(
        claude=sys.executable, codex=sys.executable, codex_home=str(project.parent), model="fixture"
    )
    before = json.dumps(profile)
    report = setup.inspect(profile, project, root)
    assert report["baseline"] == "native-development-v1"
    assert not report["errors"] if os.name == "nt" else not report["ok"]
    assert json.dumps(profile) == before


@pytest.mark.parametrize("llm", setup.MODELS)
@pytest.mark.parametrize("executor", setup.EXECUTORS)
def test_create_only_templates_and_explicit_adapters(tmp_path, llm, executor, capsys):
    output = tmp_path / "profile.json"
    args = ["ralph", "profile-template", "--llm", llm, "--executor", executor, "--output", str(output)]
    assert main(args) == 0
    original = output.read_bytes()
    profile = json.loads(original)
    assert set(profile) == setup.PROFILE_FIELDS
    assert profile["llm"]["adapter"] == llm and profile["executor"]["adapter"] == executor
    assert main(args) == 1
    assert output.read_bytes() == original
    assert "not created" in capsys.readouterr().out


def test_malformed_json_returns_failure_without_writes(tmp_path, capsys):
    path = tmp_path / "profile.json"
    path.write_text("{bad json")
    assert (
        main(
            [
                "ralph",
                "doctor",
                "--profile",
                str(path),
                "--project",
                str(tmp_path),
                "--root",
                str(tmp_path / "new"),
                "--json",
            ]
        )
        == 1
    )
    assert not json.loads(capsys.readouterr().out)["ok"]
    assert path.read_text() == "{bad json"


@pytest.mark.parametrize("kind", ["oversized", "non-utf8", "hardlink", "symlink"])
def test_unusable_editable_file_is_rejected(configured, tmp_path, kind):
    profile, project, root = configured
    source = project / "main.py"
    if kind == "oversized":
        source.write_bytes(b"x" * 65537)
    elif kind == "non-utf8":
        source.write_bytes(b"\xff")
    elif kind == "hardlink":
        os.link(source, tmp_path / "shared.py")
    else:
        target = tmp_path / "outside.py"
        target.write_text("outside")
        link = project / "redirect.py"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("host does not permit fixture symlinks")
        profile["editable"] = ["redirect.py"]
    before = snapshot(project)
    assert any("editable[0]" in e for e in setup.inspect(profile, project, root)["errors"])
    assert snapshot(project) == before and not root.exists()


def test_duplicate_checks_and_native_stdin_are_rejected(configured):
    profile, project, root = configured
    profile["executor"] = {
        "adapter": "codex-windows",
        "executable": sys.executable,
        "home": str(project.parent),
    }
    profile["checks"] *= 2
    assert any("checks[1]" in e for e in setup.inspect(profile, project, root)["errors"])
    profile["checks"] = [dict(profile["checks"][0], stdin="input")]
    assert any("checks[0]" in e for e in setup.inspect(profile, project, root)["errors"])


@pytest.mark.parametrize("llm", setup.MODELS)
@pytest.mark.parametrize("executor", setup.EXECUTORS)
def test_completed_templates_preflight_the_actual_host(configured, llm, executor):
    settings, project, root = configured
    profile = setup.example_profile(llm, executor, "selected-model")
    for key in ("git", "checks", "retain_command"):
        profile[key] = settings[key]
    for descriptor in (profile["llm"], profile["executor"]):
        if "executable" in descriptor:
            descriptor["executable"] = sys.executable
        if "home" in descriptor:
            descriptor["home"] = str(project.parent)
    if llm == "command-json":
        profile["llm"]["command"] = [sys.executable, "-I", "-B", "bridge.py"]
    if llm == "chat-completions":
        profile["llm"].update(endpoint="http://127.0.0.1:8000/v1/chat/completions", api_key_env="")
    report = setup.inspect(profile, project, root)
    available = (
        executor in ("local-process", "windows-process", "codex-windows")
        if os.name == "nt"
        else executor in ("local-process", "posix-process")
    )
    assert report["ok"] == available, report
    if not available:
        assert any("unavailable" in error or "requires native Windows" in error for error in report["errors"])
    assert not root.exists()
