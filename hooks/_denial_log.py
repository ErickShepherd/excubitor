"""Denial telemetry: append one JSON line per guard deny to a local log. NOT a hook.

The four guards emit their deny JSON to the harness and, until this module, kept nothing — the
blocked-attempt record is an audit trail today and a data column for the future-analysis tomorrow (what did the agent *try* while fenced?). This module is the single shared writer;
each guard loads it by resolved path (the `runtime/spec_adapter.py` pattern — `Path(__file__)
.resolve()` follows the `~/.claude/hooks` symlink back into the repo, so the sibling is found)
and calls `record()` strictly best-effort.

CONTRACT (ordering is the whole design):
  * The deny decision is security-critical; the log is not. Guards emit the deny JSON and flush
    stdout BEFORE calling record(), and wrap the load+call in a broad try/except — a telemetry
    fault (missing module, unwritable path, full disk) silently skips the log line and NEVER
    changes the decision, the output, or the exit code. record() is additionally self-defensive
    (returns False rather than raising), but callers must not rely on that: belt and suspenders.
  * Stdlib only, no daemon, no rotation. Deny events are rare by construction — each one halts
    the agent's action — and lines are small, so an unbounded append-only file is the honest
    simple choice; rotation logic would add failure modes to a path that must stay trivial.
  * The log is OBSERVABILITY, NOT EVIDENCE. It lives on the same disk the agent can write; an
    agent can edit its own denial history (accepted, pinned in KNOWN-BYPASSES.md). Nothing in
    the trust story leans on it.

Log location: $EXCUBITOR_DENIAL_LOG if set, else ~/.claude/excubitor/denials.jsonl — one global
well-known path (deny events aren't always repo-bound, and a per-repo log in a public repo is a
leak-by-commit hazard), deliberately NOT /tmp (wiped on WSL2 restart).

Event schema — marker "excubitor.denial.v1". Deny events are not did-it claims, so they do not
force-share did-it's Receipt vocabulary; instead they carry the join keys a downstream consumer
needs (session_id, UTC ts, cwd) to line "denied before the act" up against "adjudicated after
the claim". Fields:
  schema      "excubitor.denial.v1"
  ts          ISO-8601 UTC timestamp of the deny
  guard       hook basename without .py (e.g. "guard-loop-vc")
  mode        the CLAUDE_LOOP_GUARD value at deny time, or null (unarmed guards)
  tool        payload tool_name, or null
  target      what the tool was aimed at: Bash command, or file_path/notebook_path, or null
  reason      the full permissionDecisionReason emitted to the harness
  cwd         payload cwd, or null
  session_id  payload session_id, or null
json.dumps (default ensure_ascii=True) escapes newlines/control characters in commands and
reasons, so one event is always exactly one line.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

SCHEMA = "excubitor.denial.v1"
_ENV_OVERRIDE = "EXCUBITOR_DENIAL_LOG"


def _log_path() -> str:
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return os.path.expanduser(override)
    return os.path.join(os.path.expanduser("~"), ".claude", "excubitor", "denials.jsonl")


def record(guard: str, reason: str, payload: dict) -> bool:
    """Append one denial event. Returns True on success, False on ANY fault — never raises.

    Callers still wrap this in try/except (the never-affect-the-deny contract must not depend
    on this module's internal discipline), but returning-not-raising keeps a single faulty
    event from ever looking like a guard bug.
    """
    try:
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}
        event = {
            "schema": SCHEMA,
            "ts": datetime.now(timezone.utc).isoformat(),
            "guard": guard,
            "mode": os.environ.get("CLAUDE_LOOP_GUARD") or None,
            "tool": payload.get("tool_name"),
            "target": (
                tool_input.get("command")
                or tool_input.get("file_path")
                or tool_input.get("notebook_path")
                or None
            ),
            "reason": reason,
            "cwd": payload.get("cwd"),
            "session_id": payload.get("session_id"),
        }
        path = _log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # A single write of one pre-serialized line in append mode — the closest stdlib gets to an
        # atomic append; concurrent guard processes interleave whole lines, not fragments.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        return True
    except Exception:
        return False
