#!/usr/bin/env python3
"""PreToolUse guard (Claude Code adapter): while a loop guard is armed, the loop may not disarm it.

Thin Claude Code entry point over the model-blind self-integrity policy in
`excubitor.core.policies.self_integrity`. The shared PreToolUse I/O glue lives in
`excubitor.adapters.claude_code`; this file owns the host-specific parts — the `CLAUDE_LOOP_GUARD`
arming marker, the protected surface (this host's guard script names, the disarm marker, the settings
basenames, and the `.claude` control directory), and the deny message — and hands (target | command,
cwd, surface) to the core, which does the basename/realpath matching.

A judge the model can rewrite is not a judge. The other guards in this repo fence *version-control*
acts, but every one of them has kill-switches an unattended loop could reach with ordinary file
writes: the `.claude/allow-default-branch` marker file (disables guard-default-branch per-repo),
the guard hook scripts themselves (the installed copies are symlinks back into this repo, so
editing either end rewrites the live guard), and the `hooks` block of a `.claude/settings.json`
(deregisters the guards entirely). Without this fence, "stop-and-surface" is one `touch` away from
"stop-and-act".

So: while `CLAUDE_LOOP_GUARD` is set (either mode), DENY

  * Edit/Write/NotebookEdit whose target resolves to a kill-switch path, and
  * Bash commands that *name* a kill-switch path in any segment.

Kill-switch paths — the first three matched by BASENAME (so the fence holds wherever the file lives —
repo source, `~/.claude` symlink, or a copy), the last by REALPATH-PREFIX containment:
  * `allow-default-branch` — the per-repo disarm marker,
  * the guard scripts: `guard-default-branch.py`, `guard-loop-vc.py`, `guard-one-unit.py`,
    `guard-self-integrity.py`,
  * `settings.json` / `settings.local.json` under a `.claude` directory (where hooks are registered),
  * anything inside the `excubitor/` policy-core package these hooks import at runtime — since the
    decision logic was extracted there, editing a classifier / the adapter's `emit_deny` / any core
    module (or breaking its import) disarms the guards, so the whole package directory is fenced.

The Bash rule is deliberately blunt: a command segment that names a kill-switch path as a *literal
token* denies, reads included. Distinguishing a read from a write in arbitrary shell is a losing
race, and the cost is low — the Read tool (not matched here) still reads anything. Fail direction on
ambiguity is DENY, matching the posture of the set it protects. Segments are split on the shell
command separators AND on subshell/command-substitution boundaries (`()` and backticks) — but only
OUTSIDE quotes, so a token glued inside an unquoted `(rm PATH)` / `$(rm PATH)` / `` `rm PATH` `` is
still seen, while a kill-switch name quoted in an argument (a commit message, an `echo`) is literal
text and NOT a false deny.

SCOPE / LIMITS (honest — this is a seatbelt for the default path, not a sandbox). It matches a
*literal* path token; it does NOT expand the shell. Anything that produces the kill-switch path
through an expansion the guard doesn't perform slips past — and these are ACCEPTED residuals,
documented not chased (closing them means reimplementing the shell or denying every metacharacter,
which would break ordinary globbing and lose more than it gains):
  * **word expansions that mutate the token before bash resolves it** — a glob
    (`rm hooks/guard-loop-vc.p*`, `...p?`), a brace (`rm .claude/settings.jso{n,}`,
    `...allow-default-branch{,}`), a `$VAR` / `${VAR}` / tilde reference, or a
    command-substitution *result* — the token the guard sees (`...p*`, `...jso{n,}`, `$F`) is not
    the kill-switch basename, so it does not match. Pinned as accepted-residual fixtures in
    hooks/tests/test_guard_self_integrity.py::TestAcceptedResiduals.
  * a **live command substitution inside double quotes** (`echo "$(rm PATH)"`) — segments are split
    only outside quotes (to avoid false-denying a literally-quoted path), so a substitution bash
    WOULD run inside double quotes is not seen. The unquoted forms stay caught; this narrow quoted
    case is the accepted cost of eliminating the false deny.
  * a rename of a parent directory, a `find ~/.claude -delete`, or an interpreter one-liner that
    builds the path at runtime (`python3 -c '...'`).
  * a pre-existing **hard link** outside a protected root that shares a protected file's inode —
    `realpath` has no link to resolve, so this remains the same path-layer residual documented for the
    default-branch guard in KNOWN-BYPASSES.md.
It protects the *default path* by which an agent would disarm the guards, not every path.

Registered in settings.json for the Bash|Edit|Write|NotebookEdit tools.

Contract (docs/en/hooks): deny = exit 0 + JSON on stdout with permissionDecision="deny"; emitting no
decision defers. We never exit non-zero — a guard fault must fail OPEN (process sense), never wedge the
tool. That includes an ABSENT core: a guard copied out of its package fails-open (defers) rather than
crash. The telemetry log is deliberately NOT a kill-switch path (see KNOWN-BYPASSES.md).
"""
from __future__ import annotations

