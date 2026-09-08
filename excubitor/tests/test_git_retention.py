"""Real disposable Git repositories exercise ordinary retention and policy refusals."""

import hashlib
import json
import os
import shutil
import subprocess

import pytest

from excubitor.git_retention import RetentionError, prepare_git_policy, retain


@pytest.fixture
def repository(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.upper().startswith("GIT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    git = shutil.which("git")
    assert git
    origin = tmp_path / "original"
    origin.mkdir()

    def call(project, *args):
        return subprocess.run([git, "-C", str(project), *args], check=True, capture_output=True).stdout

    call(origin, "init", "-q", "--initial-branch=main")
    call(origin, "config", "user.name", "Fixture Author")
    call(origin, "config", "user.email", "dev@erickshepherd.com")
    call(origin, "config", "commit.gpgsign", "false")
    (origin / "main.py").write_text("old\n", encoding="utf-8")
    (origin / "other.py").write_text("untouched\n", encoding="utf-8")
    (origin / "tests").mkdir()
    (origin / "tests" / "acceptance.py").write_text("assert True\n", encoding="utf-8")
    call(origin, "add", ".")
    call(origin, "commit", "-qm", "Disposable fixture")
    candidate, metadata = tmp_path / "candidate", tmp_path / "metadata"
    call(
        tmp_path,
        "clone",
        "-q",
        "--no-hardlinks",
        "--separate-git-dir",
        str(metadata),
        str(origin),
        str(candidate),
    )
    call(candidate, "checkout", "-qb", "ralph/development")
    prepare_git_policy(git, origin, candidate)
    root = tmp_path / "run"
    root.mkdir()
    job = {
        "candidate": str(candidate),
        "metadata": str(metadata),
        "origin": str(origin),
        "git": git,
        "branch": "refs/heads/ralph/development",
        "editable": ["main.py"],
    }
    request = {"candidate": str(candidate), "paths": ["main.py"], "run_id": "fixture"}

    def save():
        payload = json.dumps(job).encode()
        (root / "job.json").write_bytes(payload)
        (root / "run.json").write_text(
            json.dumps({"id": "fixture", "job_digest": hashlib.sha256(payload).hexdigest()})
        )

    save()
    (candidate / "main.py").write_text("new\n", encoding="utf-8")
    return git, origin, candidate, metadata, root, job, request, call, save


def test_retains_only_candidate_and_preserves_original_identity_and_hooks(repository):
    git, origin, candidate, metadata, root, _, request, call, _ = repository
    original_head = call(origin, "rev-parse", "HEAD")
    witness = root / "hook-witness"
    hook = origin / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\nprintf 'called' > '{witness.as_posix()}'\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    assert retain(git, origin, root, request)["retained"]
    assert witness.read_text() == "called"
    assert (
        call(candidate, "log", "-1", "--format=%an <%ae>").strip()
        == b"Fixture Author <dev@erickshepherd.com>"
    )
    assert call(candidate, "status", "--porcelain") == b""
    assert call(origin, "rev-parse", "HEAD") == original_head
    assert (origin / "main.py").read_text() == "old\n"


def test_hook_refusal_preserves_staged_work_without_fallback(repository):
    git, origin, candidate, _, root, _, request, call, _ = repository
    hook = origin / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\necho 'policy refuses this commit' >&2\nexit 42\n", encoding="utf-8", newline="\n"
    )
    hook.chmod(0o755)
    before = call(candidate, "rev-parse", "HEAD")
    with pytest.raises(RetentionError, match="policy refuses"):
        retain(git, origin, root, request)
    assert call(candidate, "rev-parse", "HEAD") == before
    assert call(candidate, "diff", "--cached", "--name-only").strip() == b"main.py"


@pytest.mark.parametrize("mutation", ["staged", "outside", "default", "marker", "origin", "hidden-diff"])
def test_rejects_candidate_and_index_surprises(repository, mutation):
    git, origin, candidate, _, root, job, request, call, save = repository
    if mutation == "staged":
        call(candidate, "add", "main.py")
    elif mutation == "outside":
        (candidate / "other.py").write_text("unexpected\n")
    elif mutation == "default":
        call(candidate, "checkout", "main")
        job["branch"] = "refs/heads/main"
        save()
    elif mutation == "marker":
        # Git marks this file hidden on Windows; update an existing descriptor
        # instead of Python's CREATE_ALWAYS (which rejects hidden files).
        with (candidate / ".git").open("r+b") as stream:
            stream.write(b"gitdir: wrong\n")
            stream.truncate()
    elif mutation == "origin":
        request["candidate"] = str(origin)
    else:
        call(candidate, "update-index", "--assume-unchanged", "other.py")
        (candidate / "other.py").write_text("hidden unexpected edit\n")
    with pytest.raises(RetentionError):
        retain(git, origin, root, request)


@pytest.mark.parametrize("name", ["../main.py", ":(glob)*", "main.py\u0000", "a\\main.py", ".git/config"])
def test_path_tricks_are_rejected_before_staging(repository, name):
    git, origin, candidate, _, root, job, request, call, save = repository
    request["paths"] = [name]
    job["editable"] = [name]
    save()
    with pytest.raises(RetentionError):
        retain(git, origin, root, request)
    assert call(candidate, "diff", "--cached", "--name-only") == b""


def test_redirected_git_environment_is_rejected(repository, monkeypatch):
    git, origin, _, _, root, _, request, _, _ = repository
    monkeypatch.setenv("GIT_WORK_TREE", str(origin))
    with pytest.raises(RetentionError, match="redirects"):
        retain(git, origin, root, request)


def test_hook_cannot_change_the_admitted_commit_tree(repository):
    git, origin, candidate, _, root, _, request, call, _ = repository
    hook = origin / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\nprintf 'hook edit' > other.py\ngit add -- other.py\n", encoding="utf-8", newline="\n"
    )
    hook.chmod(0o755)
    with pytest.raises(RetentionError, match="admitted tree"):
        retain(git, origin, root, request)
    # The helper reports the resulting policy-side change; it never rewrites history to hide it.
    assert call(candidate, "log", "-1", "--format=%s").strip() == b"Retain Ralph candidate progress"
