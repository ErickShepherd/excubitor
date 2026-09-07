"""Explicit native Claude development jobs on host-prepared candidate checkouts."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import threading
import time
from dataclasses import asdict
from pathlib import Path

from excubitor.acceptance import OutputOracle
from excubitor.candidates import GitCandidateReader
from excubitor.claude_development import ClaudeDevelopmentRuntime
from excubitor.claude_project import _clean_exit
from excubitor.processes import WindowsProcessTree
from excubitor.project_backend import ProjectBackend
from excubitor.runs import Binding, Contract, RunError, RunStore
from excubitor.supervisor import Supervisor
from excubitor.windows_development import BASELINE, WindowsDevelopmentExecutor


def register(subparsers):
    parser = subparsers.add_parser("ralph", help="start, inspect, or stop an agreed native Claude job")
    actions = parser.add_subparsers(dest="action", required=True)
    start = actions.add_parser("start", help="run a prepared job until completion or its agreed limit")
    start.add_argument("--job", type=Path, required=True, help="owner-reviewed job JSON")
    start.add_argument("--root", type=Path, required=True, help="fresh external run directory")
    start.add_argument("--baseline", choices=[BASELINE], required=True)
    start.set_defaults(_handler=_start)
    for action, handler in (("status", _status), ("stop", _stop)):
        command = actions.add_parser(action)
        command.add_argument("--root", type=Path, required=True)
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
    required = {
        "origin",
        "candidate",
        "metadata",
        "branch",
        "git",
        "claude",
        "codex",
        "codex_home",
        "model",
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
    if baseline != BASELINE or os.name != "nt":
        raise RunError("this entry point requires native Windows and the explicit development baseline")
    if type(job["time_limit_seconds"]) is not int or not 1 <= job["time_limit_seconds"] <= 86400:
        raise RunError("job time limit must be between one second and one day")
    for key in ("origin", "candidate", "metadata", "git", "claude", "codex", "codex_home"):
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
        if oracle.stdin:
            raise RunError("the current native executor does not support acceptance stdin")
        oracles.append(oracle)
    reader = GitCandidateReader(Path(job["git"]), candidate, Path(job["metadata"]), job["branch"])
    reader.collect()  # Refuse dirty or incorrectly prepared candidates before starting a run.
    root.mkdir(parents=True, exist_ok=False)
    evidence, temporary = root / "evidence", root / "temp"
    evidence.mkdir()
    temporary.mkdir()
    env = dict(os.environ)
    env.update(
        TEMP=str(temporary),
        TMP=str(temporary),
        TMPDIR=str(temporary),
        CLAUDE_CODE_TMPDIR=str(temporary),
        CLAUDE_CODE_DEBUG_LOGS_DIR=str(evidence / "debug"),
        CLAUDE_CODE_DISABLE_AUTO_MEMORY="1",
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
        CLAUDE_CODE_MAX_TURNS="4",
        DISABLE_AUTOUPDATER="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    executor = WindowsDevelopmentExecutor(
        job["codex"], candidate, evidence, codex_home=job["codex_home"], environment=env, baseline=baseline
    )
    runtime = ClaudeDevelopmentRuntime(
        job["claude"],
        candidate,
        evidence,
        executor=executor,
        environment=env,
        editable=job["editable"],
        model=job["model"],
        native_model=job["model"],
        baseline=baseline,
    )
    store = RunStore(root / "authority", create=True)
    binding = Binding("claude-development", str(root), str(origin))
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
    (root / "run.json").write_text(json.dumps({"id": run.id}), encoding="utf-8")

    def admit(current):
        if current.contract != contract or any(
            hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest for name, digest in frozen.items()
        ):
            raise RunError("original job or acceptance implementation changed")

    def commit(current, paths):
        if not set(paths).issubset(runtime.editable):
            raise RunError("candidate changed files outside the agreed editable set")
        request = json.dumps({"candidate": str(candidate), "paths": paths, "run_id": current.id}).encode()
        result = WindowsProcessTree().run(
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
    store, backend, run = _prepare(_read(args.job), args.root, args.baseline)
    cancel, done = threading.Event(), threading.Event()

    def monitor():
        while not done.wait(0.1):
            if (args.root / "stop-requested").exists():
                cancel.set()
                return

    watcher = threading.Thread(target=monitor, daemon=True)
    previous = signal.signal(signal.SIGINT, lambda *_: cancel.set())
    watcher.start()
    print(json.dumps({"started": True, "root": str(args.root), **_summary(run)}), flush=True)
    try:
        final = Supervisor(store, backend).drive(run.id, cancel=cancel)
        print(json.dumps(_summary(final)), flush=True)
        return 0 if final.state == "complete" else 1
    finally:
        done.set()
        watcher.join()
        signal.signal(signal.SIGINT, previous)
