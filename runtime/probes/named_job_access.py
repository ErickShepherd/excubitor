"""Disposable Windows native-sandbox check of host-owned process jobs.

No model, credentials, hooks, native trust enrollment, or production registration.
All mutable state belongs to the new output directory. This probes the selected
native sandbox mode only; it does not attest other tools or authenticate a task.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from excubitor.processes import WindowsProcessTree  # noqa: E402
from excubitor.windows_jobs import api, create_job  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or any(not path.is_absolute() for path in (args.codex, args.python, args.output)):
        parser.error("requires Windows and absolute paths")
    args.output.mkdir(parents=True, exist_ok=False)
    project, authority = args.output / "project", args.output / "authority"
    native_home, temporary = args.output / "native-home", args.output / "temp"
    for directory in (project, authority, native_home, temporary):
        directory.mkdir()
    oracle = authority / "original-check.txt"
    original = b"Original acceptance definition must remain unchanged.\n"
    oracle.write_bytes(original)
    job_name = "Global\\Excubitor.Run." + uuid.uuid4().hex
    absent_name = "Global\\Excubitor.Run." + uuid.uuid4().hex
    kernel, _ = api()
    job = create_job(job_name)
    source = f"""
import ctypes as c, json
from ctypes import wintypes as w
from pathlib import Path
kernel=c.WinDLL('kernel32',use_last_error=True)
kernel.OpenJobObjectW.argtypes=[w.DWORD,w.BOOL,w.LPCWSTR]
kernel.OpenJobObjectW.restype=w.HANDLE
kernel.CloseHandle.argtypes=[w.HANDLE]
kernel.CloseHandle.restype=w.BOOL
def attempt(name, access):
    c.set_last_error(0)
    handle=kernel.OpenJobObjectW(access,False,name)
    result={{'opened':bool(handle),'error':0 if handle else c.get_last_error()}}
    if handle: kernel.CloseHandle(handle)
    return result
result={{'job':{job_name!r},'access':{{}}}}
for label, access in [('query',4),('terminate',8),('assign',1),
                      ('write_dacl',0x40000),('write_owner',0x80000)]:
    result['access'][label]=attempt({job_name!r},access)
result['missing_object']=attempt({absent_name!r},4)
Path('ordinary.txt').write_text('ordinary-ok',encoding='utf-8')
result['ordinary_write']=True
try:
    Path({str(oracle)!r}).write_bytes(b'changed')
    result['oracle_write']='allowed'
except OSError as error:
    result['oracle_write']='denied'
    result['oracle_error']=error.winerror
print(json.dumps(result))
"""
    worker = project / "check_native_access.py"
    worker.write_text(source, encoding="utf-8")
    env = dict(os.environ)
    # Per-child native locations; never repurpose the owner's live config or auth.
    env.update(
        CODEX_HOME=str(native_home),
        CODEX_SQLITE_HOME=str(native_home),
        TEMP=str(temporary),
        TMP=str(temporary),
        TMPDIR=str(temporary),
    )
    env.pop("CODEX_THREAD_ID", None)
    argv = (
        str(args.codex),
        "sandbox",
        "-P",
        ":workspace",
        "--include-managed-config",
        "-c",
        'windows.sandbox="unelevated"',
        "-C",
        str(project),
        "--",
        str(args.python),
        "-I",
        "-B",
        str(worker),
    )
    report = {"passed": False, "sandbox_mode": "unelevated", "job": job_name}
    try:
        result = WindowsProcessTree().run(argv, project, env=env, timeout=30, output_limit=1024 * 1024)
        report["process"] = asdict(result)
        for key in ("stdout", "stderr"):
            report["process"]["execution"][key] = getattr(result.execution, key).decode(
                "utf-8", errors="replace"
            )
        report["oracle_unchanged"] = oracle.read_bytes() == original
        report["oracle_sha256"] = hashlib.sha256(oracle.read_bytes()).hexdigest()
        report["native_config_created"] = (native_home / "config.toml").exists()
        if result.execution.exit_code == 0:
            facts = json.loads(result.execution.stdout)
            report["facts"] = facts
            report["passed"] = (
                result.drained
                and facts["ordinary_write"]
                and (project / "ordinary.txt").read_text() == "ordinary-ok"
                and facts["oracle_write"] == "denied"
                and report["oracle_unchanged"]
                and facts["missing_object"] == {"opened": False, "error": 2}
                and all(value == {"opened": False, "error": 5} for value in facts["access"].values())
                and not report["native_config_created"]
            )
    finally:
        kernel.CloseHandle(job)
        with (args.output / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({"passed": report["passed"], "report": str(args.output / "result.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
