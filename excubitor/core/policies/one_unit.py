"""The one-unit policy: cap a headless loop worker at one unit-advancing commit per session.

Extracted VERBATIM from the shipped `hooks/guard-one-unit.py` (now a thin host adapter). Once the
worker's one unit-advancing commit has landed, deny every further tool call so the worker ends its turn
and the driver re-spawns a FRESH context for the next unit (the anti-drift re-read). "Landed" is
measured by the scope-matched commit count exceeding the baseline — subject-and-scope-matched (via the
git boundary) so a two-worker parallel stage doesn't cross-trip.

The driver's arming knobs (scope, baseline, repo) are adapter-supplied — the core reads no environment
and does no host I/O; the commit count goes through `excubitor.core.git_state`. `hooks/tests/
test_guard_one_unit.py` is the differential oracle; a decision change here is a regression.
"""
from __future__ import annotations

from excubitor.core import git_state


def deny_reason(repo_dir: "str | None", scope: str, baseline: int) -> "str | None":
    """Deny reason if this session has already committed its one unit (scoped commit count exceeds the
    baseline), else None (defer). `repo_dir` / `scope` / `baseline` come from the driver's arming knobs
    via the adapter. A git-read failure yields None (fail open) — the cap only tightens the common case.
    """
    selectors = ["-C", repo_dir] if repo_dir else []
    current = git_state.scoped_commit_count(selectors, scope)
    if current is None:
        return None  # couldn't read git → fail open
    if current > baseline:
        return (
            "one-unit cap (ralph-loop): this worker session has already committed its one unit "
            f"(scope '{scope}': {current} vs baseline {baseline}). STOP NOW — end your turn without "
            "further tool calls. The loop driver will start a FRESH session for the next unit; that "
            "fresh re-read of the spec from disk is the anti-drift point. Do not attempt more work "
            "this session. See docs/design/ralph-loop-one-unit-per-session.md."
        )
    return None
