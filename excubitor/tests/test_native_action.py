"""Protocol tests, not evidence of native GUI identity or owner authentication."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import OutputOracle
from excubitor.native_action import RalphAction
from excubitor.runs import Binding, Contract, RunStore


@pytest.fixture
def fixture(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    store = RunStore(tmp_path / "authority", create=True)
    binding = Binding("fixture", "owner", str(project))
    oracle = OutputOracle("answer", (sys.executable,), "", "ok\n")
    contract = Contract(binding, "one agreed job", ("implement",), (oracle.check,), 2, int(time.time()) + 60)
    messages, launches = [], []
    action = RalphAction(
        store,
        messages.append,
        lambda meta: Binding("fixture", meta["task"], str(project)),
        lambda _: (contract, (oracle,)),
        launches.append,
    )
    action.receive(
        {
            "method": "initialize",
            "id": 0,
            "params": {"protocolVersion": "2025-11-25", "capabilities": {"elicitation": {"form": {}}}},
        }
    )
    return store, binding, action, messages, launches


def call(action, *, name="ralph_start", task="owner", arguments=None):
    action.receive(
        {
            "method": "tools/call",
            "id": 1,
            "params": {"name": name, "_meta": {"task": task}, "arguments": arguments or {}},
        }
    )


def accept(action, messages):
    request_id = messages[-1]["id"]
    action.receive({"id": request_id, "result": {"action": "accept", "content": {"confirm": True}}})
    return request_id


def test_exact_native_accept_dispatches_once_and_connection_close_does_not_disarm(fixture):
    store, binding, action, messages, launches = fixture
    call(action)
    assert messages[-1]["method"] == "elicitation/create" and not launches
    assert store.lookup(binding) is None
    token = accept(action, messages)
    assert len(launches) == 1 and launches[0].contract.binding == binding
    action.receive({"id": token, "result": {"action": "accept", "content": {"confirm": True}}})
    assert len(launches) == 1
    action.close()
    assert store.lookup(binding).enforces


@pytest.mark.parametrize(
    "result",
    [
        {"action": "cancel"},
        {"action": "accept", "content": {"confirm": False}},
        {"action": "accept", "content": {"confirm": 1}},
    ],
)
def test_decline_or_malformed_confirmation_starts_nothing(fixture, result):
    store, binding, action, messages, launches = fixture
    call(action)
    action.receive({"id": messages[-1]["id"], "result": result})
    assert not launches and store.lookup(binding) is None


def test_transport_cancel_prevents_late_accept(fixture):
    store, binding, action, messages, launches = fixture
    call(action)
    token = messages[-1]["id"]
    action.receive({"method": "notifications/cancelled", "params": {"requestId": 1}})
    action.receive({"id": token, "result": {"action": "accept", "content": {"confirm": True}}})
    assert not launches and store.lookup(binding) is None


def test_arguments_and_other_native_scope_cannot_redirect_start(fixture):
    store, binding, action, messages, launches = fixture
    call(action, arguments={"approved": True})
    assert messages[-1]["result"]["isError"]
    call(action, task="unrelated")
    assert messages[-1]["result"]["isError"] and not launches
    assert store.lookup(binding) is None


def test_launcher_failure_retains_interruption_and_reports_error(fixture):
    store, binding, action, messages, launches = fixture

    def fail(run):
        raise RuntimeError("controller launch failed")

    action.launch = fail
    call(action)
    accept(action, messages)
    assert messages[-1]["result"]["isError"]
    assert store.lookup(binding).state == "interrupted"


def test_status_is_exact_scope_and_does_not_create_a_run(fixture):
    store, binding, action, messages, launches = fixture
    call(action, name="ralph_status")
    assert "No active" in messages[-1]["result"]["content"][0]["text"]
    call(action)
    accept(action, messages)
    call(action, name="ralph_status", task="unrelated")
    assert "No active" in messages[-1]["result"]["content"][0]["text"]
    call(action, name="ralph_status")
    assert "running" in messages[-1]["result"]["content"][0]["text"]


def test_reconnect_reuses_exact_authority_without_reapproval_or_replanning(fixture):
    store, binding, action, messages, launches = fixture
    call(action)
    accept(action, messages)
    original = store.lookup(binding)
    action.close()
    recoveries = []

    def no_new_plan(_):
        raise AssertionError("reconnection must never replace the approved plan")

    new = RalphAction(
        store, messages.append, action.binding, no_new_plan, launches.append, reconnect=recoveries.append
    )
    call(new)
    assert recoveries == [original] and len(launches) == 1
    assert store.lookup(binding) == original
    assert "Reconnecting" in messages[-1]["result"]["content"][0]["text"]
    call(new)
    assert recoveries == [original]  # Duplicate native actions do not redispatch.


def test_another_task_cannot_reconnect_a_run(fixture):
    store, binding, action, messages, launches = fixture
    call(action)
    accept(action, messages)
    recoveries = []
    new = RalphAction(
        store, messages.append, action.binding, action.plan, launches.append, reconnect=recoveries.append
    )
    call(new, task="unrelated")
    assert not recoveries and store.lookup(binding).enforces


def test_blocked_job_is_not_reapproved_or_restarted_by_start(fixture):
    store, binding, action, messages, launches = fixture
    call(action)
    accept(action, messages)
    run = store.lookup(binding)
    for _ in range(run.contract.max_attempts + 1):
        run = store.begin_attempt(run)
    assert run.state == "blocked"
    recoveries = []
    new = RalphAction(
        store, messages.append, action.binding, action.plan, launches.append, reconnect=recoveries.append
    )
    call(new)
    assert not recoveries and store.lookup(binding) == run


def test_finished_connection_thread_does_not_leave_a_stale_attachment(fixture):
    store, binding, action, messages, launches = fixture
    alive, recoveries = [True], []
    action.is_attached = lambda _: alive[0]
    action.reconnect = recoveries.append
    call(action)
    accept(action, messages)
    call(action)
    assert not recoveries
    alive[0] = False
    call(action)
    assert recoveries == [store.lookup(binding)]
    assert len(launches) == 1


def test_closed_connection_cannot_reconnect_or_start_again(fixture):
    store, binding, action, messages, launches = fixture
    call(action)
    accept(action, messages)
    original = store.lookup(binding)
    recoveries = []
    action.reconnect = recoveries.append
    action.is_attached = lambda _: False
    action.close()
    call(action)
    assert messages[-1]["result"]["isError"] and not recoveries
    assert store.lookup(binding) == original and len(launches) == 1
