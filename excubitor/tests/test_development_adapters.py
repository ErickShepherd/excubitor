"""Interchangeable model transports use one host-owned editing and review path."""

import json
import sys
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from excubitor import development_adapters as adapters
from excubitor.codex_development import completed_proposal
from excubitor.development_runtime import BASELINE, DevelopmentRuntime
from excubitor.runs import RunError
from excubitor.tests.test_project_backend import result


@pytest.mark.parametrize("kind", ["claude-cli", "codex-cli"])
def test_selected_model_uses_shared_edit_check_review_and_separate_executor(kind, tmp_path, monkeypatch):
    candidate, evidence = tmp_path / "candidate", tmp_path / "evidence"
    candidate.mkdir()
    evidence.mkdir()
    (candidate / "main.py").write_text("broken")
    calls = []

    class Model:
        def __init__(self, executable, project, output, **options):
            calls.append(("model", options["model"]))

        def generate(self, run, prompt, schema, cancel):
            calls.append(("request", schema, prompt))
            if "passed" in schema["properties"]:
                return result(), {"passed": True, "findings": "Checked."}
            return result(), {
                "files": [{"path": "main.py", "content": "fixed"}],
                "command": [sys.executable, "-B", "check.py"],
            }

    class Executor:
        baseline = BASELINE

        def run(self, argv, **options):
            calls.append(("command", argv, options))
            assert (candidate / "main.py").read_text() == "fixed"
            return result()

    monkeypatch.setattr(adapters, "ClaudeStructuredModel", Model if kind == "claude-cli" else None)
    monkeypatch.setattr(adapters, "CodexStructuredModel", Model if kind == "codex-cli" else None)
    selected = {"adapter": kind, "executable": sys.executable, "model": "chosen-model"}
    if kind == "codex-cli":
        selected["home"] = str(tmp_path)
    settings = {
        "llm": selected,
        "executor": {"adapter": "codex-windows", "executable": sys.executable, "home": str(tmp_path)},
        "editable": ["main.py"],
    }
    runtime = adapters.make_runtime(settings, candidate, evidence, executor=Executor(), environment={})
    assert type(runtime) is DevelopmentRuntime
    run = SimpleNamespace(contract=SimpleNamespace(deadline=time.time() + 60))
    cancel = threading.Event()
    runtime.work(run, "Repair main.py", cancel)
    runtime.verify(
        run, SimpleNamespace(argv=(sys.executable, "-B", "frozen.py"), stdin="", timeout_seconds=20), cancel
    )
    assert runtime.review(run, "Review independently", cancel)[1:] == (True, "Checked.")
    requests = [c for c in calls if c[0] == "request"]
    assert len(requests) == 2 and "broken" in requests[0][2] and "fixed" in requests[1][2]
    commands = [c for c in calls if c[0] == "command"]
    assert len(commands) == 2 and commands[1][2]["mode"] == "read-only"
    observations = [json.loads(p.read_text()) for p in evidence.glob("model-observation-*.json")]
    assert {item["phase"] for item in observations} == {"work", "review"}
    assert all(item["elapsed_seconds"] >= 0 and item["prompt_bytes"] > 0 for item in observations)
    assert all(item["clean_exit"] for item in observations)


@pytest.mark.parametrize("failure", ["cancelled", "timed_out", "output_limited", "not_drained"])
def test_incomplete_model_result_never_applies_proposal(tmp_path, failure):
    candidate, evidence = tmp_path / "candidate", tmp_path / "evidence"
    candidate.mkdir()
    evidence.mkdir()
    (candidate / "main.py").write_text("original")
    failed = result()
    if failure in ("timed_out", "output_limited"):
        failed = replace(failed, execution=replace(failed.execution, **{failure: True}))
    else:
        failed = replace(failed, **({"cancelled": True} if failure == "cancelled" else {"drained": False}))
    proposal = {"files": [{"path": "main.py", "content": "wrong"}], "command": []}
    runtime = DevelopmentRuntime(
        candidate,
        evidence,
        model=SimpleNamespace(generate=lambda *args: (failed, proposal)),
        executor=SimpleNamespace(baseline=BASELINE),
        editable=["main.py"],
        baseline=BASELINE,
    )
    runtime.work(
        SimpleNamespace(contract=SimpleNamespace(deadline=time.time() + 60)), "Fix", threading.Event()
    )
    assert (candidate / "main.py").read_text() == "original"
    observation = json.loads(next(evidence.glob("model-observation-*.json")).read_text())
    assert not observation["clean_exit"]


def native_events(extra=None):
    events = [{"type": "thread.started", "thread_id": "native-session"}, {"type": "turn.started"}]
    if extra:
        events.append(extra)
    events += [
        {"type": "item.completed", "item": {"type": "agent_message", "text": '{"files":[],"command":[]}'}},
        {"type": "turn.completed", "usage": {}},
    ]
    return events


def encode(events):
    return "\n".join(json.dumps(e) for e in events).encode()


def test_codex_accepts_completed_native_proposal():
    assert completed_proposal(encode(native_events())) == {"files": [], "command": []}


@pytest.mark.parametrize(
    "extra",
    [
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "aggregated_output": '{"files":[]}'},
        },
        {"type": "item.started", "item": {"type": "file_change"}},
        {"type": "turn.failed", "error": {"message": "failure"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "{}"}},
    ],
)
def test_codex_rejects_tool_output_failure_or_ambiguous_response(extra):
    with pytest.raises(RunError, match="structured proposal"):
        completed_proposal(encode(native_events(extra)))


def test_codex_rejects_truncated_turn():
    with pytest.raises(RunError, match="incomplete"):
        completed_proposal(encode(native_events()[:-1]))


def test_unknown_adapter_does_not_fall_back(tmp_path):
    with pytest.raises(RunError, match="unsupported llm"):
        adapters.normalize({"llm": {"adapter": "unknown"}, "executor": {}})
