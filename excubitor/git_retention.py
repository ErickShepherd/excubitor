"""Ordinary Git retention for an explicitly selected isolated Ralph candidate.

This helper is run by absolute file path, so it also works from an installed
wheel with Python isolated mode. It uses normal Git add/commit and respects
hooks/signing failures. It never retries through a different committer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


class RetentionError(ValueError):
    pass


def builtin_command(git, origin):
    return [
        str(Path(sys.executable).absolute()),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--git",
        str(git),
        "--origin",
        str(Path(origin).resolve()),
    ]


def is_builtin_retention(command, git, origin):
    return command == builtin_command(git, origin)


def _environment():
    # Repository redirects could stage a different project. Config, identity,
    # and signing environment settings remain ordinary Git policy.
    blocked = {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_SHALLOW_FILE",
    }
    if any(name.upper() in blocked for name in os.environ):
        raise RetentionError("remove inherited Git repository redirects before retaining work")
    return dict(os.environ)


def _reject_batch_git(git):
    # This file also runs directly under Python -I without an installed package.
    # Keep the small executable-format check here rather than importing the core.
    if os.name == "nt" and any(
        Path(path.rstrip(" .")).suffix.casefold() in (".cmd", ".bat")
        for path in (str(git), str(Path(git).resolve()))
    ):
        raise RetentionError(
            "Windows .cmd/.bat launchers cannot preserve literal arguments; select the direct native git.exe."
        )


def _git(git, project, *args, allow_failure=False):
    _reject_batch_git(git)
    result = subprocess.run(
        [str(git), "-C", str(project), *args],
        env=_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=45,
    )
    if len(result.stdout) + len(result.stderr) > 16 * 1024 * 1024:
        raise RetentionError("Git response exceeds the retention limit")
    if result.returncode and not allow_failure:
        # Preserve the real policy refusal for the host receipt; do not retry.
        raise RetentionError("Git refused retention: " + result.stderr.decode("utf-8", errors="replace"))
    return result


def prepare_git_policy(git, origin, candidate):
    """Copy effective commit settings, with hooks still rooted at the original.

    Clone does not copy local identity, hook policy, or signing configuration.
    Snapshot these before any model call, into host-owned candidate metadata.
    Structural clone settings and remote/branch references remain clone-owned.
    """
    origin, candidate = Path(origin).resolve(), Path(candidate).resolve()
    if origin == candidate or origin.is_relative_to(candidate) or candidate.is_relative_to(origin):
        raise RetentionError("commit policy requires a separate candidate")
    for project in (origin, candidate):
        top = _git(git, project, "rev-parse", "--show-toplevel").stdout
        if Path(os.fsdecode(top.strip())).resolve() != project:
            raise RetentionError("commit policy requires exact repository roots")
    raw = _git(git, origin, "config", "--list", "--null").stdout
    settings = {}
    prefixes = ("user.", "author.", "committer.", "commit.", "gpg.", "gpgsm.", "i18n.")
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        key, _, value = entry.partition(b"\n")
        name = key.decode("utf-8")
        if not name.lower().startswith(prefixes):
            continue
        settings.setdefault(name, []).append(value.decode("utf-8"))
    for name, values in settings.items():
        unset = _git(git, candidate, "config", "--local", "--unset-all", name, allow_failure=True)
        if unset.returncode not in (0, 5):  # 5 means the fresh clone had no such value
            raise RetentionError(
                "Git refused candidate policy setup: " + unset.stderr.decode(errors="replace")
            )
        for value in values:
            _git(git, candidate, "config", "--local", "--add", name, value)
    hooks = _git(git, origin, "rev-parse", "--path-format=absolute", "--git-path", "hooks").stdout
    hooks_path = Path(os.fsdecode(hooks.strip()))
    if not hooks_path.is_absolute():
        hooks_path = origin / hooks_path
    _git(git, candidate, "config", "--local", "core.hooksPath", str(hooks_path.resolve()))


def _json(path):
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise RetentionError("saved job data is redirected or oversized")
    return json.loads(path.read_bytes())


def _path(name):
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 4096
        or "\\" in name
        or ":" in name
        or "\0" in name
        or any(p in ("", ".", "..") or p.startswith(".") for p in name.split("/"))
    ):
        raise RetentionError("retention paths must be ordinary project-relative files")
    return name


def _regular_path(project, name):
    path = project
    for component in name.split("/"):
        path /= component
        if not path.exists() and not path.is_symlink():
            continue  # deletion is allowed; Git independently checks the changed paths
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RetentionError("candidate file traverses a link or reparse point")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
            raise RetentionError("candidate edit is not a bounded unshared regular file")


def _names(output):
    return {entry.decode("utf-8") for entry in output.split(b"\0") if entry}


def _changed_bytes(candidate, read):
    """Compare bytes independently of Git's stat cache and assume-unchanged flags."""
    actual, total = {}, 0
    for directory, folders, files in os.walk(candidate, followlinks=False):
        for name in folders + files:
            path = Path(directory) / name
            relative = path.relative_to(candidate).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise RetentionError("candidate contains redirected paths")
            if relative == ".git":
                continue
            if name.casefold() == ".git":
                raise RetentionError("nested Git metadata is outside retention scope")
            if name in files:
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise RetentionError("candidate contains shared or non-regular files")
                total += info.st_size
                if total > 16 * 1024 * 1024 or len(actual) >= 4096:
                    raise RetentionError("candidate exceeds the retention inventory limit")
                actual[relative] = path
    tracked, changed = set(), set()
    for entry in read("ls-tree", "-r", "-z", "--full-tree", "HEAD").split(b"\0"):
        if not entry:
            continue
        header, raw_name = entry.split(b"\t", 1)
        mode, kind, object_id = header.split()
        name = raw_name.decode("utf-8")
        if (
            mode not in (b"100644", b"100755")
            or kind != b"blob"
            or "\\" in name
            or ":" in name
            or any(p in ("", ".", "..") or p.casefold() == ".git" for p in name.split("/"))
        ):
            raise RetentionError("unsupported committed candidate path")
        tracked.add(name)
        path = actual.get(name)
        if path is None or path.read_bytes() != read("cat-file", "blob", object_id.decode()):
            changed.add(name)
        elif os.name != "nt" and bool(path.stat().st_mode & stat.S_IXUSR) != (mode == b"100755"):
            changed.add(name)
    return changed | (set(actual) - tracked)


