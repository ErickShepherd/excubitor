"""Full nested validation of the configuration an install reads — stop before any mutation.

Two surfaces are validated, both *before* a single byte is written:

* **The host settings file** (``hooks.PreToolUse`` in a Claude Code settings.json). Every entry, matcher,
  handler, and field is type-checked to arbitrary nesting depth. A malformed structure yields a precise
  diagnostic naming the offending index/field and **no write** — never a crash that corrupts a user's
  config. This generalizes the R-07 hardening in ``scripts/install_settings.py``.
* **The neutral policy** (``.excubitor/policy.toml``). Its schema version is checked: an unknown/future
  version stops the install with migration guidance rather than guessing at a format we do not
  understand. Nested value types are checked too.

Validation is pure: it reads the already-parsed structures and returns a :class:`ValidationResult`. It
does no I/O and mutates nothing — the caller decides not to write when a result is invalid.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "SUPPORTED_POLICY_VERSIONS",
    "ValidationResult",
    "validate_settings",
    "validate_policy",
]

#: Policy schema versions this build understands. An absent version means v1 (the original format);
#: a present unknown/future version stops the install.
SUPPORTED_POLICY_VERSIONS = frozenset({1})


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of validating one configuration surface. ``ok`` iff ``problems`` is empty."""

    problems: "tuple[str, ...]" = field(default=())

    @property
    def ok(self) -> bool:
        return not self.problems

    @classmethod
    def clean(cls) -> "ValidationResult":
        return cls(())


def validate_settings(data: object) -> ValidationResult:
    """Deep-validate a parsed settings.json for safe hook registration.

    Checks the whole ``hooks.PreToolUse`` structure: the top-level object shape, the hooks container,
    every entry's ``matcher`` and ``hooks`` list, and every handler's ``type``/``command``/``timeout``
    field types. Returns every problem found (each naming a precise location), so an install can refuse
    the whole write on any one of them.
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        return ValidationResult((f"settings root is not an object (got {type(data).__name__})",))

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return ValidationResult((f"hooks is not an object (got {type(hooks).__name__})",))

    pre = hooks.get("PreToolUse", [])
    if not isinstance(pre, list):
        return ValidationResult((f"hooks.PreToolUse is not a list (got {type(pre).__name__})",))

    for i, entry in enumerate(pre):
        loc = f"hooks.PreToolUse[{i}]"
        if not isinstance(entry, dict):
            problems.append(f"{loc} is not an object (got {type(entry).__name__})")
            continue
        if "matcher" in entry and not isinstance(entry["matcher"], str):
            problems.append(f"{loc}.matcher is not a string (got {type(entry['matcher']).__name__})")
        entry_hooks = entry.get("hooks", [])
        if not isinstance(entry_hooks, list):
            problems.append(f"{loc}.hooks is not a list (got {type(entry_hooks).__name__})")
            continue
        for j, handler in enumerate(entry_hooks):
            hloc = f"{loc}.hooks[{j}]"
            if not isinstance(handler, dict):
                problems.append(f"{hloc} is not an object (got {type(handler).__name__})")
                continue
            if "type" in handler and not isinstance(handler["type"], str):
                problems.append(f"{hloc}.type is not a string")
            if "command" in handler and not isinstance(handler["command"], str):
                problems.append(f"{hloc}.command is not a string")
            if "timeout" in handler and not isinstance(handler["timeout"], (int, float)):
                problems.append(f"{hloc}.timeout is not a number")
    return ValidationResult(tuple(problems))


def validate_policy(policy: object) -> ValidationResult:
    """Validate a parsed ``.excubitor/policy.toml``: known version, well-typed nested structure.

    An unknown/future ``version`` stops with migration guidance. Nested tables and their value types
    are checked so a malformed structure never reaches the mutation path.
    """
    problems: list[str] = []
    if not isinstance(policy, dict):
        return ValidationResult((f"policy is not a table (got {type(policy).__name__})",))

    version = policy.get("version", 1)
    if not isinstance(version, int) or version not in SUPPORTED_POLICY_VERSIONS:
        supported = sorted(SUPPORTED_POLICY_VERSIONS)
        return ValidationResult(
            (
                f"policy version {version!r} is not supported (this build understands {supported}); "
                f"upgrade Excubitor or migrate the policy file — refusing to guess at an unknown format",
            )
        )

    db = policy.get("default_branch")
    if db is not None:
        if not isinstance(db, dict):
            problems.append(f"default_branch is not a table (got {type(db).__name__})")
        elif "opt_out_marker" in db and not isinstance(db["opt_out_marker"], str):
            problems.append("default_branch.opt_out_marker is not a string")

    ou = policy.get("one_unit")
    if ou is not None:
        if not isinstance(ou, dict):
            problems.append(f"one_unit is not a table (got {type(ou).__name__})")
        elif "enabled" in ou and not isinstance(ou["enabled"], bool):
            problems.append("one_unit.enabled is not a boolean")

    si = policy.get("self_integrity")
    if si is not None:
        if not isinstance(si, dict):
            problems.append(f"self_integrity is not a table (got {type(si).__name__})")
        else:
            roots = si.get("protected_roots")
            if roots is not None and (
                not isinstance(roots, list) or not all(isinstance(r, str) for r in roots)
            ):
                problems.append("self_integrity.protected_roots is not a list of strings")
    return ValidationResult(tuple(problems))
