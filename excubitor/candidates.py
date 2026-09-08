"""Read actual committed candidates without executing repository code or filters.

The host supplies protected Git metadata and a dedicated branch. Submodules,
symlinks, reparse points, sparse checkouts, and extra/ignored files are rejected in
this first backend. Commit creation remains the host's authorized broker's job.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from excubitor.host_processes import process_tree
from excubitor.runs import Candidate, RunError


class GitCandidateReader:
    def __init__(
        self, git: Path, project: Path, metadata: Path, branch: str, base_branch: str = "refs/heads/main"
    ):
        if not all(path.is_absolute() for path in (git, project, metadata)):
            raise ValueError("Git executable, project, and protected metadata paths must be absolute")
        if not git.is_file() or not project.is_dir() or not metadata.is_dir():
            raise ValueError("Git candidate inputs must exist")
        if (
            not branch.startswith("refs/heads/")
            or not base_branch.startswith("refs/heads/")
            or branch == base_branch
        ):
            raise ValueError("an explicitly selected isolated branch is required")
        self.git, self.project, self.metadata, self.branch = (
            git,
            project.resolve(),
            metadata.resolve(),
            branch,
        )
        if self.metadata.is_relative_to(self.project):
            raise RunError("candidate metadata must be outside worker-writable project")
        self.identity = (self.project.stat().st_dev, self.project.stat().st_ino)
        self.base_branch = base_branch
        self.base_commit = self._git("rev-parse", "--verify", base_branch + "^{commit}").decode().strip()

    def _inventory(self):
        actual, entries = set(), 0
        for root, dirs, files in os.walk(self.project, followlinks=False):
            for name in dirs + files:
                path = Path(root) / name
                relative = path.relative_to(self.project).as_posix()
                info = path.lstat()
                entries += 1
                if entries > 8192:
                    raise RunError("candidate contains too many filesystem entries")
                if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise RunError("candidate tree traverses a link or reparse point")
                if relative == ".git":
                    continue
                if name in files:
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise RunError("candidate contains a shared or non-regular file")
                    actual.add(relative)
        return actual

    def _git(self, *args):
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_NO_REPLACE_OBJECTS="1",
            GIT_OPTIONAL_LOCKS="0",
        )
        argv = (
            str(self.git),
            "--no-replace-objects",
            "--git-dir=" + str(self.metadata),
            "--work-tree=" + str(self.project),
            *args,
        )
        result = process_tree().run(
            argv,
            self.metadata,
            env=env,
            timeout=15,
            output_limit=16 * 1024 * 1024,
            terminate_on_root_exit=True,
        )
        execution = result.execution
        failed = (
            execution.exit_code != 0
            or execution.timed_out
            or execution.output_limited
            or result.cancelled
            or not result.drained
        )
        result = execution
        if failed:
            raise RunError("trusted Git candidate inspection failed")
        if len(result.stdout) > 16 * 1024 * 1024:
            raise RunError("candidate exceeds inspection size limit")
        return result.stdout

    def collect(self) -> Candidate:
        if (self.project.stat().st_dev, self.project.stat().st_ino) != self.identity:
            raise RunError("candidate project identity changed")
        actual = self._inventory()
        marker = self.project / ".git"
        if marker.is_symlink() or not marker.is_file():
            raise RunError("candidate Git marker is missing or redirected")
        expected = "gitdir: " + str(self.metadata).replace("\\", "/")
        if marker.read_text(encoding="utf-8").strip().replace("\\", "/") != expected:
            raise RunError("candidate Git marker no longer matches protected metadata")
        if self._git("symbolic-ref", "HEAD").decode().strip() != self.branch:
            raise RunError("candidate left the selected isolated branch")
        commit = self._git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        if (
            self._git("rev-parse", "--verify", self.base_branch + "^{commit}").decode().strip()
            != self.base_commit
        ):
            raise RunError("the protected base branch changed")
        self._git("merge-base", "--is-ancestor", self.base_commit, commit)
        tree = self._git("ls-tree", "-r", "-z", "--full-tree", commit)
        tracked, fingerprint, size = set(), [], 0
        index_expected = []
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            header, raw_name = entry.split(b"\t", 1)
            mode, kind, object_id = header.split()
            name = raw_name.decode("utf-8")
            parts = name.split("/")
            if (
                mode not in (b"100644", b"100755")
                or kind != b"blob"
                or any(part in ("", ".", "..") or ":" in part or "\\" in part for part in parts)
            ):
                raise RunError("unsupported candidate entry")
            path = self.project.joinpath(*parts)
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise RunError("candidate contains a link or non-regular file")
            if os.name != "nt" and bool(info.st_mode & stat.S_IXUSR) != (mode == b"100755"):
                raise RunError("candidate executable mode differs from its commit")
            size += info.st_size
            if size > 16 * 1024 * 1024 or len(tracked) >= 4096:
                raise RunError("candidate exceeds inspection budget")
            content = path.read_bytes()
            if content != self._git("cat-file", "blob", object_id.decode()):
                raise RunError("candidate working bytes differ from its commit")
            tracked.add(name)
            fingerprint.append((name, mode.decode(), hashlib.sha256(content).hexdigest()))
            index_expected.append(mode + b" " + object_id + b" 0\t" + raw_name + b"\0")
        if not tracked or self._git("ls-files", "--stage", "-z") != b"".join(index_expected):
            raise RunError("empty candidate or index differs from committed tree")
        if actual != tracked:
            raise RunError("untracked, ignored, or missing candidate files remain")
        if self._git("rev-parse", "--verify", "HEAD^{commit}").decode().strip() != commit:
            raise RunError("candidate commit changed during inspection")
        digest = hashlib.sha256(json.dumps(fingerprint, ensure_ascii=True).encode()).hexdigest()
        return Candidate(digest, commit, True, True)
