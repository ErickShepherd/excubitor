"""Explicit native development jobs on host-prepared candidate checkouts."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from excubitor.acceptance import OutputOracle
from excubitor.candidates import GitCandidateReader
from excubitor.development_adapters import baseline_for, make_executor, make_runtime, normalize, preflight
from excubitor.development_runtime import BASELINE, LOCAL_BASELINE
from excubitor.development_runtime import clean_exit as _clean_exit
from excubitor.host_processes import background_options, process_tree
from excubitor.project_backend import ProjectBackend
from excubitor.runs import Binding, Contract, RunError, RunStore
from excubitor.supervisor import Supervisor
from excubitor.watchdog import ControllerWatchdog


def register(subparsers):
    parser = subparsers.add_parser("ralph", help="start, inspect, or stop an agreed native job")
    actions = parser.add_subparsers(dest="action", required=True)
    from excubitor.development_init import register as register_init
    from excubitor.development_setup import register as register_setup

    register_setup(actions)
    register_init(actions)
    start = actions.add_parser("start", help="run a prepared job until completion or its agreed limit")
    source = start.add_mutually_exclusive_group(required=True)
    source.add_argument("--job", type=Path, help="owner-reviewed job JSON")
    source.add_argument("--plan", type=Path, help="reviewed planning directory")
    start.add_argument("--root", type=Path, help="fresh external run directory; inferred for a plan")
    start.add_argument("--baseline", choices=[BASELINE, LOCAL_BASELINE], required=True)
    start.add_argument("--background", action="store_true", help="continue after this terminal closes")
    start.set_defaults(_handler=_start)
    plan = actions.add_parser("plan", help="prepare a reviewable job from a plain-language goal")
    plan.add_argument("--project", type=Path, required=True)
    plan.add_argument("--profile", type=Path, required=True)
    plan.add_argument("--root", type=Path, required=True)
    plan.add_argument("--goal", required=True)
    plan.set_defaults(_handler=_plan)
    for action, handler in (
        ("status", _status),
        ("stop", _stop),
        ("resume", _resume),
    ):
        command = actions.add_parser(action)
        command.add_argument("--root", type=Path, required=True)
        if action == "resume":
            command.add_argument("--background", action="store_true")
        command.set_defaults(_handler=handler)


def _read(path):
    if path.stat().st_size > 1024 * 1024:
        raise RunError("job document exceeds one MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def _load(root):
    record = _read(root / "run.json")
    return RunStore(root / "authority").get(record["id"])


def _summary(run):
    return {
        "state": run.state,
        "completed_units": run.completed_units,
        "total_units": len(run.contract.units),
        "attempts": run.attempts,
        "attempt_limit": run.contract.max_attempts,
        "reviewed": run.reviewed,
    }


def _status(args):
    print(json.dumps(_summary(_load(args.root))))
    return 0


def _stop(args):
    run = _load(args.root)
    if run.enforces:
        try:
            with (args.root / "stop-requested").open("x", encoding="utf-8") as stream:
                stream.write("Owner requested stop.\n")
        except FileExistsError:
            pass
    print(json.dumps({**_summary(run), "stop_requested": run.enforces}))
    return 0


def _prepare(job, root, baseline):
    job = normalize(job)
    required = {
        "origin",
        "candidate",
        "metadata",
        "branch",
        "git",
        "llm",
        "executor",
        "editable",
        "goal",
        "units",
        "checks",
        "check_files",
        "max_attempts",
        "time_limit_seconds",
        "retain_command",
    }
    if not isinstance(job, dict) or set(job) != required:
        raise RunError("job must contain exactly the documented fields")
    preflight(job)
    if baseline != baseline_for(job):
        raise RunError("start requires the explicit baseline selected by the executor")
    if type(job["time_limit_seconds"]) is not int or not 1 <= job["time_limit_seconds"] <= 86400:
        raise RunError("job time limit must be between one second and one day")
    for key in ("origin", "candidate", "metadata", "git"):
        path = Path(job[key])
        if not path.is_absolute() or not path.exists():
            raise RunError("job paths must be existing absolute paths: " + key)
    candidate, origin = Path(job["candidate"]).resolve(), Path(job["origin"]).resolve()
    if not root.is_absolute():
        raise RunError("run storage must use an absolute path")
    root = root.resolve()
    if any(root.is_relative_to(p) or p.is_relative_to(root) for p in (candidate, origin)):
        raise RunError("run storage must be separate from the original and candidate")
    if not isinstance(job["editable"], list) or any(not isinstance(x, str) for x in job["editable"]):
        raise RunError("editable must list file names")
    retain = job["retain_command"]
    if (
        not isinstance(retain, list)
        or not 1 <= len(retain) <= 64
        or any(not isinstance(x, str) or not x or "\0" in x for x in retain)
        or not Path(retain[0]).is_absolute()
    ):
        raise RunError("retain_command must name the host's authorized committer using literal argv")
    frozen = {}
    if not isinstance(job["check_files"], list) or not job["check_files"]:
        raise RunError("list the external files that implement the acceptance checks")
    for name in job["check_files"]:
        path = Path(name)
        if (
            not path.is_absolute()
            or not path.is_file()
            or path.is_symlink()
            or path.resolve().is_relative_to(candidate)
            or path.resolve().is_relative_to(origin)
        ):
            raise RunError("acceptance implementation files must be external regular files")
        frozen[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    oracles = []
    for raw in job["checks"]:
        raw = dict(raw)
        raw["argv"] = tuple(raw["argv"])
        oracle = OutputOracle(**raw)
        if oracle.stdin and baseline != LOCAL_BASELINE:
            raise RunError("the current native executor does not support acceptance stdin")
        oracles.append(oracle)
    reader = GitCandidateReader(Path(job["git"]), candidate, Path(job["metadata"]), job["branch"])
    reader.collect()  # Refuse dirty or incorrectly prepared candidates before starting a run.
    root.mkdir(parents=True, exist_ok=False)
    evidence, temporary = root / "evidence", root / "temp"
    evidence.mkdir()
    temporary.mkdir()
    store = RunStore(root / "authority", create=True)
    binding = Binding("ralph-development", str(root), str(origin))
    contract = Contract(
        binding,
        job["goal"],
        tuple(job["units"]),
        tuple(o.check for o in oracles),
        job["max_attempts"],
        int(time.time()) + job["time_limit_seconds"],
    )
    for oracle in oracles:
        oracle.save(store)
    (root / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    (root / "check-files.json").write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    run = store.start(
        contract, "Owner explicitly invoked ralph start with this job and development baseline."
    )
    (root / "run.json").write_text(
        json.dumps(
            {
                "id": run.id,
                "job_digest": hashlib.sha256((root / "job.json").read_bytes()).hexdigest(),
                "checks_digest": hashlib.sha256((root / "check-files.json").read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    try:
        return _attach(root)
    except Exception:
        store.interrupt(store.get(run.id))
        raise


def _attach(root):
    record = _read(root / "run.json")
    if not {"id", "job_digest", "checks_digest"} <= record.keys():
        raise RunError("this older run has no saved settings for recovery; preserve its original evidence")
    for file, key in (("job.json", "job_digest"), ("check-files.json", "checks_digest")):
        if hashlib.sha256((root / file).read_bytes()).hexdigest() != record[key]:
            raise RunError("saved job settings changed; original run cannot resume")
    job = normalize(_read(root / "job.json"))
    frozen = _read(root / "check-files.json")
    store = RunStore(root / "authority")
    run = store.get(record["id"])
    contract, binding = run.contract, run.contract.binding
    candidate, evidence, temporary = Path(job["candidate"]), root / "evidence", root / "temp"
    baseline, retain = baseline_for(job), job["retain_command"]
    reader = GitCandidateReader(Path(job["git"]), candidate, Path(job["metadata"]), job["branch"])
    env = dict(os.environ)
    env.update(
        TEMP=str(temporary),
        TMP=str(temporary),
        TMPDIR=str(temporary),
        PYTHONDONTWRITEBYTECODE="1",
    )
    executor = make_executor(job, candidate, evidence, environment=env, baseline=baseline)
    runtime = make_runtime(job, candidate, evidence, executor=executor, environment=env, baseline=baseline)

    def admit(current):
        if current.contract != contract or any(
            hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest for name, digest in frozen.items()
        ):
            raise RunError("original job or acceptance implementation changed")

    def commit(current, paths):
        if not set(paths).issubset(runtime.editable):
            raise RunError("candidate changed files outside the agreed editable set")
        request = json.dumps({"candidate": str(candidate), "paths": paths, "run_id": current.id}).encode()
        result = process_tree().run(
            tuple(retain), root, env=env, stdin=request, timeout=60, terminate_on_root_exit=True
        )
        receipt = asdict(result)
        for key in ("stdout", "stderr"):
            receipt["execution"][key] = receipt["execution"][key].decode("utf-8", errors="replace")
        (root / "retain-result.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        if not _clean_exit(result):
            raise RunError("authorized committer did not retain the candidate; see retain-result.json")

    backend = ProjectBackend(store, binding, reader, runtime, admit=admit, retain=commit)
    return store, backend, run


def _start(args):
    if getattr(args, "plan", None):
        record = _read(args.plan / "plan.json")
        if record["baseline"] != args.baseline:
            raise RunError("start must use the execution baseline shown in the reviewed plan")
        args.job = args.plan / "job.json"
        if hashlib.sha256(args.job.read_bytes()).hexdigest() != record["job_digest"]:
            raise RunError("the reviewed plan changed; prepare and review again")
        if any(
            hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest
            for name, digest in record["check_files"].items()
        ):
            raise RunError("the reviewed acceptance files changed; prepare and review again")
        args.root = args.root or args.plan / "run"
    if args.root is None:
        raise RunError("--root is required with a prepared --job")
    store, _, run = _prepare(_read(args.job), args.root, args.baseline)
    if getattr(args, "background", False):
        return _background(args.root)
    return _drive(args.root, store, run)


def _plan(args):
    from excubitor.development_plan import prepare

    print(prepare(_read(args.profile), args.project, args.root, args.goal))
    return 0


def _resume(args):
    store, _, run = _attach(args.root)
    if getattr(args, "background", False):
        return _background(args.root)
    return _drive(args.root, store, run)


def _background(root):
    command = (sys.executable, "-B", "-m", "excubitor.development_worker", "watch", str(root))
    with (root / "watchdog-stdout.txt").open("ab") as out, (root / "watchdog-stderr.txt").open("ab") as err:
        subprocess.Popen(
            command,
            cwd=Path(__file__).resolve().parents[2],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            close_fds=True,
            **background_options(),
        )
    print(json.dumps({"starting_in_background": True, "root": str(root)}))
    return 0


def _controller(args):
    try:
        store, backend, run = _attach(args.root)
        Supervisor(store, backend).drive(run.id)
    except Exception as error:
        # A handled refusal is not a controller crash and must not trigger retry.
        (args.root / "controller-error.json").write_text(
            json.dumps({"error": str(error), "type": type(error).__name__}), encoding="utf-8"
        )
    return 0


def _supervise(root, store, run, cancel):
    command = (sys.executable, "-B", "-m", "excubitor.development_worker", "controller", str(root))
    return ControllerWatchdog(store, lambda _: command, Path(__file__).resolve().parents[2]).drive(
        run.id, run.contract.binding, cancel=cancel
    )


def _drive(root, store, run):
    cancel, done = threading.Event(), threading.Event()
    if (root / "stop-requested").exists():
        cancel.set()

    def monitor():
        while not done.wait(0.1):
            if (root / "stop-requested").exists():
                cancel.set()
                return

    watcher = threading.Thread(target=monitor, daemon=True)
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    previous_term = signal.signal(signal.SIGTERM, lambda *_: cancel.set()) if os.name == "posix" else None
    watcher.start()
    print(json.dumps({"started": True, "root": str(root), **_summary(run)}), flush=True)
    try:
        final = _supervise(root, store, run, cancel)
        print(json.dumps(_summary(final)), flush=True)
        return 0 if final.state == "complete" else 1
    finally:
        done.set()
        watcher.join()
        signal.signal(signal.SIGINT, previous)
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)
