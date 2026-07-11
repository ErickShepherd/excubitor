"""Denial telemetry: append one JSON line per guard deny to a local log. NOT a hook.

The four guards emit their deny JSON to the harness and, until this module, kept nothing — the
blocked-attempt record is an audit trail today and a data column for the future-analysis tomorrow (what did the agent *try* while fenced?). This module is the single shared writer;
each guard loads it by resolved path (the `runtime/spec_adapter.py` pattern — `Path(__file__)
.resolve()` follows the `~/.claude/hooks` symlink back into the repo, so the sibling is found)
and calls `record()` strictly best-effort.

CONTRACT (ordering + bounding are the whole design):
  * The deny decision is security-critical; the log is not. Guards emit the deny JSON and flush
    stdout BEFORE calling record(), and wrap the load+call in a broad try/except — a telemetry
    fault (missing module, unwritable path, full disk) silently skips the log line and NEVER
    changes the decision, the output, or the exit code. record() is additionally self-defensive
    (returns False rather than raising), but callers must not rely on that: belt and suspenders.
  * The write is TIME-BOUNDED, not just fault-swallowed. Flush-first alone cannot save a deny
    from a *hung* write: a stalled filesystem (NFS/FUSE, failing disk) blocks the guard process,
    the PreToolUse hook times out, and the harness fails OPEN — running the very call the guard
    denied. So all filesystem I/O runs in a daemon thread joined for _WRITE_TIMEOUT_S and
    ABANDONED on expiry; the guard exits promptly with the already-flushed decision. Residual
    (documented, not chased): a kernel-level uninterruptible hang (D-state on an NFS "hard"
    mount) can still stall process *exit* itself — there is no userspace fix for that.
  * Stdlib only, no daemon process, no rotation. Deny events are rare by construction — each one
    halts the agent's action — and lines are bounded (see _MAX_FIELD), so an append-only file is
    the honest simple choice; rotation logic would add failure modes to a path that must stay
    trivial.
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
  reason      the permissionDecisionReason emitted to the harness
  cwd         payload cwd, or null
  session_id  payload session_id, or null
json.dumps (default ensure_ascii=True) escapes newlines/control characters in commands and
reasons, so one event is always exactly one line. target and reason are attacker-influenceable
(the guards fire on every tool call, and a command string can be arbitrarily large), so both are
capped at _MAX_FIELD chars — the one input that is both hostile and unbounded in a no-rotation
log.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

SCHEMA = "excubitor.denial.v1"
_ENV_OVERRIDE = "EXCUBITOR_DENIAL_LOG"
# Local appends are sub-millisecond; anything slower is the pathological case the bound exists
# for. Well under the guards' own 5s git timeouts and the 10s hook timeout.
_WRITE_TIMEOUT_S = 1.0
_MAX_FIELD = 10_000
_TRUNCATION_MARK = "…[truncated]"


def _log_path() -> str:
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return os.path.expanduser(override)
    return os.path.join(os.path.expanduser("~"), ".claude", "excubitor", "denials.jsonl")


def _cap(value):
    """Bound an attacker-influenceable string field; pass non-strings/None through."""
    if isinstance(value, str) and len(value) > _MAX_FIELD:
        return value[:_MAX_FIELD] + _TRUNCATION_MARK
    return value


def _write(path: str, line: str, done: list) -> None:
    """The blockable filesystem I/O, isolated so the caller can abandon it on timeout."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # A single write of one pre-serialized line in append mode — the closest stdlib gets to
        # an atomic append; concurrent guard processes interleave whole lines, not fragments.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
        done.append(True)
    except Exception:
        pass


def record(guard: str, reason: str, payload: dict) -> bool:
    """Append one denial event. Returns True on success, False on ANY fault or on timeout —
    never raises, never blocks longer than ~_WRITE_TIMEOUT_S.

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
            "target": _cap(
                tool_input.get("command")
                or tool_input.get("file_path")
                or tool_input.get("notebook_path")
                or None
            ),
            "reason": _cap(reason),
            "cwd": payload.get("cwd"),
            "session_id": payload.get("session_id"),
        }
        line = json.dumps(event) + "\n"
        # Daemon thread + bounded join: a hung write is ABANDONED, not waited on, so the guard
        # process can exit with the decision it already flushed (see CONTRACT).
        done: list = []
        writer = threading.Thread(target=_write, args=(_log_path(), line, done), daemon=True)
        writer.start()
        writer.join(_WRITE_TIMEOUT_S)
        return bool(done)
    except Exception:
        return False
