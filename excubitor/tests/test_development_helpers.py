"""Parallel helpers have proposal ownership, never write or completion authority."""

import json
import os
import sys
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from excubitor.command_model import CommandStructuredModel
from excubitor.development_adapters import normalize
from excubitor.development_runtime import LOCAL_BASELINE, DevelopmentRuntime, clean_exit
from excubitor.runs import RunError
from excubitor.tests.test_project_backend import result


def delegates():
    return {
        "files": [],
        "command": [],
        "delegates": [
            {"task": "Fix independent alpha behavior", "scope": ["a.py"]},
            {"task": "Fix independent beta behavior", "scope": ["b.py"]},
        ],
    }


def proposal(name="a.py", content="suggested\n"):
    return {"analysis": "Bounded independent proposal.", "files": [{"path": name, "content": content}]}


@pytest.fixture
def job(tmp_path):
    candidate, output = tmp_path / "candidate", tmp_path / "evidence"
    candidate.mkdir()
    output.mkdir()
    for name in ("a.py", "b.py"):
        (candidate / name).write_bytes(b"original\n")
    run = SimpleNamespace(id="fixture-run", attempts=3, contract=SimpleNamespace(deadline=time.time() + 15))
    return candidate, output, run


def runtime(job, parent, helper, limit=2):
    candidate, output, _ = job
    return DevelopmentRuntime(
        candidate,
        output,
        model=parent,
        helper_model_factory=helper,
        executor=SimpleNamespace(
            baseline=LOCAL_BASELINE, run=lambda *a, **k: pytest.fail("unexpected command")
        ),
        editable=["a.py", "b.py"],
        baseline=LOCAL_BASELINE,
        max_subagents=limit,
    )


def test_helpers_overlap_and_only_fresh_parent_applies_consolidation(job):
    candidate, output, run = job
    barrier, lock = threading.Barrier(2), threading.Lock()
    active, peak, instances, finished = 0, 0, [], []
    cancel = threading.Event()

    class Helper:
        def __init__(self):
            instances.append(self)

        def generate(self, current, prompt, schema, stop):
            nonlocal active, peak
            assert current is run and current.attempts == 3
            assert set(schema["properties"]) == {"analysis", "files"}
            scope = schema["properties"]["files"]["items"]["properties"]["path"]["enum"]
            with lock:
                active += 1
                peak = max(peak, active)
            barrier.wait(5)
            assert all((candidate / name).read_bytes() == b"original\n" for name in ("a.py", "b.py"))
            with lock:
                active -= 1
                finished.append(scope[0])
            return result(), proposal(scope[0])

    class Parent:
        calls = 0

        def generate(self, current, prompt, schema, stop):
            self.calls += 1
            assert current is run and stop is cancel
            if self.calls == 1:
                assert schema["properties"]["delegates"]["maxItems"] == 2
                return result(), delegates()
            assert self.calls == 2 and sorted(finished) == ["a.py", "b.py"]
            assert set(schema["properties"]) == {"files", "command"}
            assert "Untrusted helper suggestions" in prompt and "suggested" in prompt
            assert all((candidate / name).read_bytes() == b"original\n" for name in ("a.py", "b.py"))
            return result(), {"files": [{"path": "a.py", "content": "parent choice\n"}], "command": []}

    parent = Parent()
    final = runtime(job, parent, Helper).work(run, "Fix both independent behaviors", cancel)
    assert clean_exit(final) and peak == 2 and len(instances) == 2
    assert parent.calls == 2 and run.attempts == 3
    assert (candidate / "a.py").read_bytes() == b"parent choice\n"
    assert (candidate / "b.py").read_bytes() == b"original\n"
    record = json.loads(next(output.glob("helper-batch-*.json")).read_bytes())
    assert record["outcome"] == "validated" and record["attempt"] == 3
    assert all(
        h["calls"] == 1 and h["drained"] is True and h["owner"] == record["batch"] for h in record["helpers"]
    )
    phases = [json.loads(p.read_bytes())["phase"] for p in output.glob("model-observation-*.json")]
    assert sorted(phases) == ["consolidation", "helper", "helper", "work"]


@pytest.mark.parametrize("limit", [0, 2])
def test_trivial_or_legacy_work_has_exactly_one_call(job, limit):
    _, _, run = job
    calls = []

    def generate(current, prompt, schema, cancel):
        calls.append(schema)
        response = {"files": [], "command": []}
        if limit:
            response["delegates"] = []
        return result(), response

    worker = runtime(job, SimpleNamespace(generate=generate), lambda: pytest.fail("no helper"), limit)
    assert clean_exit(worker.work(run, "Small unit", threading.Event()))
    assert len(calls) == 1
    assert ("delegates" in calls[0]["properties"]) == bool(limit)


