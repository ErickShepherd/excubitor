"""Fail-closed filesystem primitives for installer-controlled paths.

Installer paths are security-sensitive even though the installer is user-invoked: following a symlink
or reusing a predictable temporary name could redirect a write outside the selected target.  These
helpers enforce lexical containment, reject symlinks in every existing path component, create unique
same-directory temporary files exclusively, and fsync both file data and directory-entry changes.
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

__all__ = [
    "PathSafetyError",
    "absolute_path",
    "ensure_contained_no_symlinks",
    "secure_mkdir",
    "atomic_write_bytes",
    "durable_unlink",
]


class PathSafetyError(ValueError):
    """A selected installer path is unsafe to read from or mutate."""


def absolute_path(path: "str | os.PathLike[str]") -> Path:
    """Return an absolute lexical path without resolving symlinks."""
    return Path(os.path.abspath(os.fspath(path)))


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def _existing_components(path: Path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            os.lstat(current)
        except FileNotFoundError:
            continue
        yield current


def ensure_contained_no_symlinks(
    path: "str | os.PathLike[str]",
    root: "str | os.PathLike[str]",
    *,
    label: str = "installer path",
) -> Path:
    """Validate lexical containment and reject every existing symlink in the path chain."""
    candidate = absolute_path(path)
    boundary = absolute_path(root)
    if not _is_within(candidate, boundary):
        raise PathSafetyError(f"{label} escapes selected root {boundary}: {candidate}")
    for component in _existing_components(candidate):
        mode = os.lstat(component).st_mode
        if stat.S_ISLNK(mode):
            raise PathSafetyError(f"{label} contains symlink component: {component}")
    return candidate


def secure_mkdir(path: Path, root: Path, mode: int) -> None:
    """Create a directory chain and verify that no component was redirected through a symlink."""
    path = ensure_contained_no_symlinks(path, root, label="directory")
    boundary = absolute_path(root)
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        if current == current.parent:
            break
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=mode)
    ensure_contained_no_symlinks(path, boundary, label="directory")


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":  # Windows has no portable directory fsync.
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes, mode: int, root: Path) -> None:
    """Atomically write via a unique exclusive temp and durably commit the directory entry."""
    path = ensure_contained_no_symlinks(path, root, label="write target")
    secure_mkdir(path.parent, root, 0o700 if mode == 0o600 else 0o755)
    ensure_contained_no_symlinks(path, root, label="write target")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        os.chmod(tmp, mode)
        with os.fdopen(fd, "wb", closefd=True) as fh:
            fd = -1
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        ensure_contained_no_symlinks(path, root, label="write target")
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def durable_unlink(path: Path, root: Path, *, missing_ok: bool = True) -> None:
    """Unlink a non-symlink target and fsync its parent directory."""
    path = ensure_contained_no_symlinks(path, root, label="unlink target")
    try:
        path.unlink()
    except FileNotFoundError:
        if not missing_ok:
            raise
        return
    _fsync_dir(path.parent)
