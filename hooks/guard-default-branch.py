#!/usr/bin/env python3
"""PreToolUse guard (Claude Code adapter): block the direct file-edit tools while on a repo's default.

Thin Claude Code adapter over the model-blind default-branch policy in
`excubitor.core.policies.default_branch`. It parses the PreToolUse envelope (Edit/Write use
`file_path`, NotebookEdit uses `notebook_path`), applies the host-specific concerns — the blanket
`CLAUDE_ALLOW_DEFAULT_BRANCH` env off-switch and the per-repo `.claude/allow-default-branch` opt-out
marker — and hands the (cwd, target, marker-relpath) to the core, then renders the veto. The
symlink-laundering target resolution and the protected-default-branch decision live in the core.

Enforces a branch-first workflow (see this repo's README, "The workflow these fences assume"): no
editing on main/master — branch first. Registered in settings.json for the Edit|Write|NotebookEdit
tools ONLY — a Bash mutation (redirection, `sed -i`, …) is out of this guard's surface (R-06 accepted
residual, named in KNOWN-BYPASSES.md); the honest claim is "the direct file-edit tools", not "all file
mutations".

Defers to the normal permission flow (no decision) when: the target isn't inside a git repo; the
current branch isn't the repo's default; a `.claude/allow-default-branch` marker exists at the repo
root; `CLAUDE_ALLOW_DEFAULT_BRANCH` is set; or — a guard copied out of its package — the core is
unreachable (fail-open, never crash). Otherwise it denies with a branch-first message.

Contract (docs/en/hooks): deny = exit 0 + JSON on stdout with permissionDecision="deny"; emitting no
decision defers. We never exit non-zero — a guard fault must not wedge the editor, only fail open.
Every deny is appended, strictly best-effort AFTER the decision is on stdout, to a local JSONL
telemetry log (hooks/_denial_log.py) — a telemetry fault never changes the decision.
"""
from __future__ import annotations

import json
import os
import sys

# The default-branch policy lives in the shared model-blind core; this hook is the thin adapter over
# it. Add the repo root — resolved through any deploy symlink — to sys.path, then import FAIL-SOFT: a
# guard copied out of its package cannot reach the core, so it defers (fail-open) — exactly as it
# already does on a git fault — rather than crash-on-load.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
try:
    from excubitor.core.policies import default_branch  # noqa: E402
except ImportError:  # copied out of its package → defer (fail-open), never crash-on-load
    default_branch = None  # type: ignore[assignment]

# The per-repo opt-out marker is host-specific (Claude Code's control dir), so the adapter owns it and
# passes it to the neutral core; the core hardcodes no host directory.
_OPT_OUT_MARKER = os.path.join(".claude", "allow-default-branch")


def _allow() -> None:
    """Emit no decision → defer to the normal permission flow. Always exit 0."""
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
        mod.record("guard-default-branch", reason, payload)
    except Exception:
        pass


def _deny(reason: str, payload: dict) -> None:
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

    # Blanket off-switch (set via settings.json "env" to disable globally).
    if os.environ.get("CLAUDE_ALLOW_DEFAULT_BRANCH"):
        _allow()

    ti = payload.get("tool_input")
    tool_input = ti if isinstance(ti, dict) else {}
    # P0.16: the fields below come off the wire as strings, but the never-exit-non-zero contract is
    # unconditional — a truthy NON-string cwd/file_path/notebook_path (a crafted or buggy payload)
    # used to reach os.path.join, TypeError, and exit 1 against the documented fail-open contract.
    # A malformed field fails OPEN like every other malformed input (a non-string target also means
    # the edit tool itself will reject the call — there is no write here to protect against).
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    file_path = tool_input.get("file_path")
    notebook_path = tool_input.get("notebook_path")
    if (file_path is not None and not isinstance(file_path, str)) or (
        notebook_path is not None and not isinstance(notebook_path, str)
    ):
        _allow()  # malformed target field → fail open, never wedge the editor
    # Edit/Write use file_path; NotebookEdit uses notebook_path. Resolve a relative target against the
    # payload cwd, else repo detection lands on the wrong directory (e.g. a sibling repo).
    logical_target = file_path or notebook_path or cwd

    if default_branch is None:
        _allow()  # copied out of its package: no policy reachable → fail OPEN (never wedge)
    reason = default_branch.deny_reason(cwd, logical_target, _OPT_OUT_MARKER)
    if reason is not None:
        _deny(reason, payload)
    _allow()


if __name__ == "__main__":
    main()
