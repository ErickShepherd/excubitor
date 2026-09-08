"""Codex ``PreToolUse`` adapter over the model-blind Excubitor dispatcher.

Codex sends one JSON object on stdin. Bash and ``apply_patch`` calls carry their native input in
``tool_input.command``. Exact MCP mutation profiles in the neutral policy may additionally map a
canonical ``mcp__server__tool`` name to every path-bearing input selector. This adapter maps those
surfaces to canonical capabilities, calls the shared dispatcher once, and renders only a deny. A pass
writes nothing, preserving Codex's normal permission flow instead of accidentally granting permission.

The outer process contract is fail-open: malformed JSON, a non-object envelope, the wrong hook event,
or an unexpected adapter failure produces no output and exits zero. A recognized ``apply_patch``
command or a configured MCP mutation is different: once the adapter recognizes the mutation surface,
failing to enumerate every target is a safety ambiguity, so it returns a structured deny. This is
input validation, not a second policy implementation; valid calls are always decided by
:mod:`excubitor.core.dispatch`. Unconfigured MCP tools remain ``other`` and therefore preserve the
host's normal permission flow.

This module is the native adapter only. Registration, trust review, bounded denial telemetry, observed
host fixtures, and live MCP denial witnesses are separate gates, so the existence of this file alone
is not a Codex support claim.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping

from excubitor import config as neutral_config
from excubitor.core import dispatch
from excubitor.core.events import Capability, Decision, PreToolEvent
from excubitor.core.policies.self_integrity import ProtectedSurface

__all__ = ["normalize", "decide", "render", "main"]

_BEGIN_PATCH = "*** Begin Patch"
_END_PATCH = "*** End Patch"
_END_FILE = "*** End of File"
_FILE_HEADERS = ("*** Add File: ", "*** Update File: ", "*** Delete File: ")
_MOVE_HEADER = "*** Move to: "
_CODEX_CONTROL_DIR = ".codex"
_CODEX_SETTINGS = frozenset({"config.toml", "hooks.json"})


class _UnsafePatchEnvelope(ValueError):
    """A recognized patch call whose complete mutation target set cannot be proven."""


class _UnsafeMcpEnvelope(ValueError):
    """A configured MCP mutation whose complete target set cannot be proven."""


def _string(value: object) -> "str | None":
    return value if isinstance(value, str) else None


def _patch_path(line: str, prefix: str) -> str:
    path = line[len(prefix) :].strip()
    if not path or "\x00" in path:
        raise _UnsafePatchEnvelope("empty or invalid patch path")
    return path


def _patch_targets(command: str) -> tuple[str, ...]:
    """Return every source and destination path in an ``apply_patch`` command.

    The parser intentionally understands only the documented patch action headers. Unknown action
    headers, a move without a source action, or a patch with no file action is denied rather than
    guessed. Duplicate paths are removed without changing order.
    """
    lines = command.splitlines()
    while lines and not lines[-1]:
        lines.pop()
    if len(lines) < 3 or lines[0] != _BEGIN_PATCH or lines[-1] != _END_PATCH:
        raise _UnsafePatchEnvelope("missing patch boundary")

    targets: list[str] = []
    active_source = False
    for line in lines[1:-1]:
        matched = False
        for prefix in _FILE_HEADERS:
            if line.startswith(prefix):
                targets.append(_patch_path(line, prefix))
                active_source = True
                matched = True
                break
        if matched:
            continue
        if line.startswith(_MOVE_HEADER):
            if not active_source:
                raise _UnsafePatchEnvelope("move destination has no source action")
            targets.append(_patch_path(line, _MOVE_HEADER))
            continue
        if line == _END_FILE:
            continue
        if line.startswith("*** "):
            raise _UnsafePatchEnvelope("unknown patch action header")

    if not targets:
        raise _UnsafePatchEnvelope("patch contains no file action")
    return tuple(dict.fromkeys(targets))


def _pointer_segment(raw: str) -> str:
    """Decode one JSON Pointer segment, rejecting malformed ``~`` escapes."""
    decoded: list[str] = []
    index = 0
    while index < len(raw):
        if raw[index] != "~":
            decoded.append(raw[index])
            index += 1
            continue
        if index + 1 >= len(raw) or raw[index + 1] not in "01":
            raise _UnsafeMcpEnvelope("invalid JSON pointer escape")
        decoded.append("~" if raw[index + 1] == "0" else "/")
        index += 2
    return "".join(decoded)


def _selector_values(tool_input: Mapping[str, object], selector: object) -> tuple[object, ...]:
    """Resolve a profile selector through the MCP JSON arguments.

    Selectors use JSON Pointer syntax plus a ``*`` segment for every member of an input array. A final
    selector may resolve to one path string or a non-empty array of path strings.
    """
    if not isinstance(selector, str) or not selector.startswith("/"):
        raise _UnsafeMcpEnvelope("target selector is not a JSON pointer")
    nodes: list[object] = [tool_input]
    for raw_segment in selector[1:].split("/"):
        segment = _pointer_segment(raw_segment)
        next_nodes: list[object] = []
        for node in nodes:
            if segment == "*":
                if not isinstance(node, list) or not node:
                    raise _UnsafeMcpEnvelope("target wildcard did not resolve a non-empty array")
                next_nodes.extend(node)
            elif isinstance(node, Mapping):
                if segment not in node:
                    raise _UnsafeMcpEnvelope("target selector field is missing")
                next_nodes.append(node[segment])
            elif isinstance(node, list) and segment.isascii() and segment.isdigit():
                position = int(segment)
                if position >= len(node):
                    raise _UnsafeMcpEnvelope("target selector index is out of range")
                next_nodes.append(node[position])
            else:
                raise _UnsafeMcpEnvelope("target selector crossed a non-container value")
        if not next_nodes:
            raise _UnsafeMcpEnvelope("target selector resolved no values")
        nodes = next_nodes
    return tuple(nodes)


def _mcp_targets(
    tool_name: str, tool_input: Mapping[str, object], configured: object
) -> "tuple[str, ...] | None":
    """Enumerate a configured MCP mutation, or return None for an unconfigured tool."""
    if not isinstance(configured, Mapping) or tool_name not in configured:
        return None
    selectors = configured[tool_name]
    if not isinstance(selectors, (list, tuple)) or not selectors:
        raise _UnsafeMcpEnvelope("mutation profile has no target selectors")

    targets: list[str] = []
    for selector in selectors:
        for selected in _selector_values(tool_input, selector):
            values = selected if isinstance(selected, list) else [selected]
            if not values:
                raise _UnsafeMcpEnvelope("target selector resolved an empty array")
            for value in values:
                if not isinstance(value, str) or not value or "\x00" in value:
                    raise _UnsafeMcpEnvelope("target is not a non-empty path string")
                targets.append(value)
    if not targets:
        raise _UnsafeMcpEnvelope("mutation profile resolved no targets")
    return tuple(dict.fromkeys(targets))


def _unit_cap(
    environ: Mapping[str, str], cwd: "str | None", enabled: bool
) -> "dispatch.UnitCap | None":
    if not enabled:
        return None
    scope = (environ.get("ONE_UNIT_CAP_SCOPE") or "").strip()
    baseline_raw = (environ.get("ONE_UNIT_CAP_BASELINE") or "").strip()
    if not scope or not (baseline_raw.isascii() and baseline_raw.isdigit()):
        return None
    return dispatch.UnitCap(
        scope=scope,
        baseline=int(baseline_raw),
        repo_dir=environ.get("ONE_UNIT_CAP_REPO") or cwd,
    )


def _protected_roots(
    cwd: str, configured: object, policy_path: "str | None"
) -> tuple[str, ...]:
    roots = [str(Path(__file__).resolve().parents[1])]
    if policy_path:
        roots.append(os.path.realpath(str(Path(policy_path).parent)))
    if isinstance(configured, tuple):
        for root in configured:
            if not isinstance(root, str) or not root:
                continue
            candidate = root if os.path.isabs(root) else os.path.join(cwd, root)
            roots.append(os.path.realpath(candidate))
    return tuple(dict.fromkeys(roots))


def _dispatch_config(
    cwd: "str | None", environ: Mapping[str, str]
) -> tuple[neutral_config.Config, dispatch.DispatchConfig]:
    start_dir = cwd or os.getcwd()
    resolved = neutral_config.resolve_config(start_dir=start_dir, environ=dict(environ))
    opt_out = None if resolved.allow_default_branch.value else str(resolved.opt_out_marker.value)
    marker = os.path.basename(os.path.normpath(str(resolved.opt_out_marker.value)))
    surface = ProtectedSurface(
        guard_scripts=frozenset(),
        marker=marker,
        settings_names=_CODEX_SETTINGS,
        control_dir=_CODEX_CONTROL_DIR,
        protected_roots=_protected_roots(
            start_dir, resolved.protected_roots.value, resolved.policy_path
        ),
    )
    return resolved, dispatch.DispatchConfig(
        opt_out_relpath=opt_out,
        unit_cap=_unit_cap(environ, cwd, bool(resolved.one_unit_enabled.value)),
        protected_surface=surface,
    )


def normalize(
    payload: Mapping[str, object], environ: "Mapping[str, str] | None" = None
) -> "tuple[PreToolEvent, dispatch.DispatchConfig] | None":
    """Normalize one native Codex envelope and resolve the adapter-supplied policy configuration."""
    if payload.get("hook_event_name") != "PreToolUse":
        return None
    tool_name = _string(payload.get("tool_name"))
    tool_input = payload.get("tool_input")
    if tool_name is None or not isinstance(tool_input, Mapping):
        return None

    cwd = _string(payload.get("cwd"))
    environment = dict(os.environ if environ is None else environ)
    resolved, dispatcher_config = _dispatch_config(cwd, environment)
    command = _string(tool_input.get("command"))
    targets: tuple[str, ...] = ()
    if tool_name == "Bash":
        capability = Capability.SHELL_EXECUTE
    elif tool_name == "apply_patch":
        if command is None:
            return None
        capability = Capability.FILE_MUTATE
        targets = _patch_targets(command)
        command = None
    elif tool_name.startswith("mcp__"):
        configured_targets = _mcp_targets(
            tool_name, tool_input, resolved.codex_mcp_mutation_profiles.value
        )
        if configured_targets is None:
            capability = Capability.OTHER
        else:
            capability = Capability.FILE_MUTATE
            targets = configured_targets
        command = None
    else:
        capability = Capability.OTHER
        command = None

    control_paths: tuple[str, ...] = ()
    if cwd:
        active_controls = [
            os.path.join(cwd, _CODEX_CONTROL_DIR, name) for name in sorted(_CODEX_SETTINGS)
        ]
        if resolved.policy_path:
            active_controls.append(resolved.policy_path)
        control_paths = tuple(active_controls)
    event = PreToolEvent(
        runtime="codex",
        native_tool=tool_name,
        capability=capability,
        cwd=cwd,
        command=command,
        targets=targets,
        session_id=_string(payload.get("session_id")),
        loop_mode=resolved.loop_mode.value,
        control_paths=control_paths,
    )
    return event, dispatcher_config


def decide(
    payload: Mapping[str, object], environ: "Mapping[str, str] | None" = None
) -> Decision:
    """Return the core decision for a native payload, or a conservative input-validation deny."""
    try:
        normalized = normalize(payload, environ)
    except _UnsafePatchEnvelope:
        return Decision.deny(
            "Excubitor could not enumerate every file targeted by this apply_patch call, so the "
            "mutation was denied instead of running with incomplete policy coverage.",
            policy="adapter-input",
        )
    except _UnsafeMcpEnvelope:
        return Decision.deny(
            "Excubitor could not enumerate every file targeted by this configured MCP mutation, so "
            "the call was denied instead of running with incomplete policy coverage.",
            policy="adapter-input",
        )
    if normalized is None:
        return Decision.pass_()
    event, dispatcher_config = normalized
    return dispatch.dispatch(event, dispatcher_config)


def render(decision: Decision) -> "dict[str, object] | None":
    """Render a deny in Codex's native shape; a pass is silence/no opinion."""
    if decision.is_pass:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": decision.reason or "Blocked by Excubitor policy.",
        }
    }


def main() -> None:
    """Command-hook entry point. Always exits zero; unexpected failures defer to Codex."""
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return
        output = render(decide(payload))
        if output is not None:
            json.dump(output, sys.stdout)
            sys.stdout.flush()
    except Exception:
        return


if __name__ == "__main__":
    main()
