#!/usr/bin/env python3
"""PreToolUse guard (Claude Code adapter): block the direct file-edit tools while on a repo's default.

Thin Claude Code entry point over the model-blind default-branch policy in
`excubitor.core.policies.default_branch`. The shared PreToolUse I/O glue (stdin parse, the
`hookSpecificOutput` render, best-effort telemetry) lives in `excubitor.adapters.claude_code`; this
file carries only the host-specific concerns — the blanket `CLAUDE_ALLOW_DEFAULT_BRANCH` off-switch and
the per-repo `.claude/allow-default-branch` opt-out marker — and hands (cwd, target, marker-relpath) to
the core. The symlink-laundering target resolution and the protected-default-branch decision live in
the core.

Enforces a branch-first workflow (README, "The workflow these fences assume"): no editing on
main/master — branch first. Registered in settings.json for the Edit|Write|NotebookEdit tools ONLY — a
Bash mutation is out of this guard's surface (R-06 accepted residual, KNOWN-BYPASSES.md); the honest
claim is "the direct file-edit tools", not "all file mutations".

Defers when: the target isn't in a git repo; the branch isn't the default; a `.claude/allow-default-
branch` marker exists; `CLAUDE_ALLOW_DEFAULT_BRANCH` is set; or — a guard copied out of its package —
the core is unreachable (fail-open, never crash). Contract (docs/en/hooks): deny = exit 0 + JSON;
emitting no decision defers; we never exit non-zero.
"""
from __future__ import annotations

import os
import sys

# Add the repo root — resolved through any deploy symlink — to sys.path, then import FAIL-SOFT: a guard
# copied out of its package can reach neither the shared adapter glue nor the policy, so it fails-open
# (defers) exactly as it already does on a git fault.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
try:
    from excubitor.adapters import claude_code  # noqa: E402
    from excubitor.core.policies import default_branch  # noqa: E402
except ImportError:  # copied out of its package → fail-open, never crash-on-load
    claude_code = None  # type: ignore[assignment]
    default_branch = None  # type: ignore[assignment]

_HOOK_DIR = os.path.dirname(os.path.realpath(__file__))  # where the _denial_log.py sibling lives
# The per-repo opt-out marker is host-specific (Claude Code's control dir), so the adapter owns it and
# passes it to the neutral core; the core hardcodes no host directory.
_OPT_OUT_MARKER = os.path.join(".claude", "allow-default-branch")


def main() -> None:
    if claude_code is None or default_branch is None:
        sys.exit(0)  # copied out of its package: no adapter/policy reachable → fail OPEN (never wedge)
    payload = claude_code.read_payload()
    if payload is None:
        claude_code.emit_pass()  # unparseable / non-object input → fail open

    # Blanket off-switch (set via settings.json "env" to disable globally).
    if os.environ.get("CLAUDE_ALLOW_DEFAULT_BRANCH"):
        claude_code.emit_pass()

    ti = payload.get("tool_input")
    tool_input = ti if isinstance(ti, dict) else {}
    # P0.16: a truthy NON-string cwd/file_path/notebook_path (a crafted or buggy payload) must fail OPEN,
    # not TypeError inside os.path.join against the never-exit-non-zero contract.
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    file_path = tool_input.get("file_path")
    notebook_path = tool_input.get("notebook_path")
    if (file_path is not None and not isinstance(file_path, str)) or (
        notebook_path is not None and not isinstance(notebook_path, str)
    ):
        claude_code.emit_pass()  # malformed target field → fail open, never wedge the editor
    # Edit/Write use file_path; NotebookEdit uses notebook_path. Resolve a relative target against the
    # payload cwd, else repo detection lands on the wrong directory (e.g. a sibling repo).
    logical_target = file_path or notebook_path or cwd

    reason = default_branch.deny_reason(cwd, logical_target, _OPT_OUT_MARKER)
    if reason is not None:
        claude_code.emit_deny(reason, "guard-default-branch", payload, _HOOK_DIR)
    claude_code.emit_pass()


if __name__ == "__main__":
    main()
