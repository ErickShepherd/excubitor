#!/usr/bin/env python3
"""PreToolUse gate: cap a headless ralph-loop worker at ONE unit per session.

A `claude -p "/<skill>"` worker spawned by a loop driver is a free-running agent: the recipe's
"one unit per iteration" is a soft instruction it will ignore on a long turn (observed: one worker
drained ~51 units in a single 2h41m turn), which silently defeats the per-iteration fresh-context
re-read that is ralph-loop's anti-drift purpose. The fix is a "tiny hook tweak" (the family forbids a
watcher/daemon — see docs/design/ralph-loop-one-unit-per-session.md): once the worker lands its one
unit-advancing commit, deny every further tool call so it ends its turn and the driver re-spawns a
FRESH context for the next unit.

ACTIVATION (opt-in, driver-set). Inert unless the spawning driver sets BOTH:
  ONE_UNIT_CAP_SCOPE     the conventional-commit scope the worker's unit commits carry
                         (driver derives it from the skill, e.g. bulk-content-review -> content-review).
  ONE_UNIT_CAP_BASELINE  the count of scope-matched commits on the branch at spawn time (integer).
Interactive sessions and `/loop` wakes set neither, so this is a no-op for them (each `/loop` wake is
already a fresh session and needs no cap).

MECHANISM. On every tool call, recompute the scoped commit count — the number of commits whose
SUBJECT carries `(<scope>)` (`git log --format=%s HEAD`, counted; NOT `rev-list --grep`, which also
matches the message body) — and DENY when it exceeds the baseline, i.e. this session has already
committed its one unit. Subject-and-scope-matched (not a raw HEAD count) so the resume‖cover parallel
stage, where two workers commit to the same branch, doesn't cross-trip (each worker's commit subject
carries a disjoint scope).

ONE_UNIT_CAP_REPO optionally pins the repo dir; otherwise the payload `cwd` (fallback: process cwd).

Contract (docs/en/hooks), mirroring guard-loop-vc.py: deny = exit 0 + JSON on stdout with
hookSpecificOutput.permissionDecision="deny"; emit no decision to defer to the normal flow. We NEVER
exit non-zero and FAIL OPEN on any error — a guard bug must never wedge the tool. The cap only tightens
the common case; a miss degrades to today's free-running behavior, never to corruption.

Registered in settings.json PreToolUse with matcher "*" (it must see every tool, since the post-commit
action to deny may be any tool, not just Bash).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def _allow() -> None:
    """Defer to the normal flow (no decision)."""
    sys.exit(0)


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _scoped_commit_count(repo_dir: str | None, scope: str) -> int | None:
    """Count this branch's commits whose SUBJECT carries `(scope)`. None on any failure (fail open).

    Counts subjects (`git log --format=%s`), NOT `rev-list --grep` — the latter matches the whole
    commit *message* (subject + body), so a worker whose commit body merely mentions another stage's
    scope would inflate that stage's count and could cross-trip the resume‖cover parallel guarantee.
    Subject-only keeps the per-worker attribution exact.
    """
    cmd = ["git"]
    if repo_dir:
        cmd += ["-C", repo_dir]
    cmd += ["log", "--format=%s", "HEAD"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    needle = f"({scope})"
    return sum(1 for line in p.stdout.splitlines() if needle in line)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow()  # unparseable input → fail open, never wedge the tool
    if not isinstance(payload, dict):
        _allow()  # valid-JSON-but-not-an-object → fail open; payload.get(...) must never raise AttributeError

    scope = (os.environ.get("ONE_UNIT_CAP_SCOPE") or "").strip()
    baseline_raw = (os.environ.get("ONE_UNIT_CAP_BASELINE") or "").strip()
    # Inert unless the driver armed BOTH knobs (opt-in; interactive/`/loop` sessions set neither).
    # isascii() guards against non-ASCII "digits" (e.g. '²', fullwidth) that str.isdigit() accepts but
    # int() then rejects with ValueError — treat those as not-armed (inert), never crash.
    if not scope or not (baseline_raw.isascii() and baseline_raw.isdigit()):
        _allow()
    baseline = int(baseline_raw)

    repo_dir = os.environ.get("ONE_UNIT_CAP_REPO") or payload.get("cwd") or os.getcwd()
    current = _scoped_commit_count(repo_dir, scope)
    if current is None:
        _allow()  # couldn't read git → fail open

    if current > baseline:
        _deny(
            "one-unit cap (ralph-loop): this worker session has already committed its one unit "
            f"(scope '{scope}': {current} vs baseline {baseline}). STOP NOW — end your turn without "
            "further tool calls. The loop driver will start a FRESH session for the next unit; that "
            "fresh re-read of the spec from disk is the anti-drift point. Do not attempt more work "
            "this session. See docs/design/ralph-loop-one-unit-per-session.md."
        )
    _allow()


if __name__ == "__main__":
    main()
