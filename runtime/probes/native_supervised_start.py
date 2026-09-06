"""Disposable native confirmation -> watchdog -> real Codex workers experiment.

Prepare an already trusted fixture, then serve via process-only MCP overrides.
The native CLI must remain open during this test. No hooks or app registrations
are installed. Forced controller death is injected once; watchdog death is NOT
automatically recoverable. This is not production or GUI admission.
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
            child = (
                "from pathlib import Path; import time; time.sleep(5); "
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
                },
            )
            os._exit(77)
        return result


def controller(packet, run_id):
    args = settings(packet)
    args.packet = packet
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


def serve(packet):
    args = settings(packet)
    store = RunStore(packet / "authority")
    workers = []
    output_lock = threading.Lock()
    log_lock = threading.Lock()
    log = (packet / "native.jsonl").open("x", encoding="utf-8")

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
            assert reader.collect() == final.candidate
            assert reader.base_commit == args.base_candidate["commit"]
            assert (packet / "injected-controller-crash.json").exists()
            assert not (packet / "orphan-survived").exists()
            assert args.native_config.read_bytes() == (packet / "native-config-before.toml").read_bytes()
            assert not (args.project / ".codex" / "hooks.json").exists()
            report["passed"] = True
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            report["native_configuration_unchanged"] = (
                args.native_config.read_bytes() == (packet / "native-config-before.toml").read_bytes()
            )
            write(packet / "result.json", report)
            record({"event": "job_finished", "passed": report["passed"], "state": report.get("state")})

    def launch(run):
        write(packet / "agreed-job.json", asdict(run.contract))
        worker = threading.Thread(target=run_job, args=(run,), daemon=False)
        workers.append(worker)
        worker.start()

    action = RalphAction(store, emit, codex_binding, plan, launch)
    try:
        for line in sys.stdin:
            message = json.loads(line)
            record({"direction": "in", "message": message})
            action.receive(message)
    finally:
        action.close()
        for worker in workers:
            worker.join()
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
    args = parser.parse_args()
    if any(isinstance(value, Path) and not value.is_absolute() for value in vars(args).values()):
        parser.error("all paths must be absolute")
    if args.command == "prepare":
        prepare(args)
    elif args.command == "controller":
        controller(args.packet, args.run_id)
    else:
        serve(args.packet)


if __name__ == "__main__":
    main()
