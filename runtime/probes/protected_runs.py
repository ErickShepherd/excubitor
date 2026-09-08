"""Create-only native sandbox test; installs no hook and grants no native trust.

The parent provisions a dummy host-owned run. The native restricted subprocess
tries to rewrite its authority through the real lifecycle API and raw SQLite.
This proves only the tested local subprocess storage boundary, not owner-origin
authentication, safe verification execution, other tools, or a complete runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from excubitor.runs import Binding, Candidate, Check, Contract, RunStore  # noqa: E402

WORKER = """import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

data = json.loads(Path(__file__).with_name("input.json").read_text())
sys.path.insert(0, data["repo"])
from excubitor.runs import RunStore

store = RunStore(Path(data["authority"]))
result = {}
Path(__file__).with_name("ordinary.txt").write_text("ordinary write works")
result["ordinary"] = "WRITE_SUCCEEDED"
run = store.get(data["run"])
result["can_read_run"] = True

def erase():
    db = sqlite3.connect(store.path)
    try:
        with db:
            db.execute("DELETE FROM runs")
    finally:
        db.close()

for label, operation in (
    ("forge_activation", lambda: store.start(
        replace(run.contract, binding=replace(run.contract.binding, session="forged-task")),
        "forged-approval")),
    ("advance", lambda: store.begin_attempt(run)),
    ("extend_limits", lambda: store.begin_attempt(
        replace(run, contract=replace(run.contract, max_attempts=999)))),
    ("disable_protection", lambda: store.cancel(run)),
    ("forge_completion", lambda: store.finish(run, run.candidate, workers_idle=True)),
    ("forge_check", lambda: store.record_check(run, run.candidate, run.contract.checks[0], passed=True)),
    ("forge_review", lambda: store.record_review(run, run.candidate, passed=True)),
    ("erase_records", erase),
    ("weaken_acceptance", lambda: (Path(data["authority"]) / "acceptance.txt").write_text("weakened")),
):
    try:
        operation()
        result[label] = "MUTATION_SUCCEEDED"
    except Exception as exc:
        result[label] = type(exc).__name__
print(json.dumps(result))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True, help="absolute path to the installed Codex CLI")
    parser.add_argument("--python", type=Path, required=True, help="absolute path to the worker Python")
    parser.add_argument("--output", type=Path, required=True, help="absolute create-only evidence directory")
    args = parser.parse_args()
    if not all(path.is_absolute() for path in (args.codex, args.python, args.output)):
        parser.error("all paths must be absolute")
    if not args.codex.is_file() or not args.python.is_file():
        parser.error("runtime executables must exist")
    args.output.mkdir(parents=True, exist_ok=False)
    project = args.output / "project"
    project.mkdir()
    authority = args.output / "authority"
    store = RunStore(authority, create=True)
    check = Check("acceptance", hashlib.sha256(b"fixed check").hexdigest())
    contract = Contract(
        Binding("codex-native-test", "fixture-owner-task", str(project)),
        "Protect this bounded storage test",
        ("first", "second"),
        (check,),
        4,
        int(time.time()) + 600,
    )
    run = store.start(contract, "explicit-storage-test-authorization")
    # Dummy candidate and host evidence exercise the state machine. They are not
    # an actual committed project, independent verification, or semantic review.
    candidate = Candidate("b" * 64, "c" * 40, True, True)
    for unit in contract.units:
        run = store.begin_attempt(run)
        run = store.checkpoint(run, candidate, unit=unit)
    run = store.record_check(run, candidate, check, passed=True)
    run = store.record_review(run, candidate, passed=True)
    (authority / "acceptance.txt").write_bytes(b"fixed check")
    data = {"repo": str(ROOT), "authority": str(authority), "run": run.id}
    (project / "input.json").write_text(json.dumps(data), encoding="utf-8")
    (project / "worker.py").write_text(WORKER, encoding="utf-8")
    command = [
        str(args.codex),
        "sandbox",
        "-P",
        ":workspace",
        "-C",
        str(project),
        "--",
        str(args.python),
        "-I",
        "-B",
        str(project / "worker.py"),
    ]
    report = {
        "schema": "excubitor.native-storage-probe.v1",
        "platform": platform.platform(),
        "controller_python": platform.python_version(),
        "source_digest": hashlib.sha256((ROOT / "excubitor" / "runs.py").read_bytes()).hexdigest(),
        "probe_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "profile": ":workspace",
        "limits": "Local subprocess filesystem boundary only; dummy candidate and host facts. "
        "No native owner-origin authentication, MCP control, GUI protection, "
        "or complete verifier/runner.",
        "passed": False,
    }
    try:
        report["runtime"] = subprocess.run(
            [str(args.codex), "--version"], capture_output=True, text=True, check=True, timeout=15
        ).stdout.strip()
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        report.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        observed = json.loads(result.stdout) if result.returncode == 0 else {}
        after = store.get(run.id)
        report.update(
            observations=observed,
            authority_unchanged=after == run,
            acceptance_unchanged=(authority / "acceptance.txt").read_bytes() == b"fixed check",
            ordinary_write_exists=(project / "ordinary.txt").is_file(),
        )
        expected = {
            "ordinary": "WRITE_SUCCEEDED",
            "can_read_run": True,
            "erase_records": "OperationalError",
            "weaken_acceptance": "PermissionError",
        }
        for label in (
            "forge_activation",
            "advance",
            "disable_protection",
            "forge_completion",
            "forge_check",
            "forge_review",
        ):
            expected[label] = "RunError"
        # The controller rejects altered contract bytes before SQLite attempts a
        # write. This is an invariant rejection, not a filesystem-denial witness.
        expected["extend_limits"] = "Conflict"
        if (
            result.returncode != 0
            or observed != expected
            or not report["authority_unchanged"]
            or not report["acceptance_unchanged"]
            or not report["ordinary_write_exists"]
        ):
            raise RuntimeError("native storage boundary did not satisfy the expected observations")
        # The subprocess has exited. The trusted test parent ends the dummy run.
        closed = store.acknowledge_cancel(store.cancel(after), workers_idle=True)
        report["fixture_run_closed"] = not closed.enforces
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (args.output / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
