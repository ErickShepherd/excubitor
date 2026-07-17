#!/usr/bin/env python3
"""PreToolUse gate (Claude Code adapter): cap a headless ralph-loop worker at ONE unit per session.

Thin Claude Code entry point over the model-blind one-unit policy in `excubitor.core.policies.one_unit`.
The shared PreToolUse I/O glue lives in `excubitor.adapters.claude_code`; this file carries only the
driver's arming knobs + validation and the policy call.

A `claude -p "/<skill>"` worker spawned by a loop driver is a free-running agent: the recipe's "one
unit per iteration" is a soft instruction it will ignore on a long turn, silently defeating the
per-iteration fresh-context re-read that is ralph-loop's anti-drift purpose. Once the worker lands its
one unit-advancing commit, deny every further tool call so it ends its turn and the driver re-spawns a
FRESH context (see docs/design/ralph-loop-one-unit-per-session.md).

ACTIVATION (opt-in, driver-set). Inert unless the spawning driver sets BOTH:
  ONE_UNIT_CAP_SCOPE     the conventional-commit scope the worker's unit commits carry.
  ONE_UNIT_CAP_BASELINE  the count of scope-matched commits on the branch at spawn time (integer).
ONE_UNIT_CAP_REPO optionally pins the repo dir; otherwise the payload `cwd` (fallback: process cwd).
These knobs and the scope/baseline validation are the adapter's host-specific glue; the policy receives
(repo_dir, scope, baseline).

Contract (docs/en/hooks): deny = exit 0 + JSON; emit no decision to defer. We NEVER exit non-zero and
FAIL OPEN on any error (including an absent core — a guard copied out of its package defers). The cap
only tightens the common case; a miss degrades to today's free-running behavior, never to corruption.
Registered in settings.json PreToolUse with matcher "*" (it must see every tool).
"""
from __future__ import annotations

import os
import sys

# Add the repo root — resolved through any deploy symlink — to sys.path, then import FAIL-SOFT: a guard
# copied out of its package defers (fail-open), never crash-on-load.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
try:
    from excubitor.adapters import claude_code  # noqa: E402
    from excubitor.core.policies import one_unit  # noqa: E402
except ImportError:  # copied out of its package → fail-open, never crash-on-load
    claude_code = None  # type: ignore[assignment]
    one_unit = None  # type: ignore[assignment]

_HOOK_DIR = os.path.dirname(os.path.realpath(__file__))  # where the _denial_log.py sibling lives


def main() -> None:
    if claude_code is None or one_unit is None:
        sys.exit(0)  # copied out of its package: no adapter/policy reachable → fail OPEN (never wedge)
    payload = claude_code.read_payload()
    if payload is None:
        claude_code.emit_pass()  # unparseable / non-object input → fail open

    scope = (os.environ.get("ONE_UNIT_CAP_SCOPE") or "").strip()
    baseline_raw = (os.environ.get("ONE_UNIT_CAP_BASELINE") or "").strip()
    # Inert unless the driver armed BOTH knobs (opt-in). isascii() guards against non-ASCII "digits"
    # that str.isdigit() accepts but int() rejects — treat those as not-armed (inert), never crash.
    if not scope or not (baseline_raw.isascii() and baseline_raw.isdigit()):
        claude_code.emit_pass()
    baseline = int(baseline_raw)

    repo_dir = os.environ.get("ONE_UNIT_CAP_REPO") or payload.get("cwd") or os.getcwd()
    reason = one_unit.deny_reason(repo_dir, scope, baseline)
    if reason is not None:
        claude_code.emit_deny(reason, "guard-one-unit", payload, _HOOK_DIR)
    claude_code.emit_pass()


if __name__ == "__main__":
    main()
