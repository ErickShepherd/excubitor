from pathlib import Path

import pytest

from excubitor.claude_development import ClaudeDevelopmentRuntime
from excubitor.runs import RunError
from excubitor.windows_development import WindowsDevelopmentExecutor


@pytest.fixture
def runtime(tmp_path):
    project = tmp_path / "candidate"
    project.mkdir()
    (project / "code.py").write_text("original")
    (tmp_path / "agreement.json").write_text("frozen")
    runtime = object.__new__(ClaudeDevelopmentRuntime)
    runtime.project = project
    runtime.editable = frozenset({"code.py"})
    return runtime


@pytest.mark.parametrize("path", ["../agreement.json", "agreement.json", ".git", "C:/agreement.json"])
def test_agreement_edits_rejected_before_any_write(runtime, path):
    with pytest.raises(RunError):
        runtime.apply({"files": [{"path": path, "content": "forged"}], "command": []})
    assert (runtime.project / "code.py").read_text() == "original"
    assert (runtime.project.parent / "agreement.json").read_text() == "frozen"


def test_batch_validates_all_paths_before_writing(runtime):
    (runtime.project / "other.py").write_text("other")
    runtime.editable = frozenset({"code.py", "other.py"})
    with pytest.raises(RunError):
        runtime.apply(
            {
                "files": [
                    {"path": "code.py", "content": "changed"},
                    {"path": "../agreement.json", "content": "forged"},
                ],
                "command": [],
            }
        )
    assert (runtime.project / "code.py").read_text() == "original"


def test_bad_command_does_not_partially_apply(runtime):
    with pytest.raises(RunError):
        runtime.apply({"files": [{"path": "code.py", "content": "changed"}], "command": ["python"]})
    assert (runtime.project / "code.py").read_text() == "original"


def test_valid_edit_and_literal_command(runtime):
    import sys

    command = [sys.executable, "-B", "-c", "print('a; b')"]
    assert runtime.apply({"files": [{"path": "code.py", "content": "fixed\n"}], "command": command}) == tuple(
        command
    )
    assert runtime.snapshot() == {"code.py": "fixed\n"}


def test_malformed_work_and_review_are_retryable_but_scope_refusals_are_fatal(runtime, monkeypatch):
    import threading
    import time
    from types import SimpleNamespace

    from excubitor.acceptance import Execution
    from excubitor.model_response import InvalidModelResponse
    from excubitor.processes import ProcessResult

    result = ProcessResult(Execution(0, b"", b"", .01), False, True, 1)
    run = SimpleNamespace(contract=SimpleNamespace(deadline=time.time() + 30))
    monkeypatch.setattr(runtime, "_call", lambda *a, **kw: (result, {"files": []}))
    failed = runtime.work(run, "implement", threading.Event())
    assert failed.retryable_error == "model-output" and failed.drained
    reviewed, passed, findings = runtime.review(run, "review", threading.Event())
    assert reviewed.retryable_error == "model-output" and not passed and findings
    with pytest.raises(RunError) as refusal:
        runtime.apply({"files": [{"path": "../agreement.json", "content": "bad"}], "command": []})
    assert not isinstance(refusal.value, InvalidModelResponse)


def test_shared_file_rejected(runtime):
    import os

    os.link(runtime.project / "code.py", runtime.project.parent / "alias.py")
    with pytest.raises(RunError, match="unshared"):
        runtime.apply({"files": [{"path": "code.py", "content": "bad"}], "command": []})
    assert (runtime.project.parent / "alias.py").read_text() == "original"


def test_baseline_cannot_be_implicitly_admitted(tmp_path):
    with pytest.raises(RunError, match="explicit"):
        WindowsDevelopmentExecutor(
            Path("unused"),
            tmp_path,
            tmp_path,
            codex_home=tmp_path,
            environment={},
            baseline="credential-isolated",
        )
