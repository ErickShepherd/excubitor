"""Canonical, model-blind event and decision types for the Excubitor policy core.

These are the two value types every policy speaks: a normalized `PreToolEvent` in, a `Decision` out.
A runtime adapter builds a `PreToolEvent` from a native pre-execution hook payload (a host's own
pre-tool event, or a generic JSON envelope); the pure policy functions consume it and return a
`Decision`; the adapter renders that decision back into the host's native veto shape. See
`docs/design/model-agnostic-runtime.md` (§"Canonical event contract") for the per-host mappings —
the host names live in that design doc and in the adapters, never in this neutral module.

Two design rules are load-bearing and are enforced by tests:

1. **The passing outcome is named `pass`, never `allow`.** `pass` means *Excubitor has no objection;
   preserve the host's normal permission flow*. Several hosts treat an explicit native "allow" as a
   grant that SKIPS the user's permission prompt — so the core must never emit one. Adapters render
   `pass` as no-decision / empty success, and only `deny` as a structured veto.

2. **The core is model-blind and host-free.** No field carries a model identity, and policies must
   never branch on `runtime` (it is telemetry/diagnostics only). This module is pure data — stdlib
   types only, with no host coupling: it starts no child processes, reads no host configuration or
   global paths, and hard-codes no runtime name.

`PreToolEvent.from_dict`/generic-protocol parsing, the full malformed-input fixture matrix, and the
`allow`→`pass` migration of the legacy `runtime/spec_adapter.py` envelope are deliberately NOT here —
they belong to the generic-protocol unit (`excubitor.pre_tool.v1`, plan item C1.9). This module only
defines the types and their outward (`to_dict`) serialization.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "SCHEMA",
    "Capability",
    "LoopMode",
    "Outcome",
    "Decision",
    "PreToolEvent",
]

#: Explicit compatibility/version marker carried on every canonical event.
SCHEMA = "excubitor.pre_tool.v1"


class Capability(str, Enum):
    """The semantic action a native tool performs, used for classification instead of a tool name.

    A `native_tool` string is host-specific (`Bash`, `apply_patch`, `run_shell_command`, `write_file`,
    `Edit`, `Write`, `NotebookEdit`); the *capability* is what policies actually branch on. `OTHER`
    covers read-only and unrelated tools a policy has no opinion about.
    """

    SHELL_EXECUTE = "shell.execute"
    FILE_MUTATE = "file.mutate"
    NOTEBOOK_MUTATE = "notebook.mutate"
    OTHER = "other"


class LoopMode(str, Enum):
    """The neutral arming signal an adapter derives from its host's loop-guard environment.

    Maps the host's arming marker onto host-agnostic modes (a conservative marker → `CONSERVATIVE`,
    a verifiable-autonomy marker → `VERIFIABLE`); the adapter owns the host-specific env-var/marker
    names. The unarmed/"null" state is represented as Python ``None`` — the absence of a mode — not
    an enum member, matching the shipped guards' "inactive unless armed" posture.
    """

    CONSERVATIVE = "conservative"
    VERIFIABLE = "verifiable"


class Outcome(str, Enum):
    """The two-valued result of a policy decision. Never an explicit "allow" — see module docstring."""

    PASS = "pass"
    DENY = "deny"


@dataclass(frozen=True)
class Decision:
    """A policy's verdict on one event: `pass` (no objection) or `deny` (veto, with a reason).

    Immutable by construction. Build one with the :meth:`pass_` / :meth:`deny` constructors rather
    than the raw initializer so the vocabulary stays consistent across policies.
    """

    outcome: Outcome
    reason: str | None = None
    policy: str | None = None

    @classmethod
    def pass_(cls) -> "Decision":
        """Excubitor has no objection; the host keeps its normal permission flow.

        Spelled with a trailing underscore because ``pass`` is a Python keyword; the serialized wire
        value is the string ``"pass"`` (never ``"allow"``).
        """
        return cls(Outcome.PASS)

    @classmethod
    def deny(cls, reason: str, policy: str | None = None) -> "Decision":
        """Veto the call. ``reason`` is human-readable; ``policy`` names the deciding policy (e.g.
        ``"loop-vc"``, ``"default-branch"``) for telemetry and diagnostics."""
        return cls(Outcome.DENY, reason=reason, policy=policy)

    @property
    def is_pass(self) -> bool:
        return self.outcome is Outcome.PASS

    @property
    def is_deny(self) -> bool:
        return self.outcome is Outcome.DENY

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the canonical decision envelope.

        ``pass`` → ``{"decision": "pass", "reason": null}``; ``deny`` →
        ``{"decision": "deny", "reason": "...", "policy": "..."}``. The ``policy`` key is present only
        when set, so a pass decision has the minimal two-key shape.
        """
        out: dict[str, Any] = {"decision": self.outcome.value, "reason": self.reason}
        if self.policy is not None:
            out["policy"] = self.policy
        return out


@dataclass(frozen=True)
class PreToolEvent:
    """A normalized, host-agnostic pre-execution tool event — the sole input to every policy.

    An adapter constructs this from a native payload; policies read it and return a :class:`Decision`.
    Field meanings (see the design doc's contract table):

    * ``capability``    — the semantic action (:class:`Capability`); policies branch on this, not
      ``native_tool``.
    * ``runtime``       — adapter/telemetry identity only; **policies must not branch on it**.
    * ``native_tool``   — the host's own tool name, retained for diagnostics.
    * ``cwd``           — absolute working directory when known.
    * ``command``       — the shell command string for ``SHELL_EXECUTE``; otherwise ``None``.
    * ``targets``       — EVERY file the tool may mutate (a patch can touch several); never just the
      first path. Held as a tuple so the event stays immutable.
    * ``session_id``    — optional telemetry join key.
    * ``loop_mode``     — the neutral arming signal (:class:`LoopMode`), or ``None`` when unarmed.
    * ``control_paths`` — host registration/config paths whose mutation could disarm enforcement
      (e.g. a settings file or an active hook registration).
    * ``schema``        — the versioned compatibility marker; defaults to :data:`SCHEMA`.
    """

    capability: Capability
    runtime: str | None = None
    native_tool: str | None = None
    cwd: str | None = None
    command: str | None = None
    targets: tuple[str, ...] = ()
    session_id: str | None = None
    loop_mode: LoopMode | None = None
    control_paths: tuple[str, ...] = ()
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the canonical `excubitor.pre_tool.v1` event mapping (keys in contract order)."""
        return {
            "schema": self.schema,
            "runtime": self.runtime,
            "native_tool": self.native_tool,
            "capability": self.capability.value,
            "cwd": self.cwd,
            "command": self.command,
            "targets": list(self.targets),
            "session_id": self.session_id,
            "loop_mode": self.loop_mode.value if self.loop_mode is not None else None,
            "control_paths": list(self.control_paths),
        }
