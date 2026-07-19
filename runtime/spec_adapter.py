#!/usr/bin/env python3
"""Generic runtime adapter — the `excubitor.pre_tool.v1` protocol over the model-blind core.

A runtime that can intercept a tool call before execution maps its native event onto the versioned
canonical envelope below and calls `decide`; the adapter normalizes it into a `PreToolEvent`, runs the
model-blind dispatcher (ALL four policies, not just loop-VC), and returns a two-outcome decision. This
is the host-agnostic proof that "portable to any runtime that can intercept tool calls" is a running,
tested fact: the Claude Code hooks and this generic adapter reach the SAME decisions through the SAME
core (`runtime/tests/test_spec_adapter.py` asserts the deny agreement).

Canonical event (`excubitor.pre_tool.v1`) — the host fills what it knows; missing fields degrade
conservatively:

    {
      "schema": "excubitor.pre_tool.v1",     # optional marker
      "runtime": "codex",                      # telemetry/diagnostics only; policies never branch on it
      "native_tool": "apply_patch",            # diagnostics
      "capability": "file.mutate",             # shell.execute | file.mutate | notebook.mutate | other
      "cwd": "/repo",
      "command": "git push",                   # for shell.execute; else null
      "targets": ["/repo/a.py", "/repo/b.py"], # EVERY mutated path (a patch can touch several)
      "session_id": "...",
      "loop_mode": "conservative",             # null | conservative | verifiable  (aliases: 1 | yolo)
      "control_paths": ["/repo/.codex/config.toml"]
    }

Per-policy arming knobs that are NOT part of the neutral event (the host supplies them out of band) go
in an optional `config` object — the opt-out marker relpath (default-branch), the one-unit cap, and the
protected surface (self-integrity). Absent config → those policies are inactive; loop-VC needs only the
event. A legacy shell-only envelope `{command, cwd, loop_mode}` (no `capability`) still works: the
capability is inferred from a present command / targets.

Result — a two-outcome decision; `pass` means Excubitor has NO objection (preserve the host's normal
permission flow — NEVER an auto-approve), `deny` is a veto:

    {"decision": "pass", "reason": null}
    {"decision": "deny", "reason": "...", "policy": "loop-vc"}

Process contract: the adapter never crashes on a malformed envelope — it fails toward `pass` (no
opinion), so a bad event can never wedge a host tool. A caller is CONFORMING only if it invokes this
before execution and honors `deny`; a demo that prints a decision but cannot veto is not an enforcement
port.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add the repo root to sys.path so this adapter — which may run as a standalone CLI from any cwd — can
# import the model-blind core package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from excubitor.core import dispatch  # noqa: E402
from excubitor.core.events import Capability, LoopMode, PreToolEvent  # noqa: E402
from excubitor.core.policies.self_integrity import ProtectedSurface  # noqa: E402

_CAP_BY_VALUE = {c.value: c for c in Capability}
# Neutral loop-mode names plus the legacy raw marker values, so an older `{loop_mode: "1"|"yolo"}`
# envelope still arms correctly.
_LOOP_MODE = {
    "conservative": LoopMode.CONSERVATIVE,
    "1": LoopMode.CONSERVATIVE,
    "verifiable": LoopMode.VERIFIABLE,
    "yolo": LoopMode.VERIFIABLE,
}


def _str_or_none(v: object) -> "str | None":
    return v if isinstance(v, str) else None


def _str_tuple(v: object) -> "tuple[str, ...]":
    return tuple(x for x in v if isinstance(x, str)) if isinstance(v, (list, tuple)) else ()


def _to_event(event: object) -> "PreToolEvent | None":
    """Normalize a generic envelope into a canonical PreToolEvent, or None if it is not even an object
    (→ the caller fails toward `pass`). Individual fields degrade conservatively rather than raise."""
    if not isinstance(event, dict):
        return None
    command = _str_or_none(event.get("command"))
    targets = _str_tuple(event.get("targets"))
    cap_raw = event.get("capability")
    if isinstance(cap_raw, str) and cap_raw in _CAP_BY_VALUE:
        capability = _CAP_BY_VALUE[cap_raw]
    elif command:  # a legacy/shell envelope with a command but no explicit capability
        capability = Capability.SHELL_EXECUTE
    elif targets:
        capability = Capability.FILE_MUTATE
    else:
        capability = Capability.OTHER
    lm_raw = event.get("loop_mode")
    loop_mode = _LOOP_MODE.get(str(lm_raw).strip().lower()) if lm_raw else None
    return PreToolEvent(
        capability=capability,
        runtime=_str_or_none(event.get("runtime")),
        native_tool=_str_or_none(event.get("native_tool")),
        cwd=_str_or_none(event.get("cwd")),
        command=command,
        targets=targets,
        session_id=_str_or_none(event.get("session_id")),
        loop_mode=loop_mode,
        control_paths=_str_tuple(event.get("control_paths")),
    )


def _to_config(config: object) -> "dispatch.DispatchConfig":
    """Build the adapter's DispatchConfig from an optional host-supplied `config` object. A None / bad
    config yields an empty config (only loop-VC, which needs no config, is then active)."""
    if not isinstance(config, dict):
        return dispatch.DispatchConfig()
    unit_cap = None
    cap = config.get("unit_cap")
    if isinstance(cap, dict) and isinstance(cap.get("scope"), str) and isinstance(cap.get("baseline"), int):
        unit_cap = dispatch.UnitCap(
            scope=cap["scope"], baseline=cap["baseline"], repo_dir=_str_or_none(cap.get("repo_dir"))
        )
    surface = None
    surf = config.get("protected_surface")
    if isinstance(surf, dict):
        surface = ProtectedSurface(
            guard_scripts=frozenset(_str_tuple(surf.get("guard_scripts"))),
            marker=surf.get("marker") if isinstance(surf.get("marker"), str) else "",
            settings_names=frozenset(_str_tuple(surf.get("settings_names"))),
            control_dir=surf.get("control_dir") if isinstance(surf.get("control_dir"), str) else "",
            protected_roots=_str_tuple(surf.get("protected_roots")),
        )
    return dispatch.DispatchConfig(
        opt_out_relpath=_str_or_none(config.get("opt_out_relpath")),
        unit_cap=unit_cap,
        protected_surface=surface,
    )


def decide(event: object, config: object = None) -> dict:
    """Normalize a generic `excubitor.pre_tool.v1` event, run the dispatcher, return the decision dict.
    A malformed event fails toward `pass` (no opinion) — never a crash that would wedge a host tool."""
    pre = _to_event(event)
    if pre is None:
        return _pass()
    return dispatch.dispatch(pre, _to_config(config)).to_dict()


def _pass() -> dict:
    return {"decision": "pass", "reason": None}


def main(argv: list[str]) -> int:
    """CLI: read one JSON object on stdin, print the decision JSON on stdout.

    Accepts either a bare event (`{...canonical fields...}`) or a wrapper `{"event": {...}, "config":
    {...}}`. Mirrors the fail-open PROCESS contract: an unparseable envelope yields `pass` (never a
    crash that would wedge a host tool)."""
    import json

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps(_pass()))
        return 0
    if isinstance(payload, dict) and "event" in payload:
        event, config = payload.get("event"), payload.get("config")
    else:
        event, config = payload, None  # backward-compat: the whole object is the event
    print(json.dumps(decide(event, config)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
