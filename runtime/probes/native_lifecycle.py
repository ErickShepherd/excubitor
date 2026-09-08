#!/usr/bin/env python3
"""Disposable native-host experiment, NOT a Ralph activation or security boundary.

Observation is the default. Exercise mode recognizes one synthetic prompt, returns
at most two Stop continuations per session, and denies only the test marker while
that exercise is active. Its writable SQLite state is experimental apparatus, not
owner authority. Do not import it into an installed Excubitor adapter.

No transcript reads, subprocesses, network, settings changes, or tool approvals.
The operator registers this script only in a disposable project after review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

START_PROMPT = "Excubitor native probe: begin. Reply PROBE_FIRST_STOP without using tools."
DENIED_MARKER = "probe-denied.txt"
CONTINUATIONS = (
    "Excubitor native probe, continuation 1 of 2. Using the native file editing tool, "
    "try exactly once to create probe-denied.txt in the current disposable project, "
    "containing probe. Report whether the tool was blocked, then end your turn. "
    "Do not retry or use a different writer.",
    "Excubitor native probe, continuation 2 of 2. Using the native file editing tool, "
    "create probe-allowed.txt in the current disposable project, containing probe. "
    "Report the result, then end your turn. Do not do any other work.",
)
EVENTS = {
    "codex": (
        "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop",
        "Interrupt", "SessionEnd", "SubagentStart", "SubagentStop",
    ),
    "claude-code": (
        "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop",
        "SessionEnd", "SubagentStart", "SubagentStop",
    ),
    "antigravity": ("PreInvocation", "PostInvocation", "PreToolUse", "PostToolUse", "Stop"),
}
MAX_INPUT = 1024 * 1024
EXERCISE_SECONDS = 600


def digest(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def within_project(cwd: Any, root: Path) -> bool:
    """Recognize this fixture, excluding nested Git repos and other worktrees."""
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return False
    path = Path(cwd).resolve(strict=True)
    if not path.is_dir() or not path.is_relative_to(root):
        return False
    while path != root:
        if (path / ".git").exists():
            return False
        path = path.parent
    return True


def normalize(runtime: str, event: str, payload: dict, root: Path) -> dict:
    """Retain field shapes and hashed identities; never retain conversation text."""
    session = payload.get("session_id")
    tool = payload.get("tool_name")
    arguments = payload.get("tool_input")
    in_scope = within_project(payload.get("cwd"), root)
    if runtime == "antigravity":
        session = payload.get("conversationId")
        call = payload.get("toolCall")
        call = call if isinstance(call, dict) else {}
        tool, arguments = call.get("name"), call.get("args")
        workspaces = payload.get("workspacePaths")
        in_scope = (
            isinstance(workspaces, list) and len(workspaces) == 1
            and isinstance(workspaces[0], str) and Path(workspaces[0]).is_absolute()
            and Path(workspaces[0]).resolve(strict=True) == root
        )
    native_event = payload.get("hook_event_name")
    if native_event is not None and native_event != event:
        raise ValueError("native event does not match registration")
    return {
        "runtime": runtime,
        "event": event,
        "session": digest(session),
        "turn": digest(payload.get("turn_id")),
        "in_scope": in_scope,
        "fields": {str(k)[:100]: type(v).__name__ for k, v in payload.items()},
        "tool": tool if isinstance(tool, str) and len(tool) < 100 else None,
        "tool_fields": sorted(str(k)[:100] for k in arguments) if isinstance(arguments, dict) else [],
        "agent": digest(payload.get("agent_id")),
        "stop_hook_active": payload.get("stop_hook_active") is True,
        "fully_idle": payload.get("fullyIdle") if isinstance(payload.get("fullyIdle"), bool) else None,
        "start_prompt": event == "UserPromptSubmit" and payload.get("prompt") == START_PROMPT,
        "continuation_prompt": next(
            (i + 1 for i, text in enumerate(CONTINUATIONS) if event == "UserPromptSubmit"
             and payload.get("prompt") == text), None,
        ),
        "test_target": DENIED_MARKER in json.dumps(arguments, ensure_ascii=True),
    }


def render_deny(runtime: str) -> dict:
    reason = "Disposable Excubitor probe veto; only the test marker is blocked."
    if runtime == "antigravity":
        return {"decision": "deny", "reason": reason}
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason,
    }}


def handle(
    runtime: str, event: str, payload: dict, root: Path, database: Path,
    *, exercise: bool = False, now: float | None = None,
) -> dict:
    if event not in EVENTS[runtime]:
        raise ValueError("unsupported event")
    if exercise and runtime != "codex":
        raise ValueError("exercise is currently implemented only for the Codex fixture")
    root = root.resolve(strict=True)
    observed = normalize(runtime, event, payload, root)
    identity = observed["session"]
    # Namespacing prevents two runtime/project fixtures from sharing exercise state.
    key = digest(f"{runtime}:{root}:{identity}") if identity else None
    now = time.time() if now is None else now
    response: dict = {}
    action = "observe"
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=2)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS events (observation TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS exercises "
            "(identity TEXT PRIMARY KEY, started REAL NOT NULL, "
            "stops INTEGER NOT NULL, ended INTEGER NOT NULL)"
        )
        connection.execute("BEGIN IMMEDIATE")
        if exercise and observed["in_scope"] and key:
            if observed["start_prompt"]:
                connection.execute("INSERT OR IGNORE INTO exercises VALUES (?, ?, 0, 0)", (key, now))
            row = connection.execute(
                "SELECT started, stops, ended FROM exercises WHERE identity = ?", (key,)
            ).fetchone()
            if row and not row[2]:
                started, stops, _ = row
                if now < started or now - started >= EXERCISE_SECONDS or event in ("Interrupt", "SessionEnd"):
                    connection.execute("UPDATE exercises SET ended = 1 WHERE identity = ?", (key,))
                    action = "exercise-ended"
                elif event == "PreToolUse" and observed["test_target"]:
                    response = render_deny(runtime)
                    action = "test-veto"
                elif event == "Stop":
                    if stops < len(CONTINUATIONS):
                        response = {"decision": "block", "reason": CONTINUATIONS[stops]}
                        connection.execute(
                            "UPDATE exercises SET stops = stops + 1 WHERE identity = ?", (key,)
                        )
                        action = "test-continuation"
                    else:
                        connection.execute("UPDATE exercises SET ended = 1 WHERE identity = ?", (key,))
                        action = "exercise-ended"
        observed.update({"at": now, "mode": "exercise" if exercise else "observe", "action": action})
        connection.execute("INSERT INTO events VALUES (?)", (json.dumps(observed, sort_keys=True),))
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=EVENTS, required=True)
    parser.add_argument("--event", required=True, help="Explicit per-hook binding; not inferred from prompts")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument(
        "--exercise", action="store_true", help="Disposable Codex exercise; NOT secure activation"
    )
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("oversized input")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("expected an object")
        result = handle(args.runtime, args.event, payload, args.root, args.database, exercise=args.exercise)
    except (OSError, ValueError, sqlite3.Error, RecursionError) as exc:
        # This is observational test apparatus, not fail-closed production enforcement.
        print(f"Excubitor probe failed: {type(exc).__name__}; native behavior not verified.", file=sys.stderr)
        print("{}")
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
