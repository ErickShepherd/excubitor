#!/usr/bin/env python3
"""Runtime-neutral adapter — proof that the guard's decision core is host-independent.

The Claude Code hook `hooks/guard-loop-vc.py` is ONE adapter over a pure decision core. Its `main()`
does three host-specific things — read a Claude Code PreToolUse JSON envelope from stdin, check the
arming signal, and write a Claude Code `hookSpecificOutput` decision to stdout — and then delegates the
actual judgment to `_dangerous(command, yolo, cwd)`, which with `split_segments` / `_classify` /
`_yolo_merge_reason` has **zero Claude Code dependency**: a command string and a little context in, a
deny-reason-or-None out.

This module drives that SAME core (imported, not reimplemented — one source of truth for the security
logic) from a **generic** envelope, so "portable to any runtime that can intercept tool calls" is a
running, tested fact rather than a claim. `runtime/tests/test_spec_adapter.py` asserts the two adapters
agree decision-for-decision. `SPEC.md` documents the contract and what a real port to a third-party
runtime requires (and what it cannot fix — a host whose hooks don't fire on some invocation path).

Only the tiny envelope/arming glue is per-runtime and lives here; the classification never forks.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_HOOK = Path(__file__).resolve().parents[1] / "hooks" / "guard-loop-vc.py"


def _load_core() -> ModuleType:
    """Import the decision core from the Claude Code hook by path (its filename is hyphenated, so it
    isn't a normal import). Importing does not run its CLI — that is behind an `if __name__` guard."""
    spec = importlib.util.spec_from_file_location("_guard_loop_vc_core", _HOOK)
    if spec is None or spec.loader is None:  # pragma: no cover - only if the hook file vanished
        raise ImportError(f"cannot load guard decision core from {_HOOK}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_core = _load_core()


def decide(event: dict) -> dict:
    """Runtime-neutral guard decision. See SPEC.md for the full contract.

    Input — a host-agnostic envelope (the host maps its own shell tool-call event onto this):
      {
        "command":   "<the shell command string>",   # required for a decision; absent → allow
        "cwd":       "<working directory>",           # optional; used for branch detection in yolo mode
        "loop_mode": "1" | "yolo" | None,             # the arming signal; None/absent → guard inactive
      }
    Output:
      {"decision": "deny", "reason": "<why>"}   when the command is a fenced VC mutation, or
      {"decision": "allow", "reason": None}     otherwise (including when the guard is not armed).

    The classification is byte-for-byte the same logic the Claude Code hook applies — this function
    only translates the envelope and the arming signal, which is inherently the per-runtime part.
    """
    if not isinstance(event, dict):
        return _allow()
    loop_mode = event.get("loop_mode")
    if not loop_mode:
        return _allow()  # inactive unless the loop is explicitly armed (same posture as the hook)
    command = event.get("command")
    # Type-guard the envelope fields before handing them to the core: a wrongly-typed `command`
    # (e.g. an int) would raise deep in split_segments (`len(command)`), breaking the fail-open promise
    # this adapter makes. A non-string command has nothing to classify → allow; cwd must be str-or-None.
    if not isinstance(command, str) or not command:
        return _allow()
    cwd = event.get("cwd")
    cwd = cwd if isinstance(cwd, str) else None
    yolo = str(loop_mode).strip().lower() == "yolo"
    reason = _core._dangerous(command, yolo, cwd)
    return {"decision": "deny", "reason": reason} if reason else _allow()


def _allow() -> dict:
    return {"decision": "allow", "reason": None}


def main(argv: list[str]) -> int:
    """CLI: read one generic-envelope JSON object on stdin, print the decision JSON on stdout.

    Demonstrates the adapter end-to-end and mirrors the hook's fail-open PROCESS contract: an
    unparseable envelope yields an allow (never a crash that would wedge a host tool)."""
    import json
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps(_allow()))
        return 0
    print(json.dumps(decide(event if isinstance(event, dict) else {})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
