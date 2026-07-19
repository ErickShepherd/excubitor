"""Claude Code adapter: the shared PreToolUse envelope glue for the guard hook entry points.

The four shipped guard hooks (`guard-loop-vc`, `guard-default-branch`, `guard-one-unit`,
`guard-self-integrity`) are thin Claude Code entry points over the model-blind core. Each is registered
for its own tool/matcher and enforces its OWN policy, but they all share the same host glue: read a
`PreToolUse` JSON envelope from stdin, emit either no decision (defer) or a
`hookSpecificOutput.permissionDecision="deny"`, and append the deny to best-effort telemetry AFTER it
is on stdout. This module is that shared glue, so each entry point carries only its arming, its policy
call, and its host-specific deny wording.

Design note (scope of this adapter — owner-ratified C1.8 decision). These entry points call their
INDIVIDUAL core policy, not the dispatcher: each hook is registered for one tool-surface and must
enforce exactly one policy, and routing a single hook through `dispatch()` (which runs every armed
policy) would over-run policies and break each hook's byte-untouched differential oracle. The
consolidated normalize→`dispatch()`→render adapter is the generic runtime path
(`runtime/spec_adapter.py`, C1.9) and any future single-hook host; the shipped Claude Code registration
stays four parity-exact entry points. So this module deliberately factors only the shared I/O glue.

Contract (docs/en/hooks): deny = exit 0 + JSON on stdout with `permissionDecision="deny"`; no decision
defers. We NEVER exit non-zero. Telemetry is best-effort and strictly AFTER the decision is
serialized/flushed, so a telemetry fault never changes or delays a decision. Adapter modules are
host-specific by design — the core-neutrality invariant does not apply here.
"""
from __future__ import annotations

import json
import os
import sys


def read_payload() -> "dict | None":
    """Parse the PreToolUse JSON envelope from stdin. Returns the dict, or None on unparseable / non-
    object input — the caller then defers (fail open, never wedge the tool)."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:  # JSONDecodeError is a ValueError subclass
        return None
    return payload if isinstance(payload, dict) else None


def emit_pass() -> "None":  # NoReturn
    """Emit no decision → defer to the normal permission flow. Always exit 0."""
    sys.exit(0)


def emit_deny(reason: str, guard_name: str, payload: dict, denial_log_dir: str) -> "None":  # NoReturn
    """Render the `hookSpecificOutput` deny to stdout, flush, then append best-effort telemetry, exit 0.

    `reason` is the fully-composed, host-facing deny message (the entry point owns its wording).
    `denial_log_dir` is the entry point's own resolved directory — the sibling `_denial_log.py` lives
    there, so the `~/.claude` symlink layout still finds it after the glue moved into this package."""
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    # Decision first, telemetry second: flush the deny to the harness BEFORE any telemetry I/O.
    # Flushing alone is necessary but not sufficient — a hung write would still hold this process past
    # the hook timeout (which fails OPEN and lets the fenced call run) — so record() also time-bounds
    # the filesystem I/O in an abandonable daemon thread (see hooks/_denial_log.py).
    sys.stdout.flush()
    _record_denial(guard_name, reason, payload, denial_log_dir)
    sys.exit(0)


def _record_denial(guard_name: str, reason: str, payload: dict, denial_log_dir: str) -> None:
    """Best-effort denial telemetry via the sibling `_denial_log.py` in `denial_log_dir`. ANY fault —
    module missing (a guard copied with no sibling), unwritable log, anything — is swallowed: the deny
    already flushed to stdout must never be affected."""
    try:
        import importlib.util

        mod_path = os.path.join(denial_log_dir, "_denial_log.py")
        spec = importlib.util.spec_from_file_location("_denial_log", mod_path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.record(guard_name, reason, payload)
    except Exception:
        pass
