"""The model-blind policy dispatcher: run every policy for one event, deny wins.

An adapter normalizes a native pre-tool event into a `PreToolEvent`, calls `dispatch`, and renders the
returned `Decision` (`pass` → no opinion; `deny` → the host's structured veto). Each policy is wrapped
in a `decide_*(event, …) -> Decision` function that maps the canonical event onto the extracted
policy's inputs; `dispatch` consults them in a **deterministic deny-precedence order** and returns the
first `deny`, else `pass`.

Deny precedence (fixed, so the reported reason is deterministic when more than one policy would deny —
which is rare, since the policies are largely disjoint by capability and arming):

    self-integrity  →  loop-vc  →  default-branch  →  one-unit

self-integrity (the meta-guard that protects the others from being disarmed) is consulted first; then
the version-control act fence, the branch-first edit fence, and the one-unit cap. Any deny is a correct
deny — precedence only decides which reason surfaces.

Per-policy arming is reflected in the event and the adapter-supplied `DispatchConfig`: loop-vc and
self-integrity are inactive when `event.loop_mode is None` (unarmed); one-unit is inactive without a
`UnitCap`; default-branch is inactive without an opt-out-marker relpath; self-integrity is inactive
without a `ProtectedSurface`. A None config entry disables that policy — the adapter enables only what
its host arms.

This module does **no host I/O**: no stdin/stdout, no process exit, no environment reads, no host paths.
`denial_record` formats a neutral telemetry record from a decision; the adapter writes it BEST-EFFORT
and only AFTER it has serialized and flushed the native veto — preserving the decision-first ordering so
a telemetry fault never delays or changes a decision. (A hardened, hang-bounded, neutral-state-path
writer is a later packaging concern — the shipped guards still use `hooks/_denial_log.py`.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from excubitor.core.events import Capability, Decision, LoopMode, PreToolEvent
from excubitor.core.policies import default_branch, loop_vc, one_unit, self_integrity
from excubitor.core.policies.self_integrity import ProtectedSurface

__all__ = [
    "UnitCap",
    "DispatchConfig",
    "decide_loop_vc",
    "decide_default_branch",
    "decide_one_unit",
    "decide_self_integrity",
    "dispatch",
    "denial_record",
    "DENY_PRECEDENCE",
]

_FILE_CAPS = (Capability.FILE_MUTATE, Capability.NOTEBOOK_MUTATE)


@dataclass(frozen=True)
class UnitCap:
    """The one-unit cap's driver-supplied arming: the commit scope, the spawn-time baseline count, and
    an optional repo dir (falls back to the event cwd)."""

    scope: str
    baseline: int
    repo_dir: "str | None" = None


@dataclass(frozen=True)
class DispatchConfig:
    """Adapter-supplied per-policy configuration. A None entry disables that policy for this dispatch —
    the adapter enables only the policies its host arms and supplies each policy's host-specific config
    (the opt-out marker relpath, the one-unit cap, the protected surface)."""

    opt_out_relpath: "str | None" = None
    unit_cap: "UnitCap | None" = None
    protected_surface: "ProtectedSurface | None" = None


def decide_loop_vc(event: PreToolEvent) -> Decision:
    """Version-control act fence. Inactive unless armed (loop_mode set) and the event is a shell
    command. `VERIFIABLE` loop mode selects the YOLO deny set."""
    if event.loop_mode is None or event.capability is not Capability.SHELL_EXECUTE or not event.command:
        return Decision.pass_()
    yolo = event.loop_mode is LoopMode.VERIFIABLE
    reason = loop_vc._dangerous(event.command, yolo, event.cwd)
    return Decision.deny(reason, policy="loop-vc") if reason else Decision.pass_()


def decide_default_branch(event: PreToolEvent, opt_out_relpath: "str | None") -> Decision:
    """Branch-first edit fence. Inactive without an opt-out marker relpath (adapter-supplied) or for a
    non-file-mutation event. Checks every mutation target (a symlink-resolved container counts)."""
    if opt_out_relpath is None or event.capability not in _FILE_CAPS:
        return Decision.pass_()
    cwd = event.cwd or "."
    for target in event.targets:
        reason = default_branch.deny_reason(cwd, target, opt_out_relpath)
        if reason:
            return Decision.deny(reason, policy="default-branch")
    return Decision.pass_()


def decide_one_unit(event: PreToolEvent, cap: "UnitCap | None") -> Decision:
    """One-unit-per-session cap. Inactive without a driver-supplied cap; applies to any tool (the cap
    denies once this session's scope-matched commit count exceeds the baseline)."""
    if cap is None:
        return Decision.pass_()
    reason = one_unit.deny_reason(cap.repo_dir or event.cwd, cap.scope, cap.baseline)
    return Decision.deny(reason, policy="one-unit") if reason else Decision.pass_()


def decide_self_integrity(event: PreToolEvent, surface: "ProtectedSurface | None") -> Decision:
    """Kill-switch fence (the meta-guard). Inactive unless armed (loop_mode set) and a surface is
    supplied. Denies a file target or a shell token that resolves to / names a kill-switch path."""
    if event.loop_mode is None or surface is None:
        return Decision.pass_()
    cwd = event.cwd or "."
    hit: "str | None" = None
    if event.capability in _FILE_CAPS:
        for target in event.targets:
            hit = self_integrity.target_kill_switch(target, cwd, surface)
            if hit:
                break
    elif event.capability is Capability.SHELL_EXECUTE and event.command:
        hit = self_integrity.bash_kill_switch(event.command, cwd, surface)
    if hit:
        return Decision.deny(
            f"may not touch {hit} — that path can disarm the loop's own guards, and a judge the "
            f"model can rewrite is not a judge",
            policy="self-integrity",
        )
    return Decision.pass_()


#: The fixed order in which deny precedence is resolved (see the module docstring).
DENY_PRECEDENCE = ("self-integrity", "loop-vc", "default-branch", "one-unit")


def dispatch(event: PreToolEvent, config: DispatchConfig) -> Decision:
    """Run every configured policy for `event` and return the first `deny` in `DENY_PRECEDENCE` order,
    else `pass`. Deterministic and side-effect-free (the only I/O is the policies' read-only git
    queries, via the git boundary)."""
    by_policy = {
        "self-integrity": decide_self_integrity(event, config.protected_surface),
        "loop-vc": decide_loop_vc(event),
        "default-branch": decide_default_branch(event, config.opt_out_relpath),
        "one-unit": decide_one_unit(event, config.unit_cap),
    }
    for policy in DENY_PRECEDENCE:
        if by_policy[policy].is_deny:
            return by_policy[policy]
    return Decision.pass_()


def denial_record(event: PreToolEvent, decision: Decision) -> "dict[str, Any]":
    """A neutral, host-free telemetry record for a `deny` decision. The adapter writes this BEST-EFFORT
    and only AFTER it has serialized and flushed the native veto — a telemetry fault must never delay or
    change a decision. The core hardcodes no state path or timestamp; the writer supplies those."""
    return {
        "policy": decision.policy,
        "reason": decision.reason,
        "runtime": event.runtime,
        "capability": event.capability.value,
        "cwd": event.cwd,
        "command": event.command,
        "targets": list(event.targets),
        "session_id": event.session_id,
    }
