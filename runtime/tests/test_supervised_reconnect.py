"""Native adapter wiring with fixture identities; no Codex or model is launched.

Windows cases kill real host processes and reconcile real kernel jobs. Synthetic
approval/binding fixtures do not establish authentic native task resumption.
"""

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from excubitor.acceptance import OutputOracle
from excubitor.native_action import RalphAction
from excubitor.runs import Binding, Contract, RunError, RunStore
from runtime.probes.native_supervised_start import (
    ConnectionJobs,
    connection_directory,
    connection_fault_ready,
    native_config_unchanged,
    write,
)

ROOT = str(Path(__file__).resolve().parents[2])


@pytest.fixture
def accepted(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    store = RunStore(tmp_path / "authority", create=True)
    oracle = OutputOracle("answer", (sys.executable,), "", "ok\n")
    oracle.save(store)
    run = store.start(
        Contract(
            Binding("fixture", "owner", str(project)),
            "test",
            ("unit",),
            (oracle.check,),
            2,
            int(time.time()) + 60,
        ),
        "explicit-offline-fixture",
    )
    return tmp_path, store, run


def test_start_and_reconnect_preserve_agreement_and_live_dispatch(accepted):
    packet, store, run = accepted
    entered, release = threading.Event(), threading.Event()
    calls, records = [], []

    def drive(current):
        calls.append(current)
        entered.set()
        assert release.wait(5)

    first = ConnectionJobs(packet, store, drive, records.append)
    try:
        first.start(run)
        assert entered.wait(5) and first.active(run)
        original = (packet / "agreed-job.json").read_bytes()
        first.reconnect(run)
        assert calls == [run] and len(records) == 1
    finally:
        release.set()
        first.join()
    assert not first.active(run)
    second = ConnectionJobs(packet, store, calls.append, records.append)
    second.reconnect(run)
    second.join()
    assert calls == [run, run] and records[-1]["kind"] == "reconnect"
    assert (packet / "agreed-job.json").read_bytes() == original
    assert store.get(run.id) == run


@pytest.mark.parametrize("damage", ["missing", "torn", "deadline", "checks", "oracle"])
def test_changed_or_missing_agreement_and_oracles_refuse_dispatch(accepted, damage):
    packet, store, run = accepted
    agreement = packet / "agreed-job.json"
    raw = json.loads(json.dumps(asdict(run.contract)))
    if damage == "deadline":
        raw["deadline"] += 1
    elif damage == "checks":
        raw["checks"] = []
    if damage != "missing":
        agreement.write_text("{" if damage == "torn" else json.dumps(raw))
    if damage == "oracle":
        for path in (store.directory / "oracles").iterdir():
            path.write_bytes(b"corrupted")
    calls = []
    jobs = ConnectionJobs(packet, store, calls.append, lambda _: None)
    with pytest.raises(RunError):
        jobs.reconnect(run)
    assert not calls and store.get(run.id) == run


def test_connection_records_never_overwrite_previous_lifetimes(tmp_path):
    first = connection_directory(tmp_path)
    (first / "native.jsonl").write_bytes(b"retained original evidence\n")
    second = connection_directory(tmp_path)
    assert first != second and second.is_dir()
    assert (first / "native.jsonl").read_bytes() == b"retained original evidence\n"


def test_fault_cannot_kill_a_later_connection_or_use_incomplete_marker(tmp_path):
    first, second = connection_directory(tmp_path), connection_directory(tmp_path)
    path = tmp_path / "injected-controller-crash.json"
    assert not connection_fault_ready(tmp_path, first)
    path.write_text("{")
    assert not connection_fault_ready(tmp_path, first)
    path.write_text(
        json.dumps({"connection": first.name, "fault_mode": "connection", "worker_drained": True})
    )
    assert connection_fault_ready(tmp_path, first)
    assert not connection_fault_ready(tmp_path, second)


def test_missing_or_changed_native_config_cannot_certify_completion(tmp_path):
    native = tmp_path / "native-config.toml"
    native.write_bytes(b"original")
    assert not native_config_unchanged(native, tmp_path)
    (tmp_path / "native-config-before.toml").write_bytes(b"original")
    assert native_config_unchanged(native, tmp_path)
    native.write_bytes(b"changed")
    assert not native_config_unchanged(native, tmp_path)
    native.unlink()
    assert not native_config_unchanged(native, tmp_path)


@pytest.mark.skipif(os.name != "nt", reason="disposable Windows server process")
def test_injected_connection_failure_exits_only_its_original_lifetime(accepted):
    packet, store, run = accepted
    code = (
        f"import sys; sys.path.insert(0,{ROOT!r})\n"
        "from pathlib import Path\nfrom types import SimpleNamespace\n"
        "import runtime.probes.native_supervised_start as m\n"
        "m.settings=lambda _: SimpleNamespace(fault_mode='connection')\n"
        f"m.serve(Path({str(packet)!r}))\n"
    )
    processes = []
    try:
        first = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        processes.append(first)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            lifetimes = list((packet / "connections").glob("*/native.jsonl"))
            if lifetimes:
                break
            time.sleep(0.01)
        assert len(lifetimes) == 1
        lifetime = lifetimes[0].parent
        write(
            packet / "injected-controller-crash.json",
            {
                "fault_mode": "connection",
                "connection": lifetime.name,
                "worker_drained": True,
            },
        )
        assert first.wait(timeout=5) == 78
        assert (lifetime / "injected-connection-exit.json").exists()
        second = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        processes.append(second)
        out, err = second.communicate(b'{"method":"ping","id":1}\n', timeout=5)
        assert second.returncode == 0 and not err
        assert json.loads(out)["result"] == {}
        assert len(list((packet / "connections").iterdir())) == 2
        assert store.get(run.id) == run
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="real Windows process ownership")
@pytest.mark.parametrize("retain_handle", [False, True])
def test_new_action_reconnects_after_connection_process_loss(tmp_path, retain_handle):
    import _winapi

    from excubitor.tests.test_watchdog import fixture as controller_fixture
    from excubitor.windows_jobs import api

    store, run, watchdog, project = controller_fixture(tmp_path, mode="hang_first")
    write(tmp_path / "agreed-job.json", asdict(run.contract))
    original = (tmp_path / "agreed-job.json").read_bytes()
    owner = tmp_path / "connection-owner.py"
    owner.write_text(
        f"import sys; sys.path.insert(0,{ROOT!r})\n"
        "from pathlib import Path\n"
        "from excubitor.runs import RunStore\n"
        "from excubitor.watchdog import ControllerWatchdog\n"
        "from runtime.probes.native_supervised_start import ConnectionJobs\n"
        f"packet=Path({str(tmp_path)!r})\n"
        f"store=RunStore(Path({str(store.directory)!r})); run=store.get({run.id!r})\n"
        f"watchdog=ControllerWatchdog(store,lambda _: {watchdog.argv(run)!r},packet)\n"
        "jobs=ConnectionJobs(packet,store,lambda r: watchdog.drive(r.id,r.contract.binding),lambda _: None)\n"
        "jobs.reconnect(run); jobs.join()\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", str(owner)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    kernel, _ = api()
    retained = controller = None
    messages, completions, records = [], [], []
    jobs = ConnectionJobs(
        tmp_path,
        store,
        lambda r: completions.append(watchdog.drive(r.id, r.contract.binding)),
        records.append,
    )

    def refuse_plan(_):
        raise RunError("no new approval or plan is allowed in this reconnect fixture")

    action = RalphAction(
        store,
        messages.append,
        lambda m: Binding("fixture", m["task"], str(project)),
        refuse_plan,
        refuse_plan,
        reconnect=jobs.reconnect,
        is_attached=jobs.active,
    )

    def call(task="owner-task", name="ralph_start"):
        action.receive(
            {
                "method": "tools/call",
                "id": len(messages),
                "params": {"name": name, "arguments": {}, "_meta": {"task": task}},
            }
        )

    try:
        deadline = time.monotonic() + 5
        marker = project / "controller-pid"
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        controller = _winapi.OpenProcess(0x100000, False, int(marker.read_text()))
        history = store.directory / "supervision" / (run.id + ".controller.jsonl")
        launch = json.loads(history.read_text().splitlines()[0])
        if retain_handle:
            retained = kernel.OpenJobObjectW(4, False, launch["job"])
            assert retained
        process.kill()
        process.communicate(timeout=5)
        if retain_handle:
            assert _winapi.WaitForSingleObject(controller, 50) == 258
        call(task="unrelated", name="ralph_status")
        assert "No active" in messages[-1]["result"]["content"][0]["text"]
        call(task="unrelated")
        assert messages[-1]["result"]["isError"] and not records
        call()
        assert not messages[-1]["result"]["isError"]
        jobs.join()
        assert len(completions) == 1
        final = completions[0]
        assert final.state == "complete" and final.attempts == 3
        assert final.contract == run.contract and final.reviewed
        assert store.lookup(run.contract.binding) is None
        assert _winapi.WaitForSingleObject(controller, 5000) == 0
        assert (project / "attempts").read_text().splitlines() == ["1", "2", "3"]
        receipt = json.loads(history.read_text().splitlines()[1])
        assert receipt["reconciled"] and receipt["kernel_evidence"]["active"] == 0
        assert receipt["kernel_evidence"]["evidence"] == (
            "kernel-object-drained" if retain_handle else "kernel-object-absent"
        )
        assert (tmp_path / "agreed-job.json").read_bytes() == original
        assert not any(m.get("method") == "elicitation/create" for m in messages)
        assert records[0]["attempts"] == 1 and records[0]["contract"] == run.contract.digest
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
        if retained:
            kernel.TerminateJobObject(retained, 1)
            kernel.CloseHandle(retained)
        jobs.join()
        if controller:
            _winapi.CloseHandle(controller)
