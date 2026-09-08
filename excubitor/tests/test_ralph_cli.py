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


def test_saved_stop_is_observed_before_watchdog_entry(tmp_path, monkeypatch):
    (tmp_path / "stop-requested").touch()
    monkeypatch.setattr(ralph, "_summary", lambda run: {})

    def supervise(root, store, run, cancel):
        assert cancel.is_set()
        return SimpleNamespace(state="cancelled")

    monkeypatch.setattr(ralph, "_supervise", supervise)
    assert ralph._drive(tmp_path, None, None) == 1


@pytest.fixture(params=["legacy", "claude-cli", "codex-cli"])
def prepared(project, tmp_path, monkeypatch, request):  # noqa: F811 - imported pytest fixture
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
    if request.param != "legacy":
        job["llm"] = {"adapter": request.param, "executable": job["claude"], "model": job["model"]}
        if request.param == "codex-cli":
            job["llm"]["home"] = job["codex_home"]
        job["executor"] = {"adapter": "codex-windows", "executable": job["codex"], "home": job["codex_home"]}
        for key in ("claude", "codex", "codex_home", "model"):
            del job[key]
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    args = SimpleNamespace(job=job_file, root=tmp_path / "run", baseline=BASELINE)
    monkeypatch.setattr(ralph, "make_executor", lambda *a, **k: None)
    monkeypatch.setattr(
        ralph,
        "_supervise",
        lambda root, store, run, cancel: ralph.Supervisor(store, ralph._attach(root)[1]).drive(
            run.id, cancel=cancel
        ),
    )
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
    monkeypatch.setattr(ralph, "make_runtime", lambda *a, **k: runtime)
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

    monkeypatch.setattr(ralph, "make_runtime", lambda *a, **k: Runtime())

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
    monkeypatch.setattr(ralph, "make_runtime", lambda *a, **k: SimpleNamespace(editable={"main.py"}))
    _, backend, run = ralph._prepare(job, args.root, BASELINE)
    check.write_text("# weakened check", encoding="utf-8")
    with pytest.raises(ralph.RunError, match="acceptance implementation changed"):
        backend.admit(run)


@pytest.mark.parametrize("change", ["budget", "model", "executor", "subagents"])
def test_resume_rejects_changed_saved_settings(prepared, monkeypatch, change):
    args, _, _, job = prepared
    monkeypatch.setattr(ralph, "make_runtime", lambda *a, **k: SimpleNamespace(editable={"main.py"}))
    ralph._prepare(job, args.root, BASELINE)
    path = args.root / "job.json"
    changed = json.loads(path.read_text())
    if change == "budget":
        changed["max_attempts"] = 100
    elif change == "model":
        changed["llm"]["model"] = "another-model"
    elif change == "subagents":
        changed["max_subagents"] = 4
    else:
        changed["executor"]["adapter"] = "another-executor"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ralph.RunError, match="saved job settings changed"):
        ralph._resume(args)


@pytest.mark.parametrize("limit", [None, 0, 2, 4])
def test_saved_helper_limit_is_frozen_and_old_jobs_are_not_rewritten(prepared, monkeypatch, limit):
    args, _, _, job = prepared
    if limit is not None:
        job["max_subagents"] = limit
    observed = []

    def runtime(settings, *args, **kwargs):
        observed.append(settings.get("max_subagents", 0))
        return SimpleNamespace(editable={"main.py"})

    monkeypatch.setattr(ralph, "make_runtime", runtime)
    ralph._prepare(job, args.root, BASELINE)
    path = args.root / "job.json"
    before = path.read_bytes()
    assert ("max_subagents" in json.loads(before)) == (limit is not None)
    ralph._attach(args.root)
    assert path.read_bytes() == before
    assert observed == [limit or 0, limit or 0]


def test_failed_runtime_attachment_is_recorded_as_interrupted(prepared, monkeypatch):
    args, _, _, job = prepared

    def unavailable(*args, **kwargs):
        raise ralph.RunError("runtime unavailable")

    monkeypatch.setattr(ralph, "make_runtime", unavailable)
    with pytest.raises(ralph.RunError, match="runtime unavailable"):
        ralph._prepare(job, args.root, BASELINE)
    assert ralph._load(args.root).state == "interrupted"


def test_plain_goal_prepares_clone_and_frozen_checks_without_starting(prepared, monkeypatch, tmp_path):
    from excubitor import development_plan

    _, source, _, job = prepared
    profile = {
        k: v
        for k, v in job.items()
        if k not in {"origin", "candidate", "metadata", "branch", "goal", "units"}
    }
    profile["check_files"] = ["untouched.txt"]
    source_bytes = (source / "main.py").read_bytes()

    class Planner:
        def _call(self, *args, **kwargs):
            assert kwargs["schema"]["properties"]["units"]["maxItems"] == 2
            return result(), {"goal": "Implement the requested behavior.", "units": ["Fix main.py"]}

    monkeypatch.setattr(development_plan, "make_runtime", lambda *a, **k: Planner())
    root = tmp_path / "planned"
    preview = development_plan.prepare(profile, source, root, "Fix the behavior")
    assert "Implementation has not started" in preview
    assert not (root / "run").exists()
    assert (root / "candidate/main.py").read_bytes() == source_bytes == (source / "main.py").read_bytes()
    assert (root / "checks/untouched.txt").read_bytes() == (source / "untouched.txt").read_bytes()
    planned = json.loads((root / "job.json").read_text())
    assert planned["candidate"] != str(source) and planned["units"] == ["Fix main.py"]


def test_planner_rejects_units_that_consume_retry_budget(prepared, monkeypatch, tmp_path):
    from excubitor import development_plan

    _, source, _, job = prepared
    profile = {
        k: v
        for k, v in job.items()
        if k not in {"origin", "candidate", "metadata", "branch", "goal", "units"}
    }
    profile["check_files"] = ["untouched.txt"]
    planner = SimpleNamespace(
        _call=lambda *a, **k: (result(), {"goal": "Fix", "units": ["first", "second", "third"]})
    )
    monkeypatch.setattr(development_plan, "make_runtime", lambda *a, **k: planner)
    root = tmp_path / "too-many-units"
    with pytest.raises(ralph.RunError, match="valid plan"):
        development_plan.prepare(profile, source, root, "Fix behavior")
    assert not (root / "job.json").exists() and not (root / "run").exists()
