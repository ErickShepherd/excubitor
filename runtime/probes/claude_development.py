"""Disposable real-code rehearsal for the explicit native development baseline.

No install, registration or production runtime promotion. Fixture Git commits
are local; development-repository commits remain subject to its own broker.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "codex", "codex-home", "claude"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--baseline", choices=[BASELINE], required=True)
    args = parser.parse_args()
    root = args.root
    if not root.is_absolute() or root.drive.upper() != "D:":
        raise ValueError("this owner-authorized rehearsal requires a fresh absolute D: output directory")
    root.mkdir(parents=True, exist_ok=False)
    origin, candidate, metadata, evidence, temporary = (root / n for n in ("origin", "candidate", "git", "evidence", "temp"))
    for path in (origin, evidence, temporary):
        path.mkdir()
    original = "def median(values):\n    values = sorted(values)\n    if not values:\n        raise ValueError('empty input')\n    return values[len(values) // 2]\n"
    (origin / "median.py").write_text(original, encoding="utf-8")
    git = Path(shutil.which("git")).resolve()
    env = dict(os.environ)
    env.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary),
               CLAUDE_CODE_TMPDIR=str(temporary), CLAUDE_CODE_DEBUG_LOGS_DIR=str(evidence / "debug"),
               CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
               CLAUDE_CODE_MAX_TURNS="4", DISABLE_AUTOUPDATER="1", PYTHONDONTWRITEBYTECODE="1")
    git_env = {k: v for k, v in env.items() if not k.upper().startswith("GIT_")}
    git_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    # Use the owner's configured public author, rather than inventing an identity.
    author = {}
    for field in ("name", "email"):
        result = WindowsProcessTree().run((str(git), "config", "user." + field),
                                         Path(__file__).resolve().parents[2], env=env, timeout=10)
        if not _clean_exit(result) or not result.execution.stdout.strip():
            raise RunError("configure the Git author before running the rehearsal")
        author[field] = result.execution.stdout.decode("utf-8").strip()

    def git_command(*argv):
        result = WindowsProcessTree().run((str(git), *argv), root, env=git_env, timeout=15)
        if not _clean_exit(result):
            raise RunError("disposable Git failed: " + result.execution.stderr.decode(errors="replace"))
        return result.execution.stdout

    git_command("init", "-q", "-b", "main", "--separate-git-dir", str(metadata), str(candidate))
    (candidate / "median.py").write_text(original, encoding="utf-8")

    def retain(run, paths):
        if set(paths) != {"median.py"}:
            raise RunError("fixture scope only permits median.py")
        git_command("-C", str(candidate), "add", "--", *paths)
        git_command("-C", str(candidate), "-c", "user.name=" + author["name"],
                    "-c", "user.email=" + author["email"], "-c", "commit.gpgsign=false",
                    "commit", "-qm", "Retain native development candidate")

    retain(None, ("median.py",))
    git_command("-C", str(candidate), "checkout", "-qb", "ralph/native-development")
    reader = GitCandidateReader(git, candidate, metadata, "refs/heads/ralph/native-development")
    check = root / "check_median.py"
    check.write_text("""import sys
sys.path.insert(0, sys.argv[1])
from median import median
assert median([1, 2]) == 1.5
assert median([8, 1, 3, 2]) == 2.5
assert median([-3, -2]) == -2.5
assert median([3, 1, 2]) == 2
assert median([7]) == 7
assert median(iter([9, 1, 2, 3])) == 2.5
items = [3, 1, 2]; median(items); assert items == [3, 1, 2]
try: median([])
except ValueError: pass
else: raise AssertionError('empty input must fail')
sys.stdout.buffer.write(b'median-ok\\n')
""", encoding="utf-8")
    frozen = hashlib.sha256(check.read_bytes()).hexdigest()
    store = RunStore(root / "authority", create=True)
    binding = Binding("claude-development", "owner-authorized-code-slice", str(origin))
    oracle = OutputOracle("median behavior", (sys.executable, "-I", "-B", str(check), str(candidate)),
                          "", "median-ok\n", timeout_seconds=90)
    oracle.save(store)
    executor = WindowsDevelopmentExecutor(args.codex, candidate, evidence, codex_home=args.codex_home,
                                           environment=env, baseline=args.baseline)
    failed = executor.run(oracle.argv, mode="read-only", timeout=90)
    if failed.execution.exit_code != 1 or b"AssertionError" not in failed.execution.stderr or not failed.drained:
        raise RunError("initial real bug not established")
    contract = Contract(binding,
        "Fix median.py: median accepts a finite iterable of numbers, returns the middle sorted value for odd "
        "length and arithmetic mean of two middle values for even length; empty input raises ValueError; "
        "do not mutate the input. Preserve all other files. Run the supplied acceptance command using Python -B.",
        ("Fix median and execute its native tests.",), (oracle.check,), 3, int(time.time()) + 720)
    run = store.start(contract, "Owner said Do it for the explicit native-development-v1 slice; retain local branch only.")
    runtime = ClaudeDevelopmentRuntime(args.claude, candidate, evidence, executor=executor, environment=env,
        editable=("median.py",), model="claude-fable-5-1", native_model="claude-fable-5-1", baseline=args.baseline)

    def admit(current):
        if current.contract != contract or hashlib.sha256(check.read_bytes()).hexdigest() != frozen:
            raise RunError("original agreement or check changed")

    backend = ProjectBackend(store, binding, reader, runtime, admit=admit, retain=retain)
    report = {"baseline": BASELINE, "passed": False, "initial_test_failed": True,
              "owner_starts": 1, "intermediate_owner_interventions": 0}
    try:
        # An actual boundary rejection, not a prompt telling the worker to behave.
        try:
            runtime.apply({"files": [{"path": "../authority/contract.json", "content": "forged"}], "command": []})
        except RunError:
            report["agreement_edit_denied"] = True
        else:
            raise AssertionError("agreement edit accepted")
        ordinary = Binding("claude-development", "ordinary-other-task", str(origin))
        assert store.lookup(ordinary) is None
        # Ordinary work executes while the Ralph run is active, without a run wrapper.
        plain = WindowsProcessTree().run((sys.executable, "-I", "-B", "-c",
                    "from pathlib import Path; Path('ordinary.txt').write_text('ordinary')"),
                    root, env=env, timeout=10)
        assert _clean_exit(plain)
        final = Supervisor(store, backend).drive(run.id)
        assert final.state == "complete" and final.reviewed and final.contract == contract
        assert reader.collect() == final.candidate
        assert RunStore(store.directory).get(run.id) == final and store.lookup(binding) is None
        assert store.lookup(ordinary) is None and (root / "ordinary.txt").read_text() == "ordinary"
        assert (origin / "median.py").read_text() == original
        assert hashlib.sha256(check.read_bytes()).hexdigest() == frozen
        before = len(list(evidence.glob("execution-*.json")))
        assert Supervisor(store, backend).drive(run.id) == final
        assert len(list(evidence.glob("execution-*.json"))) == before
        report.update(passed=True, final=asdict(final), original_unchanged=True, frozen_check_unchanged=True,
                      ordinary_task_unarmed=True, ordinary_command_passed=True, completed_run_does_not_restart=True)
    except BaseException as error:
        report.update(error=repr(error), state=asdict(store.get(run.id)))
        raise
    finally:
        (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "packet": str(root), "error": report.get("error")}))


if __name__ == "__main__":
    main()
