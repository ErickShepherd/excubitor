"""Opt-in native development execution; NOT credential/hostile-code isolation.

Reuses the installed, already provisioned Codex command API. No setup, read-denial
ACLs, fallback execution, registration or vendor credentials are implemented here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, replace
from pathlib import Path

BASELINE = "native-development-v1"


def _bridge(path):
    request = json.loads(Path(path).read_text(encoding="utf-8"))
    process = subprocess.Popen(request["server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    with Path(request["events"]).open("x", encoding="utf-8") as events:

        def send(value):
            process.stdin.write(json.dumps(value).encode() + b"\n")
            process.stdin.flush()

        def receive(identifier):
            while True:
                line = process.stdout.readline(2 * 1024 * 1024 + 1)
                if not line or len(line) > 2 * 1024 * 1024:
                    raise RuntimeError("missing or oversized native response")
                value = json.loads(line)
                events.write(json.dumps(value) + "\n")
                events.flush()
                if value.get("id") == identifier:
                    if "error" in value:
                        raise RuntimeError("native command rejected: " + json.dumps(value["error"]))
                    return value["result"]

        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "excubitor-development", "version": "0.1"},
                    "capabilities": {"experimentalApi": True},
                },
            }
        )
        receive(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "command/exec", "params": request["command"]})
        result = receive(2)
        process.stdin.close()
        process.wait(timeout=10)
        print(json.dumps(result), flush=True)


class WindowsDevelopmentExecutor:
    baseline = BASELINE

    def __init__(self, codex, project, output, *, codex_home, environment, baseline):
        from excubitor.runs import RunError

        if baseline != BASELINE:
            raise RunError("explicit native-development-v1 admission required; not credential isolation")
        self.codex, self.project, self.output, self.home = map(Path, (codex, project, output, codex_home))
        if not all(
            p.is_absolute() and p.exists() for p in (self.codex, self.project, self.output, self.home)
        ):
            raise ValueError("existing absolute native paths required")
        if self.output.resolve().is_relative_to(self.project.resolve()):
            raise RunError("execution evidence must be outside the candidate")
        self.environment = dict(environment)

    def run(self, argv, *, mode="workspace-write", timeout=90, cancel=None, stdin=b""):
        from excubitor.acceptance import Execution
        from excubitor.processes import WindowsProcessTree
        from excubitor.runs import RunError

        if mode not in ("workspace-write", "read-only") or stdin:
            raise RunError("unsupported development command mode or stdin")
        if (
            not isinstance(argv, tuple)
            or not 1 <= len(argv) <= 64
            or any(not isinstance(s, str) or not s or "\0" in s or len(s) > 16384 for s in argv)
            or not Path(argv[0]).is_absolute()
            or not 0 < timeout <= 300
        ):
            raise ValueError("bounded literal argv and timeout required")
        packet = self.output / ("command-" + uuid.uuid4().hex)
        packet.mkdir()
        temporary = packet / "temp"
        temporary.mkdir()
        filesystem = {
            str(self.project): "write" if mode == "workspace-write" else "read",
            str(temporary): "write",
        }
        profile = "excubitor_development"
        parent = ":workspace" if mode == "workspace-write" else ":read-only"
        policy = (
            "{ extends = "
            + json.dumps(parent)
            + ", filesystem = { "
            + ", ".join(json.dumps(k) + "=" + json.dumps(v) for k, v in filesystem.items())
            + " }, network = { enabled = false } }"
        )
        server = [
            str(self.codex),
            "app-server",
            "--stdio",
            "-c",
            'windows.sandbox="elevated"',
            "-c",
            'approval_policy="never"',
            "-c",
            "mcp_servers={}",
            "-c",
            'web_search="disabled"',
            "-c",
            "default_permissions=" + json.dumps(profile),
            "-c",
            f"permissions.{profile}=" + policy,
            "-c",
            "log_dir=" + json.dumps(str(packet / "logs")),
        ]
        for feature in (
            "plugins",
            "apps",
            "memories",
            "browser_use",
            "in_app_browser",
            "computer_use",
            "multi_agent",
        ):
            server += ["--disable", feature]
        command = {
            "command": list(argv),
            "cwd": str(self.project),
            "permissionProfile": profile,
            "timeoutMs": int(timeout * 1000),
        }
        request = packet / "request.json"
        request.write_text(
            json.dumps(
                {
                    "baseline": BASELINE,
                    "server": server,
                    "command": command,
                    "events": str(packet / "events.jsonl"),
                }
            ),
            encoding="utf-8",
        )
        # The authenticated coordinator environment is never passed through wholesale.
        allowed = {
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "SYSTEMDRIVE",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "PROGRAMDATA",
            "ALLUSERSPROFILE",
            "USERPROFILE",
            "LOCALAPPDATA",
            "APPDATA",
            "USERNAME",
            "USERDOMAIN",
            "PATH",
        }
        env = {k: v for k, v in self.environment.items() if k.upper() in allowed}
        env.update(
            CODEX_HOME=str(self.home),
            CODEX_SQLITE_HOME=str(self.home),
            TEMP=str(temporary),
            TMP=str(temporary),
            TMPDIR=str(temporary),
            PYTHONDONTWRITEBYTECODE="1",
        )
        started = time.monotonic()
        outer = WindowsProcessTree().run(
            (sys.executable, "-I", "-B", str(Path(__file__).resolve()), str(request)),
            self.project,
            env=env,
            timeout=timeout,
            cancelled=cancel,
            output_limit=2 * 1024 * 1024,
            terminate_on_root_exit=True,
        )
        receipt = asdict(outer)
        for key in ("stdout", "stderr"):
            receipt["execution"][key] = receipt["execution"][key].decode("utf-8", errors="replace")
        (packet / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        if (
            outer.execution.exit_code != 0
            or outer.cancelled
            or outer.execution.timed_out
            or outer.execution.output_limited
            or not outer.drained
        ):
            return outer
        try:
            native = json.loads(outer.execution.stdout)
            if type(native["exitCode"]) is not int or not all(
                type(native[k]) is str for k in ("stdout", "stderr")
            ):
                raise ValueError("invalid command response")
        except (ValueError, KeyError, TypeError) as error:
            raise RunError("invalid native command result") from error
        captured = [native[k].encode("utf-8") for k in ("stdout", "stderr")]
        # Windows rejects custom output caps. Keep this first adapter's accepted
        # result small; buffered protocol does not prove arbitrary output fidelity.
        execution = Execution(
            native["exitCode"],
            *captured,
            time.monotonic() - started,
            output_limited=any(len(b) >= 4096 or b"truncated" in b.lower() for b in captured),
        )
        return replace(outer, execution=execution)


if __name__ == "__main__":
    _bridge(sys.argv[1])
