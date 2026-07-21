"""Neutral policy configuration: `.excubitor/policy.toml` loading + `EXCUBITOR_*` env precedence.

This is the host-facing configuration layer the CLI and installer read — deliberately **outside**
`excubitor.core` because it does host I/O (reads environment variables and files), which the pure core
never does. It resolves the *neutral* policy a repo commits and the *runtime* arming a loop driver
supplies, with a documented precedence and honest provenance for every value (so `print-config` can
show where each setting came from).

Precedence, highest first:

1. `EXCUBITOR_*` environment variable — the neutral primary.
2. `CLAUDE_*` environment variable — the **legacy** alias, honored during the transition and recorded
   as a deprecation warning (never silently). Only the runtime signals have a legacy alias.
3. `.excubitor/policy.toml` — the committed, reviewable neutral policy (static knobs only).
4. A built-in default.

**Arming is runtime-only, never committed.** `loop_mode` (conservative / verifiable) is resolved from
the environment alone — there is deliberately no `policy.toml` key for it, so a repo cannot arm
verifiable autonomy by checking a file into version control. `policy.toml` carries only the static,
reviewable knobs (the opt-out-marker relpath, the one-unit toggle, extra protected roots).

Legacy compatibility is *recognition*, not *behavior change*: the shipped Claude Code guards still read
`CLAUDE_LOOP_GUARD` / `CLAUDE_ALLOW_DEFAULT_BRANCH` and the `.claude/allow-default-branch` marker
directly. This module additionally recognizes the neutral `EXCUBITOR_*` names and the
`.excubitor/allow-default-branch` marker for the CLI/installer surface; it does not rewire the live
guards (that is a later, out-of-loop step). Because it is not wired into live enforcement, recognizing
the neutral marker here creates **no** new live disarm path — a value the live guards do not consume
cannot unprotect anything.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from excubitor.core.events import LoopMode

__all__ = [
    "DEFAULT_OPT_OUT_MARKER",
    "LEGACY_OPT_OUT_MARKER",
    "ALLOW_DEFAULT_BRANCH_MARKERS",
    "Resolved",
    "Config",
    "load_policy_file",
    "resolve_loop_mode",
    "resolve_config",
]

#: The neutral per-repo opt-out marker relpath (recognized first).
DEFAULT_OPT_OUT_MARKER = ".excubitor/allow-default-branch"
#: The legacy Claude Code opt-out marker relpath, still recognized during the transition.
LEGACY_OPT_OUT_MARKER = ".claude/allow-default-branch"
#: Both allow-default-branch marker relpaths, neutral first — surfaced by the CLI/installer.
ALLOW_DEFAULT_BRANCH_MARKERS = (DEFAULT_OPT_OUT_MARKER, LEGACY_OPT_OUT_MARKER)

# Values accepted for the loop-guard signal on EITHER the neutral or the legacy variable, mapped to the
# neutral LoopMode. The neutral names and the legacy raw markers both resolve, so an older
# `EXCUBITOR_LOOP_GUARD=1` or a `CLAUDE_LOOP_GUARD=yolo` each arm correctly.
_LOOP_MODE_VALUES = {
    "conservative": LoopMode.CONSERVATIVE,
    "1": LoopMode.CONSERVATIVE,
    "verifiable": LoopMode.VERIFIABLE,
    "yolo": LoopMode.VERIFIABLE,
}

_POLICY_RELPATH = os.path.join(".excubitor", "policy.toml")
_MAX_SEARCH_DEPTH = 64  # backstop against a pathological directory chain


@dataclass(frozen=True)
class Resolved:
    """One resolved setting plus the honest provenance of where its value came from.

    ``source`` is a short, stable token the CLI prints verbatim: ``env:EXCUBITOR_LOOP_GUARD``,
    ``env:CLAUDE_LOOP_GUARD (legacy)``, ``policy.toml``, or ``default``.
    """

    value: object
    source: str


@dataclass(frozen=True)
class Config:
    """The fully resolved neutral configuration with per-value provenance.

    ``warnings`` collects deprecation notes (legacy variable used); the caller surfaces them rather
    than this module writing to stderr, so a hook that later consumes it never emits stray output.
    """

    loop_mode: Resolved  # value: LoopMode | None
    allow_default_branch: Resolved  # value: bool
    state_home: Resolved  # value: str | None
    opt_out_marker: Resolved  # value: str
    one_unit_enabled: Resolved  # value: bool
    protected_roots: Resolved  # value: tuple[str, ...]
    policy_path: "str | None"
    warnings: "tuple[str, ...]" = field(default=())


def _env(environ: "dict[str, str]", name: str) -> "str | None":
    """A present, non-empty environment value, else None (an empty string does not arm anything)."""
    raw = environ.get(name)
    return raw if raw else None


def load_policy_file(start_dir: "str | os.PathLike[str]") -> "tuple[dict, str | None]":
    """Find and parse `.excubitor/policy.toml`, searching from ``start_dir`` upward to the filesystem
    root (git-toplevel style). Returns ``(policy_dict, path)`` or ``({}, None)`` when none is found or it
    is unreadable/malformed — a bad policy file degrades to defaults, it never raises into a host tool.
    """
    current = Path(start_dir).resolve()
    for _ in range(_MAX_SEARCH_DEPTH):
        candidate = current / _POLICY_RELPATH
        if candidate.is_file():
            try:
                return tomllib.loads(candidate.read_text(encoding="utf-8")), str(candidate)
            except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
                return {}, None
        if current.parent == current:
            break
        current = current.parent
    return {}, None


def resolve_loop_mode(environ: "dict[str, str]") -> "tuple[LoopMode | None, str, tuple[str, ...]]":
    """Resolve the loop-guard arming from the environment alone (never from a committed file).

    Returns ``(loop_mode, source, warnings)``. ``EXCUBITOR_LOOP_GUARD`` wins; a bare
    ``CLAUDE_LOOP_GUARD`` is honored as a legacy alias and adds a deprecation warning. An unset or
    unrecognized value resolves to ``None`` (unarmed).
    """
    neutral = _env(environ, "EXCUBITOR_LOOP_GUARD")
    if neutral is not None:
        return _LOOP_MODE_VALUES.get(neutral.strip().lower()), "env:EXCUBITOR_LOOP_GUARD", ()
    legacy = _env(environ, "CLAUDE_LOOP_GUARD")
    if legacy is not None:
        warning = (
            "CLAUDE_LOOP_GUARD is a legacy alias; set EXCUBITOR_LOOP_GUARD "
            "(conservative|verifiable) instead."
        )
        return _LOOP_MODE_VALUES.get(legacy.strip().lower()), "env:CLAUDE_LOOP_GUARD (legacy)", (warning,)
    return None, "default", ()


def _resolve_flag(environ: "dict[str, str]", neutral: str, legacy: str) -> "tuple[bool, str, tuple]":
    """A boolean off-switch resolved neutral-env > legacy-env > default(False), with a legacy warning."""
    if _env(environ, neutral) is not None:
        return True, f"env:{neutral}", ()
    if _env(environ, legacy) is not None:
        return True, f"env:{legacy} (legacy)", (
            f"{legacy} is a legacy alias; set {neutral} instead.",
        )
    return False, "default", ()


def resolve_config(
    start_dir: "str | os.PathLike[str] | None" = None,
    environ: "dict[str, str] | None" = None,
) -> Config:
    """Resolve the full neutral configuration for the repo at ``start_dir`` under ``environ``.

    ``start_dir`` defaults to the current working directory; ``environ`` defaults to ``os.environ``.
    Every value carries its provenance, and all legacy-alias uses accumulate in ``warnings``.
    """
    environ = dict(os.environ if environ is None else environ)
    start_dir = os.getcwd() if start_dir is None else start_dir
    policy, policy_path = load_policy_file(start_dir)
    warnings: list[str] = []

    loop_mode, loop_source, loop_warn = resolve_loop_mode(environ)
    warnings.extend(loop_warn)

    allow, allow_source, allow_warn = _resolve_flag(
        environ, "EXCUBITOR_ALLOW_DEFAULT_BRANCH", "CLAUDE_ALLOW_DEFAULT_BRANCH"
    )
    warnings.extend(allow_warn)

    state = _env(environ, "EXCUBITOR_STATE_HOME")
    state_resolved = Resolved(state, "env:EXCUBITOR_STATE_HOME" if state else "default")

    db_table = policy.get("default_branch") if isinstance(policy.get("default_branch"), dict) else {}
    marker = db_table.get("opt_out_marker")
    if isinstance(marker, str) and marker:
        opt_out = Resolved(marker, "policy.toml")
    else:
        opt_out = Resolved(DEFAULT_OPT_OUT_MARKER, "default")

    ou_table = policy.get("one_unit") if isinstance(policy.get("one_unit"), dict) else {}
    ou_enabled = ou_table.get("enabled")
    one_unit = (
        Resolved(bool(ou_enabled), "policy.toml")
        if isinstance(ou_enabled, bool)
        else Resolved(True, "default")
    )

    si_table = policy.get("self_integrity") if isinstance(policy.get("self_integrity"), dict) else {}
    roots_raw = si_table.get("protected_roots")
    roots = tuple(r for r in roots_raw if isinstance(r, str)) if isinstance(roots_raw, list) else ()
    protected = Resolved(roots, "policy.toml" if roots else "default")

    return Config(
        loop_mode=Resolved(loop_mode, loop_source),
        allow_default_branch=Resolved(allow, allow_source),
        state_home=state_resolved,
        opt_out_marker=opt_out,
        one_unit_enabled=one_unit,
        protected_roots=protected,
        policy_path=policy_path,
        warnings=tuple(warnings),
    )
