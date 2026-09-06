import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.candidates import GitCandidateReader
from excubitor.runs import RunError


@pytest.fixture
def candidate(tmp_path):
    from pathlib import Path

    git = Path(shutil.which("git"))
    project, metadata = tmp_path / "project", tmp_path / "metadata"
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def command(*args):
        return subprocess.run([str(git), *args], env=env, capture_output=True, check=True)

    command("init", "-q", "-b", "main", "--separate-git-dir", str(metadata), str(project))
    (project / "hello.py").write_bytes(b"print('hello')\n")
    command("-C", str(project), "add", "hello.py")
    command(
        "-C",
        str(project),
        "-c",
        "user.name=Erick Shepherd",
        "-c",
        "user.email=dev@erickshepherd.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    command("-C", str(project), "checkout", "-qb", "ralph/test")
    return project, metadata, GitCandidateReader(git, project, metadata, "refs/heads/ralph/test"), command


def test_reads_actual_committed_bytes(candidate):
    _, _, reader, _ = candidate
    result = reader.collect()
    assert result.clean and result.isolated
    assert result == reader.collect()


def test_dirty_work_cannot_be_called_clean(candidate):
    project, _, reader, _ = candidate
    (project / "hello.py").write_bytes(b"print('changed')\n")
    with pytest.raises(RunError, match="differ"):
        reader.collect()


def test_untracked_file_cannot_be_hidden(candidate):
    project, _, reader, _ = candidate
    (project / "extra").write_bytes(b"untracked")
    with pytest.raises(RunError, match="untracked"):
        reader.collect()


def test_redirected_git_marker_is_rejected(candidate):
    project, _, reader, _ = candidate
    # Git marks this existing file hidden on Windows. OPEN_EXISTING preserves
    # its attributes; CREATE_ALWAYS from write_text is rejected by Windows.
    with (project / ".git").open("r+b") as stream:
        stream.write(b"gitdir: ../other")
        stream.truncate()
    with pytest.raises(RunError, match="marker"):
        reader.collect()


def test_staged_change_is_not_the_verified_commit(candidate):
    project, _, reader, command = candidate
    original = (project / "hello.py").read_bytes()
    (project / "hello.py").write_bytes(b"staged")
    command("-C", str(project), "add", "hello.py")
    (project / "hello.py").write_bytes(original)
    with pytest.raises(RunError, match="index"):
        reader.collect()
