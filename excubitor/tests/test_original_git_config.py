"""Normal Git line-ending configuration must not make a clean original dirty."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from excubitor import development_init, development_plan, development_setup
from excubitor.candidates import GitCandidateReader
from excubitor.runs import RunError
from excubitor.tests.test_project_backend import result


def snapshot(project):
    return {
        str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in project.rglob("*")
        if path.is_file()
    }


@pytest.fixture(params=["system", "global", "command"])
def crlf_original(tmp_path, monkeypatch, request):
    for name in list(os.environ):
        if name.upper().startswith("GIT_"):
            monkeypatch.delenv(name)
    config = tmp_path / "fixture.gitconfig"
    config.write_text("[core]\n    autocrlf = input\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    if request.param == "system":
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "0")
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(config))
    elif request.param == "global":
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    else:
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.autocrlf")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "input")
    git = shutil.which("git")
    assert git
    project = tmp_path / "original"
    project.mkdir()
    for name in ("main.py", "acceptance.py"):
        (project / name).write_bytes(b"print('original')\r\n")

    def read(*args, env=None):
        return subprocess.run(
            [git, "--no-optional-locks", "-C", str(project), *args],
            env=env,
            check=True,
            capture_output=True,
        ).stdout

    read("init", "-q")
    read("add", ".")
    read(
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=dev@erickshepherd.com",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.hooksPath=" + str(tmp_path / "no-hooks"),
        "commit",
        "-qm",
        "Prepare disposable CRLF fixture",
    )
    # Force content checking instead of a coincidental clean index stat cache.
    for name in ("main.py", "acceptance.py"):
        source = project / name
        stamp = source.stat().st_mtime_ns + 5_000_000_000
        os.utime(source, ns=(stamp, stamp))
    assert read("status", "--porcelain=v1") == b""
    assert read("show", "HEAD:main.py") == b"print('original')\n"
    isolated = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    isolated.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    assert b"main.py" in read("status", "--porcelain=v1", env=isolated)
    profile = development_setup.example_profile("command-json", "local-process", "fixture-model")
    profile.update(
        git=git,
        editable=["main.py"],
        check_files=["acceptance.py"],
        retain_command=[sys.executable, "-I", "-B", str(tmp_path / "retainer.py")],
    )
    profile["llm"]["command"] = [sys.executable, "-I", "-B", str(tmp_path / "bridge.py")]
    profile["checks"][0]["argv"][0] = sys.executable
    return project, profile, config


def test_clean_crlf_original_keeps_effective_config_and_candidate_exact_bytes(
    crlf_original, tmp_path, monkeypatch
):
    project, profile, config = crlf_original
    before, config_before = snapshot(project), config.read_bytes()
    # Inherited repository redirects must not affect any original or candidate query.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        monkeypatch.setenv(name, str(tmp_path / "wrong-repository"))
    assert development_init.tracked_files(project, profile["git"]) == ["acceptance.py", "main.py"]
    root = tmp_path / "plan"
    report = development_setup.inspect(profile, project, root)
    assert report["ok"], report
    assert not root.exists()
    planner = SimpleNamespace(_call=lambda *a, **k: (result(), {"goal": "Fix", "units": ["Fix main.py"]}))
    monkeypatch.setattr(development_plan, "make_runtime", lambda *a, **k: planner)
    development_plan.prepare(profile, project, root, "Fix main.py")
    assert snapshot(project) == before
    assert config.read_bytes() == config_before
    job = json.loads((root / "job.json").read_bytes())
    assert job["max_attempts"] == profile["max_attempts"]
    assert job["time_limit_seconds"] == profile["time_limit_seconds"]
    assert (root / "checks/acceptance.py").read_bytes() == (project / "acceptance.py").read_bytes()
    candidate = root / "candidate"
    reader = GitCandidateReader(Path(profile["git"]), candidate, root / "git", job["branch"])
    reader.collect()
    assert (candidate / "main.py").read_bytes() == b"print('original')\n"
    (candidate / "main.py").write_bytes(b"print('original')\r\n")
    with pytest.raises(RunError, match="working bytes differ"):
        reader.collect()


def test_real_original_edit_still_rejected_without_changes(crlf_original, tmp_path, monkeypatch):
    project, profile, config = crlf_original
    (project / "main.py").write_bytes(b"print('precious edit')\r\n")
    before, config_before = snapshot(project), config.read_bytes()
    with pytest.raises(ValueError, match="dirty"):
        development_init.tracked_files(project, profile["git"])
    assert any(
        "dirty" in error
        for error in development_setup.inspect(profile, project, tmp_path / "doctor")["errors"]
    )
    monkeypatch.setattr(development_plan, "make_runtime", lambda *a, **k: pytest.fail("no model call"))
    with pytest.raises(RunError, match="clean original"):
        development_plan.prepare(profile, project, tmp_path / "plan", "Fix")
    assert snapshot(project) == before and config.read_bytes() == config_before


def test_original_change_during_planning_still_rejected(crlf_original, tmp_path, monkeypatch):
    project, profile, _ = crlf_original

    def model(*args, **kwargs):
        (project / "main.py").write_bytes(b"print('concurrent edit')\r\n")
        return result(), {"goal": "Fix", "units": ["Fix main.py"]}

    monkeypatch.setattr(development_plan, "make_runtime", lambda *a, **k: SimpleNamespace(_call=model))
    root = tmp_path / "plan"
    with pytest.raises(RunError, match="original changed during planning"):
        development_plan.prepare(profile, project, root, "Fix")
    assert (project / "main.py").read_bytes() == b"print('concurrent edit')\r\n"
    assert not (root / "job.json").exists()