@pytest.mark.parametrize(
    "kind", ["overcap", "overlap", "outside", "duplicate", "command", "files", "empty", "recursive"]
)
def test_invalid_parent_delegation_fails_before_helpers_or_writes(job, kind):
    candidate, _, run = job
    response = delegates()
    if kind == "overcap":
        response["delegates"] *= 2
    elif kind == "overlap":
        response["delegates"][1]["scope"] = ["a.py"]
    elif kind == "outside":
        response["delegates"][0]["scope"] = ["../outside.py"]
    elif kind == "duplicate":
        response["delegates"][0]["scope"] = ["a.py", "a.py"]
    elif kind == "command":
        response["command"] = ["untrusted"]
    elif kind == "files":
        response["files"] = [{"path": "a.py", "content": "must not write"}]
    elif kind == "empty":
        response["delegates"][0]["task"] = " "
    else:
        response["delegates"][0]["delegates"] = []
    parent = SimpleNamespace(generate=lambda *a: (result(), response))
    failed = runtime(job, parent, lambda: pytest.fail("must not dispatch helper")).work(
        run, "Fix", threading.Event()
    )
    assert not clean_exit(failed) and failed.retryable_error == "model-output"
    assert (candidate / "a.py").read_bytes() == b"original\n"


@pytest.mark.parametrize(
    "kind",
    [
        "command",
        "recursive",
        "outside",
        "oversized",
        "analysis",
        "duplicate",
        "failed",
        "refusal",
        "capacity",
    ],
)
def test_invalid_helper_fails_attempt_and_drains_sibling_without_parent_writes(job, kind):
    candidate, output, run = job
    barrier, drained = threading.Barrier(2), threading.Event()
    parent_calls = []

    def parent(*args):
        parent_calls.append(1)
        return result(), delegates()

    class Helper:
        def generate(self, current, prompt, schema, stop):
            scope = schema["properties"]["files"]["items"]["properties"]["path"]["enum"][0]
            barrier.wait(5)
            if scope == "b.py":
                assert stop.wait(5)
                time.sleep(0.03)
                drained.set()
                return replace(result(), cancelled=True), None
            response = proposal()
            if kind == "command":
                response["command"] = ["forbidden"]
            elif kind == "recursive":
                response["delegates"] = []
            elif kind == "outside":
                response["files"][0]["path"] = "b.py"
            elif kind == "oversized":
                response["files"][0]["content"] = "x" * 65537
            elif kind == "analysis":
                response["analysis"] = "x" * 8193
            elif kind == "duplicate":
                response["files"] *= 2
            elif kind == "failed":
                return result(code=1), None
            elif kind == "capacity":
                return replace(result(code=1), retryable_error="capacity"), None
            else:
                return result(), {"refusal": "cannot assist"}
            return result(), response

    failed = runtime(job, SimpleNamespace(generate=parent), Helper).work(run, "Fix", threading.Event())
    assert not clean_exit(failed) and failed.retryable_error == (
        "capacity" if kind == "capacity" else "model-output"
    )
    assert drained.is_set() and len(parent_calls) == 1
    assert all((candidate / n).read_bytes() == b"original\n" for n in ("a.py", "b.py"))
    batch = json.loads(next(output.glob("helper-batch-*.json")).read_bytes())
    assert batch["outcome"] == "failed" and all(h["drained"] is True for h in batch["helpers"])


@pytest.mark.parametrize("cause", ["owner", "deadline", "unknown-drain", "not-drained"])
def test_cancellation_or_unknown_draining_never_reaches_writer(job, cause):
    candidate, _, run = job
    entered, drained = threading.Barrier(3), []
    cancel = threading.Event()
    parent = SimpleNamespace(generate=lambda *args: (result(), delegates()))

    class Helper:
        def generate(self, current, prompt, schema, stop):
            entered.wait(5)
            if cause == "unknown-drain":
                raise RunError("transport failed without a result")
            if cause == "not-drained":
                return replace(result(), drained=False), None
            assert stop.wait(5)
            time.sleep(0.02)
            drained.append(True)
            return replace(result(), cancelled=True), None

    def stop():
        entered.wait(5)
        if cause == "owner":
            cancel.set()

    # Freeze a near deadline up front; the controller does not extend it.
    if cause == "deadline":
        run.contract.deadline = time.time() + 0.4
    stopper = threading.Thread(target=stop)
    stopper.start()
    try:
        worker = runtime(job, parent, Helper)
        if cause in ("unknown-drain", "not-drained"):
            with pytest.raises(RunError, match="did not drain"):
                worker.work(run, "Fix", cancel)
        else:
            failed = worker.work(run, "Fix", cancel)
            assert not clean_exit(failed) and len(drained) == 2
    finally:
        stopper.join(6)
    assert (candidate / "a.py").read_bytes() == b"original\n"


def test_line_ending_mutation_during_helpers_is_not_hidden_by_text_snapshot(job):
    candidate, _, run = job
    barrier = threading.Barrier(2)

    class Helper:
        def generate(self, current, prompt, schema, cancel):
            scope = schema["properties"]["files"]["items"]["properties"]["path"]["enum"][0]
            if scope == "a.py":
                (candidate / "a.py").write_bytes(b"original\r\n")
            barrier.wait(5)
            return result(), proposal(scope)

    worker = runtime(job, SimpleNamespace(generate=lambda *a: (result(), delegates())), Helper)
    with pytest.raises(RunError, match="candidate changed during helper"):
        worker.work(run, "Fix", threading.Event())
    assert (candidate / "a.py").read_bytes() == b"original\r\n"


