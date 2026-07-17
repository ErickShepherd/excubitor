#!/usr/bin/env python3
"""PreToolUse gate (Claude Code adapter): cap a headless ralph-loop worker at ONE unit per session.

Thin Claude Code adapter over the model-blind one-unit policy in `excubitor.core.policies.one_unit`.
The adapter owns the driver's arming knobs and envelope; the policy owns the decision (scoped commit
count vs baseline, via the git boundary).

A `claude -p "/<skill>"` worker spawned by a loop driver is a free-running agent: the recipe's "one
unit per iteration" is a soft instruction it will ignore on a long turn (observed: one worker drained
~51 units in a single 2h41m turn), silently defeating the per-iteration fresh-context re-read that is
ralph-loop's anti-drift purpose. The fix is a "tiny hook tweak" (the family forbids a watcher/daemon —
see docs/design/ralph-loop-one-unit-per-session.md): once the worker lands its one unit-advancing
commit, deny every further tool call so it ends its turn and the driver re-spawns a FRESH context.

ACTIVATION (opt-in, driver-set). Inert unless the spawning driver sets BOTH:
  ONE_UNIT_CAP_SCOPE     the conventional-commit scope the worker's unit commits carry
                         (driver derives it from the skill, e.g. bulk-content-review -> content-review).
  ONE_UNIT_CAP_BASELINE  the count of scope-matched commits on the branch at spawn time (integer).
Interactive sessions and `/loop` wakes set neither, so this is a no-op for them (each `/loop` wake is
already a fresh session and needs no cap). ONE_UNIT_CAP_REPO optionally pins the repo dir; otherwise
the payload `cwd` (fallback: process cwd). These knobs and the scope/baseline validation are the
adapter's host-specific glue; the policy receives (repo_dir, scope, baseline).

Contract (docs/en/hooks), mirroring guard-loop-vc.py: deny = exit 0 + JSON on stdout with
hookSpecificOutput.permissionDecision="deny"; emit no decision to defer. We NEVER exit non-zero and
FAIL OPEN on any error — a guard fault must never wedge the tool. That includes an ABSENT core (a
guard copied out of its package): it defers rather than crash-on-load. The cap only tightens the common
case; a miss degrades to today's free-running behavior, never to corruption.

Every deny is appended, strictly best-effort AFTER the decision is on stdout, to a local JSONL
telemetry log (hooks/_denial_log.py) — a telemetry fault never changes the decision.

Registered in settings.json PreToolUse with matcher "*" (it must see every tool, since the post-commit
action to deny may be any tool, not just Bash).
"""
from __future__ import annotations

import json
import os
import sys

# The one-unit policy lives in the shared model-blind core; this hook is the thin adapter over it. Add
# the repo root — resolved through any deploy symlink — to sys.path, then import FAIL-SOFT: a guard
# copied out of its package defers (fail-open), never crash-on-load.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
try:
    from excubitor.core.policies import one_unit  # noqa: E402
except ImportError:  # copied out of its package → defer (fail-open), never crash-on-load
    one_unit = None  # type: ignore[assignment]


def _allow() -> None:
    """Defer to the normal flow (no decision)."""
    sys.exit(0)


def _record_denial(reason: str, payload: dict) -> None:
    """Best-effort denial telemetry via the sibling hooks/_denial_log.py (loaded by resolved
    path, the runtime/spec_adapter.py pattern, so the ~/.claude symlink layout finds it). ANY
    fault — module missing (a copied guard with no sibling), unwritable log, anything — is
    swallowed: the deny already flushed to stdout must never be affected."""
    try:
        import importlib.util

        mod_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "_denial_log.py")
        spec = importlib.util.spec_from_file_location("_denial_log", mod_path)
        if spec is None or spec.loader is None:
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.record("guard-one-unit", reason, payload)
    except Exception:
        pass


def _deny(reason: str, payload: dict) -> None:
    json.dump(  # same form as the sibling guards (guard-loop-vc / guard-default-branch / self-integrity)
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
    # Flushing alone is necessary but not sufficient — a hung write would still hold this process
    # past the hook timeout (which fails OPEN and lets the fenced call run) — so record() also
    # time-bounds the filesystem I/O in an abandonable daemon thread (see hooks/_denial_log.py).
    sys.stdout.flush()
    _record_denial(reason, payload)
    sys.exit(0)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:  # JSONDecodeError is a ValueError subclass — one catch suffices
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
    if one_unit is None:
        _allow()  # copied out of its package: no policy reachable → fail OPEN (never wedge)
    reason = one_unit.deny_reason(repo_dir, scope, baseline)
    if reason is not None:
        _deny(reason, payload)
    _allow()


if __name__ == "__main__":
    main()