import os
import sys

# Resolve the hook's own dir and the repo root (through any deploy symlink), add the repo root to
# sys.path, then import FAIL-SOFT: a guard copied out of its package fails-open (defers, per the process
# contract), never crash-on-load.
_HOOK_DIR = os.path.dirname(os.path.realpath(__file__))  # where the _denial_log.py sibling lives
_REPO_ROOT = os.path.dirname(_HOOK_DIR)
sys.path.insert(0, _REPO_ROOT)
try:
    from excubitor.adapters import claude_code  # noqa: E402
    from excubitor.core.policies import self_integrity  # noqa: E402
except ImportError:  # copied out of its package → fail-open, never crash-on-load
    claude_code = None  # type: ignore[assignment]
    self_integrity = None  # type: ignore[assignment]

# The protected surface is HOST-SPECIFIC, so the adapter owns it and passes it to the neutral core:
# kill-switch BASENAMES (Claude Code's guard scripts, the disarm marker, the settings under `.claude`)
# PLUS the load-bearing policy-core DIRECTORY. The extraction moved the guards' decision logic into the
# `excubitor/` package, so editing anything there — neuter a classifier, make the adapter's emit_deny a
# no-op (disarms all four at once), or just break the import (fail-open) — disarms the guards, and must
# be fenced too. `_PACKAGE_ROOT` is realpath'd so a symlinked deploy and symlink-laundered targets both
# resolve against it; the core matches it by realpath-prefix (not basename, so unrelated files are safe).
_GUARD_SCRIPTS = frozenset(
    {"guard-default-branch.py", "guard-loop-vc.py", "guard-one-unit.py", "guard-self-integrity.py"}
)
_MARKER = "allow-default-branch"
_SETTINGS = frozenset({"settings.json", "settings.local.json"})
_CONTROL_DIR = ".claude"
_PACKAGE_ROOT = os.path.realpath(os.path.join(_REPO_ROOT, "excubitor"))


def main() -> None:
    if claude_code is None or self_integrity is None:
        sys.exit(0)  # copied out of its package: no adapter/policy reachable → fail OPEN (process contract)
    payload = claude_code.read_payload()
    if payload is None:
        claude_code.emit_pass()  # unparseable / non-object input → fail open

    # Inactive unless explicitly in a guarded loop — the same opt-in marker as guard-loop-vc.py, either
    # mode ("1" or "yolo"): YOLO's permit-to-act leans on these guards even harder.
    if not os.environ.get("CLAUDE_LOOP_GUARD"):
        claude_code.emit_pass()

    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    tool_input = ti if isinstance(ti, dict) else {}
    # Same P0.16 posture as guard-default-branch.py / guard-loop-vc.py: a truthy NON-string cwd or
    # target field (crafted or buggy payload) must fail OPEN, not TypeError inside os.path.join —
    # this is the meta-guard protecting the others, so it must honor the never-exit-non-zero contract.
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()

    surface = self_integrity.ProtectedSurface(
        guard_scripts=_GUARD_SCRIPTS,
        marker=_MARKER,
        settings_names=_SETTINGS,
        control_dir=_CONTROL_DIR,
        protected_roots=(_PACKAGE_ROOT,),
    )

    hit = None
    if tool in ("Edit", "Write", "NotebookEdit"):
        target = tool_input.get("file_path") or tool_input.get("notebook_path")
        if target is not None and not isinstance(target, str):
            claude_code.emit_pass()  # malformed target field → fail open, never wedge the editor
        if target:
            hit = self_integrity.target_kill_switch(target, cwd, surface)
    elif tool == "Bash":
        command = tool_input.get("command")
        if command is not None and not isinstance(command, str):
            claude_code.emit_pass()  # malformed command field → fail open
        hit = self_integrity.bash_kill_switch(command or "", cwd, surface)

    if hit:
        claude_code.emit_deny(
            f"Blocked: an autonomous loop (CLAUDE_LOOP_GUARD set) may not touch {hit} — "
            f"that path can disarm the loop's own guards, and a judge the model can rewrite "
            f"is not a judge. Reads still work through the Read tool. If a kill-switch file "
            f"genuinely needs changing, that is stop-and-surface work for a human outside the "
            f"loop. This is a seatbelt for the default path, not a sandbox — see this hook's "
            f"SCOPE / LIMITS docstring for what it does not catch.",
            "guard-self-integrity",
            payload,
            _HOOK_DIR,
        )
    claude_code.emit_pass()


if __name__ == "__main__":
    main()
