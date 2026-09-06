"""Disposable native confirmation -> watchdog -> real Codex workers experiment.

Prepare an already trusted fixture, then serve via process-only MCP overrides.
No hooks or app registrations are installed. A new native connection can reconnect
the same accepted job through the shared watchdog, after exact old-worker drainage.
Forced controller death is injected once. Native task resumption with this wiring
still needs a live witness. This is not production or GUI admission.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import tomllib
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from excubitor.acceptance import OutputOracle  # noqa: E402
from excubitor.approval import codex_binding  # noqa: E402
from excubitor.candidates import GitCandidateReader  # noqa: E402
from excubitor.native_action import RalphAction  # noqa: E402
from excubitor.runs import Contract, RunError, RunStore  # noqa: E402
from excubitor.supervisor import Supervisor  # noqa: E402
from excubitor.watchdog import ControllerWatchdog  # noqa: E402
from runtime.probes.supervised_job import GOAL, NativeDemo, fixture_git  # noqa: E402


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def settings(packet):
    raw = json.loads((packet / "settings.json").read_text(encoding="utf-8"))
    return SimpleNamespace(
        **{
            key: Path(value)
            if key in ("codex", "python", "git", "project", "metadata", "native_config", "output")
            else value
            for key, value in raw.items()
        }
    )


def prepare(args):
    prior = json.loads((args.reuse_completed / "result.json").read_text(encoding="utf-8"))
    if prior.get("state") != "complete" or not prior.get("passed"):
        raise RunError("requires a passing completed disposable demonstration")
    project = Path(prior["project"])
    marker = (project / ".git").read_text(encoding="utf-8").strip()
    if not marker.startswith("gitdir: "):
        raise RunError("expected the existing disposable protected Git layout")
    metadata = Path(marker.removeprefix("gitdir: "))
    if not metadata.is_absolute() or metadata.is_relative_to(project):
        raise RunError("fixture metadata must be absolute and outside the project")
    version = subprocess.run(
        [str(args.codex), "--version"], capture_output=True, text=True, check=True
    ).stdout
    if os.name != "nt" or version.strip() != "codex-cli 0.153.4":
        raise RunError("this experiment requires the previously tested Windows CLI")
    native_bytes = args.native_config.read_bytes()
    native = tomllib.loads(native_bytes.decode("utf-8-sig"))
    if native.get("windows", {}).get("sandbox") != "elevated":
        raise RunError("requires the existing native Windows sandbox")
    if not any(
        os.path.normcase(key) == os.path.normcase(str(project.resolve()))
        and value.get("trust_level") == "trusted"
        for key, value in native.get("projects", {}).items()
    ):
        raise RunError("refusing fresh project trust enrollment")
    base = "refs/heads/" + prior["retained_branch"]
    reader = GitCandidateReader(
        args.git,
        project,
        metadata,
        base,
        prior.get("protected_base_branch", "refs/heads/ralph/demo"),
    )
    if asdict(reader.collect()) != prior["candidate"]:
        raise RunError("the completed disposable candidate changed")
    options = []
    for key in ("model", "model_reasoning_effort"):
        if key in native:
            options.extend(("-c", key + "=" + json.dumps(native[key])))
    options.extend(("-c", 'windows.sandbox="elevated"', "-c", 'web_search="disabled"'))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "native-config-before.toml").write_bytes(native_bytes)
    store = RunStore(args.output / "authority", create=True)
    branch = "refs/heads/ralph/" + args.output.name
    fixture_git(args.git, project, "checkout", "-qb", branch.removeprefix("refs/heads/"), metadata=metadata)
    (project / "arithmetic.py").write_bytes(b"def double(n):\n    raise NotImplementedError\n")
    (project / "main.py").write_bytes(b"raise NotImplementedError\n")
    fixture_git(args.git, project, "add", "arithmetic.py", "main.py", metadata=metadata)
    fixture_git(
        args.git,
        project,
        "-c",
        "user.name=Erick Shepherd",
        "-c",
        "user.email=dev@erickshepherd.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Initialize native confirmed disposable job",
        metadata=metadata,
    )
    write(
        store.directory / "review-schema.json",
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"passed": {"type": "boolean"}, "findings": {"type": "string"}},
            "required": ["passed", "findings"],
        },
    )
    write(
        args.output / "settings.json",
        {
            "codex": str(args.codex),
            "python": str(args.python),
            "git": str(args.git),
            "project": str(project),
            "metadata": str(metadata),
            "output": str(args.output),
            "native_config": str(args.native_config),
            "branch": branch,
            "base_branch": base,
            "model_options": options,
            "base_candidate": prior["candidate"],
        },
    )
    print(json.dumps({"prepared": str(args.output), "project": str(project), "run_started": False}))


class CrashingDemo(NativeDemo):
    def work(self, run, unit, feedback, cancel):
        result = super().work(run, unit, feedback, cancel)
        if run.attempts == 1 and result.execution.exit_code == 0:
            # Actual worker has drained. Simulate an abrupt controller death with
            # a still-live descendant that would write outside the candidate later.
            # The OUTER job must terminate it before restarting the controller.
            connection_loss = getattr(self.args, "fault_mode", "controller") == "connection"
            child = (
                f"from pathlib import Path; import time; time.sleep({600 if connection_loss else 5}); "
                f"Path({str(self.args.packet / 'orphan-survived')!r}).write_text('bad')"
            )
            subprocess.Popen(
                [str(self.args.python), "-I", "-B", "-c", child], creationflags=subprocess.CREATE_NO_WINDOW
            )
            write(
                self.args.packet / "injected-controller-crash.json",
                {
                    "attempt": run.attempts,
                    "worker_drained": result.drained,
                    "contract": run.contract.digest,
                    "connection": getattr(self.args, "connection", None),
                    "fault_mode": "connection" if connection_loss else "controller",
                },
            )
            if connection_loss:
                # The serving process observes this exact lifetime's marker and
                # exits itself. Its watchdog owns this controller and descendant.
                # The original watchdog deadline remains the outer bound.
                while True:
                    time.sleep(1)
            os._exit(77)
        return result


def controller(packet, run_id, connection=None):
    args = settings(packet)
    args.packet = packet
    args.connection = connection
    args.output = packet / ("controller-" + uuid.uuid4().hex)
    args.output.mkdir()
    store = RunStore(packet / "authority")
    backend = CrashingDemo(args, store, args.project, args.model_options)
    try:
        run = Supervisor(store, backend).drive(run_id)
        write(args.output / "finished.json", {"state": run.state, "attempts": run.attempts})
    except Exception as exc:
        # Report handled errors and exit zero; a denied native action must never
        # become an excuse for watchdog retries or bypassing native policy.
        write(args.output / "finished.json", {"error": f"{type(exc).__name__}: {exc}"})


def agreed_job(packet, store, run):
    """Check the original preview and oracle bytes before any resumed launch."""
    try:
        saved = json.loads((packet / "agreed-job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunError("original agreement is missing or unreadable; recovery refused") from exc
    if saved != json.loads(json.dumps(asdict(run.contract))):
        raise RunError("reconnect cannot replace the originally agreed job")
    current = store.get(run.id)
    if current.contract != run.contract:
        raise RunError("accepted run changed before dispatch")
    for check in run.contract.checks:
        OutputOracle.load(store, check)


class ConnectionJobs:
    """Dispatch the same host-owned watchdog from each admitted connection.

    Thread liveness only suppresses duplicate dispatch in this process. The
    watchdog's OS lock and kernel reconciliation establish actual worker safety.
    This class does not authenticate native metadata or create recovery evidence.
    """

    def __init__(self, packet, store, drive, record):
        self.packet, self.store, self.drive, self.record = packet, store, drive, record
        self.threads = {}
        self.lock = threading.Lock()

    def active(self, run):
        with self.lock:
            worker = self.threads.get(run.id)
            return worker is not None and worker.is_alive()

    def start(self, run):
        write(self.packet / "agreed-job.json", asdict(run.contract))
        self._dispatch(run, "start")

    def reconnect(self, run):
        self._dispatch(run, "reconnect")

    def _dispatch(self, run, kind):
        agreed_job(self.packet, self.store, run)
        with self.lock:
            existing = self.threads.get(run.id)
            if existing is not None and existing.is_alive():
                return
            self.record(
                {
                    "event": "dispatch",
                    "kind": kind,
                    "run_id": run.id,
                    "contract": run.contract.digest,
                    "attempts": self.store.get(run.id).attempts,
                }
            )
            worker = threading.Thread(target=self._drive, args=(run,), daemon=False)
            self.threads[run.id] = worker
            worker.start()

    def _drive(self, run):
        try:
            self.drive(run)
        except Exception as exc:
            self.record({"event": "dispatch_failed", "error": f"{type(exc).__name__}: {exc}"})

    def join(self):
        with self.lock:
            workers = list(self.threads.values())
        for worker in workers:
            if worker.ident is not None:
                worker.join()


def connection_directory(packet):
    parent = packet / "connections"
    parent.mkdir(exist_ok=True)
    lifetime = parent / uuid.uuid4().hex
    lifetime.mkdir()
    return lifetime


def connection_fault_ready(packet, lifetime):
    path = packet / "injected-controller-crash.json"
    if not path.exists():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return False  # Writer may still be flushing; never act on partial bytes.
    return (
        value.get("fault_mode") == "connection"
        and value.get("connection") == lifetime.name
        and value.get("worker_drained") is True
    )


def native_config_unchanged(config, packet):
    try:
        return config.read_bytes() == (packet / "native-config-before.toml").read_bytes()
    except OSError:
        return False


def serve(packet):
    args = settings(packet)
    store = RunStore(packet / "authority")
    lifetime = connection_directory(packet)
    output_lock = threading.Lock()
    log_lock = threading.Lock()
    log = (lifetime / "native.jsonl").open("x", encoding="utf-8")

    def record(value):
        with log_lock:
            log.write(json.dumps(value) + "\n")
            log.flush()
            os.fsync(log.fileno())

    def emit(value):
        record({"direction": "out", "message": value})
        with output_lock:
            print(json.dumps(value), flush=True)

    def plan(binding):
        if (packet / "agreed-job.json").exists():
            raise RunError("this disposable packet already has an agreed job; it cannot start another")
        if not native_config_unchanged(args.native_config, packet):
            raise RunError("native configuration changed before confirmation; no job will be prepared")
        if Path(binding.project) != args.project.resolve():
            raise RunError("native task does not match the selected disposable project")
        argv = (
            str(args.python),
            "-I",
            "-B",
            "-c",
            "import runpy,sys; sys.path.insert(0,'.'); runpy.run_path('main.py',run_name='__main__')",
        )
        oracles = tuple(
            OutputOracle(name, argv, data, expected, timeout_seconds=15)
            for name, data, expected in (
                ("double-positive", "double 7\n", "14\n"),
                ("double-negative", "double -3\n", "-6\n"),
                ("sum-mixed", "sum 4 -2 5\n", "7\n"),
                ("sum-empty", "sum\n", "0\n"),
            )
        )
        return Contract(
            binding,
            GOAL,
            ("Implement integer doubling", "Implement stdin command routing and integer sum"),
            tuple(oracle.check for oracle in oracles),
            6,
            int(time.time()) + 900,
        ), oracles

    def run_job(run):
        report = {
            "passed": False,
            "run_id": run.id,
            "project": str(args.project),
            "real_model_workers": True,
            "registration_added": False,
            "retained_branch": args.branch.removeprefix("refs/heads/"),
            "protected_base_branch": args.base_branch,
        }
        try:
            agreed_job(packet, store, run)
            if not native_config_unchanged(args.native_config, packet):
                raise RunError("native configuration changed; no controller will be launched")
            watchdog = ControllerWatchdog(
                store,
                lambda current: (
                    str(args.python),
                    "-I",
                    "-B",
                    str(Path(__file__).resolve()),
                    "controller",
                    "--packet",
                    str(packet),
                    "--run-id",
                    current.id,
                    "--connection",
                    lifetime.name,
                ),
                ROOT,
            )
            final = watchdog.drive(run.id, run.contract.binding)
            reader = GitCandidateReader(args.git, args.project, args.metadata, args.branch, args.base_branch)
            report.update(
                state=final.state,
                attempts=final.attempts,
                completed_units=final.completed_units,
                checks=dict(final.check_results),
                reviewed=final.reviewed,
                candidate=asdict(final.candidate) if final.candidate else None,
                inactive_after_completion=store.lookup(run.contract.binding) is None,
            )
            assert final.state == "complete" and final.attempts >= 4
            agreed_job(packet, store, final)
            assert reader.collect() == final.candidate
            assert reader.base_commit == args.base_candidate["commit"]
            assert (packet / "injected-controller-crash.json").exists()
            if getattr(args, "fault_mode", "controller") == "connection":
                history = store.directory / "supervision" / (run.id + ".controller.jsonl")
                events = [json.loads(line) for line in history.read_text().splitlines()]
                assert events[1]["event"] == "drained" and events[1]["reconciled"]
                assert events[1]["kernel_evidence"]["active"] == 0
                assert list((packet / "connections").glob("*/injected-connection-exit.json"))
                report["watchdog_loss_reconciled"] = True
            assert not (packet / "orphan-survived").exists()
            assert args.native_config.read_bytes() == (packet / "native-config-before.toml").read_bytes()
            assert not (args.project / ".codex" / "hooks.json").exists()
            report["passed"] = True
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            report["native_configuration_unchanged"] = native_config_unchanged(args.native_config, packet)
            if not report["native_configuration_unchanged"]:
                report["passed"] = False
                report.setdefault(
                    "error", "native configuration drift or missing baseline; evidence retained"
                )
            write(lifetime / (run.id + "-" + uuid.uuid4().hex + ".json"), report)
            # Retain all connection outcomes. Only successful completion provides
            # a reusable top-level packet; a competing/failed reconnect cannot
            # overwrite that result or prevent later recovery evidence being saved.
            if report["passed"] and not (packet / "result.json").exists():
                write(packet / "result.json", report)
            record({"event": "job_finished", "passed": report["passed"], "state": report.get("state")})

    jobs = ConnectionJobs(packet, store, run_job, record)
    action = RalphAction(
        store, emit, codex_binding, plan, jobs.start, reconnect=jobs.reconnect, is_attached=jobs.active
    )
    stop_fault = threading.Event()

    def fault():
        while not stop_fault.wait(0.05):
            if connection_fault_ready(packet, lifetime):
                write(lifetime / "injected-connection-exit.json", {"connection": lifetime.name})
                # This disposable serving process terminates only itself. It
                # never searches for or kills the user's application processes.
                os._exit(78)

    monitor = None
    if getattr(args, "fault_mode", "controller") == "connection":
        monitor = threading.Thread(target=fault, daemon=True)
        monitor.start()
    try:
        for line in sys.stdin:
            message = json.loads(line)
            record({"direction": "in", "message": message})
            action.receive(message)
    finally:
        stop_fault.set()
        if monitor is not None:
            monitor.join()
        action.close()
        jobs.join()
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    prep = subs.add_parser("prepare")
    for name in ("codex", "python", "git", "output", "native-config", "reuse-completed"):
        prep.add_argument("--" + name, type=Path, required=True)
    for name in ("serve", "controller"):
        command = subs.add_parser(name)
        command.add_argument("--packet", type=Path, required=True)
        if name == "controller":
            command.add_argument("--run-id", required=True)
            command.add_argument("--connection")
    args = parser.parse_args()
    if any(isinstance(value, Path) and not value.is_absolute() for value in vars(args).values()):
        parser.error("all paths must be absolute")
    if args.command == "prepare":
        prepare(args)
    elif args.command == "controller":
        controller(args.packet, args.run_id, args.connection)
    else:
        serve(args.packet)


if __name__ == "__main__":
    main()