def retain(git, origin, root, request):
    root, origin = Path(root).resolve(), Path(origin).resolve()
    job = _json(root / "job.json")
    record = _json(root / "run.json")
    if hashlib.sha256((root / "job.json").read_bytes()).hexdigest() != record["job_digest"]:
        raise RetentionError("saved agreement changed")
    if not isinstance(request, dict) or set(request) != {"candidate", "paths", "run_id"}:
        raise RetentionError("invalid retention request")
    candidate = Path(job["candidate"])
    metadata = Path(job["metadata"])
    if (
        not candidate.is_absolute()
        or candidate.is_symlink()
        or not candidate.is_dir()
        or candidate.resolve() != candidate
        or not metadata.is_absolute()
        or not metadata.is_dir()
        or metadata.is_symlink()
        or metadata.resolve() != metadata
        or candidate == origin
        or candidate.is_relative_to(origin)
        or origin.is_relative_to(candidate)
        or metadata.is_relative_to(candidate)
        or root.is_relative_to(candidate)
        or Path(job["origin"]).resolve() != origin
        or request["candidate"] != str(candidate)
        or request["run_id"] != record["id"]
        or Path(job["git"]).resolve() != Path(git).resolve()
    ):
        raise RetentionError("retention request does not match the isolated saved candidate")
    branch = job["branch"]
    if not isinstance(branch, str) or not branch.startswith("refs/heads/ralph/"):
        raise RetentionError("ordinary retention requires a dedicated ralph branch")
    paths = request["paths"]
    if not isinstance(paths, list) or not paths or len(paths) > 32:
        raise RetentionError("retention needs a bounded list of changed paths")
    allowed = {_path(name) for name in job["editable"]}
    names = {_path(name) for name in paths}
    if len(names) != len(paths) or not names <= allowed:
        raise RetentionError("retention request exceeds the admitted editable files")
    marker = candidate / ".git"
    if (
        marker.is_symlink()
        or not marker.is_file()
        or marker.stat().st_nlink != 1
        or marker.read_text(encoding="utf-8").strip().replace("\\", "/")
        != "gitdir: " + str(metadata).replace("\\", "/")
    ):
        raise RetentionError("candidate Git metadata binding changed")

    def read(*args):
        return _git(git, candidate, *args).stdout

    if Path(os.fsdecode(read("rev-parse", "--show-toplevel").strip())).resolve() != candidate:
        raise RetentionError("candidate is not the selected repository root")
    if Path(os.fsdecode(read("rev-parse", "--absolute-git-dir").strip())).resolve() != metadata:
        raise RetentionError("candidate metadata differs from the saved job")
    if read("symbolic-ref", "HEAD").decode().strip() != branch:
        raise RetentionError("candidate left the selected branch")
    default = _git(git, candidate, "symbolic-ref", "refs/remotes/origin/HEAD", allow_failure=True)
    if not default.returncode and default.stdout.decode().strip().removeprefix("refs/remotes/origin/") == (
        branch.removeprefix("refs/heads/")
    ):
        raise RetentionError("retention cannot commit on the origin default branch")
    before = read("rev-parse", "--verify", "HEAD^{commit}").strip()
    if read("diff", "--cached", "--name-only", "-z", "--no-renames", "HEAD", "--"):
        raise RetentionError("candidate already contains staged changes; inspect them before retrying")
    changed = _changed_bytes(candidate, read)
    if changed != names:
        raise RetentionError("actual candidate changes do not match the requested paths")
    if read("ls-files", "--others", "--ignored", "--exclude-standard", "-z"):
        raise RetentionError("ignored candidate files must be reviewed before retention")
    for name in names:
        _regular_path(candidate, name)
    # --literal-pathspecs is essential: '--' alone does not disable Git magic.
    read("--literal-pathspecs", "add", "--", *sorted(names))
    if _names(read("diff", "--cached", "--name-only", "-z", "--no-renames", "HEAD", "--")) != names:
        raise RetentionError("staged paths changed during retention; preserving the index for inspection")
    for name in names:
        path = candidate / name
        if path.exists() and read("cat-file", "blob", ":" + name) != path.read_bytes():
            raise RetentionError("Git filters changed candidate bytes; preserving staged work for inspection")
    staged_tree = read("write-tree").strip()
    if read("rev-parse", "HEAD").strip() != before or read("symbolic-ref", "HEAD").decode().strip() != branch:
        raise RetentionError("candidate branch changed before commit")
    read("commit", "-m", "Retain Ralph candidate progress")
    if (
        read("rev-parse", "HEAD^{tree}").strip() != staged_tree
        or read("rev-parse", "HEAD^").strip() != before
        or read("symbolic-ref", "HEAD").decode().strip() != branch
        or read("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none").strip()
        or read("ls-files", "--others", "--ignored", "--exclude-standard", "-z")
    ):
        raise RetentionError("commit did not preserve the admitted tree and clean isolated branch")
    return {"retained": True, "paths": sorted(names), "branch": branch}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--origin", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.git.is_absolute() or not args.git.is_file():
            raise RetentionError("Git must be an existing absolute executable")
        _reject_batch_git(args.git)
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise RetentionError("oversized retention request")
        result = retain(args.git, args.origin, Path.cwd(), json.loads(raw))
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print("Retention stopped: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
