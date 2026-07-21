"""The deterministic, side-effect-free install plan — the ``--dry-run`` output.

An :class:`InstallPlan` is exactly what an install *would* do, computed by reading only: the directories
it would ensure, the artifact files it would stage (with their content hashes), and the settings
registrations it would merge. Building and rendering a plan never touches the filesystem — the "writes
nothing" contract for ``--dry-run`` is proven by a byte-for-byte snapshot test around
:func:`build_install_plan`.

The plan is the single source the transaction layer will later execute (Stage/Register), so a dry-run
shows precisely the mutation an apply performs — no drift between what is previewed and what is written.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from excubitor.installers.runtime import Artifact, Registration, RuntimeProfile, RuntimeTarget

__all__ = ["PlannedAction", "InstallPlan", "build_install_plan", "render_plan"]


@dataclass(frozen=True)
class PlannedAction:
    """One step of an install, tagged by ``kind`` (``ensure_dir`` / ``stage_file`` / ``register_hook``).

    A ``stage_file`` carries ``sha256``/``size`` so the plan and the receipt agree on exact bytes; a
    ``register_hook`` carries the full exact tuple. Rendered deterministically.
    """

    kind: str
    target_path: "str | None" = None
    basename: "str | None" = None
    sha256: "str | None" = None
    size: "int | None" = None
    matcher: "str | None" = None
    command: "str | None" = None
    timeout: "int | None" = None


@dataclass(frozen=True)
class InstallPlan:
    """A complete, deterministic description of one runtime+scope install. Writes nothing to build."""

    runtime: str
    scope: str
    settings_path: str
    hooks_dir: str
    detected: bool
    actions: "tuple[PlannedAction, ...]" = field(default=())

    @property
    def staged_files(self) -> "tuple[PlannedAction, ...]":
        return tuple(a for a in self.actions if a.kind == "stage_file")

    @property
    def registrations(self) -> "tuple[PlannedAction, ...]":
        return tuple(a for a in self.actions if a.kind == "register_hook")


def build_install_plan(profile: RuntimeProfile, target: RuntimeTarget) -> InstallPlan:
    """Compute the install plan for ``target`` by reading the artifact source and target paths only.

    Order is deterministic: ensure the control and hooks dirs, stage every artifact (sorted), then the
    registrations (in profile order). No filesystem mutation occurs — artifact bytes are read to hash
    them, existence is tested, nothing is created.
    """
    actions: "list[PlannedAction]" = []
    actions.append(PlannedAction(kind="ensure_dir", target_path=str(target.control_dir)))
    actions.append(PlannedAction(kind="ensure_dir", target_path=str(target.hooks_dir)))

    artifacts: "list[Artifact]" = profile.artifacts()
    hooks_dir = Path(target.hooks_dir)
    for artifact in artifacts:
        dest = hooks_dir / artifact.basename
        actions.append(
            PlannedAction(
                kind="stage_file",
                target_path=str(dest),
                basename=artifact.basename,
                sha256=artifact.sha256,
                size=len(artifact.content),
            )
        )

    registrations: "list[Registration]" = profile.registrations(target)
    for reg in registrations:
        actions.append(
            PlannedAction(
                kind="register_hook",
                basename=reg.script,
                matcher=reg.matcher,
                command=reg.command,
                timeout=reg.timeout,
                target_path=str(target.settings_path),
            )
        )

    return InstallPlan(
        runtime=target.runtime,
        scope=target.scope.value,
        settings_path=str(target.settings_path),
        hooks_dir=str(target.hooks_dir),
        detected=target.detected,
        actions=tuple(actions),
    )


def render_plan(plan: InstallPlan) -> str:
    """Render the plan as deterministic, human-readable text for ``--dry-run``."""
    lines = [
        f"excubitor install plan — runtime={plan.runtime} scope={plan.scope}",
        f"  runtime detected: {'yes' if plan.detected else 'no (control dir would be created)'}",
        f"  settings file:    {plan.settings_path}",
        f"  hooks directory:  {plan.hooks_dir}",
        "  planned actions (dry-run — nothing written):",
    ]
    for action in plan.actions:
        if action.kind == "ensure_dir":
            lines.append(f"    ensure-dir  {action.target_path}")
        elif action.kind == "stage_file":
            lines.append(
                f"    stage-file  {action.target_path}  "
                f"(sha256={action.sha256[:12]}… {action.size} bytes)"
            )
        elif action.kind == "register_hook":
            lines.append(
                f"    register    matcher={action.matcher!r:<32} timeout={action.timeout}  "
                f"command={action.command!r}"
            )
    return "\n".join(lines) + "\n"
