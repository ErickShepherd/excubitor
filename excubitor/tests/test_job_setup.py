"""Proposal-to-confirmation behavior with fixture transport, not native admission."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import OutputOracle
from excubitor.job_setup import CheckRunner, JobPlanner, LaunchDefaults
from excubitor.native_action import RalphAction
from excubitor.runs import Binding, Candidate, NotReady, RunStore


def proposal():
    return {
        "goal": "Normalize a line of comma-separated words.",
        "units": ["Split and trim words", "Sort and print words"],
        "checks": [{"name": "trim-sort", "runner": "program", "stdin": " b, a \n", "stdout": "a,b\n"}],
    }


@pytest.fixture
def setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    clock = [100]

    def admit(contract, oracles):
        assert Path(contract.binding.project) == project
        assert all(oracle.argv == (sys.executable, "-I", "-B", "main.py") for oracle in oracles)

    planner = JobPlanner(
        LaunchDefaults(6, 900, 12, 3600),
        (CheckRunner("program", (sys.executable, "-I", "-B", "main.py"), 15),),
        admit=admit,
        clock=lambda: clock[0],
    )
    store = RunStore(tmp_path / "authority", create=True, clock=lambda: clock[0])
    messages, launches, recoveries = [], [], []

    def fixed_plan(_):
        raise AssertionError("proposal mode must not fall back to the hard-coded test job")

    def action():
        result = RalphAction(
            store,
            messages.append,
            lambda meta: Binding("fixture", meta["task"], str(project)),
            fixed_plan,
            launches.append,
            reconnect=recoveries.append,
            drafts=planner,
        )
        result.receive(
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"elicitation": {"form": {}}},
                },
            }
        )
        return result

    return action(), action, planner, store, project, clock, messages, launches, recoveries


def call(action, arguments=None, task="owner", name="ralph_start"):
    action.receive(
        {
            "method": "tools/call",
            "id": "call",
            "params": {
                "name": name,
                "_meta": {"task": task},
                "arguments": {} if arguments is None else arguments,
            },
        }
    )


def answer(action, token, confirm=True):
    action.receive({"id": token, "result": {"action": "accept", "content": {"confirm": confirm}}})


def test_proposal_needs_one_native_confirmation_and_snapshots_exact_checks(setup):
    action, _, _, store, project, _, messages, launches, _ = setup
    draft = proposal()
    call(action, {"job": draft})
    form = messages[-1]
    assert form["method"] == "elicitation/create"
    assert "Normalize" in form["params"]["message"] and '"a,b\\n"' in form["params"]["message"]
    assert not launches and store.lookup(Binding("fixture", "owner", str(project))) is None
    assert not (store.directory / "oracles").exists()
    draft["goal"] = "changed after preview"
    draft["checks"][0]["stdout"] = "anything"
    answer(action, form["id"])
    assert len(launches) == 1
    run = launches[0]
    assert run.contract.goal == proposal()["goal"]
    assert run.contract.max_attempts == 6 and run.contract.deadline == 1000
    assert OutputOracle.load(store, run.contract.checks[0]).stdout == "a,b\n"
    answer(action, form["id"])
    assert len(launches) == 1


def test_descriptor_exposes_host_runners_and_defaults_but_no_authority(setup):
    action, _, _, _, _, _, messages, _, _ = setup
    action.receive({"method": "tools/list", "id": 1})
    start, status = messages[-1]["result"]["tools"]
    properties = start["inputSchema"]["properties"]["job"]["properties"]
    assert properties["attempts"]["default"] == 6
    assert properties["seconds"]["default"] == 900
    assert properties["checks"]["items"]["properties"]["runner"]["enum"] == ["program"]
    assert set(properties) == {"goal", "units", "checks", "attempts", "seconds"}
    assert status["inputSchema"]["properties"] == {} and status["annotations"]["readOnlyHint"]


@pytest.mark.parametrize(
    "location,field",
    [
        ("root", "approved"),
        ("root", "_meta"),
        ("root", "run_id"),
        ("job", "binding"),
        ("job", "project"),
        ("job", "completion"),
        ("job", "authorization"),
        ("job", "deadline"),
        ("job", "storage"),
        ("check", "argv"),
        ("check", "environment"),
        ("check", "executable"),
    ],
)
def test_proposal_cannot_smuggle_identity_approval_commands_or_completion(setup, location, field):
    action, _, _, store, project, _, messages, launches, _ = setup
    draft = proposal()
    arguments = {"job": draft}
    target = {"root": arguments, "job": draft, "check": draft["checks"][0]}[location]
    target[field] = "not authority"
    call(action, arguments)
    assert messages[-1]["result"]["isError"] and not launches and not action.pending
    assert store.lookup(Binding("fixture", "owner", str(project))) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempts", True),
        ("attempts", 1),
        ("attempts", 13),
        ("seconds", 0),
        ("seconds", 3601),
        ("units", []),
        ("units", ["same", "same"]),
        ("units", [{}]),
        ("checks", []),
        ("goal", "  "),
    ],
)
def test_invalid_or_excessive_job_never_reaches_confirmation(setup, field, value):
    action, _, _, _, _, _, messages, launches, _ = setup
    draft = proposal()
    draft[field] = value
    call(action, {"job": draft})
    assert messages[-1]["result"]["isError"] and not launches and not action.pending


@pytest.mark.parametrize(
    "field,value",
    [
        ("runner", "unadmitted"),
        ("runner", {}),
        ("name", "bad\nname"),
        ("exit_code", True),
        ("timeout_seconds", 16),
        pytest.param("stdout", "x" * 65537, id="oversized-output"),
    ],
)
def test_check_boundaries_refuse_unadmitted_or_changed_execution(setup, field, value):
    action, _, _, _, _, _, messages, launches, _ = setup
    draft = proposal()
    draft["checks"][0][field] = value
    call(action, {"job": draft})
    assert messages[-1]["result"]["isError"] and not launches and not action.pending


def test_oversized_preview_cannot_start_a_partial_job(setup):
    action, _, _, store, _, _, messages, launches, _ = setup
    draft = proposal()
    draft["checks"][0]["stdout"] = "x" * 32768
    call(action, {"job": draft})
    assert messages[-1]["result"]["isError"] and not launches and not action.pending
    assert not (store.directory / "oracles").exists()


def test_missing_job_cannot_fall_back_to_an_example_and_status_is_ordinary(setup):
    action, _, _, _, _, _, messages, launches, _ = setup
    call(action)
    assert messages[-1]["result"]["isError"]
    call(action, name="ralph_status")
    assert "No active" in messages[-1]["result"]["content"][0]["text"]
    assert not launches


def test_pending_preview_cannot_be_replaced_and_decline_leaves_no_run(setup):
    action, _, _, store, project, _, messages, launches, _ = setup
    call(action, {"job": proposal()})
    token = messages[-1]["id"]
    other = proposal()
    other["goal"] = "substitution"
    call(action, {"job": other})
    assert messages[-1]["result"]["isError"]
    assert list(action.pending) == [token]
    answer(action, token, False)
    assert not launches and store.lookup(Binding("fixture", "owner", str(project))) is None


def test_confirmation_cannot_cross_connections_and_close_discards_draft(setup):
    first, create, _, _, _, _, messages, launches, _ = setup
    call(first, {"job": proposal()})
    token = messages[-1]["id"]
    second = create()
    answer(second, token)
    assert not launches
    first.close()
    answer(first, token)
    assert not launches


def test_reconnect_ignores_changed_defaults_and_refuses_replacement_job(setup):
    first, create, planner, store, project, clock, messages, launches, recoveries = setup
    call(first, {"job": proposal()})
    answer(first, messages[-1]["id"])
    run = store.begin_attempt(launches[0])
    first.close()
    clock[0] += 10
    planner.defaults = LaunchDefaults(12, 3600, 12, 3600)
    second = create()
    call(second, {"job": proposal()})
    assert messages[-1]["result"]["isError"] and not recoveries
    call(second)
    assert recoveries == [run] and len(launches) == 1
    assert recoveries[0].attempts == 1 and recoveries[0].contract.deadline == 1000
    call(second, name="ralph_status", task="unrelated")
    assert "No active" in messages[-1]["result"]["content"][0]["text"]
    assert store.lookup(Binding("fixture", "owner", str(project))) == run


def test_explicit_limits_are_displayed_and_freeze_once(setup):
    action, _, planner, _, _, _, messages, launches, _ = setup
    draft = proposal()
    draft.update(attempts=8, seconds=1800)
    call(action, {"job": draft})
    assert "8 attempts" in messages[-1]["params"]["message"]
    answer(action, messages[-1]["id"])
    assert launches[0].contract.deadline == 1900
    assert planner.defaults.attempts == 6


def test_schema_is_not_mutable_host_configuration(setup):
    _, _, planner, _, project, _, _, _, _ = setup
    changed = copy.deepcopy(planner.schema)
    changed["properties"]["attempts"]["default"] = 10000
    binding = Binding("fixture", "owner", str(project))
    contract, oracles = planner(binding, proposal())
    assert contract.max_attempts == 6 and oracles[0].argv[0] == sys.executable
    assert json.loads(json.dumps(planner.schema))["properties"]["attempts"]["default"] == 6


def test_status_reports_recorded_completion_without_reactivating_or_capturing_other_task(setup):
    action, create, _, store, _, _, messages, launches, _ = setup
    call(action, {"job": proposal()})
    answer(action, messages[-1]["id"])
    run = launches[0]
    candidate = Candidate("a" * 64, "b" * 40, True, True)
    for unit in run.contract.units:
        run = store.begin_attempt(run)
        run = store.checkpoint(run, candidate, unit=unit)
    for check in run.contract.checks:
        run = store.record_check(run, candidate, check, passed=True)
    run = store.record_review(run, candidate, passed=True)
    finished = store.finish(run, candidate, workers_idle=True)
    action.close()
    reopened = create()
    call(reopened, name="ralph_status")
    text = messages[-1]["result"]["content"][0]["text"]
    assert "Last job completed" in text and "2 of 6 attempts" in text and "recorded completion" in text
    call(reopened, name="ralph_status", task="unrelated")
    assert messages[-1]["result"]["content"][0]["text"] == "No active Ralph job in this task."
    assert store.lookup(finished.contract.binding) is None
    assert store.latest(finished.contract.binding) == finished and len(launches) == 1


def test_status_keeps_latest_cancelled_job_separate_from_prior_history(setup):
    action, _, _, store, _, _, messages, launches, _ = setup
    for index in range(2):
        draft = proposal()
        draft["goal"] += str(index)
        call(action, {"job": draft})
        answer(action, messages[-1]["id"])
        last = store.acknowledge_cancel(store.cancel(launches[-1]), workers_idle=True)
    call(action, name="ralph_status")
    text = messages[-1]["result"]["content"][0]["text"]
    assert "cancelled" in text and "no completion is claimed" in text
    assert store.latest(last.contract.binding) == last
    assert store.lookup(last.contract.binding) is None


@pytest.mark.parametrize("phase", ["work", "review"])
def test_status_explains_capacity_failure_without_new_approval_or_other_task_capture(setup, phase):
    action, create, _, store, _, clock, messages, launches, _ = setup
    call(action, {"job": proposal()})
    answer(action, messages[-1]["id"])
    run = store.begin_attempt(launches[0])
    run = store.record_capacity_failure(run, phase)
    assert "capacity exhaustion" in action.status(run.contract.binding)
    assert "original time and attempt limits" in action.status(run.contract.binding)
    clock[0] = run.contract.deadline
    run = store.begin_attempt(run)
    assert run.state == "blocked"
    reopened = create()
    call(reopened, name="ralph_status")
    text = messages[-1]["result"]["content"][0]["text"]
    assert "capacity exhaustion" in text and "not complete" in text
    assert ("independent reviewer" in text) == (phase == "review")
    call(reopened, name="ralph_status", task="unrelated")
    assert messages[-1]["result"]["content"][0]["text"] == "No active Ralph job in this task."
    assert len(launches) == 1 and store.get(run.id).contract == run.contract


def test_host_admission_refusal_cannot_be_replaced_by_a_valid_draft(setup):
    action, _, planner, store, project, _, messages, launches, _ = setup

    def refuse(contract, oracles):
        raise NotReady("selected host mode has not been admitted")

    planner.admit = refuse
    call(action, {"job": proposal()})
    assert messages[-1]["result"]["isError"] and not action.pending and not launches
    assert store.lookup(Binding("fixture", "owner", str(project))) is None
