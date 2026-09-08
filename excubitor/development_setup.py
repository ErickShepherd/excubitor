"""Create-only profile examples and read-only checks before paid planning."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

from excubitor.acceptance import OutputOracle
from excubitor.command_model import literal_command
from excubitor.development_adapters import baseline_for, normalize, preflight
from excubitor.development_helpers import subagent_limit
from excubitor.development_runtime import LOCAL_BASELINE
from excubitor.literal_command import BatchCommandError
from excubitor.original_git import original_git_environment
from excubitor.runs import RunError

PROFILE_FIELDS = {
    "git",
    "llm",
    "executor",
    "editable",
    "checks",
    "check_files",
    "max_attempts",
    "max_subagents",
    "time_limit_seconds",
    "retain_command",
}
MODELS = ("claude-cli", "codex-cli", "command-json", "chat-completions")
EXECUTORS = ("local-process", "codex-windows", "windows-process", "posix-process")


def register(actions):
    template = actions.add_parser("profile-template", help="create a profile example without overwriting")
    template.add_argument("--output", type=Path, required=True)
    template.add_argument("--llm", choices=MODELS, required=True)
    template.add_argument("--executor", choices=EXECUTORS, required=True)
    template.add_argument("--model", default="REPLACE_MODEL")
    template.set_defaults(_handler=_template)
    doctor = actions.add_parser("doctor", help="check profile and original without model calls or writes")
    doctor.add_argument("--profile", type=Path, required=True)
    doctor.add_argument("--project", type=Path, required=True)
    doctor.add_argument("--root", type=Path, required=True, help="the proposed fresh planning directory")
    doctor.add_argument("--json", action="store_true", help="emit a machine-readable report")
    doctor.set_defaults(_handler=_doctor)


def example_profile(llm, executor, model):
    prefix = "C:/REPLACE/" if os.name == "nt" else "/REPLACE/"
    suffix = ".exe" if os.name == "nt" else ""
    selected = {"adapter": llm, "model": model}
    if llm in ("claude-cli", "codex-cli"):
        selected["executable"] = prefix + ("claude" if llm == "claude-cli" else "codex") + suffix
        if llm == "codex-cli":
            selected["home"] = prefix + "existing-codex-home"
    elif llm == "command-json":
        selected["command"] = [prefix + "python" + suffix, "-I", "-B", prefix + "model_bridge.py"]
    else:
        selected.update(
            endpoint="https://REPLACE.example/v1/chat/completions",
            api_key_env="RALPH_MODEL_API_KEY",
            response_format="json_schema",
        )
    execution = {"adapter": executor}
    if executor == "codex-windows":
        execution.update(executable=prefix + "codex" + suffix, home=prefix + "existing-codex-home")
    return {
        "git": prefix + "git" + suffix,
        "llm": selected,
        "executor": execution,
        "editable": ["main.py"],
        "checks": [
            {
                "name": "agreed behavior",
                "argv": [
                    prefix + "python" + suffix,
                    "-I",
                    "-B",
                    "{checks}/tests/acceptance.py",
                    "{candidate}",
                ],
                "stdin": "",
                "stdout": "ok\n",
                "stderr": "",
                "exit_code": 0,
                "timeout_seconds": 30,
            }
        ],
        "check_files": ["tests/acceptance.py"],
        "max_attempts": 8,
        "max_subagents": 2,
        "time_limit_seconds": 1800,
        "retain_command": [prefix + "authorized-committer" + suffix],
    }


def _template(args):
    try:
        # Exclusive creation also rejects existing symlinks. Never create parents.
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(example_profile(args.llm, args.executor, args.model), stream, indent=2)
            stream.write("\n")
    except OSError:
        print("Profile not created: use a new file in an existing writable directory.")
        return 1
    print(
        "Created profile example. Replace every REPLACE value and review files, checks, limits and committer."
    )
    if args.executor in ("windows-process", "posix-process", "local-process"):
        print("Selected trusted-local-v1: local process management; no filesystem or network sandbox.")
    return 0


def _project_file(project, name, *, editable):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\0" in name:
        raise ValueError("use a project-relative file name with forward slashes")
    parts = name.split("/")
    if any(p in ("", ".", "..") or p.casefold() == ".git" for p in parts):
        raise ValueError("file names cannot escape the project or use Git metadata")
    if editable and any(p.startswith(".") for p in parts):
        raise ValueError("editable files cannot use hidden path components")
    path = project
    for part in parts:
        path /= part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("file paths cannot use symlinks or Windows reparse points")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > (65536 if editable else 1024 * 1024):
        raise ValueError("select an existing regular file within the size limit")
    if editable and info.st_nlink != 1:
        raise ValueError("editable files cannot be hard-linked")
    path.read_text(encoding="utf-8")


def _placeholders(value):
    if isinstance(value, str):
        return "REPLACE" in value
    if isinstance(value, dict):
        return any(_placeholders(item) for item in value.values())
    if isinstance(value, list):
        return any(_placeholders(item) for item in value)
    return False


def inspect(profile, project, root):
    """Check local facts only; do not construct a runtime or execute checks/clients."""
    errors, warnings = (
        [],
        [
            "No model, acceptance check or committer was run. Login, model availability, endpoint support, "
            "executor permissions and commit authorization still require runtime evidence.",
        ],
    )
    report = {"ok": False, "baseline": None, "errors": errors, "warnings": warnings}
    if _placeholders(profile):
        errors.append("Replace all REPLACE placeholders in the profile.")
    if isinstance(profile, dict):
        try:
            subagent_limit(profile.get("max_subagents", 0))
        except RunError as error:
            errors.append(str(error))
            return report
    try:
        profile = normalize(profile)
    except BatchCommandError as error:
        errors.append(str(error))
        return report
    except (RunError, ValueError, TypeError, OSError):
        errors.append(
            "Invalid model/executor settings: check descriptor fields, explicit model, "
            "existing executable/home paths, endpoint and literal command arguments."
        )
        return report
    report["baseline"] = baseline_for(profile)
    try:
        preflight(profile)
    except RunError as error:
        errors.append(str(error))
    if report["baseline"] == LOCAL_BASELINE:
        warnings.append(
            "trusted-local-v1 manages process lifetimes, with no filesystem or network sandbox. "
            "It must be explicitly selected and is never a fallback after a native denial."
        )
    if set(profile) not in (PROFILE_FIELDS, PROFILE_FIELDS - {"max_subagents"}):
        errors.append("Use the complete reusable profile fields; job/plan fields do not belong in a profile.")
        return report
    limit = profile.get("max_subagents", 0)
    warnings.append(
        f"Frozen helper limit: {limit}. Each work attempt uses at most "
        f"{limit + 2 if limit else 1} model calls; helpers only propose, and one parent writes. "
        "All calls share the original deadline; verification and review remain separate."
    )
    llm = profile["llm"]
    if llm["adapter"] == "chat-completions" and llm["api_key_env"]:
        name = llm["api_key_env"]
        if "=" in name or "\0" in name or not os.environ.get(name):
            errors.append("The selected API-key environment variable is invalid or empty in this process.")
    for field, maximum in (("max_attempts", 10000), ("time_limit_seconds", 86400)):
        if type(profile[field]) is not int or not 1 <= profile[field] <= maximum:
            errors.append(f"{field} must be an integer from 1 to {maximum}.")
    for label, command in (("git", [profile["git"]]), ("retain_command", profile["retain_command"])):
        try:
            literal_command(command)
        except BatchCommandError as error:
            errors.append(label + " must use literal argv. " + str(error))
        except (RunError, ValueError, TypeError, OSError):
            errors.append(label + " must select an existing absolute executable and literal arguments.")
    project, root = Path(project), Path(root)
    if not project.is_absolute() or not project.is_dir():
        errors.append("Project must be an existing absolute repository directory.")
        return report
    project = project.resolve()
    if (
        not root.is_absolute()
        or root.exists()
        or root.is_symlink()
        or root.resolve().is_relative_to(project)
        or project.is_relative_to(root.resolve())
    ):
        errors.append("Planning root must be a fresh absolute directory separate from the original.")
    for field, maximum in (("editable", 32), ("check_files", None)):
        names = profile[field]
        if (
            not isinstance(names, list)
            or not names
            or any(not isinstance(n, str) for n in names)
            or len(set(names)) != len(names)
            or (maximum and len(names) > maximum)
        ):
            errors.append(
                field + " must list distinct existing files" + (" (at most 32)." if maximum else ".")
            )
            continue
        for index, name in enumerate(names):
            try:
                _project_file(project, name, editable=field == "editable")
            except (ValueError, OSError):
                errors.append(
                    f"{field}[{index}] is missing, redirected, non-UTF-8, oversized or an invalid path."
                )
    checks = profile["checks"]
    if not isinstance(checks, list) or not checks:
        errors.append("Select at least one frozen acceptance check.")
    else:
        seen = set()
        for index, check in enumerate(checks):
            try:
                if not isinstance(check, dict) or not isinstance(check.get("argv"), list):
                    raise ValueError("invalid check")
                argv = tuple(
                    a.replace("{candidate}", str(root / "candidate")).replace(
                        "{checks}", str(root / "checks")
                    )
                    for a in check["argv"]
                )
                oracle = OutputOracle(**{**check, "argv": argv})
                literal_command(oracle.argv)
                if oracle.name in seen or (oracle.stdin and report["baseline"] != LOCAL_BASELINE):
                    raise ValueError("duplicate check or unsupported stdin")
                seen.add(oracle.name)
            except BatchCommandError as error:
                errors.append(f"checks[{index}]: " + str(error))
            except (RunError, ValueError, TypeError, AttributeError, OSError):
                errors.append(
                    f"checks[{index}] has invalid fields, executable, expected output, timeout, "
                    "duplicate name or stdin unsupported by the selected executor."
                )
    # Preserve ordinary cleanliness semantics, while disabling index refresh
    # writes and inherited repository redirects.
    if not any(e.startswith("git must") for e in errors):
        env = original_git_environment()
        try:

            def git(*args):
                return subprocess.run(
                    [
                        profile["git"],
                        "--no-optional-locks",
                        "-c",
                        "core.fsmonitor=false",
                        "-C",
                        str(project),
                        *args,
                    ],
                    env=env,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=15,
                    check=True,
                ).stdout.strip()

            top = Path(os.fsdecode(git("rev-parse", "--show-toplevel"))).resolve()
            if top != project:
                errors.append("Project must name the repository root, not a subdirectory.")
            git("rev-parse", "--verify", "HEAD")
            if git("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"):
                errors.append(
                    "Original repository is dirty; planning requires a clean original. "
                    "Preserve or deliberately retain your work before planning."
                )
        except (OSError, ValueError, subprocess.SubprocessError):
            errors.append("Could not read the original Git repository and its existing revision.")
    report["ok"] = not errors
    return report


def _doctor(args):
    try:
        if args.profile.stat().st_size > 1024 * 1024:
            raise ValueError("oversized")
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        report = inspect(profile, args.project, args.root)
    except (OSError, ValueError, TypeError, RunError):
        report = {
            "ok": False,
            "baseline": None,
            "errors": ["Cannot read a valid profile (limit: one MiB)."],
            "warnings": [],
        }
    if args.json:
        print(json.dumps(report))
    else:
        print("Local preflight passed." if report["ok"] else "Local preflight needs fixes.")
        if report["baseline"]:
            print("Execution baseline: " + report["baseline"])
        for error in report["errors"]:
            print("Fix: " + error)
        for warning in report["warnings"]:
            print("Note: " + warning)
    return 0 if report["ok"] else 1
