"""Exit-code checks cannot discard the original acceptance or host failures."""

import hashlib
import json
import sys
from dataclasses import replace

import pytest

from excubitor.acceptance import Execution, OutputOracle, record_output
from excubitor.runs import Binding, Candidate, Contract, RunError, RunStore


def test_legacy_oracle_bytes_are_unchanged(tmp_path):
    legacy = {
        "name": "legacy",
        "argv": [sys.executable, "check.py"],
        "stdin": "",
        "stdout": "ok\n",
        "stderr": "",
        "exit_code": 0,
        "timeout_seconds": 30,
    }
    payload = json.dumps(legacy, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    oracle = OutputOracle(**{**legacy, "argv": tuple(legacy["argv"])})
    assert oracle.payload == payload
    assert oracle.check.oracle_digest == hashlib.sha256(payload).hexdigest()
    store = RunStore(tmp_path / "authority", create=True)
    oracle.save(store)
    assert OutputOracle.load(store, oracle.check) == oracle
    assert replace(oracle, stdout="", mode="exit-code").check != oracle.check


@pytest.fixture
def active(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    oracle = OutputOracle("tests", (sys.executable, "test.py"), "", "", mode="exit-code")
    contract = Contract(
        Binding("codex-cli", "session", str(project)), "fix", ("fix",), (oracle.check,), 3, 200
    )
    store = RunStore(tmp_path / "authority", create=True, clock=lambda: 10)
    oracle.save(store)
    run = store.start(contract, "fixture-authorization")
    run = store.begin_attempt(run)
    candidate = Candidate("a" * 64, "b" * 40, True, True)
    run = store.checkpoint(run, candidate, unit="fix")
    return store, run, candidate, oracle


def test_exit_code_accepts_variable_diagnostic_output_without_completing(active):
    store, run, candidate, oracle = active
    for result in (Execution(0, b"3 passed in 0.1s\n", b"warning\n", 0.5), Execution(0, b"\xff", b"", 1)):
        run = record_output(store, run, candidate, oracle.check, result)
        assert dict(run.check_results) == {"tests": True}
        assert run.state == "running"
        assert not run.reviewed


@pytest.mark.parametrize(
    "mutation",
    [
        {"exit_code": 1},
        {"exit_code": None},
        {"exit_code": False},
        {"timed_out": True},
        {"output_limited": True},
        {"elapsed_seconds": 31},
        {"elapsed_seconds": float("nan")},
        {"stdout": "All tests passed"},
        {"stderr": None},
    ],
)
def test_exit_code_does_not_hide_host_failure(active, mutation):
    store, run, candidate, oracle = active
    result = replace(Execution(0, b"passed\n", b"", 0.5), **mutation)
    run = record_output(store, run, candidate, oracle.check, result)
    assert dict(run.check_results) == {"tests": False}


def test_saved_mode_tampering_cannot_reuse_the_accepted_check(active):
    store, run, candidate, oracle = active
    blob = store.directory / "oracles" / (oracle.check.oracle_digest + ".json")
    data = json.loads(blob.read_bytes())
    del data["mode"]
    blob.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RunError, match="protected acceptance"):
        record_output(store, run, candidate, oracle.check, Execution(0, b"", b"", 1))


def test_exit_code_mode_does_not_silently_ignore_expected_output():
    with pytest.raises(ValueError, match="expected output"):
        OutputOracle("tests", (sys.executable,), "", "ok", mode="exit-code")
    with pytest.raises(ValueError, match="acceptance mode"):
        OutputOracle("tests", (sys.executable,), "", "", mode="worker-claims-success")
