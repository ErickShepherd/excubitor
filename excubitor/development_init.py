"""Project-aware, create-only setup. No model calls or repository mutations."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from excubitor.acceptance import OutputOracle
from excubitor.command_model import literal_command
from excubitor.development_helpers import subagent_limit
from excubitor.development_setup import MODELS, _project_file
from excubitor.git_retention import builtin_command
from excubitor.http_model_client import validate_endpoint
from excubitor.literal_command import reject_windows_batch
from excubitor.original_git import original_git_environment
from excubitor.runs import RunError


def register(actions):
    parser = actions.add_parser("init", help="create a concrete project profile without model calls")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--llm", choices=MODELS, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--executable", help="CLI executable name on PATH, or absolute path")
    parser.add_argument("--codex-home", type=Path)
    parser.add_argument("--model-command", help="command-json bridge argv as a literal JSON array")
    parser.add_argument("--endpoint")
    parser.add_argument(
        "--api-key-env", default="RALPH_MODEL_API_KEY", help="environment name, never the key"
    )
    parser.add_argument("--response-format", choices=("json_schema", "json_object"), default="json_schema")
    parser.add_argument("--git", default="git")
    parser.add_argument(
        "--editable", action="append", required=True, help="tracked-file glob; repeat as needed"
    )
    parser.add_argument("--check-file", action="append", required=True, help="tracked frozen-test glob")
    parser.add_argument(
        "--check-argv", action="append", required=True, help="literal JSON argv using {checks}"
    )
    parser.add_argument("--check-timeout", type=int, default=60)
    parser.add_argument("--max-attempts", type=int, default=12)
    parser.add_argument(
        "--max-subagents", type=int, default=2, help="helpers per work attempt, 0 disables (0–4)"
    )
    parser.add_argument("--time-limit-seconds", type=int, default=3600)
    parser.add_argument("--retain-command", help="optional authorized committer argv as a literal JSON array")
    parser.set_defaults(_handler=_init)


def executable(value):
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("select a nonempty executable name or absolute path")
    path = Path(value)
    if not path.is_absolute() and ("/" in value or "\\" in value):
        raise ValueError("use an executable name on PATH or an absolute path")
    resolved = shutil.which(value)
    if not resolved:
        raise ValueError("executable not found: " + value)
    reject_windows_batch(resolved)
    return str(Path(resolved).absolute())


def command(text):
    if not isinstance(text, str) or len(text) > 256 * 1024:
        raise ValueError("command must be a bounded literal JSON array")
    values = json.loads(text)
    if not isinstance(values, list) or not values:
        raise ValueError("command must be a nonempty literal JSON array, not shell text")
    values[0] = executable(values[0])
    return list(literal_command(values))


def tracked_files(project, git):
    env = original_git_environment()

    def read(*args):
        return subprocess.run(
            [git, "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(project), *args],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=15,
        ).stdout

    if Path(os.fsdecode(read("rev-parse", "--show-toplevel").strip())).resolve() != project:
        raise ValueError("project must be the repository root")
    read("rev-parse", "--verify", "HEAD")
    if read("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none").strip():
        raise ValueError("original repository is dirty; retain your existing work before init")
    raw = read("ls-files", "--stage", "-z")
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("tracked-file inventory exceeds setup limit")
    names = []
    for record in raw.split(b"\0"):
        if record:
            header, name = record.split(b"\t", 1)
            mode, _, stage = header.split()
            if mode not in (b"100644", b"100755") or stage != b"0":
                raise ValueError("setup requires regular tracked files without submodules or conflicts")
            names.append(name.decode("utf-8"))
    return names


def select(project, tracked, patterns, *, editable):
    selected = set()
    for pattern in patterns:
        if (
            not isinstance(pattern, str)
            or not pattern
            or len(pattern) > 4096
            or "\\" in pattern
            or ":" in pattern
            or "\0" in pattern
            or any(part in ("", ".", "..") or part.casefold() == ".git" for part in pattern.split("/"))
        ):
            raise ValueError("use bounded project-relative globs with forward slashes")
        matches = {name for name in tracked if fnmatch.fnmatchcase(name, pattern)}
        if not matches:
            raise ValueError("pattern did not match a tracked file: " + pattern)
        selected.update(matches)
    if not selected or len(selected) > (32 if editable else 512):
        raise ValueError("select 1–32 editable files and 1–512 frozen check files")
    for name in selected:
        _project_file(project, name, editable=editable)
    return sorted(selected)


def create_profile(args):
    max_subagents = subagent_limit(getattr(args, "max_subagents", 2))
    project = args.project.resolve(strict=True)
    output = args.output.absolute()
    if output.resolve().is_relative_to(project):
        raise ValueError("save the profile outside the original so the repository stays clean")
    if not isinstance(args.model, str) or not args.model.strip() or len(args.model) > 200:
        raise ValueError("select an explicit bounded model name")
    if not 1 <= args.max_attempts <= 10000 or not 1 <= args.time_limit_seconds <= 86400:
        raise ValueError("attempt and time limits must be positive and bounded (maximum one day)")
    git = executable(args.git)
    tracked = tracked_files(project, git)
    editable = select(project, tracked, args.editable, editable=True)
    frozen = select(project, tracked, args.check_file, editable=False)
    if set(editable) & set(frozen):
        raise ValueError("editable files and frozen acceptance files must not overlap")
    checks = []
    for index, text in enumerate(args.check_argv, 1):
        argv = command(text)
        if not any("{checks}" in value for value in argv[1:]):
            raise ValueError("each check command must execute the frozen files through {checks}")
        oracle = OutputOracle(
            f"acceptance {index}", tuple(argv), "", "", timeout_seconds=args.check_timeout, mode="exit-code"
        )
        checks.append(json.loads(oracle.payload))
    selected = {"adapter": args.llm, "model": args.model}
    if args.llm in ("claude-cli", "codex-cli"):
        selected["executable"] = executable(args.executable or args.llm.removesuffix("-cli"))
        if args.llm == "codex-cli":
            home = args.codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
            if not home.is_dir():
                raise ValueError("select an existing Codex home after completing the CLI login")
            selected["home"] = str(home.resolve())
    elif args.llm == "command-json":
        selected["command"] = command(args.model_command)
    else:
        validate_endpoint(args.endpoint)
        if not isinstance(args.api_key_env, str) or (
            args.api_key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.api_key_env)
        ):
            raise ValueError("api-key-env must be an environment variable name, never the credential")
        selected.update(
            endpoint=args.endpoint, api_key_env=args.api_key_env, response_format=args.response_format
        )
    retain = command(args.retain_command) if args.retain_command else builtin_command(git, project)
    return {
        "git": git,
        "llm": selected,
        "executor": {"adapter": "local-process"},
        "editable": editable,
        "checks": checks,
        "check_files": frozen,
        "max_attempts": args.max_attempts,
        "max_subagents": max_subagents,
        "time_limit_seconds": args.time_limit_seconds,
        "retain_command": retain,
    }


def _init(args):
    try:
        profile = create_profile(args)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(profile, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError, TypeError, RunError, subprocess.SubprocessError) as exc:
        print("Profile not created: " + str(exc))
        return 1
    print(
        "Created a concrete profile. Review selected files, check commands, model, "
        "and limits before plan/start."
    )
    print(
        "Execution uses trusted local processes; model credentials stay in existing "
        "login or environment settings."
    )
    print("Completion retains local commits on the isolated candidate branch using the selected committer.")
    return 0
