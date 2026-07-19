#!/usr/bin/env python3
"""PreToolUse guard (Claude Code adapter): fence the version-control actions of an autonomous loop.

Thin Claude Code entry point over the model-blind loop-VC policy in `excubitor.core.policies.loop_vc`.
The shared PreToolUse I/O glue — stdin parse, the `hookSpecificOutput` render, best-effort telemetry —
lives in `excubitor.adapters.claude_code`; this file carries only the arming, the policy call, and the
host-specific deny wording.

TWO MODES (see docs/design/loop-yolo-verifiable-autonomy.md): CLAUDE_LOOP_GUARD=1 (conservative —
"stop-and-surface, never stop-and-act") blocks merge/push/branch-delete/reset/clean/worktree-remove/
`gh pr merge`/direct ref-moves; CLAUDE_LOOP_GUARD=yolo (verifiable autonomy) relaxes only to allow a
`--no-ff` merge into a confirmed non-default branch. `git clean` (no dry-run) is denied in both. The
classifier (segment splitting, launcher/shell/eval step-over, the git/gh deny set) lives in the core
and is documented there; accepted residuals are in KNOWN-BYPASSES.md.

Contract (docs/en/hooks): deny = exit 0 + JSON on stdout with permissionDecision="deny"; no decision
defers. We never exit non-zero — a guard fault must fail OPEN, never wedge the tool. That includes an
ABSENT core: a guard copied out of its package can't import the adapter/policy, so it fails-open
(defers) rather than crash. Registered in settings.json for the Bash tool.
"""
from __future__ import annotations

import os
import sys

# Add the repo root — resolved through any deploy symlink — to sys.path, then import FAIL-SOFT: a guard
# copied out of its package can reach neither the shared adapter glue nor the policy, so it fails-open.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
try:
    from excubitor.adapters import claude_code  # noqa: E402
    from excubitor.core.policies import loop_vc  # noqa: E402
except ImportError:  # copied out of its package → fail-open contract, never crash-on-load
    claude_code = None  # type: ignore[assignment]
    loop_vc = None  # type: ignore[assignment]

_HOOK_DIR = os.path.dirname(os.path.realpath(__file__))  # where the _denial_log.py sibling lives


def _deny_message(reason: str, yolo: bool) -> str:
    if yolo:
        return (
            f"Blocked: even in YOLO mode (CLAUDE_LOOP_GUARD=yolo) a loop may not {reason}. "
            f"YOLO permits autonomous acts only within the reversible/internal blast radius (commit, "
            f"and `--no-ff` merges into NON-default branches) gated by a verifiable Definition of Done; "
            f"it does NOT permit destructive, irreversible, or external acts — push/force-push, "
            f"hard-reset, git clean, branch-delete, worktree-remove, gh pr merge, a merge into the "
            f"default branch, or a fast-forward merge. Keep working on your own non-default branch and "
            f"integrate only via `--no-ff` merges into non-default branches. "
            f"See docs/design/loop-yolo-verifiable-autonomy.md."
        )
    return (
        f"Blocked: an autonomous loop (CLAUDE_LOOP_GUARD set) may not {reason}. "
        f"Loops are stop-and-surface, never stop-and-act: keep working and committing on "
        f"your own branch, then STOP and surface the branch for an out-of-loop reviewer "
        f"(e.g. pre-merge-review) or a human to merge. A self-paced loop cannot bless its "
        f"own completion — telos discharge is surface-not-correctness and a loop that writes "
        f"its own witnesses routes around the SUSPECT guard. To allow autonomous integration of "
        f"verifiable work, set CLAUDE_LOOP_GUARD=yolo instead (reversible/internal acts only); to "
        f"lift the guard entirely, unset it (accepting unattended irreversible VC actions)."
    )


def main() -> None:
    if claude_code is None or loop_vc is None:
        sys.exit(0)  # copied out of its package: no adapter/policy reachable → fail OPEN (never wedge)
    payload = claude_code.read_payload()
    if payload is None:
        claude_code.emit_pass()  # unparseable / non-object input → fail open

    # Inactive unless explicitly in a guarded loop (opt-in marker). The value selects the mode.
    marker = os.environ.get("CLAUDE_LOOP_GUARD")
    if not marker:
        claude_code.emit_pass()
    yolo = marker.strip().lower() == "yolo"

    if payload.get("tool_name") != "Bash":
        claude_code.emit_pass()  # matcher should restrict to Bash, but never assume

    # Same P0.16 posture as guard-default-branch.py: a truthy NON-string command/cwd must fail OPEN, not
    # TypeError inside split_segments/os.path.join against the never-exit-non-zero contract.
    tool_input = payload.get("tool_input")
    command = (tool_input if isinstance(tool_input, dict) else {}).get("command")
    if not isinstance(command, str):
        claude_code.emit_pass()  # absent or malformed command → nothing parseable to fence
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    reason = loop_vc._dangerous(command, yolo, cwd)
    if reason:
        claude_code.emit_deny(_deny_message(reason, yolo), "guard-loop-vc", payload, _HOOK_DIR)
    claude_code.emit_pass()


if __name__ == "__main__":
    main()