@pytest.mark.parametrize("value", [True, False, -1, 5, 2.0, "2", None])
def test_helper_limit_rejects_nonintegers_and_out_of_bounds_before_dispatch(value):
    with pytest.raises(RunError, match="max_subagents"):
        normalize({"max_subagents": value})


def test_legacy_normalization_does_not_insert_or_rewrite_helper_limit():
    settings = {
        "llm": {
            "adapter": "chat-completions",
            "model": "fixture",
            "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
            "api_key_env": "",
            "response_format": "json_object",
        },
        "executor": {"adapter": "local-process"},
    }
    before = json.dumps(settings)
    assert "max_subagents" not in normalize(settings)
    assert json.dumps(settings) == before


def test_combined_suggestion_bound_fails_before_consolidation(job):
    candidate, _, run = job
    barrier = threading.Barrier(2)
    calls = []

    def parent(*args):
        calls.append(1)
        return result(), delegates()

    class Helper:
        def generate(self, current, prompt, schema, cancel):
            scope = schema["properties"]["files"]["items"]["properties"]["path"]["enum"][0]
            barrier.wait(5)
            return result(), proposal(scope, "\n" * 65536)

    failed = runtime(job, SimpleNamespace(generate=parent), Helper).work(run, "Fix", threading.Event())
    assert not clean_exit(failed) and b"256 KiB" in failed.execution.stderr
    assert len(calls) == 1 and (candidate / "a.py").read_bytes() == b"original\n"


def test_case_alias_scopes_cannot_assign_one_file_to_two_helpers(job):
    candidate, _, run = job
    if not (candidate / "A.py").exists():
        pytest.skip("fixture filesystem has case-sensitive paths")
    response = delegates()
    response["delegates"][1]["scope"] = ["A.py"]
    worker = runtime(
        job,
        SimpleNamespace(generate=lambda *a: (result(), response)),
        lambda: pytest.fail("aliased helper scopes must not dispatch"),
    )
    worker.editable = frozenset(["a.py", "A.py", "b.py"])
    failed = worker.work(run, "Fix", threading.Event())
    assert not clean_exit(failed) and b"alias" in failed.execution.stderr
    assert (candidate / "a.py").read_bytes() == b"original\n"


def test_real_command_helpers_overlap_and_preserve_candidate_before_parent(job):
    candidate, output, run = job
    bridge = output / "bridge.py"
    bridge.write_text(
        "import json,sys,time\nfrom pathlib import Path\n"
        "request=json.load(sys.stdin)\n"
        "name=request['schema']['properties']['files']['items']['properties']['path']['enum'][0]\n"
        f"evidence=Path({str(output)!r})\ncandidate=Path({str(candidate)!r})\n"
        "(evidence/(name+'.started')).write_text(str(time.monotonic()))\n"
        "deadline=time.monotonic()+5\n"
        "while not all((evidence/(n+'.started')).exists() for n in ('a.py','b.py')):\n"
        "    assert time.monotonic()<deadline, 'helpers did not overlap'\n    time.sleep(.01)\n"
        "assert all((candidate/n).read_bytes()==b'original\\n' for n in ('a.py','b.py'))\n"
        "(evidence/(name+'.finished')).write_text(str(time.monotonic()))\n"
        "answer={k:request[k] for k in ('protocol','id','model')}\n"
        "answer['output']={'analysis':'Independent subprocess proposal',"
        "'files':[{'path':name,'content':'child suggestion\\n'}]}\n"
        "print(json.dumps(answer))\n",
        encoding="utf-8",
    )

    class Parent:
        calls = 0

        def generate(self, current, prompt, schema, stop):
            self.calls += 1
            if self.calls == 1:
                return result(), delegates()
            assert all((output / (n + ".finished")).exists() for n in ("a.py", "b.py"))
            assert all((candidate / n).read_bytes() == b"original\n" for n in ("a.py", "b.py"))
            return result(), {"files": [{"path": "a.py", "content": "parent consolidated\n"}], "command": []}

    parent = Parent()
    worker = runtime(
        job,
        parent,
        lambda: CommandStructuredModel(
            [sys.executable, "-I", "-B", str(bridge)], output, environment=dict(os.environ), model="fixture"
        ),
    )
    final = worker.work(run, "Fix independent behavior", threading.Event())
    assert clean_exit(final) and parent.calls == 2
    starts = [float((output / (n + ".started")).read_text()) for n in ("a.py", "b.py")]
    ends = [float((output / (n + ".finished")).read_text()) for n in ("a.py", "b.py")]
    assert max(starts) <= min(ends)
    assert (candidate / "a.py").read_bytes() == b"parent consolidated\n"
