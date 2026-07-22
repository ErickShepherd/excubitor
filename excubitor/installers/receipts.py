"""Exact, hash-bound installation receipts — the record that makes upgrade/uninstall precise.

A receipt records *exactly* what one installation owns: each staged file by absolute path **and**
SHA-256, and each settings registration by its full exact tuple (event, matcher-set, handler type,
command, timeout). Upgrade and uninstall consult the receipt and touch **only** what it records — never
a path that merely contains a guard's name, never a registration matched by substring. This is the
mechanism behind the invariant "rollback and uninstall may remove only receipt-owned bytes and
entries".

Ownership is deliberately strict:

* A file is receipt-owned **only when its current bytes still hash to what the receipt recorded** — so
  a user file that happens to share a path, or one the user edited after install, is never removed by
  us. Drift (path present, hash changed) is reported, not clobbered.
* A registration is owned only on an exact tuple match (the matcher compared as an alternative *set*,
  so ``A|B`` equals ``B|A`` but nothing looser).

Receipts live in a mutable state directory (``EXCUBITOR_STATE_HOME`` or a platform default), never in
committed policy — a receipt is install state, not reviewable policy.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import excubitor

__all__ = [
    "RECEIPT_SCHEMA",
    "OwnedFile",
    "OwnedRegistration",
    "Receipt",
    "matcher_key",
    "state_home_dir",
    "receipt_path",
]

#: The receipt file's schema/version marker.
RECEIPT_SCHEMA = "excubitor.receipt.v1"


def matcher_key(matcher: str) -> "tuple[str, ...]":
    """Semantic matcher identity: the sorted alternative set, or ``('*',)`` for the wildcard.

    ``"Write|Edit"`` and ``"Edit|Write"`` share a key; a cosmetic ordering difference is never a
    different registration.
    """
    m = matcher.strip() if isinstance(matcher, str) else ""
    return ("*",) if m == "*" else tuple(sorted(t for t in m.split("|") if t))


@dataclass(frozen=True)
class OwnedFile:
    """A staged file this installation owns, bound to exact bytes by SHA-256."""

    path: str
    sha256: str

    def to_dict(self) -> dict:
        return {"path": self.path, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, d: dict) -> "OwnedFile":
        return cls(path=str(d["path"]), sha256=str(d["sha256"]))


@dataclass(frozen=True)
class OwnedRegistration:
    """A settings registration this installation owns, as an exact tuple."""

    matcher: str
    command: str
    timeout: int
    handler_type: str = "command"
    event: str = "PreToolUse"

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "matcher": self.matcher,
            "type": self.handler_type,
            "command": self.command,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OwnedRegistration":
        return cls(
            event=str(d.get("event", "PreToolUse")),
            matcher=str(d["matcher"]),
            handler_type=str(d.get("type", "command")),
            command=str(d["command"]),
            timeout=int(d["timeout"]),
        )

    def matches(self, event: str, matcher: str, command: str, timeout: object, handler_type: str) -> bool:
        """Exact-tuple ownership: same event/type/command/timeout and the same matcher *set*."""
        return (
            self.event == event
            and self.handler_type == handler_type
            and self.command == command
            and self.timeout == timeout
            and matcher_key(self.matcher) == matcher_key(matcher)
        )


@dataclass(frozen=True)
class Receipt:
    """The complete ownership record for one runtime+scope installation."""

    runtime: str
    scope: str
    settings_path: str
    excubitor_version: str
    installed_at: str
    files: "tuple[OwnedFile, ...]" = field(default=())
    registrations: "tuple[OwnedRegistration, ...]" = field(default=())
    #: Whether the settings file existed before this install. If False, an uninstall that empties the
    #: file removes it — restoring "absent" so the round trip is byte-for-byte.
    settings_preexisted: bool = True
    schema: str = RECEIPT_SCHEMA

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "runtime": self.runtime,
            "scope": self.scope,
            "settings_path": self.settings_path,
            "excubitor_version": self.excubitor_version,
            "installed_at": self.installed_at,
            "settings_preexisted": self.settings_preexisted,
            "files": [f.to_dict() for f in self.files],
            "registrations": [r.to_dict() for r in self.registrations],
        }

    def to_json(self) -> str:
        """Deterministic JSON (sorted keys, trailing newline) so a receipt file is stable."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, d: dict) -> "Receipt":
        if not isinstance(d, dict):
            raise ValueError("receipt root is not an object")
        if d.get("schema") != RECEIPT_SCHEMA:
            raise ValueError(f"unrecognized receipt schema {d.get('schema')!r}")
        required = {
            "schema", "runtime", "scope", "settings_path", "excubitor_version", "installed_at",
            "settings_preexisted", "files", "registrations",
        }
        if set(d) != required:
            raise ValueError("receipt has an invalid field set")
        for name in ("runtime", "scope", "settings_path", "excubitor_version", "installed_at"):
            if not isinstance(d[name], str):
                raise ValueError(f"receipt field {name} is not a string")
        if not isinstance(d["settings_preexisted"], bool):
            raise ValueError("receipt field settings_preexisted is not a boolean")
        if not isinstance(d["files"], list) or not isinstance(d["registrations"], list):
            raise ValueError("receipt files and registrations must be lists")
        return cls(
            runtime=d["runtime"],
            scope=d["scope"],
            settings_path=d["settings_path"],
            excubitor_version=d["excubitor_version"],
            installed_at=d["installed_at"],
            files=tuple(OwnedFile.from_dict(f) for f in d["files"]),
            registrations=tuple(OwnedRegistration.from_dict(r) for r in d["registrations"]),
            settings_preexisted=d["settings_preexisted"],
            schema=d["schema"],
        )

    @classmethod
    def from_json(cls, text: str) -> "Receipt":
        return cls.from_dict(json.loads(text))

    def owns_file_bytes(self, path: str, current_sha256: str) -> bool:
        """True iff the receipt records ``path`` with EXACTLY ``current_sha256`` — the hash-bound test.

        Uninstall removes a file only when this holds: the path we recorded still carries the bytes we
        wrote. A path match with a different hash means the file drifted and is not ours to remove.
        """
        return any(f.path == path and f.sha256 == current_sha256 for f in self.files)

    def records_path(self, path: str) -> bool:
        """True iff the receipt records ``path`` at all (regardless of current bytes) — used to
        distinguish 'not ours' from 'ours but drifted'."""
        return any(f.path == path for f in self.files)

    def owns_registration(
        self, event: str, matcher: str, command: str, timeout: object, handler_type: str = "command"
    ) -> bool:
        """True iff some recorded registration matches this exact tuple (matcher as a set)."""
        return any(r.matches(event, matcher, command, timeout, handler_type) for r in self.registrations)

    @staticmethod
    def hash_file(path: "str | os.PathLike[str]") -> str:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state_home_dir(state_home: "str | None" = None, environ: "dict[str, str] | None" = None) -> Path:
    """Resolve the mutable state directory: explicit arg > ``EXCUBITOR_STATE_HOME`` > platform default.

    Platform default: ``$XDG_STATE_HOME/excubitor`` or ``~/.local/state/excubitor`` (Linux/Unix),
    ``%LOCALAPPDATA%\\excubitor`` (Windows), ``~/Library/Application Support/excubitor`` (macOS).
    """
    environ = os.environ if environ is None else environ
    if state_home:
        return Path(state_home)
    env_home = environ.get("EXCUBITOR_STATE_HOME")
    if env_home:
        return Path(env_home)
    if os.name == "nt":
        base = environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "excubitor"
    if sys_is_darwin():
        return Path.home() / "Library" / "Application Support" / "excubitor"
    xdg = environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "excubitor"


def sys_is_darwin() -> bool:
    import sys

    return sys.platform == "darwin"


def receipt_path(runtime: str, scope: str, state_home: "str | None" = None,
                 environ: "dict[str, str] | None" = None) -> Path:
    """The receipt file path for one runtime+scope under the resolved state dir."""
    return state_home_dir(state_home, environ) / "receipts" / f"{runtime}-{scope}.json"


def current_version() -> str:
    return excubitor.__version__
