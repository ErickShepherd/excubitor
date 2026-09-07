"""Exercise the CLI against real Git, durable run state, and the shared supervisor."""

import json
import os
import sys
import threading
from types import SimpleNamespace

import pytest

from excubitor.commands import ralph
from excubitor.tests.test_project_backend import project, result  # noqa: F401
from excubitor.windows_development import BASELINE

pytestmark = pytest.mark.skipif(os.name != "nt", reason="native Windows entry point")


@pytest.fixture
def prepared(project, tmp_path, monkeypatch):  # noqa: F811 - imported pytest fixture
    origin, candidate, reader, _, _, _, _ = project
    check = tmp_path / "check.py"
    check.write_text("# Frozen acceptance implementation\n", encoding="utf-8")
    retainer = tmp_path / "retain.py"
    retainer.write_text(
        "import json,subprocess,sys\n"
        "from pathlib import Path\n"
        "request=json.load(sys.stdin)\n"
        f"assert Path(request['candidate']) == Path({str(candidate)!r})\n"
        "assert request['paths']==['main.py']\n"
        f"git={str(reader.git)!r}\n"
        "def call(*args): subprocess.run([git,'-C',request['candidate'],*args],check=True)\n"
        "call('add','--',*request['paths'])\n"
        "call('-c','user.name=Erick Shepherd','-c','user.email=dev@erickshepherd.com',"
        "'-c','commit.gpgsign=false','commit','-qm','Retain disposable CLI test')\n",
        encoding="utf-8",
    )
    job = {
        "origin": str(origin),
        "candidate": str(candidate),
        "metadata": str(reader.metadata),
        "branch": reader.branch,
        "git": str(reader.git),
        "claude": sys.executable,
        "codex": sys.executable,
        "codex_home": str(tmp_path),
        "model": "test-native-model",
        "editable": ["main.py"],
        "goal": "Implement the two agreed units and repair any failed check.",
        "units": ["First unit", "Second unit"],
        "checks": [
            {"name": "behavior", "argv": [sys.executable, "-B", str(check)], "stdin": "", "stdout": "ok\n"}
        ],
        "check_files": [str(check)],
        "max_attempts": 4,
        "time_limit_seconds": 60,
        "retain_command": [sys.executable, "-I", "-B", str(retainer)],
    }
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    args = SimpleNamespace(job=job_file, root=tmp_path / "run", baseline=BASELINE)
    monkeypatch.setattr(ralph, "WindowsDevelopmentExecutor", lambda *a, **k: None)
    return args, candidate, check, job


def test_start_finishes_two_units_and_retries_without_another_start(prepared, monkeypatch):
    args, candidate, _, _ = prepared

    class Runtime:
        editable = {"main.py"}
        calls = 0

        def work(self, run, prompt, cancel):
            self.calls += 1
            (candidate / "main.py").write_bytes(f"# attempt {self.calls}\n".encode())
            return result()

        def verify(self, run, oracle, cancel):
            return result(stdout=b"ok\n" if self.calls == 3 else b"retry\n")

        def review(self, *args):
            return result(), True, "Reviewed both units."

    runtime = Runtime()
    monkeypatch.setattr(ralph, "ClaudeDevelopmentRuntime", lambda *a, **k: runtime)
    assert ralph._start(args) == 0
    final = ralph._load(args.root)
    assert (final.state, final.completed_units, final.attempts, final.reviewed) == ("complete", 2, 3, True)
    assert ralph._status(args) == 0
    assert ralph._stop(args) == 0
    assert not (args.root / "stop-requested").exists()


def test_stop_from_another_client_cancels_and_drains_active_worker(prepared, monkeypatch):
    args, _, _, _ = prepared
    entered, drained = threading.Event(), threading.Event()

    class Runtime:
        editable = {"main.py"}

        def work(self, run, prompt, cancel):
            entered.set()
            assert cancel.wait(10)
            drained.set()
            return result()

    monkeypatch.setattr(ralph, "ClaudeDevelopmentRuntime", lambda *a, **k: Runtime())

    def stop():
        if entered.wait(10):
            ralph._stop(args)

    stopper = threading.Thread(target=stop)
    stopper.start()
    try:
        assert ralph._start(args) == 1
    finally:
        stopper.join(12)
    assert drained.is_set() and ralph._load(args.root).state == "cancelled"


def test_changed_acceptance_file_is_rejected_before_a_worker(prepared, monkeypatch):
    args, _, check, job = prepared
    monkeypatch.setattr(
        ralph, "ClaudeDevelopmentRuntime", lambda *a, **k: SimpleNamespace(editable={"main.py"})
    )
    _, backend, run = ralph._prepare(job, args.root, BASELINE)
    check.write_text("# weakened check", encoding="utf-8")
    with pytest.raises(ralph.RunError, match="acceptance implementation changed"):
        backend.admit(run)
