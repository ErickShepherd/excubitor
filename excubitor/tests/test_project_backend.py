"""Real disposable Git and output checks; native transport and review are fixtures."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import Execution, OutputOracle
from excubitor.candidates import GitCandidateReader
from excubitor.codex_project import REVIEW_SCHEMA, CodexProjectRuntime, _capacity_failure
from excubitor.job_setup import CheckRunner, JobPlanner, LaunchDefaults
from excubitor.native_action import RalphAction
from excubitor.processes import ProcessResult
from excubitor.project_backend import ProjectBackend
from excubitor.runs import Binding, NotReady, RunError, RunStore
from excubitor.supervisor import Supervisor


def result(stdout=b"", stderr=b"", code=0):
    return ProcessResult(Execution(code, stdout, stderr, 0.01), cancelled=False, drained=True, processes=1)


@pytest.fixture
def project(tmp_path):
    origin, candidate, metadata = (tmp_path / name for name in ("origin", "candidate", "git"))
    origin.mkdir()
    (origin / "ordinary.txt").write_bytes(b"Unrelated ordinary work stays here.\n")
    git = Path(shutil.which("git"))
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)

    def command(*args):
        return subprocess.run([str(git), *args], env=env, capture_output=True, check=True, timeout=15)

    command("init", "-q", "-b", "main", "--separate-git-dir", str(metadata), str(candidate))
    (candidate / "main.py").write_bytes(b"raise NotImplementedError\n")
    (candidate / "untouched.txt").write_bytes(b"This file is outside the requested changes.\n")

    def retain(run, paths):
        # Disposable offline fixture only; production must supply its admitted
        # commit broker. This test never enrolls or commits the development repo.
        command("-C", str(candidate), "add", "--", *paths)
        command(
            "-C",
            str(candidate),
            "-c",
            "user.name=Erick Shepherd",
            "-c",
            "user.email=dev@erickshepherd.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-qm",
            "Retain fixture attempt",
        )

    retain(None, ("main.py", "untouched.txt"))
    command("-C", str(candidate), "checkout", "-qb", "ralph/test")
    reader = GitCandidateReader(git, candidate, metadata, "refs/heads/ralph/test")
    store = RunStore(tmp_path / "authority", create=True)
    binding = Binding("fixture", "owner", str(origin))
    argv = (sys.executable, "-I", "-B", "main.py")
    planner = JobPlanner(
        LaunchDefaults(6, 300, 12, 600), (CheckRunner("program", argv, 10),), admit=lambda *args: None
    )
    return origin, candidate, reader, store, binding, planner, retain


@pytest.mark.parametrize(
    "goal,stdin,expected,correct",
    [
        (
            "Normalize, deduplicate, and sort comma-separated words.",
            " b, a,b \n",
            "a,b\n",
            "import sys; sys.stdout.reconfigure(newline='\\n'); "
            "print(','.join(sorted(set(w.strip() for w in sys.stdin.read().strip().split(',')))))\n",
        ),
        (
            "Count whitespace-separated words.",
            "one  two three\n",
            "3\n",
            "import sys; sys.stdout.reconfigure(newline='\\n'); print(len(sys.stdin.read().split()))\n",
        ),
    ],
    ids=["normalize-words", "count-words"],
)
def test_proposed_jobs_drive_real_candidate_repair_review_and_inactive_completion(
    project, goal, stdin, expected, correct
):
    origin, candidate, reader, store, binding, planner, retain = project
    initial_base = reader.base_commit
    prompts, outcomes, messages = [], [], []

    class Runtime:
        def work(self, run, prompt, cancel):
            prompts.append(prompt)
            (candidate / "main.py").write_bytes(
                b"print('incorrect')\n" if run.attempts == 1 else correct.encode()
            )
            return result()

        def verify(self, run, oracle, cancel):
            actual = subprocess.run(
                oracle.argv, cwd=candidate, input=oracle.stdin.encode(), capture_output=True, timeout=10
            )
            return result(actual.stdout, actual.stderr, actual.returncode)

        def review(self, run, prompt, cancel):
            prompts.append(prompt)
            # Exercise a separate review rejection after the immutable checks pass.
            return result(), run.attempts >= 3, "Explain and repair the candidate's edge cases."

    backend = ProjectBackend(store, binding, reader, Runtime(), admit=lambda run: None, retain=retain)
    action = RalphAction(
        store,
        messages.append,
        lambda meta: binding,
        lambda _: pytest.fail("new jobs must use their submitted proposal"),
        lambda run: outcomes.append(Supervisor(store, backend).drive(run.id)),
        drafts=planner,
    )
    action.receive(
        {
            "method": "initialize",
            "id": 0,
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {"elicitation": {"form": {}}},
            },
        }
    )
    draft = {
        "goal": goal,
        "units": ["Implement the requested CLI behavior"],
        "checks": [
            {"name": "example", "runner": "program", "stdin": stdin, "stdout": expected},
        ],
    }
    action.receive(
        {
            "method": "tools/call",
            "id": 1,
            "params": {
                "name": "ralph_start",
                "arguments": {"job": draft},
            },
        }
    )
    assert not outcomes and not prompts and store.lookup(binding) is None
    assert (candidate / "main.py").read_bytes() == b"raise NotImplementedError\n"
    form = messages[-1]
    action.receive({"id": form["id"], "result": {"action": "accept", "content": {"confirm": True}}})
    final = outcomes[0]
    assert final.state == "complete" and final.attempts == 3 and final.reviewed
    assert reader.collect() == final.candidate and reader.base_commit == initial_base
    assert store.lookup(binding) is None
    assert "Original acceptance checks failed" in prompts[1]
    assert "Independent review requires repair" in prompts[3]
    assert all(goal in prompt for prompt in prompts)
    assert (origin / "ordinary.txt").read_bytes() == b"Unrelated ordinary work stays here.\n"
    assert not (origin / "main.py").exists()
    assert "Last job completed" in action.status(binding)


@pytest.mark.parametrize("path", [".codex", "nested/.agents", ".claude", ".cursor", "nested/.git"])
def test_runtime_configuration_cannot_reach_committer(project, path):
    _, candidate, reader, store, binding, planner, _ = project
    contract, oracles = planner(
        binding,
        {
            "goal": "work",
            "units": ["unit"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": ""}],
        },
    )
    for oracle in oracles:
        oracle.save(store)
    run = store.start(contract, "fixture")
    commits = []
    backend = ProjectBackend(
        store, binding, reader, object(), admit=lambda run: None, retain=lambda *x: commits.append(x)
    )
    (candidate / path).mkdir(parents=True)
    with pytest.raises(RunError, match="configuration|metadata"):
        backend.checkpoint(run)
    assert not commits


def test_commit_refusal_preserves_partial_work_and_cannot_complete(project):
    _, candidate, reader, store, binding, planner, _ = project
    contract, oracles = planner(
        binding,
        {
            "goal": "work",
            "units": ["unit"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": ""}],
        },
    )
    for oracle in oracles:
        oracle.save(store)
    run = store.start(contract, "fixture")

    class Runtime:
        def work(self, run, prompt, cancel):
            (candidate / "main.py").write_bytes(b"print('partial work')\n")
            return result()

    def refuse(*args):
        raise NotReady("authorized committer refused the candidate")

    backend = ProjectBackend(store, binding, reader, Runtime(), admit=lambda run: None, retain=refuse)
    with pytest.raises(NotReady, match="committer"):
        Supervisor(store, backend).drive(run.id)
    assert store.get(run.id).state == "interrupted"
    assert (candidate / "main.py").read_bytes() == b"print('partial work')\n"


def test_missing_isolation_or_native_admission_is_rejected(project):
    origin, _, reader, store, binding, planner, retain = project
    with pytest.raises(RunError, match="separate"):
        ProjectBackend(
            store,
            Binding("fixture", "owner", str(reader.project)),
            reader,
            object(),
            admit=lambda run: None,
            retain=retain,
        )
    contract, _ = planner(
        binding,
        {
            "goal": "work",
            "units": ["unit"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": ""}],
        },
    )
    run = store.start(contract, "fixture")

    def refuse(run):
        raise NotReady("native tool surfaces are not admitted")

    backend = ProjectBackend(store, binding, reader, object(), admit=refuse, retain=retain)
    with pytest.raises(NotReady, match="native"):
        backend.work(run, "unit", "", threading.Event())


def test_host_commit_path_receives_added_and_deleted_files(project):
    _, candidate, reader, store, binding, planner, retain = project
    contract, _ = planner(
        binding,
        {
            "goal": "Replace the module",
            "units": ["Replace the module"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": ""}],
        },
    )
    run = store.start(contract, "fixture")
    requested = []

    def commit(current, paths):
        requested.append(paths)
        retain(current, paths)

    backend = ProjectBackend(store, binding, reader, object(), admit=lambda run: None, retain=commit)
    (candidate / "main.py").unlink()
    (candidate / "replacement.py").write_bytes(b"print('replacement')\n")
    retained = backend.checkpoint(run)
    assert requested == [("main.py", "replacement.py")]
    assert retained.clean and retained.isolated and reader.collect() == retained


def test_uncommitted_worker_bytes_cannot_be_certified_by_a_successful_callback(project):
    _, candidate, reader, store, binding, planner, _ = project
    contract, _ = planner(
        binding,
        {
            "goal": "work",
            "units": ["unit"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": ""}],
        },
    )
    run = store.start(contract, "fixture")
    backend = ProjectBackend(
        store, binding, reader, object(), admit=lambda run: None, retain=lambda *args: None
    )
    (candidate / "main.py").write_bytes(b"print('worker claim')\n")
    with pytest.raises(RunError, match="differ"):
        backend.checkpoint(run)


def test_changed_oracle_cannot_reach_native_execution(project):
    _, _, reader, store, binding, planner, retain = project
    contract, oracles = planner(
        binding,
        {
            "goal": "work",
            "units": ["unit"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": "expected"}],
        },
    )
    for oracle in oracles:
        oracle.save(store)
    run = store.start(contract, "fixture")
    backend = ProjectBackend(store, binding, reader, object(), admit=lambda run: None, retain=retain)
    next((store.directory / "oracles").iterdir()).write_text("{}")
    with pytest.raises(RunError, match="acceptance"):
        backend.verify(run, oracles[0], threading.Event())


def test_unchanged_candidate_does_not_request_an_empty_commit(project):
    _, _, reader, store, binding, planner, _ = project
    contract, _ = planner(
        binding,
        {
            "goal": "Already implemented work",
            "units": ["Check existing behavior"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": ""}],
        },
    )
    run = store.start(contract, "fixture")
    commits = []
    backend = ProjectBackend(
        store, binding, reader, object(), admit=lambda run: None, retain=lambda *args: commits.append(args)
    )
    assert backend.checkpoint(run) == reader.collect()
    assert not commits


def test_native_transport_narrows_children_and_validates_actual_review(project, tmp_path):
    _, candidate, _, store, binding, planner, _ = project
    output = tmp_path / "native-output"
    output.mkdir()
    schema = store.directory / "review-schema.json"
    schema.write_text(json.dumps(REVIEW_SCHEMA))
    driver = CodexProjectRuntime(
        Path(sys.executable), candidate, output, schema, environment=dict(os.environ), admit=lambda: None
    )
    contract, _ = planner(
        binding,
        {
            "goal": "work",
            "units": ["unit"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": ""}],
        },
    )
    run = store.start(contract, "fixture")
    calls = []

    class Tree:
        reply = result(b'{"type":"turn.completed"}\n')

        def run(self, argv, cwd, **kwargs):
            calls.append((argv, cwd, kwargs))
            return self.reply

    tree = Tree()
    driver.tree = tree
    _, passed, _ = driver.review(run, "independent", threading.Event())
    assert not passed
    tree.reply = result(
        (
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "agent_message",
                        "text": json.dumps({"passed": True, "findings": "reviewed"}),
                    },
                }
            )
            + '\n{"type":"turn.completed"}\n'
        ).encode()
    )
    _, passed, _ = driver.review(run, "independent", threading.Event())
    assert passed
    argv, cwd, options = calls[-1]
    assert "--ignore-user-config" in argv and "--ephemeral" in argv
    assert 'approval_policy="never"' in argv
    overrides = tomllib.loads("\n".join(argv[index + 1] for index, value in enumerate(argv) if value == "-c"))
    assert overrides["mcp_servers"] == {}
    assert argv[argv.index("--sandbox") + 1] == "read-only" and cwd == candidate
    assert options["stdin"] == b"independent" and options["timeout"] <= 180
    schema.write_text("{}")
    with pytest.raises(RunError, match="schema"):
        driver.review(run, "independent", threading.Event())
    assert len(calls) == 2


def test_native_configuration_failure_interrupts_without_repeated_attempts(project, tmp_path):
    _, candidate, reader, store, binding, planner, retain = project
    output = tmp_path / "native-output"
    output.mkdir()
    schema = store.directory / "review-schema.json"
    schema.write_text(json.dumps(REVIEW_SCHEMA))
    driver = CodexProjectRuntime(
        Path(sys.executable), candidate, output, schema, environment=dict(os.environ), admit=lambda: None
    )
    contract, oracles = planner(
        binding,
        {
            "goal": "work",
            "units": ["unit"],
            "checks": [{"name": "check", "runner": "program", "stdin": "", "stdout": "expected"}],
        },
    )
    for oracle in oracles:
        oracle.save(store)
    run = store.start(contract, "fixture")
    before = reader.collect()

    class Tree:
        calls = 0

        def run(self, *args, **kwargs):
            self.calls += 1
            return result(
                stderr=b"Error loading config.toml: invalid transport\nin `mcp_servers.node_repl`\n\n",
                code=1,
            )

    tree = Tree()
    driver.tree = tree
    backend = ProjectBackend(store, binding, reader, driver, admit=lambda run: None, retain=retain)
    with pytest.raises(RunError, match="native configuration failed before model start"):
        Supervisor(store, backend).drive(run.id)
    stopped = store.get(run.id)
    assert stopped.state == "interrupted" and stopped.attempts == 1 and tree.calls == 1
    assert stopped.contract == contract and stopped.completed_units == 0 and not stopped.reviewed
    assert reader.collect() == before
    evidence = json.loads((output / "execution-0001.json").read_text())
    assert evidence["drained"] and evidence["execution"]["exit_code"] == 1
    with pytest.raises(RunError, match="native configuration failed before model start"):
        driver.review(run, "review", threading.Event())
    # A candidate program can print the same text. Its failed acceptance check
    # must remain an ordinary check result, not a native startup diagnosis.
    check = driver.verify(run, oracles[0], threading.Event())
    assert check.execution.exit_code == 1 and check.drained


@pytest.mark.parametrize("prefix", [[], [{"type": "item.completed", "item": {"type": "command_execution"}}]])
def test_native_capacity_terminal_event_is_recognized_even_after_tools(prefix):
    event = {
        "type": "turn.failed",
        "error": {"message": "Selected model is at capacity. Please try a different model."},
    }
    output = "\n".join(json.dumps(item) for item in [*prefix, event]).encode()
    assert _capacity_failure(result(output, code=1))
    assert not _capacity_failure(result(output, code=0))
    assert not _capacity_failure(result(output, code=2))


@pytest.mark.parametrize(
    "events",
    [
        [
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "aggregated_output": (
                        '{"type":"turn.failed","error":{"message":'
                        '"Selected model is at capacity. Please try a different model."}}'
                    ),
                },
            }
        ],
        [{"type": "error", "message": "Selected model is at capacity. Please try a different model."}],
        [{"type": "turn.failed", "error": {"message": "some other failure"}}],
        [
            {"type": "turn.completed"},
            {
                "type": "turn.failed",
                "error": {"message": "Selected model is at capacity. Please try a different model."},
            },
        ],
        [None],
    ],
)
def test_native_capacity_does_not_accept_candidate_text_or_other_errors(events):
    assert not _capacity_failure(result("\n".join(json.dumps(item) for item in events).encode(), code=1))


def test_native_capacity_classifies_workers_and_reviewers_but_not_program_checks(tmp_path):
    project, output = tmp_path / "project", tmp_path / "output"
    project.mkdir()
    output.mkdir()
    schema = output / "schema.json"
    schema.write_text(json.dumps(REVIEW_SCHEMA))
    driver = CodexProjectRuntime(
        Path(sys.executable), project, output, schema, environment={}, admit=lambda: None
    )
    failed = result(
        b'{"type":"turn.failed","error":{"message":'
        b'"Selected model is at capacity. Please try a different model."}}\n',
        code=1,
    )
    driver.tree = SimpleNamespace(run=lambda *args, **kwargs: failed)
    run = SimpleNamespace(contract=SimpleNamespace(deadline=time.time() + 100))
    cancel = threading.Event()
    assert driver.work(run, "work", cancel).retryable_error == "capacity"
    review, passed, _ = driver.review(run, "review", cancel)
    assert review.retryable_error == "capacity" and not passed
    oracle = OutputOracle("check", (sys.executable,), "", "")
    assert driver.verify(run, oracle, cancel).retryable_error is None
    records = [json.loads(path.read_text()) for path in sorted(output.glob("execution-*.json"))]
    assert [item["retryable_error"] for item in records] == ["capacity", "capacity", None]
