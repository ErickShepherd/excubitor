"""The harmless-denial probe framework: a synthetic denied action confined to a disposable sandbox.

A probe answers "does a guard actually veto a dangerous call *before it executes*?" without ever risking
a real repository. The design (``docs/design/installable-multi-runtime-distribution.md`` §"Harmless
denial probe") requires a probe that is safe *even when the hook fails*: it targets a disposable
directory and a unique marker, and it never touches a user file, a real repo, or a real default branch.

The synthetic action is an edit on the **default branch of a throwaway git repo** — exactly what
``guard-default-branch`` denies. The disposable **marker** is the file that edit would create:

* a working guard → the edit is denied → the marker is never created;
* a broken/failing guard → the edit would run → but it can only ever create the marker *inside the
  disposable sandbox*. A real repository is never the target, so hook failure cannot damage one.

Two probe drivers are provided:

* :func:`run_in_process` — drive the model-blind core directly (a framework self-check that the probe
  is well-formed: a working core denies it).
* :func:`run_hook_subprocess` — drive an installed guard *script* end-to-end as a subprocess with a real
  host payload (evidence the staged hook vetoes). This is a hook-level witness — it is **not** proof the
  real runtime dispatches the hook; that requires a real host (see ``doctor``/C2.9), which reports
  ``needs-probe`` when no such witness exists.

The verdict a probe reports is deliberately two-part: the guard returned a structured **deny**, AND the
disposable marker was **not** created. Presence of a staged file is never, by itself, a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from excubitor.core import dispatch
from excubitor.core.events import Capability, LoopMode, PreToolEvent

__all__ = [
    "ProbeSandbox",
    "ProbeOutcome",
    "PROBE_OPT_OUT_RELPATH",
    "create_sandbox",
    "probe_event",
    "run_in_process",
    "run_hook_subprocess",
]

#: The opt-out marker relpath the probe's default-branch policy is armed with (matches the neutral
#: default). It is never present in the sandbox, so the probe's repo stays protected.
PROBE_OPT_OUT_RELPATH = ".excubitor/allow-default-branch"


@dataclass
class ProbeSandbox:
    """A disposable sandbox: a throwaway git repo on its default branch and a unique marker path.

    Everything lives under ``root``; :meth:`cleanup` removes it entirely. The marker is a file *inside*
    the repo that the synthetic edit would create — it does not exist until (and unless) a failing
    guard lets the edit through.
    """

    root: Path
    repo: Path
    marker: Path

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> "ProbeSandbox":
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()


def create_sandbox(parent: "str | Path | None" = None) -> ProbeSandbox:
    """Create a disposable git repo on its default branch plus a unique, not-yet-existing marker path.

    Uses a fresh temp directory (never a real repo). The repo is initialized on ``main`` with one empty
    commit so its current branch is the (protected) default. Raises ``RuntimeError`` if git is missing.
    """
    root = Path(tempfile.mkdtemp(prefix="excubitor-probe-", dir=str(parent) if parent else None))
    repo = root / "repo"
    repo.mkdir()
    try:
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=probe@example.com",
             "-c", "user.name=excubitor-probe", "commit", "--allow-empty", "-m", "probe base"],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise RuntimeError(f"probe sandbox needs git: {exc}") from exc
    marker = repo / f"probe-marker-{uuid.uuid4().hex}.txt"
    return ProbeSandbox(root=root, repo=repo, marker=marker)


@dataclass(frozen=True)
class ProbeOutcome:
    """A probe's two-part verdict: the guard denied AND the disposable marker was not created."""

    denied: bool
    marker_untouched: bool
    reason: "str | None" = None
    detail: "str | None" = None

    @property
    def passed(self) -> bool:
        """A probe passes only when the action was denied *and* left no marker."""
        return self.denied and self.marker_untouched


def probe_event(sandbox: ProbeSandbox) -> PreToolEvent:
    """The synthetic pre-tool event: an armed-loop file edit to the marker in the default-branch repo."""
    return PreToolEvent(
        capability=Capability.FILE_MUTATE,
        native_tool="Write",
        cwd=str(sandbox.repo),
        targets=(str(sandbox.marker),),
        loop_mode=LoopMode.CONSERVATIVE,
    )


def _dispatch_config() -> "dispatch.DispatchConfig":
    return dispatch.DispatchConfig(opt_out_relpath=PROBE_OPT_OUT_RELPATH)


def run_in_process(sandbox: ProbeSandbox) -> ProbeOutcome:
    """Drive the model-blind core directly, then simulate the runtime's enforcement of its decision.

    If the core denies, the marker is never written (the tool is vetoed). If the core *fails* to deny,
    the marker write is simulated — and it can only ever land inside the disposable sandbox, proving a
    failed guard cannot reach a real repo. Returns the two-part verdict.
    """
    decision = dispatch.dispatch(probe_event(sandbox), _dispatch_config())
    if decision.is_pass:
        # Simulate the tool running because the guard did not veto it. Confined to the sandbox marker.
        sandbox.marker.write_text("probe-would-have-written-this\n", encoding="utf-8")
    return ProbeOutcome(
        denied=decision.is_deny,
        marker_untouched=not sandbox.marker.exists(),
        reason=decision.reason,
        detail="in-process core probe",
    )


def run_hook_subprocess(guard_script: "str | Path", sandbox: ProbeSandbox,
                        python: "str | None" = None, env: "dict[str, str] | None" = None) -> ProbeOutcome:
    """Drive an installed guard *script* end-to-end as a subprocess with a real Claude Code payload.

    Sends a ``PreToolUse`` envelope on stdin and parses the hook's structured decision. The hook only
    *reports* a decision (it never performs the edit), so the marker is expected to remain absent
    regardless; ``marker_untouched`` guards against a misbehaving hook writing it. ``env`` overrides the
    subprocess environment (e.g. a ``PYTHONPATH`` so a staged guard can import the installed core, as it
    would in a pip-installed host). Returns the verdict, or ``denied=False`` if the hook cannot be run.
    """
    payload = {
        "tool_name": "Write",
        "cwd": str(sandbox.repo),
        "tool_input": {"file_path": str(sandbox.marker), "content": "probe"},
    }
    try:
        completed = subprocess.run(
            [python or sys.executable, str(guard_script)],
            input=json.dumps(payload), capture_output=True, text=True, timeout=30, env=env,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return ProbeOutcome(denied=False, marker_untouched=not sandbox.marker.exists(),
                            reason=None, detail=f"hook could not be invoked: {exc}")
    denied = _is_structured_deny(completed.stdout)
    reason = _deny_reason(completed.stdout)
    return ProbeOutcome(
        denied=denied,
        marker_untouched=not sandbox.marker.exists(),
        reason=reason,
        detail="hook subprocess probe (hook-level witness, not a runtime-dispatch witness)",
    )


def _parse_hook_output(stdout: str) -> "dict | None":
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _is_structured_deny(stdout: str) -> bool:
    data = _parse_hook_output(stdout)
    if data is None:
        return False
    hook_out = data.get("hookSpecificOutput", {})
    return isinstance(hook_out, dict) and hook_out.get("permissionDecision") == "deny"


def _deny_reason(stdout: str) -> "str | None":
    data = _parse_hook_output(stdout)
    if data is None:
        return None
    hook_out = data.get("hookSpecificOutput", {})
    return hook_out.get("permissionDecisionReason") if isinstance(hook_out, dict) else None
