"""Disposable Windows native-sandbox check of host-owned process jobs.

No model calls, login, hooks, native trust enrollment, or production registration.
The default creates isolated native state under the new output directory. Explicit
existing-home mode reuses native sandbox credentials without copying them; Codex
can write runtime files in that home and therefore needs separate storage authority.
This probes one native shell boundary, not other tools or task authentication.
"""

from __future__ import annotations

import argparse
import ctypes as c
import hashlib
import inspect
import json
import os
import sys
import tomllib
import uuid
from ctypes import wintypes as w
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from excubitor.processes import WindowsProcessTree  # noqa: E402
from excubitor.runs import RunError  # noqa: E402
from excubitor.windows_jobs import api, create_job  # noqa: E402

PROTECTED_NATIVE_FILES = (
    "config.toml",
    ".sandbox/setup_marker.json",
    ".sandbox-secrets/sandbox_users.json",
)


def existing_native_home(home):
    """Read-only prerequisite check; never provision, repair, or copy credentials.

    This checks the observed setup format, not native readiness or authenticity.
    Stop on a native setup request; existing files do not authorize host changes.
    """
    try:
        config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8-sig"))
        marker = json.loads((home / ".sandbox" / "setup_marker.json").read_text(encoding="utf-8"))
        if config.get("windows", {}).get("sandbox") != "elevated" or marker.get("version") != 5:
            raise ValueError("requires the existing elevated sandbox and observed setup format")
        return native_fingerprints(home)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise RunError(
            "existing sandbox files are missing or unsupported; no native process started"
        ) from error


def native_fingerprints(home):
    # Only digests are retained, never native configuration or credential bytes.
    return {name: hashlib.sha256((home / name).read_bytes()).hexdigest() for name in PROTECTED_NATIVE_FILES}


def token_facts():
    """Observe the current token, without changing it or exposing credentials."""
    kernel = c.WinDLL("kernel32", use_last_error=True)
    security = c.WinDLL("advapi32", use_last_error=True)
    for library, name, args, result_type in (
        (kernel, "GetCurrentProcess", [], w.HANDLE),
        (kernel, "CloseHandle", [w.HANDLE], w.BOOL),
        (kernel, "LocalFree", [c.c_void_p], c.c_void_p),
        (security, "OpenProcessToken", [w.HANDLE, w.DWORD, c.c_void_p], w.BOOL),
        (security, "GetTokenInformation", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
        (security, "ConvertSidToStringSidW", [c.c_void_p, c.c_void_p], w.BOOL),
    ):
        function = getattr(library, name)
        function.argtypes, function.restype = args, result_type
    token = w.HANDLE()
    if not security.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
        raise c.WinError(c.get_last_error())
    result = {}
    try:
        for label, kind in (("user", 1), ("integrity", 25)):
            size, value = w.DWORD(), w.LPWSTR()
            security.GetTokenInformation(token, kind, None, 0, c.byref(size))
            data = c.create_string_buffer(size.value)
            if not security.GetTokenInformation(token, kind, data, size, c.byref(size)):
                raise c.WinError(c.get_last_error())
            sid = c.cast(data, c.POINTER(c.c_void_p))[0]
            if not security.ConvertSidToStringSidW(sid, c.byref(value)):
                raise c.WinError(c.get_last_error())
            try:
                result[label] = value.value
            finally:
                kernel.LocalFree(value)
        return result
    finally:
        kernel.CloseHandle(token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--existing-elevated-home", type=Path)
    args = parser.parse_args()
    paths = (args.codex, args.python, args.output, args.existing_elevated_home)
    if os.name != "nt" or any(path is not None and not path.is_absolute() for path in paths):
        parser.error("requires Windows and absolute paths")
    try:
        before = existing_native_home(args.existing_elevated_home) if args.existing_elevated_home else None
    except RunError as error:
        parser.error(str(error))
    mode = "elevated" if before is not None else "unelevated"
    args.output.mkdir(parents=True, exist_ok=False)
    project, authority = args.output / "project", args.output / "authority"
    native_home, temporary = args.output / "native-home", args.output / "temp"
    for directory in (project, authority, native_home, temporary):
        directory.mkdir()
    sqlite_home = native_home
    if args.existing_elevated_home:
        native_home = args.existing_elevated_home
    oracle = authority / "original-check.txt"
    original = b"Original acceptance definition must remain unchanged.\n"
    oracle.write_bytes(original)
    job_name = "Global\\Excubitor.Run." + uuid.uuid4().hex
    absent_name = "Global\\Excubitor.Run." + uuid.uuid4().hex
    kernel, _ = api()
    job = create_job(job_name)
    source = f"""
import ctypes as c, json, os, time
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
{inspect.getsource(token_facts)}
result={{'job':{job_name!r},'access':{{}}}}
result['pid']=os.getpid()
result['token']=token_facts()
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
time.sleep(0.2)  # Allow the host to observe this exact child in its kernel job.
"""
    worker = project / "check_native_access.py"
    worker.write_text(source, encoding="utf-8")
    env = dict(os.environ)
    # Per-child native locations; never repurpose the owner's live config or auth.
    env.update(
        CODEX_HOME=str(native_home),
        CODEX_SQLITE_HOME=str(sqlite_home),
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
        "windows.sandbox=" + json.dumps(mode),
        "-c",
        "log_dir=" + json.dumps(str(args.output / "native-logs")),
        "-C",
        str(project),
        "--",
        str(args.python),
        "-I",
        "-B",
        str(worker),
    )
    report = {
        "passed": False,
        "sandbox_mode": mode,
        "job": job_name,
        "host_token": token_facts(),
        "protected_native_before": before,
    }
    try:
        result = WindowsProcessTree().run(argv, project, env=env, timeout=30, output_limit=1024 * 1024)
        report["process"] = asdict(result)
        for key in ("stdout", "stderr"):
            report["process"]["execution"][key] = getattr(result.execution, key).decode(
                "utf-8", errors="replace"
            )
        report["oracle_unchanged"] = oracle.read_bytes() == original
        report["oracle_sha256"] = hashlib.sha256(oracle.read_bytes()).hexdigest()
        if before is not None:
            report["protected_native_after"] = native_fingerprints(native_home)
            native_unchanged = report["protected_native_after"] == before
        else:
            report["native_config_created"] = (native_home / "config.toml").exists()
            native_unchanged = not report["native_config_created"]
        report["native_configuration_unchanged"] = native_unchanged
        if result.execution.exit_code == 0:
            facts = json.loads(result.execution.stdout)
            report["facts"] = facts
            report["worker_observed_in_host_job"] = facts["pid"] in result.observed_pids
            report["passed"] = (
                result.drained
                and report["worker_observed_in_host_job"]
                and facts["ordinary_write"]
                and (project / "ordinary.txt").read_text() == "ordinary-ok"
                and facts["oracle_write"] == "denied"
                and report["oracle_unchanged"]
                and facts["missing_object"] == {"opened": False, "error": 2}
                and all(value == {"opened": False, "error": 5} for value in facts["access"].values())
                and native_unchanged
                and (before is None or facts["token"]["user"] != report["host_token"]["user"])
            )
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        kernel.CloseHandle(job)
        with (args.output / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps({"passed": report["passed"], "report": str(args.output / "result.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
