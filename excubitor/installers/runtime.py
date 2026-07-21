"""Runtime profiles and deterministic discovery of a runtime's install targets.

A :class:`RuntimeProfile` declares everything host-specific about installing Excubitor into one runtime:
where its settings file and hook directory live per scope, which artifact files an install stages, and
which pre-tool registrations it merges. Discovery resolves those templates into concrete
:class:`RuntimeTarget` paths for a given scope + home/project root, **without writing anything** — it
only reports what exists.

Only Claude Code is modeled. The artifact set is the four shipped guard scripts plus their telemetry
helper, sourced from the single canonical copy under the repo's ``hooks/`` directory (or an override).
Bundling those artifacts *inside a distributed native plugin* is a later campaign's job
(``docs/design/installable-multi-runtime-distribution.md`` assigns the marketplace plugin to Campaign
3); Campaign 2's installer transaction is proven here against isolated test homes using the real guard
scripts as the staged artifacts.

Nothing in this module mutates the filesystem. It resolves paths and reads artifact bytes so a plan can
be computed; the actual staging/registration is the transaction layer's job.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import excubitor

__all__ = [
    "Scope",
    "Artifact",
    "Registration",
    "RuntimeTarget",
    "RuntimeProfile",
    "CLAUDE_CODE",
    "profile_for",
    "discover",
]

#: The exact-tuple registration timeout (seconds) an install writes into settings.json.
CANON_TIMEOUT = 10


class Scope(str, Enum):
    """Install scope. ``USER`` is home-wide; ``PROJECT`` is checked-in per-repo. (Managed is later.)"""

    USER = "user"
    PROJECT = "project"


@dataclass(frozen=True)
class Artifact:
    """One file an install stages: its destination basename, byte content, and content hash.

    ``content`` is read from the canonical source at plan time so the hash pinned into the receipt is
    the real thing the transaction will write — ownership is hash-bound, never name-guessed.
    """

    basename: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class Registration:
    """One pre-tool hook registration an install merges into settings.json, as an exact tuple.

    The command invokes the staged guard script by absolute path under the target hooks dir. Ownership
    and idempotence are decided on the full ``(event, matcher-set, type, command, timeout)`` tuple,
    never a substring — mirroring the hardening in ``scripts/install_settings.py`` (R-07 / finding 3).
    """

    script: str
    matcher: str
    command: str
    timeout: int = CANON_TIMEOUT
    event: str = "PreToolUse"
    handler_type: str = "command"


@dataclass(frozen=True)
class RuntimeTarget:
    """The concrete, resolved install target for one runtime + scope, plus whether it already exists."""

    runtime: str
    scope: Scope
    control_dir: Path
    settings_path: Path
    hooks_dir: Path
    detected: bool


# The four shipped guard scripts (registered) plus the telemetry helper (staged, not registered).
_GUARD_REGISTRATIONS: "tuple[tuple[str, str], ...]" = (
    ("guard-default-branch.py", "Edit|Write|NotebookEdit"),
    ("guard-loop-vc.py", "Bash"),
    ("guard-one-unit.py", "*"),
    ("guard-self-integrity.py", "Bash|Edit|Write|NotebookEdit"),
)
_UNREGISTERED_ARTIFACTS: "tuple[str, ...]" = ("_denial_log.py",)


def _artifacts_source() -> Path:
    """Resolve the directory holding the canonical guard scripts.

    Order: the ``EXCUBITOR_ARTIFACTS_DIR`` override (tests / a future bundled location), then the repo's
    ``hooks/`` directory relative to the installed package (present in a source checkout). Raising here
    is correct: an install with no artifact source cannot proceed, and a silent empty stage would be a
    worse failure than a precise error. Distributing these artifacts inside a native plugin is Campaign
    3's job.
    """
    override = os.environ.get("EXCUBITOR_ARTIFACTS_DIR")
    if override:
        return Path(override)
    repo_hooks = Path(excubitor.__file__).resolve().parent.parent / "hooks"
    return repo_hooks


@dataclass(frozen=True)
class RuntimeProfile:
    """Everything host-specific about installing Excubitor into one runtime."""

    runtime_id: str
    control_dirname: str  # e.g. ".claude"
    user_settings_name: str  # e.g. "settings.json"
    project_settings_name: str  # e.g. "settings.local.json"
    hooks_subdir: str  # e.g. "hooks"

    def target(
        self, scope: Scope, home: "str | os.PathLike[str]", project_root: "str | os.PathLike[str] | None"
    ) -> RuntimeTarget:
        """Resolve concrete paths for ``scope``. USER hangs off ``home``; PROJECT off ``project_root``.

        Reads the filesystem only to test existence (``detected``); it never creates anything.
        """
        if scope is Scope.USER:
            base = Path(home).expanduser()
            settings_name = self.user_settings_name
        else:
            if project_root is None:
                raise ValueError("project scope requires a project_root")
            base = Path(project_root)
            settings_name = self.project_settings_name
        control_dir = base / self.control_dirname
        settings_path = control_dir / settings_name
        hooks_dir = control_dir / self.hooks_subdir
        detected = control_dir.exists() or settings_path.exists()
        return RuntimeTarget(
            runtime=self.runtime_id,
            scope=scope,
            control_dir=control_dir,
            settings_path=settings_path,
            hooks_dir=hooks_dir,
            detected=detected,
        )

    def artifacts(self) -> "list[Artifact]":
        """Read the artifact set (guard scripts + telemetry helper) from the canonical source.

        Returns them sorted by basename for a deterministic plan. Raises ``FileNotFoundError`` with a
        precise message if any artifact is missing, so a plan is never silently incomplete.
        """
        source = _artifacts_source()
        names = sorted({s for s, _ in _GUARD_REGISTRATIONS} | set(_UNREGISTERED_ARTIFACTS))
        out: "list[Artifact]" = []
        for name in names:
            path = source / name
            if not path.is_file():
                raise FileNotFoundError(f"install artifact not found: {path}")
            out.append(Artifact(basename=name, content=path.read_bytes()))
        return out

    def registrations(self, target: RuntimeTarget) -> "list[Registration]":
        """The exact-tuple pre-tool registrations for ``target`` (commands use the absolute hooks dir)."""
        out: "list[Registration]" = []
        for script, matcher in _GUARD_REGISTRATIONS:
            command = f"python3 {target.hooks_dir / script}"
            out.append(Registration(script=script, matcher=matcher, command=command))
        return out

    def control_paths(self, target: RuntimeTarget) -> "list[Path]":
        """Host registration/config paths whose mutation could disarm enforcement (self-integrity)."""
        return [target.settings_path, target.hooks_dir]


#: The only supported runtime profile today.
CLAUDE_CODE = RuntimeProfile(
    runtime_id="claude-code",
    control_dirname=".claude",
    user_settings_name="settings.json",
    project_settings_name="settings.local.json",
    hooks_subdir="hooks",
)

_PROFILES = {CLAUDE_CODE.runtime_id: CLAUDE_CODE}


def profile_for(runtime_id: str) -> RuntimeProfile:
    """Look up a runtime profile by id. Raises ``KeyError`` for an unsupported runtime — Excubitor never
    pretends to support Codex/Gemini/Copilot here; those are later campaigns."""
    try:
        return _PROFILES[runtime_id]
    except KeyError:
        raise KeyError(
            f"unsupported runtime {runtime_id!r}; supported: {sorted(_PROFILES)} "
            f"(other hosts are designed, not built)"
        ) from None


def discover(
    home: "str | os.PathLike[str]",
    project_root: "str | os.PathLike[str] | None" = None,
    scope: Scope = Scope.USER,
) -> "list[RuntimeTarget]":
    """Deterministically resolve targets for every supported runtime at ``scope``.

    Sorted by runtime id, reads only. ``detected`` reflects whether the runtime's control dir/settings
    already exist — an ``--runtime auto`` caller installs only into detected runtimes, while an explicit
    ``--runtime`` may create the control dir. Writes nothing.
    """
    targets: "list[RuntimeTarget]" = []
    for runtime_id in sorted(_PROFILES):
        profile = _PROFILES[runtime_id]
        if scope is Scope.PROJECT and project_root is None:
            continue
        targets.append(profile.target(scope, home, project_root))
    return targets
