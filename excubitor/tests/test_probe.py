"""Tests for the harmless-denial probe framework (C2.8).

The two load-bearing properties: a well-formed probe (a working guard denies it, no marker), and — the
safety proof — even a totally failing guard confines its only effect to the disposable marker, leaving
a real repository byte-for-byte untouched.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from excubitor import probe
from excubitor.core import dispatch
from excubitor.core.events import Decision

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_DEFAULT_BRANCH = REPO_ROOT / "hooks" / "guard-default-branch.py"


def _snapshot(root: Path) -> "dict[str, str]":
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@pytest.fixture
def sandbox():
    sb = probe.create_sandbox()
    try:
        yield sb
    finally:
        sb.cleanup()


# --- the probe is well-formed ----------------------------------------------------------------------

def test_in_process_probe_passes_against_the_working_core(sandbox) -> None:
    outcome = probe.run_in_process(sandbox)
    assert outcome.denied is True
    assert outcome.marker_untouched is True
    assert outcome.passed is True
    assert not sandbox.marker.exists()  # a working guard never let the marker be created


def test_sandbox_repo_is_on_a_protected_default_branch(sandbox) -> None:
    branch = subprocess.run(["git", "-C", str(sandbox.repo), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    assert branch == "main"


def test_probe_targets_only_the_disposable_sandbox(sandbox) -> None:
    event = probe.probe_event(sandbox)
    assert event.targets == (str(sandbox.marker),)
    assert str(sandbox.root) in str(sandbox.marker)  # the target is inside the throwaway sandbox


# --- the safety proof: a failing guard cannot damage a real repo -----------------------------------

def test_failing_guard_only_touches_the_disposable_marker(sandbox, monkeypatch, tmp_path) -> None:
    # A real-looking repository elsewhere, representing a user's actual repo.
    real_repo = tmp_path / "real-repo"
    real_repo.mkdir()
    (real_repo / "important.py").write_text("print('do not touch me')\n")
    subprocess.run(["git", "init", "-b", "main", str(real_repo)], check=True, capture_output=True)
    before_real = _snapshot(real_repo)

    # Simulate a COMPLETELY broken guard: it never denies anything (fail-open to pass).
    monkeypatch.setattr(dispatch, "dispatch", lambda *a, **k: Decision.pass_())

    outcome = probe.run_in_process(sandbox)

    # The broken guard fails the probe (no deny) — and the ONLY thing written is the sandbox marker.
    assert outcome.denied is False
    assert outcome.passed is False
    assert sandbox.marker.exists()  # the (harmless) effect landed on the disposable marker
    assert str(sandbox.root) in str(sandbox.marker)
    # The real repo is byte-for-byte untouched: the probe's blast radius is the sandbox, by construction.
    assert _snapshot(real_repo) == before_real


def test_cleanup_removes_the_whole_sandbox() -> None:
    sb = probe.create_sandbox()
    root = sb.root
    assert root.exists()
    sb.cleanup()
    assert not root.exists()


def test_context_manager_cleans_up() -> None:
    with probe.create_sandbox() as sb:
        root = sb.root
        assert root.exists()
    assert not root.exists()


# --- hook-subprocess probe (end-to-end against the real guard script) ------------------------------

def test_hook_subprocess_probe_denies(sandbox) -> None:
    outcome = probe.run_hook_subprocess(GUARD_DEFAULT_BRANCH, sandbox)
    assert outcome.denied is True
    assert outcome.marker_untouched is True  # the hook only reports; it never writes the marker
    assert outcome.reason and "default branch" in outcome.reason
    assert "not a runtime-dispatch witness" in outcome.detail  # honest about what it does NOT prove


def test_hook_subprocess_handles_a_missing_hook(sandbox, tmp_path) -> None:
    outcome = probe.run_hook_subprocess(tmp_path / "nonexistent-guard.py", sandbox)
    assert outcome.denied is False  # cannot be invoked → not a pass
    assert outcome.marker_untouched is True
